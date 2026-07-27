package worker

import (
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
	workers   int
	taskCh    chan Task
	stopCh    chan struct{}
	wg        sync.WaitGroup
	resultWg  sync.WaitGroup
	redis     *queue.RedisQueue
	store     *store.MySQLStore
	taskStatuses map[string]*TaskStatus
	taskMu       sync.Mutex
	fetcher   *client.RestyFetcher
	submitted atomic.Int64
	completed atomic.Int64
	failed    atomic.Int64
}

func NewPool(workerCount int, rq *queue.RedisQueue, mysqlStore *store.MySQLStore) *Pool {
	return &Pool{
		workers: workerCount,
		taskCh:  make(chan Task, 1000),
		stopCh:  make(chan struct{}),
		redis:   rq,
		store:   mysqlStore,
		taskStatuses: make(map[string]*TaskStatus),
	}
}

func (p *Pool) Start() {
	p.fetcher = client.NewRestyFetcher(0.5)
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
	return Stats{
		Submitted: p.submitted.Load(),
		Completed: p.completed.Load(),
		Failed:    p.failed.Load(),
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
		log.Printf("[worker-%d] FETCH FAIL %s: %v", id, task.URL[:60], err)
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
	log.Printf("[worker-%d] FETCHED: %s (%d bytes)", id, task.Title[:40], len(html))

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
		log.Printf("[worker-%d] -> Redis HTML: %s (%d bytes)", id, task.Title[:40], len(html))
	} else {
		log.Printf("[worker-%d] FETCHED: %s (%d bytes) [no Redis]", id, task.Title[:40], len(html))
	}

	p.completed.Add(1)
}
// WorkerManager: public API wrapping the worker pool
// Architecture: WorkerManager -> Pool -> N goroutines
// Each goroutine: Fetch(URL) -> Save HTML -> Push to Redis
type WorkerManager struct {
	pool *Pool
}

func NewWorkerManager(workerCount int, rq *queue.RedisQueue, mysqlStore *store.MySQLStore) *WorkerManager {
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
				msg, err := p.redis.PopResultMessage()
				if err != nil {
					continue
				}
				if msg == nil {
					continue
				}
				if err := p.consumeResult(msg); err != nil {
					log.Printf("[result] consume error: %v", err)
				}
			}
		}
	}()
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
				p.handleSearchDone(sd)
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

func (p *Pool) handleSearchDone(msg *protocol.SearchDoneMessage) {
	p.taskMu.Lock()
	ts := p.getOrCreateTaskStatus(msg.TaskID)
	ts.SearchDone = true
	ts.Expected = msg.URLCount
	status := p.determineTaskStatus(ts)
	p.taskMu.Unlock()

	log.Printf("[task:%s] search_done: expected=%d stored=%d", msg.TaskID, msg.URLCount, ts.Stored)

	if status != "" {
		log.Printf("[task:%s] %s: stored=%d failed=%d expected=%d", msg.TaskID, status, ts.Stored, ts.Failed, ts.Expected)
		if p.store != nil {
			p.store.UpdateTask(msg.TaskID, status, ts.Stored)
		}
	}
}

func (p *Pool) checkTaskCompletion(taskID string) {
	p.taskMu.Lock()
	ts, ok := p.taskStatuses[taskID]
	if !ok {
		p.taskMu.Unlock()
		return
	}
	status := p.determineTaskStatus(ts)
	p.taskMu.Unlock()

	if status != "" {
		log.Printf("[task:%s] %s: stored=%d failed=%d expected=%d", taskID, status, ts.Stored, ts.Failed, ts.Expected)
		if p.store != nil {
			p.store.UpdateTask(taskID, status, ts.Stored)
		}
	}
}

func (p *Pool) consumeResult(msg *protocol.ResultMessage) error {
	log.Printf("[result] processing: task=%s url=%s score=%d", msg.TaskID, msg.URL[:60], msg.Score)

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

	var publishTime time.Time
	if msg.PublishDate != "" {
		publishTime, _ = time.Parse(time.RFC3339, msg.PublishDate)
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
		p.checkTaskCompletion(msg.TaskID)
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

	p.store.UpdateTask(msg.TaskID, "running", stored)
	p.checkTaskCompletion(msg.TaskID)
	log.Printf("[result] saved: task=%s url=%s score=%d", msg.TaskID, msg.URL[:60], msg.Score)
	return nil
}

func (wm *WorkerManager) Start()        { wm.pool.Start() }
func (wm *WorkerManager) Stop()         { wm.pool.Stop() }
func (wm *WorkerManager) Submit(t Task) { wm.pool.Submit(t) }
func (wm *WorkerManager) Stats() Stats  { return wm.pool.Stats() }
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
				payload, err := p.redis.PopURL()
				if err != nil {
					continue
				}
				if payload == nil {
					continue
				}
			p.submitted.Add(1)
			p.taskCh <- Task{
				TaskID:  payload.TaskID,
				URL:     payload.URL,
				Title:   payload.Title,
				Site:    payload.Site,
				Keyword: payload.Keyword,
				Level:   payload.Level,
			}
			}
		}
	}()
}
func (wm *WorkerManager) StartEventConsumer()  { wm.pool.StartEventConsumer() }
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
				p.consumeError(msg)
			}
		}
	}()
}

func (p *Pool) consumeError(msg *protocol.ErrorMessage) {
	// Search-level errors: task-wide failure, mark as failed directly
	if msg.Stage == "search" && msg.URL == "" {
		p.taskMu.Lock()
		ts := p.getOrCreateTaskStatus(msg.TaskID)
		ts.SearchDone = true
		ts.Expected = 0
		p.taskMu.Unlock()

		log.Printf("[task:%s] search failed: %s", msg.TaskID, msg.Error)
		if p.store != nil {
			p.store.UpdateTask(msg.TaskID, "failed", 0)
		}
		return
	}

	// URL-level errors: idempotent failure count
	p.taskMu.Lock()
	ts := p.getOrCreateTaskStatus(msg.TaskID)

	// Success has priority: URL already stored, skip
	if _, exists := ts.storedURLs[msg.URL]; exists {
		p.taskMu.Unlock()
		return
	}
	// Duplicate error: URL already failed, skip (idempotent)
	if _, exists := ts.failedURLs[msg.URL]; exists {
		p.taskMu.Unlock()
		return
	}

	ts.failedURLs[msg.URL] = struct{}{}
	ts.Failed = len(ts.failedURLs)
	p.taskMu.Unlock()

	log.Printf("[task:%s] error: stage=%s url=%s code=%s", msg.TaskID, msg.Stage, msg.URL[:60], msg.ErrorCode)
	p.checkTaskCompletion(msg.TaskID)
}

func (wm *WorkerManager) StartErrorConsumer()  { wm.pool.StartErrorConsumer() }
