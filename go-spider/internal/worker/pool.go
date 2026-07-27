package worker

import (
	"log"
	"sync"
	"sync/atomic"
	"time"

	"crawler-platform/internal/client"
	"crawler-platform/internal/config"
	"crawler-platform/internal/queue"
)

type Task struct {
	URL     string
	Title   string
	SiteCfg *config.SiteConfig
}

type Stats struct {
	Submitted int64
	Completed int64
	Failed    int64
	QueueLen  int
}

type Pool struct {
	workers   int
	taskCh    chan Task
	stopCh    chan struct{}
	wg        sync.WaitGroup
	redis     *queue.RedisQueue
	fetcher   *client.RestyFetcher
	submitted atomic.Int64
	completed atomic.Int64
	failed    atomic.Int64
}

func NewPool(workerCount int, rq *queue.RedisQueue) *Pool {
	return &Pool{
		workers: workerCount,
		taskCh:  make(chan Task, 1000),
		stopCh:  make(chan struct{}),
		redis:   rq,
	}
}

func (p *Pool) Start() {
	p.fetcher = client.NewRestyFetcher(0.5)
	for i := 0; i < p.workers; i++ {
		p.wg.Add(1)
		go p.worker(i)
	}
	log.Printf("[worker] pool started with %d workers", p.workers)
}

func (p *Pool) Stop() {
	close(p.stopCh)
	p.wg.Wait()
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
			if err := p.redis.PushHTML(task.URL, task.Title, html); err != nil {
				log.Printf("[worker-%d] REDIS HTML FAIL: %v", id, err)
				p.redis.PushError(task.URL, fmt.Sprintf("redis_push_fail: %v", err))
				p.failed.Add(1)
				return
			}
			log.Printf("[worker-%d] -> Redis HTML: %s (%d bytes)", id, task.Title[:40], len(html))
			p.redis.PushError(task.URL, fmt.Sprintf("fetch_fail: %v", err))
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

func NewWorkerManager(workerCount int, rq *queue.RedisQueue) *WorkerManager {
	return &WorkerManager{pool: NewPool(workerCount, rq)}
}

func (wm *WorkerManager) Start()        { wm.pool.Start() }
func (wm *WorkerManager) Stop()         { wm.pool.Stop() }
func (wm *WorkerManager) Submit(t Task) { wm.pool.Submit(t) }
func (wm *WorkerManager) Stats() Stats  { return wm.pool.Stats() }
