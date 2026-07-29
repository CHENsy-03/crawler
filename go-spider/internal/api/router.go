package api

import (
	"crawler-platform/internal/queue"
	"crawler-platform/internal/store"
	"crawler-platform/internal/worker"

	"github.com/gin-gonic/gin"
)

// articleQuerier is the subset of store.QueryArticles needed by the API.
type articleQuerier interface {
	QueryArticles(keyword string, limit int) ([]store.Article, error)
}

type Server struct {
	router  *gin.Engine
	redis   *queue.RedisQueue
	manager *worker.WorkerManager
	store   *TaskStore
	db      articleQuerier
}

func NewServer(rq *queue.RedisQueue, mgr *worker.WorkerManager, db articleQuerier) *Server {
	s := &Server{
		router:  gin.Default(),
		redis:   rq,
		manager: mgr,
		store:   NewTaskStore(),
		db:      db,
	}
	s.routes()
	return s
}

func (s *Server) routes() {
	s.router.GET("/health", s.health)
	s.router.GET("/ready", s.ready)
	s.router.GET("/task/status", s.taskStatus)
	s.router.POST("/task/create", s.createTask)
	s.router.GET("/articles", s.listArticles)

	// API wrapper copies Python FastAPI routes for compatibility
	s.router.GET("/metrics", s.metrics)
	s.router.GET("/sites", s.listSites)
}

func (s *Server) Run(addr string) error {
	return s.router.Run(addr)
}
