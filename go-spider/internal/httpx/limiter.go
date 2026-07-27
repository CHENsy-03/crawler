package httpx

import (
	"net/url"
	"strings"
	"sync"
	"time"
)

type RateLimiter struct {
	mu       sync.Mutex
	buckets  map[string]*tokenBucket
	rate     float64
}

type tokenBucket struct {
	tokens   float64
	lastTime time.Time
}

func NewRateLimiter(defaultRPS float64) *RateLimiter {
	return &RateLimiter{
		buckets: make(map[string]*tokenBucket),
		rate:    defaultRPS,
	}
}

func (rl *RateLimiter) domainRate(domain string) float64 {
	if strings.Contains(domain, "gov.cn") {
		return 2.0
	}
	return rl.rate
}

func (rl *RateLimiter) Wait(rawURL string) {
	u, err := url.Parse(rawURL)
	if err != nil {
		return
	}
	domain := u.Host

	rl.mu.Lock()
	bucket, ok := rl.buckets[domain]
	if !ok {
		bucket = &tokenBucket{tokens: 1, lastTime: time.Now()}
		rl.buckets[domain] = bucket
	}

	rate := rl.domainRate(domain)
	now := time.Now()
	elapsed := now.Sub(bucket.lastTime).Seconds()
	bucket.tokens += elapsed * rate
	if bucket.tokens > rate {
		bucket.tokens = rate
	}
	bucket.lastTime = now

	if bucket.tokens < 1.0 {
		waitTime := time.Duration((1.0 - bucket.tokens) / rate * float64(time.Second))
		rl.mu.Unlock()
		time.Sleep(waitTime)
		rl.mu.Lock()
		bucket.tokens = 0
		bucket.lastTime = time.Now()
	} else {
		bucket.tokens -= 1.0
	}
	rl.mu.Unlock()
}
