package api

import (
	"log"
	"sync"
	"time"

	"crawler-platform/internal/worker"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

type Task struct {
	ID        string       `json:"id"`
	Site      string       `json:"site"`
	Keywords  string       `json:"keywords"`
	Status    string       `json:"status"`
	CreatedAt time.Time    `json:"created_at"`
	Stats     worker.Stats `json:"stats"`
}

type TaskStore struct {
	mu    sync.RWMutex
	tasks map[string]*Task
}

func NewTaskStore() *TaskStore {
	return &TaskStore{tasks: make(map[string]*Task)}
}

func (ts *TaskStore) Create(site, keywords string) *Task {
	task := &Task{
		ID:        uuid.New().String()[:8],
		Site:      site,
		Keywords:  keywords,
		Status:    "created",
		CreatedAt: time.Now(),
	}
	ts.mu.Lock()
	ts.tasks[task.ID] = task
	ts.mu.Unlock()
	return task
}

func (ts *TaskStore) Get(id string) *Task {
	ts.mu.RLock()
	defer ts.mu.RUnlock()
	return ts.tasks[id]
}

func (ts *TaskStore) Update(id string, status string, stats worker.Stats) {
	ts.mu.Lock()
	defer ts.mu.Unlock()
	if t, ok := ts.tasks[id]; ok {
		t.Status = status
		t.Stats = stats
	}
}

type CreateTaskReq struct {
	Site     string `json:"site" binding:"required"`
	Keywords string `json:"keywords" binding:"required"`
	MaxPages int    `json:"max_pages"`
	Workers  int    `json:"workers"`
}

func (s *Server) health(c *gin.Context) {
	c.JSON(200, gin.H{"status": "ok"})
}

func (s *Server) ready(c *gin.Context) {
	c.JSON(200, gin.H{"status": "ready"})
}

func (s *Server) createTask(c *gin.Context) {
	var req CreateTaskReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"error": err.Error()})
		return
	}
	if req.Workers == 0 {
		req.Workers = 4
	}
	if req.MaxPages < 0 {
		c.JSON(400, gin.H{"error": "max_pages must be >= 0"})
		return
	}
	if req.MaxPages == 0 {
		req.MaxPages = 1
	}

	task := s.store.Create(req.Site, req.Keywords)

	go func() {
		if err := s.redis.PushSearch(task.ID, req.Site, req.Keywords, 1, req.MaxPages); err != nil {
			log.Printf("[task:%s] PushSearch error: %v", task.ID, err)
			s.store.Update(task.ID, "failed", worker.Stats{})
			return
		}
		log.Printf("[task:%s] pushed search: site=%s keyword=%s max_pages=%d", task.ID, req.Site, req.Keywords, req.MaxPages)
		s.store.Update(task.ID, "searching", worker.Stats{})

		for {
			stats := s.manager.Stats()
			s.store.Update(task.ID, "running", stats)
			if stats.Completed+stats.Failed >= stats.Submitted && stats.QueueLen == 0 {
				s.store.Update(task.ID, "completed", stats)
				log.Printf("[task:%s] completed: %d ok, %d failed", task.ID, stats.Completed, stats.Failed)
				return
			}
			time.Sleep(3 * time.Second)
		}
	}()

	c.JSON(202, gin.H{"task_id": task.ID, "status": "created"})
}

func (s *Server) taskStatus(c *gin.Context) {
	id := c.Query("id")
	if id == "" {
		c.JSON(400, gin.H{"error": "id required"})
		return
	}
	task := s.store.Get(id)
	if task == nil {
		c.JSON(404, gin.H{"error": "task not found"})
		return
	}
	c.JSON(200, task)
}

func (s *Server) listArticles(c *gin.Context) {
	// Result consumption moved to WorkerManager.StartResultConsumer.
	// TODO: query articles from MySQL for this endpoint.
	c.JSON(200, gin.H{"count": 0, "articles": []interface{}{}})
}

func (s *Server) metrics(c *gin.Context) {
	c.String(200, "# TYPE crawler gauge\ncrawler_info{version=\"1.0\"} 1\n")
}

func (s *Server) listSites(c *gin.Context) {
	c.JSON(200, []gin.H{
		{"key": "czj_beijing", "name": "北京市财政局"},
		{"key": "czj_hangzhou", "name": "杭州市财政局"},
	})
}
