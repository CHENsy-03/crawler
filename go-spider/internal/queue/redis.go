package queue

import (
	"context"
	"encoding/json"
	"fmt"
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

type ResultDispatchKind int

const (
	ResultDispatchLegacy ResultDispatchKind = iota + 1
	ResultDispatchV1
	ResultDispatchV2
)

// ResultDispatch is the result of a single BRPOP on crawler:result.
// Zero value is invalid; callers must switch on Kind explicitly.
type ResultDispatch struct {
	Kind    ResultDispatchKind
	Message *protocol.ResultMessage
	V2      *protocol.ArticleResultV2
}

// PopResultDispatch performs one BRPOP and explicitly dispatches the raw
// crawler:result message by protocol_version. It never issues a second BRPOP.
func (rq *RedisQueue) PopResultDispatch() (*ResultDispatch, error) {
	raw, err := rq.popRaw(rq.resQueue)
	if err != nil {
		return nil, err
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &fields); err != nil {
		return nil, fmt.Errorf("decode result message fields: %w", err)
	}
	if fields == nil {
		return nil, fmt.Errorf("result message must be a JSON object")
	}
	pvRaw, exists := fields["protocol_version"]
	if !exists {
		var msg protocol.ResultMessage
		if err := json.Unmarshal(raw, &msg); err != nil {
			return nil, fmt.Errorf("decode legacy result message: %w", err)
		}
		return &ResultDispatch{Kind: ResultDispatchLegacy, Message: &msg}, nil
	}
	var versionValue any
	if err := json.Unmarshal(pvRaw, &versionValue); err != nil {
		return nil, fmt.Errorf("decode result protocol_version: %w", err)
	}
	version, ok := versionValue.(string)
	if !ok {
		return nil, fmt.Errorf("result protocol_version must be a string")
	}
	switch version {
	case protocol.Version:
		var msg protocol.ResultMessage
		if err := json.Unmarshal(raw, &msg); err != nil {
			return nil, fmt.Errorf("decode v1 result message: %w", err)
		}
		return &ResultDispatch{Kind: ResultDispatchV1, Message: &msg}, nil
	case protocol.VersionV2:
		decoded, err := protocol.DecodeV2ArticleMessage(raw)
		if err != nil {
			return nil, fmt.Errorf("decode v2 article_result: %w", err)
		}
		msg, ok := decoded.(*protocol.ArticleResultV2)
		if !ok {
			return nil, fmt.Errorf("v2 message type %T is not article_result", decoded)
		}
		return &ResultDispatch{Kind: ResultDispatchV2, V2: msg}, nil
	default:
		return nil, fmt.Errorf("unsupported result protocol_version %q", version)
	}
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

type URLDispatchResult struct {
	Legacy *HTMLPayload
	V2     *protocol.URLMessageV2
}

func (rq *RedisQueue) popRaw(queue string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	result, err := rq.client.BRPop(ctx, 3*time.Second, queue).Result()
	if err != nil {
		return nil, err
	}
	return []byte(result[1]), nil
}

func (rq *RedisQueue) PopURLDispatch() (*URLDispatchResult, error) {
	raw, err := rq.popRaw(rq.urlQueue)
	if err != nil {
		return nil, err
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &fields); err != nil {
		return nil, fmt.Errorf("decode url message fields: %w", err)
	}
	if fields == nil {
		return nil, fmt.Errorf("url message must be a JSON object")
	}
	rawVersion, exists := fields["protocol_version"]
	if !exists {
		var legacy HTMLPayload
		if err := json.Unmarshal(raw, &legacy); err != nil {
			return nil, err
		}
		return &URLDispatchResult{Legacy: &legacy}, nil
	}
	var versionValue any
	if err := json.Unmarshal(rawVersion, &versionValue); err != nil {
		return nil, fmt.Errorf("decode url protocol_version: %w", err)
	}
	version, ok := versionValue.(string)
	if !ok || version == "" {
		return nil, fmt.Errorf("url protocol_version must be a non-empty string")
	}
	switch version {
	case protocol.Version:
		var legacy HTMLPayload
		if err := json.Unmarshal(raw, &legacy); err != nil {
			return nil, err
		}
		return &URLDispatchResult{Legacy: &legacy}, nil
	case protocol.VersionV2:
		decoded, err := protocol.DecodeV2ArticleMessage(raw)
		if err != nil {
			return nil, err
		}
		msg, ok := decoded.(*protocol.URLMessageV2)
		if !ok {
			return nil, fmt.Errorf("v2 message type %T is not url", decoded)
		}
		return &URLDispatchResult{V2: msg}, nil
	default:
		return nil, fmt.Errorf("unsupported protocol_version %q", version)
	}
}

func (rq *RedisQueue) pushRaw(queue string, data []byte) error {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	return rq.client.LPush(ctx, queue, data).Err()
}

func (rq *RedisQueue) PushHTMLMessageV2(msg *protocol.HTMLMessageV2) error {
	if err := msg.Validate(); err != nil {
		return err
	}
	data, err := json.Marshal(msg)
	if err != nil {
		return err
	}
	return rq.pushRaw(rq.htmlQueue, data)
}
