package api

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"strconv"
	"strings"
	"sync"
	"time"

	"crawler-platform/internal/protocol"
	"crawler-platform/internal/store"
	"crawler-platform/internal/worker"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

// parseIntParam parses a query parameter as an integer.
func parseIntParam(s, name string) (int, error) {
	v, err := strconv.Atoi(s)
	if err != nil {
		return 0, fmt.Errorf("%s must be a number", name)
	}
	return v, nil
}

// isDBReady returns true when the underlying database connection is usable.
// It handles pure nil interfaces, typed nil pointers (e.g. nil *store.MySQLStore),
// and valid database connections. Test fakes always return true.
func isDBReady(db articleQuerier) bool {
	if db == nil {
		return false
	}
	switch v := db.(type) {
	case *store.MySQLStore:
		return v != nil
	default:
		return true
	}
}

type Task struct {
	ID              string       `json:"id"`
	Site            string       `json:"site"`
	Keywords        string       `json:"keywords"`
	ProtocolVersion string       `json:"protocol_version"`
	TargetURL       string       `json:"target_url"`
	Status          string       `json:"status"`
	CreatedAt       time.Time    `json:"created_at"`
	Stats           worker.Stats `json:"stats"`
}

type TaskStore struct {
	mu    sync.RWMutex
	tasks map[string]*Task
}

func NewTaskStore() *TaskStore {
	return &TaskStore{tasks: make(map[string]*Task)}
}

func (ts *TaskStore) Create(site, keywords string) *Task {
	return ts.create("1.0", site, "", keywords)
}

func (ts *TaskStore) CreateV2(targetURL string, keywords []string) *Task {
	return ts.create("2.0", "", targetURL, strings.Join(keywords, ","))
}

func (ts *TaskStore) create(protocolVersion, site, targetURL, keywords string) *Task {
	task := &Task{
		ID:              uuid.New().String()[:8],
		Site:            site,
		Keywords:        keywords,
		ProtocolVersion: protocolVersion,
		TargetURL:       targetURL,
		Status:          "created",
		CreatedAt:       time.Now(),
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

type CreateTaskV1Req struct {
	Site     string `json:"site"`
	Profile  string `json:"profile"`
	Keywords string `json:"keywords"`
	MaxPages int    `json:"max_pages"`
	Workers  int    `json:"workers"`
}

type CreateTaskV2Req struct {
	ProtocolVersion string   `json:"protocol_version"`
	TargetURL       string   `json:"target_url"`
	Keywords        []string `json:"keywords"`
	MaxPages        int      `json:"max_pages"`
	Workers         int      `json:"workers"`
}

type createTaskHeader struct {
	ProtocolVersion string `json:"protocol_version"`
	Site            string `json:"site"`
	TargetURL       string `json:"target_url"`
}

func normalizeMaxPages(v int) (int, error) {
	if v < 0 {
		return 0, fmt.Errorf("max_pages must be >= 0")
	}
	if v == 0 {
		return 1, nil
	}
	return v, nil
}

func (s *Server) health(c *gin.Context) {
	c.JSON(200, gin.H{"status": "ok"})
}

func (s *Server) ready(c *gin.Context) {
	c.JSON(200, gin.H{"status": "ready"})
}

func jsonFieldIsArray(raw json.RawMessage) bool {
	trimmed := bytes.TrimSpace(raw)
	return len(trimmed) > 0 && trimmed[0] == '['
}

func (s *Server) createTask(c *gin.Context) {
	raw, err := c.GetRawData()
	if err != nil {
		c.JSON(400, gin.H{"error": err.Error()})
		return
	}
	var header createTaskHeader
	if err := json.Unmarshal(raw, &header); err != nil {
		c.JSON(400, gin.H{"error": err.Error()})
		return
	}
	var rawFields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &rawFields); err != nil {
		c.JSON(400, gin.H{"error": err.Error()})
		return
	}
	allowedFields := map[string]bool{
		"protocol_version": true,
		"site":             true,
		"profile":          true,
		"keywords":         true,
		"keyword":          true,
		"target_url":       true,
		"max_pages":        true,
		"workers":          true,
	}
	for field := range rawFields {
		if !allowedFields[field] {
			c.JSON(400, gin.H{"error": fmt.Sprintf("unknown field %q", field)})
			return
		}
	}
	if header.ProtocolVersion != "" && header.ProtocolVersion != "1.0" && header.ProtocolVersion != "2.0" {
		c.JSON(400, gin.H{"error": fmt.Sprintf("unsupported protocol_version %q", header.ProtocolVersion)})
		return
	}

	_, hasTargetURL := rawFields["target_url"]
	_, hasKeywords := rawFields["keywords"]
	_, hasSite := rawFields["site"]
	_, hasProfile := rawFields["profile"]
	_, hasKeyword := rawFields["keyword"]

	if hasSite && hasProfile {
		c.JSON(400, gin.H{"error": "site and profile are mutually exclusive"})
		return
	}

	switch header.ProtocolVersion {
	case "":
		if hasTargetURL || (hasKeywords && jsonFieldIsArray(rawFields["keywords"])) {
			c.JSON(400, gin.H{"error": "protocol_version required for v2 target_url/keywords requests"})
			return
		}
	case "1.0":
		if hasTargetURL || (hasKeywords && jsonFieldIsArray(rawFields["keywords"])) {
			c.JSON(400, gin.H{"error": "target_url and keywords cannot be combined with v1 site/profile requests"})
			return
		}
	case "2.0":
		if hasSite || hasProfile || hasKeyword {
			c.JSON(400, gin.H{"error": "site, profile, and keyword cannot be combined with v2 target_url requests"})
			return
		}
	}

	switch header.ProtocolVersion {
	case "2.0":
		var req CreateTaskV2Req
		if err := json.Unmarshal(raw, &req); err != nil {
			c.JSON(400, gin.H{"error": err.Error()})
			return
		}
		if req.TargetURL == "" {
			c.JSON(400, gin.H{"error": "target_url is required for v2"})
			return
		}
		if err := protocol.ValidateTargetURL(req.TargetURL); err != nil {
			c.JSON(400, gin.H{"error": err.Error()})
			return
		}
		normalized, err := protocol.NormalizeKeywords(req.Keywords)
		if err != nil {
			c.JSON(400, gin.H{"error": err.Error()})
			return
		}
		maxPages, err := normalizeMaxPages(req.MaxPages)
		if err != nil {
			c.JSON(400, gin.H{"error": err.Error()})
			return
		}
		task := s.store.CreateV2(req.TargetURL, normalized)

		go func() {
			if err := s.redis.PushSearchRequested(task.ID, req.TargetURL, normalized, 1, maxPages); err != nil {
				log.Printf("[task:%s] PushSearchRequested error: %v", task.ID, err)
				s.store.Update(task.ID, "failed", worker.Stats{})
				return
			}
			log.Printf("[task:%s] pushed search_requested: target_url=%s keywords=%v max_pages=%d", task.ID, req.TargetURL, normalized, maxPages)
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

		c.JSON(202, gin.H{"task_id": task.ID, "status": "created", "protocol_version": "2.0"})

	case "", "1.0":
		var req CreateTaskV1Req
		if err := json.Unmarshal(raw, &req); err != nil {
			c.JSON(400, gin.H{"error": err.Error()})
			return
		}
		if req.Site == "" && req.Profile != "" {
			req.Site = req.Profile
		}
		if req.Site == "" || req.Keywords == "" {
			c.JSON(400, gin.H{"error": "site/profile and keywords are required for v1"})
			return
		}
		maxPages, err := normalizeMaxPages(req.MaxPages)
		if err != nil {
			c.JSON(400, gin.H{"error": err.Error()})
			return
		}
		task := s.store.Create(req.Site, req.Keywords)

		go func() {
			if err := s.redis.PushSearch(task.ID, req.Site, req.Keywords, 1, maxPages); err != nil {
				log.Printf("[task:%s] PushSearch error: %v", task.ID, err)
				s.store.Update(task.ID, "failed", worker.Stats{})
				return
			}
			log.Printf("[task:%s] pushed search: site=%s keyword=%s max_pages=%d", task.ID, req.Site, req.Keywords, maxPages)
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

		c.JSON(202, gin.H{"task_id": task.ID, "status": "created", "protocol_version": "1.0"})

	default:
		c.JSON(400, gin.H{"error": "unsupported protocol_version"})
	}
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
	keyword := c.Query("keyword")
	limitStr := c.DefaultQuery("limit", "100")

	limit, err := parseIntParam(limitStr, "limit")
	if err != nil {
		c.JSON(400, gin.H{"error": err.Error()})
		return
	}
	if limit <= 0 {
		c.JSON(400, gin.H{"error": "limit must be positive"})
		return
	}
	if limit > 1000 {
		c.JSON(400, gin.H{"error": "limit must not exceed 1000"})
		return
	}
	if !isDBReady(s.db) {
		c.JSON(503, gin.H{"error": "database not available"})
		return
	}

	articles, err := s.db.QueryArticles(keyword, limit)
	if err != nil {
		log.Printf("[api] listArticles query error: %v", err)
		c.JSON(500, gin.H{"error": "internal server error"})
		return
	}
	if articles == nil {
		articles = []store.Article{}
	}
	c.JSON(200, gin.H{"count": len(articles), "articles": articles})
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
