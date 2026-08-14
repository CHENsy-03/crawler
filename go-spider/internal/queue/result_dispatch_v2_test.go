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

const resultContractQueue = "crawler:result"

type resultBRPopHook struct {
	t             *testing.T
	resultJSON    string
	brpopCalls    int
	processCalls  int
	dialCalls     int
	pipelineCalls int
}

func (h *resultBRPopHook) DialHook(next redis.DialHook) redis.DialHook {
	return func(ctx context.Context, network, addr string) (net.Conn, error) {
		h.dialCalls++
		return next(ctx, network, addr)
	}
}

func (h *resultBRPopHook) ProcessHook(next redis.ProcessHook) redis.ProcessHook {
	return func(ctx context.Context, cmd redis.Cmder) error {
		h.processCalls++
		if cmd.Name() != "brpop" {
			h.t.Fatalf("unexpected command %q", cmd.Name())
			return fmt.Errorf("unexpected command %q", cmd.Name())
		}
		stringCmd, ok := cmd.(*redis.StringSliceCmd)
		if !ok {
			h.t.Fatalf("expected *redis.StringSliceCmd, got %T", cmd)
			return fmt.Errorf("unexpected command type %T", cmd)
		}
		args := cmd.Args()
		queueName, _ := args[1].(string)
		if queueName != resultContractQueue {
			h.t.Fatalf("brpop queue = %q, want %q", queueName, resultContractQueue)
			return fmt.Errorf("unexpected queue %q", queueName)
		}
		h.brpopCalls++
		stringCmd.SetVal([]string{queueName, h.resultJSON})
		return nil
	}
}

func (h *resultBRPopHook) ProcessPipelineHook(next redis.ProcessPipelineHook) redis.ProcessPipelineHook {
	return func(ctx context.Context, cmds []redis.Cmder) error {
		h.pipelineCalls++
		return next(ctx, cmds)
	}
}

func (h *resultBRPopHook) assertNoNetwork(t *testing.T) {
	t.Helper()
	if h.processCalls != 1 || h.brpopCalls != 1 {
		t.Fatalf("process=%d brpop=%d, want 1 each", h.processCalls, h.brpopCalls)
	}
	if h.dialCalls != 0 || h.pipelineCalls != 0 {
		t.Fatalf("dial=%d pipeline=%d, want 0", h.dialCalls, h.pipelineCalls)
	}
}

func newResultContractQueue(t *testing.T, resultJSON string) (*RedisQueue, *resultBRPopHook) {
	t.Helper()
	client := redis.NewClient(&redis.Options{Addr: "127.0.0.1:1"})
	hook := &resultBRPopHook{t: t, resultJSON: resultJSON}
	client.AddHook(hook)
	return &RedisQueue{client: client, resQueue: resultContractQueue}, hook
}

func loadResultV2Fixture(t *testing.T, key string) map[string]any {
	t.Helper()
	data, err := os.ReadFile(pythonArticleResultV2Fixture)
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	var fixture map[string]any
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode fixture: %v", err)
	}
	payload, ok := fixture[key].(map[string]any)
	if !ok {
		t.Fatalf("fixture key %q missing", key)
	}
	return payload
}

func TestResultDispatchLegacyMissingVersion(t *testing.T) {
	raw := `{"task_id":"t1","url":"https://example.gov.cn/a.html","site":"s","keyword":"k","level":1,"title":"T","content":"C","score":1}`
	rq, hook := newResultContractQueue(t, raw)
	dispatch, err := rq.PopResultDispatch()
	if err != nil {
		t.Fatal(err)
	}
	if dispatch.Kind != ResultDispatchLegacy || dispatch.Message == nil || dispatch.V2 != nil {
		t.Fatalf("unexpected dispatch: %#v", dispatch)
	}
	hook.assertNoNetwork(t)
}

func TestResultDispatchV1(t *testing.T) {
	raw := `{"protocol_version":"1.0","task_id":"t1","url":"https://example.gov.cn/a.html","site":"s","keyword":"k","level":1,"title":"T","content":"C","score":1}`
	rq, hook := newResultContractQueue(t, raw)
	dispatch, err := rq.PopResultDispatch()
	if err != nil {
		t.Fatal(err)
	}
	if dispatch.Kind != ResultDispatchV1 || dispatch.Message == nil || dispatch.V2 != nil {
		t.Fatalf("unexpected dispatch: %#v", dispatch)
	}
	hook.assertNoNetwork(t)
}

func TestResultDispatchV2UsesB1Fixture(t *testing.T) {
	payload := loadResultV2Fixture(t, "article_result_v2")
	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	rq, hook := newResultContractQueue(t, string(raw))
	dispatch, err := rq.PopResultDispatch()
	if err != nil {
		t.Fatal(err)
	}
	if dispatch.Kind != ResultDispatchV2 || dispatch.V2 == nil || dispatch.Message != nil {
		t.Fatalf("unexpected dispatch: %#v", dispatch)
	}
	if dispatch.V2.HitID != "hit-019b-1" || dispatch.V2.Status != "accepted" {
		t.Fatalf("unexpected v2 fields: %+v", dispatch.V2)
	}
	hook.assertNoNetwork(t)
}

func TestResultDispatchV2EmptyEvidencePreserved(t *testing.T) {
	payload := loadResultV2Fixture(t, "article_result_v2_empty_evidence")
	raw, _ := json.Marshal(payload)
	rq, hook := newResultContractQueue(t, string(raw))
	dispatch, err := rq.PopResultDispatch()
	if err != nil {
		t.Fatal(err)
	}
	if dispatch.V2 == nil || len(dispatch.V2.MatchedEvidence) != 0 {
		t.Fatalf("expected empty evidence, got %#v", dispatch.V2)
	}
	data, _ := json.Marshal(dispatch.V2)
	var decoded map[string]any
	_ = json.Unmarshal(data, &decoded)
	if decoded["matched_evidence"] == nil {
		t.Fatalf("matched_evidence must serialize as []")
	}
	hook.assertNoNetwork(t)
}

func TestResultDispatchRejectsInvalidVersions(t *testing.T) {
	cases := []string{
		`{"protocol_version":null,"task_id":"t"}`,
		`{"protocol_version":"","task_id":"t"}`,
		`{"protocol_version":2.0,"task_id":"t"}`,
		`{"protocol_version":true,"task_id":"t"}`,
		`{"protocol_version":{},"task_id":"t"}`,
		`{"protocol_version":[],"task_id":"t"}`,
		`{"protocol_version":"9.9","task_id":"t"}`,
		`{not-json`,
		`[1,2,3]`,
		`null`,
	}
	for _, raw := range cases {
		rq, hook := newResultContractQueue(t, raw)
		if _, err := rq.PopResultDispatch(); err == nil {
			t.Fatalf("expected rejection for %s", raw)
		}
		hook.assertNoNetwork(t)
	}
}

func TestResultDispatchRejectsInvalidV2WithoutFallback(t *testing.T) {
	cases := []func(map[string]any){
		func(m map[string]any) { m["unknown"] = true },
		func(m map[string]any) { m["hit_id"] = nil },
		func(m map[string]any) {
			m["content_hash"] = "0000000000000000000000000000000000000000000000000000000000000000"
		},
		func(m map[string]any) { m["status"] = "bogus" },
	}
	for _, mutate := range cases {
		payload := loadResultV2Fixture(t, "article_result_v2")
		mutate(payload)
		raw, _ := json.Marshal(payload)
		rq, hook := newResultContractQueue(t, string(raw))
		dispatch, err := rq.PopResultDispatch()
		if err == nil {
			t.Fatalf("expected v2 rejection, got %#v", dispatch)
		}
		hook.assertNoNetwork(t)
	}
}

func TestPopResultMessageLegacyBehaviorRemains(t *testing.T) {
	raw := `{"task_id":"t1","url":"https://example.gov.cn/a.html","site":"s","keyword":"k","level":1,"title":"T","content":"C","score":1}`
	rq, hook := newResultContractQueue(t, raw)
	msg, err := rq.PopResultMessage()
	if err != nil {
		t.Fatal(err)
	}
	if msg == nil || msg.TaskID != "t1" {
		t.Fatalf("unexpected result: %#v", msg)
	}
	hook.assertNoNetwork(t)
}
