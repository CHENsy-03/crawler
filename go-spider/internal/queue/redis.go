package queue

import (
	"context"
	"encoding/json"
	"time"

	"github.com/redis/go-redis/v9"
)

type HTMLPayload struct {
	URL     string `json:"url"`
	Site    string `json:"site"`
	Keyword string `json:"keyword"`
	Level   int    `json:"level"`
	HTML    string `json:"html,omitempty"`
	Time    string `json:"time"`
}

type RedisQueue struct {
	client    *redis.Client
	urlQueue  string
	htmlQueue string
	errQueue  string
	resQueue  string
}

func NewRedisQueue(addr string) *RedisQueue {
	client := redis.NewClient(&redis.Options{
		Addr:         addr,
		DialTimeout:  3 * time.Second,
		ReadTimeout:  3 * time.Second,
		WriteTimeout: 3 * time.Second,
	})
	return &RedisQueue{
		client:    client,
		urlQueue:  "crawler:url",
		htmlQueue: "crawler:html",
		errQueue:  "crawler:error",
		resQueue:  "crawler:result",
	}
}

func (rq *RedisQueue) Ping() error {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	return rq.client.Ping(ctx).Err()
}

func (rq *RedisQueue) PushURLTask(url, site, keyword string, level int) error {
	payload := HTMLPayload{
		URL: url, Site: site, Keyword: keyword, Level: level,
		Time: time.Now().Format(time.RFC3339),
	}
	return rq.push(rq.urlQueue, payload)
}

func (rq *RedisQueue) PushHTML(url, title, html string) error {
	payload := HTMLPayload{
		URL: url, Title: title, HTML: html,
		Time: time.Now().Format(time.RFC3339),
	}
	return rq.push(rq.htmlQueue, payload)
}

func (rq *RedisQueue) PushError(url, errMsg string) error {
	payload := HTMLPayload{
		URL: url, Error: errMsg,
		Time: time.Now().Format(time.RFC3339),
	}
	return rq.push(rq.errQueue, payload)
}

func (rq *RedisQueue) push(queue string, payload HTMLPayload) error {
	data, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	return rq.client.LPush(ctx, queue, data).Err()
}

func (rq *RedisQueue) PopURL() (*HTMLPayload, error) {
	return rq.pop(rq.urlQueue)
}

func (rq *RedisQueue) PopHTML() (*HTMLPayload, error) {
	return rq.pop(rq.htmlQueue)
}

func (rq *RedisQueue) PopResult() (*HTMLPayload, error) {
	return rq.pop(rq.resQueue)
}

func (rq *RedisQueue) pop(queue string) (*HTMLPayload, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	result, err := rq.client.BRPop(ctx, 3*time.Second, queue).Result()
	if err != nil {
		return nil, err
	}
	var payload HTMLPayload
	if err := json.Unmarshal([]byte(result[1]), &payload); err != nil {
		return nil, err
	}
	return &payload, nil
}
