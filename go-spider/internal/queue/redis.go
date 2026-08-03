package queue

import (
	"context"
	"encoding/json"
	"time"

	"crawler-platform/internal/protocol"

	"github.com/redis/go-redis/v9"
)

type HTMLPayload struct {
	TaskID  string `json:"task_id"`
	URL     string `json:"url"`
	Site    string `json:"site"`
	Keyword string `json:"keyword"`
	Level   int    `json:"level"`
	HTML    string `json:"html,omitempty"`
	Time    string `json:"time"`
	Title   string `json:"title,omitempty"`
	Error   string `json:"error,omitempty"`
	Score   int    `json:"score"`
}

type RedisQueue struct {
	client      *redis.Client
	searchQueue string
	eventQueue  string
	urlQueue    string
	htmlQueue   string
	errQueue    string
	resQueue    string
}

func NewRedisQueue(addr string) *RedisQueue {
	client := redis.NewClient(&redis.Options{
		Addr:         addr,
		DialTimeout:  3 * time.Second,
		ReadTimeout:  3 * time.Second,
		WriteTimeout: 3 * time.Second,
	})
	return &RedisQueue{
		client:      client,
		eventQueue:  "crawler:event",
		searchQueue: "crawler:search",
		urlQueue:    "crawler:url",
		htmlQueue:   "crawler:html",
		errQueue:    "crawler:error",
		resQueue:    "crawler:result",
	}
}

func (rq *RedisQueue) Ping() error {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	return rq.client.Ping(ctx).Err()
}

func (rq *RedisQueue) PushURLTask(url, site, keyword string, level int, title, taskID string) error {
	payload := HTMLPayload{
		TaskID: taskID, URL: url, Site: site, Keyword: keyword, Level: level, Title: title,
		Time: time.Now().Format(time.RFC3339),
	}
	return rq.push(rq.urlQueue, payload)
}

func (rq *RedisQueue) PushHTML(url, title, html, site, keyword string, level int, taskID string) error {
	payload := HTMLPayload{
		TaskID: taskID, URL: url, Title: title, HTML: html,
		Site: site, Keyword: keyword, Level: level,
		Time: time.Now().Format(time.RFC3339),
	}
	return rq.push(rq.htmlQueue, payload)
}

// Deprecated: Use PushErrorMessage instead. This function uses the old HTMLPayload format.
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
func (rq *RedisQueue) PushSearch(taskID, site, keyword string, level, maxPages int) error {
	msg := protocol.SearchMessage{
		Envelope: protocol.Envelope{
			ProtocolVersion: protocol.Version,
			TaskID:          taskID,
			MessageID:       protocol.NewMessageID(),
			Timestamp:       time.Now().Format(time.RFC3339),
		},
		Type:     "search",
		Site:     site,
		Keyword:  keyword,
		Level:    level,
		MaxPages: maxPages,
	}
	data, err := json.Marshal(msg)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	return rq.client.LPush(ctx, rq.searchQueue, data).Err()
}

func (rq *RedisQueue) PushSearchRequested(taskID, targetURL string, keywords []string, level, maxPages int) error {
	normalized, err := protocol.NormalizeKeywords(keywords)
	if err != nil {
		return err
	}
	msg := protocol.SearchRequestedMessage{
		Envelope: protocol.Envelope{
			ProtocolVersion: protocol.VersionV2,
			TaskID:          taskID,
			MessageID:       protocol.NewMessageID(),
			Timestamp:       time.Now().Format(time.RFC3339),
		},
		Type:      protocol.TypeSearchRequested,
		TargetURL: targetURL,
		Keywords:  normalized,
		Level:     level,
		MaxPages:  maxPages,
	}
	if err := msg.Validate(); err != nil {
		return err
	}
	data, err := json.Marshal(msg)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	return rq.client.LPush(ctx, rq.searchQueue, data).Err()
}

func (rq *RedisQueue) PopSearch() (*protocol.SearchMessage, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	result, err := rq.client.BRPop(ctx, 3*time.Second, rq.searchQueue).Result()
	if err != nil {
		return nil, err
	}
	var msg protocol.SearchMessage
	if err := json.Unmarshal([]byte(result[1]), &msg); err != nil {
		return nil, err
	}
	return &msg, nil
}

func (rq *RedisQueue) PopSearchRequested() (*protocol.SearchRequestedMessage, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	result, err := rq.client.BRPop(ctx, 3*time.Second, rq.searchQueue).Result()
	if err != nil {
		return nil, err
	}
	var msg protocol.SearchRequestedMessage
	if err := json.Unmarshal([]byte(result[1]), &msg); err != nil {
		return nil, err
	}
	return &msg, nil
}

func (rq *RedisQueue) PushResultMessage(msg *protocol.ResultMessage) error {
	data, err := json.Marshal(msg)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	return rq.client.LPush(ctx, rq.resQueue, data).Err()
}

func (rq *RedisQueue) PopResultMessage() (*protocol.ResultMessage, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	result, err := rq.client.BRPop(ctx, 3*time.Second, rq.resQueue).Result()
	if err != nil {
		return nil, err
	}
	var msg protocol.ResultMessage
	if err := json.Unmarshal([]byte(result[1]), &msg); err != nil {
		return nil, err
	}
	return &msg, nil
}
func (rq *RedisQueue) PopSearchDone() (*protocol.SearchDoneMessage, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	result, err := rq.client.BRPop(ctx, 3*time.Second, rq.eventQueue).Result()
	if err != nil {
		return nil, err
	}
	var msg protocol.SearchDoneMessage
	if err := json.Unmarshal([]byte(result[1]), &msg); err != nil {
		return nil, err
	}
	return &msg, nil
}
func (rq *RedisQueue) PushErrorMessage(msg *protocol.ErrorMessage) error {
	data, err := json.Marshal(msg)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	return rq.client.LPush(ctx, rq.errQueue, data).Err()
}

func (rq *RedisQueue) PopErrorMessage(timeout time.Duration) (*protocol.ErrorMessage, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	result, err := rq.client.BRPop(ctx, timeout, rq.errQueue).Result()
	if err != nil {
		return nil, err
	}
	var msg protocol.ErrorMessage
	if err := json.Unmarshal([]byte(result[1]), &msg); err != nil {
		return nil, err
	}
	return &msg, nil
}
