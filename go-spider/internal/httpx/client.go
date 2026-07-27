package httpx

import (
	"fmt"
	"log"
	"net/url"
	"time"

	"github.com/go-resty/resty/v2"
)

type Client struct {
	resty   *resty.Client
	limiter *RateLimiter
	breaker *CircuitBreaker
	retry   RetryConfig
	deadQ   *DeadQueue
}

func NewClient(name string) *Client {
	return &Client{
		resty: resty.New().
			SetTimeout(15 * time.Second).
			SetHeader("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
		limiter: NewRateLimiter(3.0),
		breaker: NewBreaker(name, 3, 60*time.Second),
		retry:   DefaultRetryConfig,
		deadQ:   NewDeadQueue(100),
	}
}

func (c *Client) Get(rawURL string) (string, error) {
	domain := extractDomain(rawURL)
	breaker := c.breaker

	if !breaker.Allow() {
		err := fmt.Errorf("breaker OPEN for %s", domain)
		c.deadQ.Push(DeadTask{URL: rawURL, Error: err.Error(), Time: time.Now()})
		return "", err
	}

	var result string
	err := RetryWithBackoff(c.retry, func() error {
		c.limiter.Wait(rawURL)

		resp, e := c.resty.R().Get(rawURL)
		if e != nil {
			breaker.Failure()
			return e
		}
		if resp.StatusCode() >= 400 {
			breaker.Failure()
			return fmt.Errorf("HTTP %d", resp.StatusCode())
		}
		breaker.Success()
		result = resp.String()
		return nil
	})

	if err != nil {
		log.Printf("[httpx] GET FAIL %s: %v", rawURL[:80], err)
		c.deadQ.Push(DeadTask{URL: rawURL, Error: err.Error(), Time: time.Now()})
		return "", err
	}

	return result, nil
}

func (c *Client) DeadQueue() *DeadQueue { return c.deadQ }
func (c *Client) SetRateLimit(rps float64) { c.limiter.rate = rps }

func extractDomain(rawURL string) string {
	u, err := url.Parse(rawURL)
	if err != nil {
		return "unknown"
	}
	return u.Host
}
