package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"crawler-platform/internal/api"
	"crawler-platform/internal/config"
	"crawler-platform/internal/protocol"
	"crawler-platform/internal/queue"
	"crawler-platform/internal/store"
	"crawler-platform/internal/worker"
)

type cliInput struct {
	mode               string
	siteKey            string
	targetURL          string
	keywords           string
	normalizedKeywords []string
}

func prepareCLIInput(siteKey, targetURL, keywords string) (*cliInput, error) {
	if targetURL != "" && siteKey != "" {
		return nil, fmt.Errorf("--url and --site are mutually exclusive")
	}
	if targetURL == "" && siteKey == "" {
		return nil, fmt.Errorf("either --site or --url is required\nUsage: go-spider --site czj_beijing --keywords 低空经济\n       go-spider --url https://example.gov.cn/search --keywords 低空经济,通用爬虫")
	}
	if strings.TrimSpace(keywords) == "" {
		return nil, fmt.Errorf("--keywords is required and must not be blank")
	}
	input := &cliInput{
		mode:      "v1",
		siteKey:   siteKey,
		targetURL: targetURL,
		keywords:  strings.TrimSpace(keywords),
	}
	if targetURL != "" {
		if err := protocol.ValidateTargetURL(targetURL); err != nil {
			return nil, err
		}
		normalized, err := protocol.NormalizeKeywords(strings.Split(keywords, ","))
		if err != nil {
			return nil, err
		}
		input.mode = "v2"
		input.normalizedKeywords = normalized
	}
	return input, nil
}

func runCLI(siteKey, targetURL, keywords, redisAddr string, workers, maxPages int, newQueue func(string) *queue.RedisQueue, mysqlStore *store.MySQLStore) error {
	input, err := prepareCLIInput(siteKey, targetURL, keywords)
	if err != nil {
		return err
	}
	if newQueue == nil {
		newQueue = queue.NewRedisQueue
	}
	redisQueue := newQueue(redisAddr)
	if err := redisQueue.Ping(); err != nil {
		return fmt.Errorf("Redis not available: %w", err)
	}

	mgr := worker.NewWorkerManager(workers, redisQueue, mysqlStore)
	mgr.Start()
	defer mgr.Stop()

	taskID := protocol.NewTaskID()
	if input.mode == "v2" {
		if err := redisQueue.PushSearchRequested(taskID, input.targetURL, input.normalizedKeywords, 0, maxPages); err != nil {
			return err
		}
		log.Printf("[spider] pushed search_requested: target_url=%s keywords=%v", input.targetURL, input.normalizedKeywords)
	} else {
		cfg := config.MustLoad(input.siteKey, "../config")
		log.Printf("[spider] site=%s domain=%s workers=%d", cfg.Name, cfg.Domain, workers)
		if err := redisQueue.PushSearch(taskID, input.siteKey, input.keywords, 0, maxPages); err != nil {
			return err
		}
		log.Printf("[spider] pushed search: site=%s keyword=%s", input.siteKey, input.keywords)
	}

	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	defer signal.Stop(sig)

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
				return nil
			}
		case <-sig:
			log.Println("[spider] received signal, shutting down")
			return nil
		}
	}
}

func main() {
	siteKey := flag.String("site", "", "site key from config")
	targetURL := flag.String("url", "", "target url for v2 search")
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

		server := api.NewServer(redisQueue, mgr, mysqlStore)
		addr := fmt.Sprintf(":%d", *apiPort)
		log.Printf("[api] Gin server starting on %s", addr)
		if err := server.Run(addr); err != nil {
			log.Fatalf("[api] server error: %v", err)
		}
		return
	}

	if err := runCLI(*siteKey, *targetURL, *keywords, *redisAddr, *workers, *maxPages, nil, mysqlStore); err != nil {
		fmt.Println(err)
		os.Exit(1)
	}
}
