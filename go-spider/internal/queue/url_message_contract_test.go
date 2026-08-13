package queue

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"testing"

	"github.com/redis/go-redis/v9"
)

const (
	pythonURLMessageContractFixture = "../../../tests/fixtures/url_message_contract.json"
	contractURLQueue                = "crawler:url"
)

// brpopContractHook is a test-only go-redis hook. It intercepts the BRPOP
// command issued by RedisQueue.pop() and returns the shared fixture without
// calling the next network layer.
type brpopContractHook struct {
	t          *testing.T
	resultJSON string

	brpopCalls    int
	processCalls  int
	dialCalls     int
	pipelineCalls int
}

func (h *brpopContractHook) DialHook(next redis.DialHook) redis.DialHook {
	return func(ctx context.Context, network, addr string) (net.Conn, error) {
		h.dialCalls++
		return next(ctx, network, addr)
	}
}

func (h *brpopContractHook) ProcessHook(next redis.ProcessHook) redis.ProcessHook {
	return func(ctx context.Context, cmd redis.Cmder) error {
		h.processCalls++
		if cmd.Name() != "brpop" {
			h.t.Fatalf("unexpected command %q; no network dial is allowed", cmd.Name())
			return fmt.Errorf("unexpected command %q", cmd.Name())
		}
		stringCmd, ok := cmd.(*redis.StringSliceCmd)
		if !ok {
			h.t.Fatalf("expected *redis.StringSliceCmd, got %T", cmd)
			return fmt.Errorf("unexpected command type %T", cmd)
		}
		args := cmd.Args()
		if len(args) < 2 {
			h.t.Fatalf("brpop args too short: %#v", args)
			return fmt.Errorf("brpop args too short")
		}
		queue, ok := args[1].(string)
		if !ok || queue != contractURLQueue {
			h.t.Fatalf("brpop queue = %#v, want %q", args[1], contractURLQueue)
			return fmt.Errorf("unexpected brpop queue %#v", args[1])
		}
		h.brpopCalls++
		stringCmd.SetVal([]string{queue, h.resultJSON})
		return nil
	}
}

func (h *brpopContractHook) ProcessPipelineHook(next redis.ProcessPipelineHook) redis.ProcessPipelineHook {
	return func(ctx context.Context, cmds []redis.Cmder) error {
		h.pipelineCalls++
		return next(ctx, cmds)
	}
}

func (h *brpopContractHook) assertNoNetwork(t *testing.T) {
	t.Helper()
	if h.processCalls != 1 {
		t.Fatalf("ProcessHook calls = %d, want 1", h.processCalls)
	}
	if h.brpopCalls != 1 {
		t.Fatalf("BRPOP calls = %d, want 1", h.brpopCalls)
	}
	if h.dialCalls != 0 {
		t.Fatalf("DialHook calls = %d, want 0", h.dialCalls)
	}
	if h.pipelineCalls != 0 {
		t.Fatalf("ProcessPipelineHook calls = %d, want 0", h.pipelineCalls)
	}
}

func newContractQueue(t *testing.T, resultJSON string) (*RedisQueue, *brpopContractHook) {
	t.Helper()
	client := redis.NewClient(&redis.Options{Addr: "127.0.0.1:1"})
	hook := &brpopContractHook{t: t, resultJSON: resultJSON}
	client.AddHook(hook)
	return &RedisQueue{client: client, urlQueue: contractURLQueue}, hook
}

func readContractFixture(t *testing.T) string {
	t.Helper()
	data, err := os.ReadFile(pythonURLMessageContractFixture)
	if err != nil {
		t.Fatalf("read shared fixture: %v", err)
	}
	return string(data)
}

func TestPythonURLMessageContractDecodesThroughProductionPopURL(t *testing.T) {
	fixtureJSON := readContractFixture(t)
	rq, hook := newContractQueue(t, fixtureJSON)

	payload, err := rq.PopURL()
	if err != nil {
		t.Fatalf("PopURL returned error: %v", err)
	}
	if payload == nil {
		t.Fatal("PopURL returned nil payload")
	}
	hook.assertNoNetwork(t)
	assertHTMLPayloadCommonFields(t, payload)
}

func TestPythonURLMessageContractRejectsInvalidJSONThroughProductionPopURL(t *testing.T) {
	rq, hook := newContractQueue(t, "{not-json")

	payload, err := rq.PopURL()
	if err == nil {
		t.Fatal("PopURL returned nil error for invalid JSON")
	}
	if payload != nil {
		t.Fatalf("PopURL returned payload for invalid JSON: %#v", payload)
	}
	hook.assertNoNetwork(t)
}

// This direct json.Unmarshal test is HTMLPayload structure compatibility
// evidence only. Production path evidence is covered by the PopURL tests.
func TestPythonURLMessageContractIsHTMLPayloadStructCompatible(t *testing.T) {
	data := readContractFixture(t)
	var payload HTMLPayload
	if err := json.Unmarshal([]byte(data), &payload); err != nil {
		t.Fatalf("json.Unmarshal HTMLPayload: %v", err)
	}
	assertHTMLPayloadCommonFields(t, &payload)
}

func assertHTMLPayloadCommonFields(t *testing.T, payload *HTMLPayload) {
	t.Helper()
	if payload.TaskID != "task-compat-001" {
		t.Fatalf("TaskID = %q, want task-compat-001", payload.TaskID)
	}
	if payload.URL != "https://example.gov.cn/a.html" {
		t.Fatalf("URL = %q, want shared fixture URL", payload.URL)
	}
	if payload.Site != "example.gov.cn" {
		t.Fatalf("Site = %q, want example.gov.cn", payload.Site)
	}
	if payload.Keyword != "低空经济" {
		t.Fatalf("Keyword = %q, want 低空经济", payload.Keyword)
	}
	if payload.Level != 1 {
		t.Fatalf("Level = %d, want 1", payload.Level)
	}
	if payload.Title != "示例标题" {
		t.Fatalf("Title = %q, want 示例标题", payload.Title)
	}
	if payload.Time != "" {
		t.Fatalf("legacy time unexpectedly decoded: %q", payload.Time)
	}
	if payload.HTML != "" || payload.Error != "" || payload.Score != 0 {
		t.Fatalf("unexpected HTMLPayload-only fields: html=%q error=%q score=%d", payload.HTML, payload.Error, payload.Score)
	}
}

func TestPythonURLMessageContractHasNoNestedPayloadOrLegacyTime(t *testing.T) {
	data := readContractFixture(t)
	var root map[string]any
	if err := json.Unmarshal([]byte(data), &root); err != nil {
		t.Fatalf("decode shared fixture: %v", err)
	}
	for _, key := range []string{
		"protocol_version",
		"task_id",
		"message_id",
		"timestamp",
		"type",
		"url",
		"site",
		"keyword",
		"level",
		"title",
	} {
		if _, ok := root[key]; !ok {
			t.Fatalf("missing contract field %q", key)
		}
	}
	if _, ok := root["time"]; ok {
		t.Fatal("legacy time field must not be present")
	}
	if _, ok := root["payload"]; ok {
		t.Fatal("nested payload field must not be present")
	}
}
