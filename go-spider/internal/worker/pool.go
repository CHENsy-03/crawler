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
	Expected   int
	Stored     int
	Failed     int
	SearchDone bool
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
		return
	}
	log.Printf("[worker-%d] FETCHED: %s (%d bytes)", id, task.Title[:40], len(html))

		if p.redis != nil {
			if err := p.redis.PushHTML(task.URL, task.Title, html, task.Site, task.Keyword, task.Level, task.TaskID); err != nil {
			log.Printf("[worker-%d] REDIS HTML FAIL: %v", id, err)
			p.redis.PushError(task.URL, fmt.Sprintf("redis_push_fail: %v", err))
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

func (p *Pool) handleSearchDone(msg *protocol.SearchDoneMessage) {
	p.taskMu.Lock()
	ts := p.getOrCreateTaskStatus(msg.TaskID)
	ts.SearchDone = true
	ts.Expected = msg.URLCount
	done := ts.SearchDone && ts.Stored == ts.Expected
	p.taskMu.Unlock()

	log.Printf("[task:%s] search_done: expected=%d stored=%d", msg.TaskID, msg.URLCount, ts.Stored)

	if done {
		log.Printf("[task:%s] completed: stored=%d expected=%d", msg.TaskID, ts.Stored, ts.Expected)
		if p.store != nil {
			p.store.UpdateTask(msg.TaskID, "completed", ts.Stored)
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
	done := ts.SearchDone && ts.Stored == ts.Expected
	p.taskMu.Unlock()

	if done {
		log.Printf("[task:%s] completed: stored=%d expected=%d", taskID, ts.Stored, ts.Expected)
		if p.store != nil {
			p.store.UpdateTask(taskID, "completed", ts.Stored)
		}
	}
}

func (p *Pool) consumeResult(msg *protocol.ResultMessage) error {
	log.Printf("[result] processing: task=%s url=%s score=%d", msg.TaskID, msg.URL[:60], msg.Score)

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
		ts := p.getOrCreateTaskStatus(msg.TaskID)
		ts.Failed++
		p.taskMu.Unlock()
		p.checkTaskCompletion(msg.TaskID)
		return fmt.Errorf("save article: %w", err)
	}

	p.taskMu.Lock()
	ts := p.getOrCreateTaskStatus(msg.TaskID)
	ts.Stored++
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
