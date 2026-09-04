package worker

import (
	"context"
	"errors"
	"fmt"
	"log"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"crawler-platform/internal/client"
	"crawler-platform/internal/config"
	"crawler-platform/internal/protocol"
	"crawler-platform/internal/queue"
	"crawler-platform/internal/store"
)

type Task struct {
	TaskID  string
	URL     string
	Title   string
	Site    string
	Keyword string
	Level   int
	SiteCfg *config.SiteConfig
}

// taskStore is the subset of store capabilities used by the worker pool.
// Production uses taskStore; tests provide a fake.
type taskStore interface {
	UpdateTask(id, status string, count int) error
	SaveArticle(article *store.Article) error
}

// articleResultV2Store is implemented by production MySQLStore after B5.
// It is intentionally separate from taskStore so legacy fakes remain untouched.
type articleResultV2Store interface {
	PersistArticleResultV2(context.Context, *protocol.ArticleResultV2) (store.PersistArticleResultV2Outcome, error)
}

type Stats struct {
	Submitted int64
	Completed int64
	Failed    int64
	QueueLen  int
}

type TaskStatus struct {
	SearchDone bool
	Expected   int
	Stored     int
	Failed     int
	storedURLs map[string]struct{}
	failedURLs map[string]struct{}
}

type Pool struct {
	workers      int
	taskCh       chan Task
	stopCh       chan struct{}
	wg           sync.WaitGroup
	resultWg     sync.WaitGroup
	redis        *queue.RedisQueue
	store        taskStore
	taskStatuses map[string]*TaskStatus
	taskMu       sync.Mutex
	fetcher      *client.RestyFetcher
	v2           *V2DownloadCoordinator
	submitted    atomic.Int64
	completed    atomic.Int64
	failed       atomic.Int64
}

func NewPool(workerCount int, rq *queue.RedisQueue, mysqlStore taskStore) *Pool {
	return &Pool{
		workers:      workerCount,
		taskCh:       make(chan Task, 1000),
		stopCh:       make(chan struct{}),
		redis:        rq,
		store:        mysqlStore,
		taskStatuses: make(map[string]*TaskStatus),
	}
}

func (p *Pool) Start() {
	p.fetcher = client.NewRestyFetcher(0.5)
	if p.redis != nil {
		p.v2 = NewV2DownloadCoordinator(p.fetcher, p.redis)
	}
	for i := 0; i < p.workers; i++ {
		p.wg.Add(1)
		go p.worker(i)
	}
	if p.redis != nil {
		p.StartRedisConsumer()
	}
	p.StartEventConsumer()
	if p.store != nil {
		p.StartResultConsumer()
	}
	p.StartErrorConsumer()
	log.Printf("[worker] pool started with %d workers", p.workers)
}

func (p *Pool) Stop() {
	if p.v2 != nil {
		p.v2.Stop()
	}
	close(p.stopCh)
	p.wg.Wait()
	p.resultWg.Wait()
	log.Println("[worker] pool stopped")
}

func (p *Pool) Submit(task Task) {
	p.submitted.Add(1)
	p.taskCh <- task
}

func (p *Pool) Stats() Stats {
	submitted, completed, failed := p.submitted.Load(), p.completed.Load(), p.failed.Load()
	if p.v2 != nil {
		v2Submitted, v2Completed, v2Failed := p.v2.Stats()
		submitted += v2Submitted
		completed += v2Completed
		failed += v2Failed
	}
	return Stats{
		Submitted: submitted,
		Completed: completed,
		Failed:    failed,
		QueueLen:  len(p.taskCh),
	}
}

func (p *Pool) worker(id int) {
	defer p.wg.Done()
	for {
		select {
		case <-p.stopCh:
			return
		case task := <-p.taskCh:
			p.process(id, task)
		}
	}
}

func (p *Pool) process(id int, task Task) {
	html, err := p.fetcher.Fetch(task.URL)
	if err != nil {
		log.Printf("[worker-%d] FETCH FAIL %s: %v", id, task.URL, err)
		p.failed.Add(1)
		if p.redis != nil {
			if pushErr := p.redis.PushErrorMessage(&protocol.ErrorMessage{
				Envelope: protocol.Envelope{
					ProtocolVersion: protocol.Version,
					TaskID:          task.TaskID,
					MessageID:       protocol.NewMessageID(),
					Timestamp:       time.Now().Format(time.RFC3339),
				},
				Type:      "error",
				Stage:     "download",
				Site:      task.Site,
				Keyword:   task.Keyword,
				Level:     task.Level,
				URL:       task.URL,
				ErrorCode: "DOWNLOAD_FAILED",
				Error:     err.Error(),
				Retryable: true,
			}); pushErr != nil {
				log.Printf("[worker-%d] PUSH ERROR FAIL: %v", id, pushErr)
			}
		}
		return
	}
	log.Printf("[worker-%d] FETCHED: %s (%d bytes)", id, task.Title, len(html))

	if p.redis != nil {
		if err := p.redis.PushHTML(task.URL, task.Title, html, task.Site, task.Keyword, task.Level, task.TaskID); err != nil {
			log.Printf("[worker-%d] REDIS HTML FAIL: %v", id, err)
			if pushErr := p.redis.PushErrorMessage(&protocol.ErrorMessage{
				Envelope: protocol.Envelope{
					ProtocolVersion: protocol.Version,
					TaskID:          task.TaskID,
					MessageID:       protocol.NewMessageID(),
					Timestamp:       time.Now().Format(time.RFC3339),
				},
				Type:      "error",
				Stage:     "download",
				Site:      task.Site,
				Keyword:   task.Keyword,
				Level:     task.Level,
				URL:       task.URL,
				ErrorCode: "DOWNLOAD_FAILED",
				Error:     fmt.Sprintf("html_push_fail: %v", err),
				Retryable: true,
			}); pushErr != nil {
				log.Printf("[worker-%d] PUSH ERROR FAIL: %v", id, pushErr)
			}
			p.failed.Add(1)
			return
		}
		log.Printf("[worker-%d] -> Redis HTML: %s (%d bytes)", id, task.Title, len(html))
	} else {
		log.Printf("[worker-%d] FETCHED: %s (%d bytes) [no Redis]", id, task.Title, len(html))
	}

	p.completed.Add(1)
}

// WorkerManager: public API wrapping the worker pool
// Architecture: WorkerManager -> Pool -> N goroutines
// Each goroutine: Fetch(URL) -> Save HTML -> Push to Redis
type WorkerManager struct {
	pool *Pool
}

func NewWorkerManager(workerCount int, rq *queue.RedisQueue, mysqlStore taskStore) *WorkerManager {
	return &WorkerManager{pool: NewPool(workerCount, rq, mysqlStore)}
}

func (p *Pool) StartResultConsumer() {
	p.resultWg.Add(1)
	go func() {
		defer p.resultWg.Done()
		log.Println("[worker] Result consumer started: listening crawler:result")
		for {
			select {
			case <-p.stopCh:
				log.Println("[worker] Result consumer stopped")
				return
			default:
				dispatch, err := p.redis.PopResultDispatch()
				if err != nil {
					continue
				}
				if dispatch == nil {
					continue
				}
				if err := p.handleResultDispatch(dispatch); err != nil {
					log.Printf("[result] dispatch error: %v", err)
				}
			}
		}
	}()
}

func (p *Pool) handleResultDispatch(dispatch *queue.ResultDispatch) error {
	if dispatch == nil {
		return fmt.Errorf("result dispatch is nil")
	}
	switch dispatch.Kind {
	case queue.ResultDispatchLegacy, queue.ResultDispatchV1:
		if dispatch.Message == nil {
			return fmt.Errorf("legacy/v1 result message is nil")
		}
		return p.consumeResult(dispatch.Message)
	case queue.ResultDispatchV2:
		if dispatch.V2 == nil {
			return fmt.Errorf("v2 article_result is nil")
		}
		return p.consumeV2Result(dispatch.V2)
	default:
		return fmt.Errorf("unknown result dispatch kind %d", dispatch.Kind)
	}
}

func (p *Pool) consumeV2Result(msg *protocol.ArticleResultV2) error {
	v2Store, ok := p.store.(articleResultV2Store)
	if !ok {
		return fmt.Errorf("store does not support ArticleResultV2 persistence")
	}
	outcome, err := v2Store.PersistArticleResultV2(context.Background(), msg)
	if err != nil {
		if errors.Is(err, store.ErrArticleResultConflict) {
			log.Printf("[result] v2 conflict: task=%s hit=%s", msg.TaskID, msg.HitID)
		} else {
			log.Printf("[result] v2 persist error: task=%s hit=%s err=%v", msg.TaskID, msg.HitID, err)
		}
		return err
	}
	log.Printf("[result] v2 persisted: task=%s hit=%s status=%s inserted=%t replayed=%t", msg.TaskID, msg.HitID, msg.Status, outcome.Inserted, outcome.Replayed)
	return nil
}
func (p *Pool) getOrCreateTaskStatus(taskID string) *TaskStatus {
	if ts, ok := p.taskStatuses[taskID]; ok {
		return ts
	}
	ts := &TaskStatus{}
	ts.storedURLs = make(map[string]struct{})
	ts.failedURLs = make(map[string]struct{})
	p.taskStatuses[taskID] = ts
	return ts
}

func (p *Pool) StartEventConsumer() {
	p.resultWg.Add(1)
	go func() {
		defer p.resultWg.Done()
		log.Println("[worker] Event consumer started: listening crawler:event")
		for {
			select {
			case <-p.stopCh:
				log.Println("[worker] Event consumer stopped")
				return
			default:
				sd, err := p.redis.PopSearchDone()
				if err != nil {
					continue
				}
				if sd == nil {
					continue
				}
				if err := p.handleSearchDone(sd); err != nil {
					log.Printf("[event] handleSearchDone error: task=%s err=%v", sd.TaskID, err)
				}
			}
		}
	}()
}

func (p *Pool) determineTaskStatus(ts *TaskStatus) string {
	if !ts.SearchDone {
		return ""
	}
	if ts.Expected == 0 {
		return "completed"
	}
	if ts.Stored == ts.Expected {
		return "completed"
	}
	if ts.Stored+ts.Failed < ts.Expected {
		return ""
	}
	if ts.Stored > 0 && ts.Failed > 0 {
		return "completed_with_errors"
	}
	if ts.Stored == 0 && ts.Failed > 0 {
		return "failed"
	}
	return ""
}

func (p *Pool) handleSearchDone(msg *protocol.SearchDoneMessage) error {
	p.taskMu.Lock()
	ts := p.getOrCreateTaskStatus(msg.TaskID)
	ts.SearchDone = true
	ts.Expected = msg.URLCount
	status := p.determineTaskStatus(ts)
	p.taskMu.Unlock()

	log.Printf("[task:%s] search_done: expected=%d stored=%d", msg.TaskID, msg.URLCount, ts.Stored)

	if status != "" {
		if p.store != nil {
			if err := p.store.UpdateTask(msg.TaskID, status, ts.Stored); err != nil {
				log.Printf("[task:%s] failed to persist final status %s: %v", msg.TaskID, status, err)
				return err
			}
		}
		log.Printf("[task:%s] %s: stored=%d failed=%d expected=%d", msg.TaskID, status, ts.Stored, ts.Failed, ts.Expected)
	}
	return nil
}

func (p *Pool) checkTaskCompletion(taskID string) error {
	p.taskMu.Lock()
	ts, ok := p.taskStatuses[taskID]
	if !ok {
		p.taskMu.Unlock()
		return nil
	}
	status := p.determineTaskStatus(ts)
	p.taskMu.Unlock()

	if status != "" {
		if p.store != nil {
			if err := p.store.UpdateTask(taskID, status, ts.Stored); err != nil {
				log.Printf("[task:%s] failed to persist completion status %s: %v", taskID, status, err)
				return err
			}
		}
		log.Printf("[task:%s] %s: stored=%d failed=%d expected=%d", taskID, status, ts.Stored, ts.Failed, ts.Expected)
	}
	return nil
}

// parsePublishTime parses a date string from the v1 protocol into a time pointer.
// Supported formats: YYYY-MM-DD (primary), RFC3339 (fallback).
// Empty/whitespace-only returns (nil, nil).
// Invalid input returns (nil, error).
// It never returns time.Now().
func parsePublishTime(s string) (*time.Time, error) {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil, nil
	}
	if t, err := time.Parse("2006-01-02", s); err == nil {
		return &t, nil
	}
	if t, err := time.Parse(time.RFC3339, s); err == nil {
		return &t, nil
	}
	return nil, fmt.Errorf("unrecognized date format: %q", s)
}

func (p *Pool) consumeResult(msg *protocol.ResultMessage) error {
	log.Printf("[result] processing: task=%s url=%s score=%d", msg.TaskID, msg.URL, msg.Score)

	// URL-level dedup: skip if already stored or failed
	p.taskMu.Lock()
	ts := p.getOrCreateTaskStatus(msg.TaskID)
	if _, exists := ts.failedURLs[msg.URL]; exists {
		p.taskMu.Unlock()
		return nil
	}
	if _, exists := ts.storedURLs[msg.URL]; exists {
		p.taskMu.Unlock()
		return nil
	}
	p.taskMu.Unlock()

	publishTime, err := parsePublishTime(msg.PublishDate)
	if err != nil {
		log.Printf("[result] invalid publish_date %q for %s: %v", msg.PublishDate, msg.URL, err)
	}

	article := &store.Article{
		URL:             msg.URL,
		Title:           msg.Title,
		Content:         msg.Content,
		Site:            msg.Site,
		Keyword:         msg.Keyword,
		Score:           msg.Score,
		MatchedKeywords: strings.Join(msg.MatchedKeywords, ";"),
		PublishTime:     publishTime,
		CrawlTime:       time.Now(),
	}

	if err := p.store.SaveArticle(article); err != nil {
		p.taskMu.Lock()
		ts.failedURLs[msg.URL] = struct{}{}
		ts.Failed = len(ts.failedURLs)
		p.taskMu.Unlock()
		if err := p.checkTaskCompletion(msg.TaskID); err != nil {
			log.Printf("[result] checkTaskCompletion after store error: %v", err)
		}
		if p.redis != nil {
			if pushErr := p.redis.PushErrorMessage(&protocol.ErrorMessage{
				Envelope: protocol.Envelope{
					ProtocolVersion: protocol.Version,
					TaskID:          msg.TaskID,
					MessageID:       protocol.NewMessageID(),
					Timestamp:       time.Now().Format(time.RFC3339),
				},
				Type:      "error",
				Stage:     "store",
				Site:      msg.Site,
				Keyword:   msg.Keyword,
				Level:     msg.Level,
				URL:       msg.URL,
				ErrorCode: "STORE_FAILED",
				Error:     err.Error(),
				Retryable: true,
			}); pushErr != nil {
				log.Printf("[result] push error fail: %v", pushErr)
			}
		}
		return fmt.Errorf("save article: %w", err)
	}

	p.taskMu.Lock()
	ts.storedURLs[msg.URL] = struct{}{}
	ts.Stored = len(ts.storedURLs)
	stored := ts.Stored
	p.taskMu.Unlock()

	if err := p.store.UpdateTask(msg.TaskID, "running", stored); err != nil {
		log.Printf("[result] failed to update running status: task=%s err=%v", msg.TaskID, err)
	}
	if err := p.checkTaskCompletion(msg.TaskID); err != nil {
		log.Printf("[result] checkTaskCompletion after saved: task=%s err=%v", msg.TaskID, err)
		return err
	}
	log.Printf("[result] saved: task=%s url=%s score=%d", msg.TaskID, msg.URL, msg.Score)
	return nil
}

func (wm *WorkerManager) Start()               { wm.pool.Start() }
func (wm *WorkerManager) Stop()                { wm.pool.Stop() }
func (wm *WorkerManager) Submit(t Task)        { wm.pool.Submit(t) }
func (wm *WorkerManager) Stats() Stats         { return wm.pool.Stats() }
func (wm *WorkerManager) StartResultConsumer() { wm.pool.StartResultConsumer() }
func (p *Pool) StartRedisConsumer() {
	go func() {
		log.Println("[worker] Redis consumer started: listening crawler:url")
		for {
			select {
			case <-p.stopCh:
				log.Println("[worker] Redis consumer stopped")
				return
			default:
				result, err := p.redis.PopURLDispatch()
				if err != nil {
					continue
				}
				if result == nil {
					continue
				}
				if result.Legacy != nil {
					p.submitted.Add(1)
					p.taskCh <- Task{
						TaskID:  result.Legacy.TaskID,
						URL:     result.Legacy.URL,
						Title:   result.Legacy.Title,
						Site:    result.Legacy.Site,
						Keyword: result.Legacy.Keyword,
						Level:   result.Legacy.Level,
					}
				} else if result.V2 != nil {
					p.handleV2URLMessage(result.V2)
				}
			}
		}
	}()
}

func (p *Pool) handleV2URLMessage(msg *protocol.URLMessageV2) {
	if p.v2 == nil {
		log.Printf("[v2] no coordinator: task=%s url=%s", msg.TaskID, msg.URL)
		return
	}
	if err := p.v2.Handle(msg); err != nil {
		log.Printf("[v2] handle url failed: task=%s hit=%s url=%s err=%v", msg.TaskID, msg.HitID, msg.URL, err)
	}
}

func (wm *WorkerManager) StartEventConsumer() { wm.pool.StartEventConsumer() }
func (p *Pool) StartErrorConsumer() {
	p.resultWg.Add(1)
	go func() {
		defer p.resultWg.Done()
		log.Println("[worker] Error consumer started: listening crawler:error")
		for {
			select {
			case <-p.stopCh:
				log.Println("[worker] Error consumer stopped")
				return
			default:
				msg, err := p.redis.PopErrorMessage(3 * time.Second)
				if err != nil {
					continue
				}
				if msg == nil {
					continue
				}
				if err := p.consumeError(msg); err != nil {
					log.Printf("[error] consumeError: task=%s err=%v", msg.TaskID, err)
				}
			}
		}
	}()
}

func (p *Pool) consumeError(msg *protocol.ErrorMessage) error {
	// Search-level errors: task-wide failure, mark as failed directly
	if msg.Stage == "search" && msg.URL == "" {
		p.taskMu.Lock()
		ts := p.getOrCreateTaskStatus(msg.TaskID)
		ts.SearchDone = true
		ts.Expected = 0
		p.taskMu.Unlock()

		log.Printf("[task:%s] search failed: %s", msg.TaskID, msg.Error)
		if p.store != nil {
			if err := p.store.UpdateTask(msg.TaskID, "failed", 0); err != nil {
				combined := fmt.Errorf("search error %q then persist failed status: %w", msg.Error, err)
				log.Printf("[task:%s] %v", msg.TaskID, combined)
				return combined
			}
		}
		return nil
	}

	// URL-level errors: idempotent failure count
	p.taskMu.Lock()
	ts := p.getOrCreateTaskStatus(msg.TaskID)

	// Success has priority: URL already stored, skip
	if _, exists := ts.storedURLs[msg.URL]; exists {
		p.taskMu.Unlock()
		return nil
	}
	// Duplicate error: URL already failed, skip (idempotent)
	if _, exists := ts.failedURLs[msg.URL]; exists {
		p.taskMu.Unlock()
		return nil
	}

	ts.failedURLs[msg.URL] = struct{}{}
	ts.Failed = len(ts.failedURLs)
	p.taskMu.Unlock()

	log.Printf("[task:%s] error: stage=%s url=%s code=%s", msg.TaskID, msg.Stage, msg.URL, msg.ErrorCode)
	if err := p.checkTaskCompletion(msg.TaskID); err != nil {
		log.Printf("[task:%s] checkTaskCompletion after error failed: %v", msg.TaskID, err)
		return err
	}
	return nil
}

func (wm *WorkerManager) StartErrorConsumer() { wm.pool.StartErrorConsumer() }
