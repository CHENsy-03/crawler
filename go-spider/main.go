package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"crawler-platform/internal/config"
	"crawler-platform/internal/api"
	"crawler-platform/internal/protocol"
	"crawler-platform/internal/queue"
	"crawler-platform/internal/store"
	"crawler-platform/internal/worker"
)

func main() {
	siteKey := flag.String("site", "", "site key from config")
	keywords := flag.String("keywords", "", "search keywords (comma separated)")
	workers := flag.Int("workers", 4, "worker pool size")
	apiPort := flag.Int("api", 0, "start API server on port")
	redisAddr := flag.String("redis", "localhost:6379", "redis address")
	maxPages := flag.Int("max-pages", 1, "maximum search pages")
	flag.Parse()

	var mysqlStore *store.MySQLStore
	if ms, err := store.NewMySQLStore(""); err == nil {
		mysqlStore = ms
		log.Println("[store] MySQL connected")
	} else {
		log.Printf("[store] MySQL not available: %v (results will not be persisted)", err)
	}

	if *apiPort > 0 {
		redisQueue := queue.NewRedisQueue(*redisAddr)
		redisQueue.Ping()
		mgr := worker.NewWorkerManager(*workers, redisQueue, mysqlStore)
		mgr.Start()
		defer mgr.Stop()

		server := api.NewServer(redisQueue, mgr)
		addr := fmt.Sprintf(":%d", *apiPort)
		log.Printf("[api] Gin server starting on %s", addr)
		if err := server.Run(addr); err != nil {
			log.Fatalf("[api] server error: %v", err)
		}
		return
	}

	if *siteKey == "" || *keywords == "" {
		fmt.Println("Usage: go-spider --site czj_beijing --keywords 低空经济")
		os.Exit(1)
	}

	cfg := config.MustLoad(*siteKey, "../config")
	log.Printf("[spider] site=%s domain=%s workers=%d", cfg.Name, cfg.Domain, *workers)

	taskID := protocol.NewTaskID()
	redisQueue := queue.NewRedisQueue(*redisAddr)
	if err := redisQueue.Ping(); err != nil {
		log.Fatalf("[spider] Redis not available: %v", err)
	}

	mgr := worker.NewWorkerManager(*workers, redisQueue, mysqlStore)
	mgr.Start()
	defer mgr.Stop()

	if err := redisQueue.PushSearch(taskID, *siteKey, *keywords, 0, *maxPages); err != nil {
		log.Fatalf("[spider] PushSearch error: %v", err)
	}
	log.Printf("[spider] pushed search: site=%s keyword=%s", *siteKey, *keywords)

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)

	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			stats := mgr.Stats()
			if stats.Submitted == 0 {
				continue
			}
			log.Printf("[spider] stats: submitted=%d completed=%d failed=%d queue=%d",
				stats.Submitted, stats.Completed, stats.Failed, stats.QueueLen)
			if stats.Completed+stats.Failed >= stats.Submitted && stats.QueueLen == 0 {
				log.Println("[spider] all tasks completed")
				fmt.Println("Done.")
				return
			}
		case <-sig:
			log.Println("[spider] received signal, shutting down")
			mgr.Stop()
			return
		}
	}
}
