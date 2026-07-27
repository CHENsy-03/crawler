package httpx

import (
	"log"
	"math"
	"time"
)

type RetryConfig struct {
	MaxRetries int
	BaseDelay  time.Duration
	MaxDelay   time.Duration
}

var DefaultRetryConfig = RetryConfig{
	MaxRetries: 3,
	BaseDelay:  1 * time.Second,
	MaxDelay:   30 * time.Second,
}

type DeadQueue struct {
	ch chan DeadTask
}

type DeadTask struct {
	URL   string
	Error string
	Time  time.Time
}

func NewDeadQueue(size int) *DeadQueue {
	return &DeadQueue{ch: make(chan DeadTask, size)}
}

func (dq *DeadQueue) Push(task DeadTask) {
	select {
	case dq.ch <- task:
	default:
		log.Printf("[dead-queue] full, dropping: %s", task.URL[:60])
	}
}

func (dq *DeadQueue) PopAll() []DeadTask {
	var tasks []DeadTask
	for {
		select {
		case t := <-dq.ch:
			tasks = append(tasks, t)
		default:
			return tasks
		}
	}
}

func RetryWithBackoff(cfg RetryConfig, fn func() error) error {
	var lastErr error
	for attempt := 0; attempt <= cfg.MaxRetries; attempt++ {
		if attempt > 0 {
			delay := time.Duration(math.Min(
				float64(cfg.BaseDelay)*math.Pow(2, float64(attempt-1)),
				float64(cfg.MaxDelay),
			))
			log.Printf("[retry] attempt %d/%d after %v", attempt, cfg.MaxRetries, delay)
			time.Sleep(delay)
		}

		err := fn()
		if err == nil {
			return nil
		}
		lastErr = err
		log.Printf("[retry] attempt %d/%d FAILED: %v", attempt, cfg.MaxRetries, err)
	}
	return lastErr
}
