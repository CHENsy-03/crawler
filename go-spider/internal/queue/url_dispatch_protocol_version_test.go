package queue

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"strings"
	"testing"

	"github.com/redis/go-redis/v9"
)

func validURLV2Raw(t *testing.T) string {
	t.Helper()
	payload := loadArticleV2Fixture(t)["url_v2"].(map[string]any)
	data, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	return string(data)
}

func fullLegacyRaw() string {
	return `{"task_id":"t","url":"https://example.gov.cn/a","site":"s","keyword":"k","level":1,"title":"T","time":"now"}`
}

func fullV2RawWithVersion(t *testing.T, version string) string {
	t.Helper()
	payload := loadArticleV2Fixture(t)["url_v2"].(map[string]any)
	payload["protocol_version"] = version
	data, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	return string(data)
}

func TestURLDispatchMissingVersionLegacy(t *testing.T) {
	rq, hook := newContractQueue(t, fullLegacyRaw())
	result, err := rq.PopURLDispatch()
	if err != nil {
		t.Fatal(err)
	}
	if result == nil || result.Legacy == nil || result.V2 != nil {
		t.Fatalf("unexpected result: %#v", result)
	}
	hook.assertNoNetwork(t)
}

func TestURLDispatchV1Legacy(t *testing.T) {
	raw := `{"protocol_version":"1.0","task_id":"t","url":"https://example.gov.cn/a","site":"s","keyword":"k","level":1,"title":"T"}`
	rq, hook := newContractQueue(t, raw)
	result, err := rq.PopURLDispatch()
	if err != nil {
		t.Fatal(err)
	}
	if result == nil || result.Legacy == nil || result.V2 != nil {
		t.Fatalf("unexpected result: %#v", result)
	}
	hook.assertNoNetwork(t)
}

func TestURLDispatchValidV2(t *testing.T) {
	rq, hook := newContractQueue(t, validURLV2Raw(t))
	result, err := rq.PopURLDispatch()
	if err != nil {
		t.Fatal(err)
	}
	if result == nil || result.V2 == nil || result.Legacy != nil {
		t.Fatalf("unexpected result: %#v", result)
	}
	hook.assertNoNetwork(t)
}

func TestURLDispatchRejectsInvalidProtocolVersion(t *testing.T) {
	cases := map[string]string{
		"null_legacy":  `{"protocol_version":null,"task_id":"t","url":"https://example.gov.cn/a","site":"s","keyword":"k","level":1,"title":"T"}`,
		"null_v2":      fullV2RawWithVersion(t, "null"),
		"empty":        fullV2RawWithVersion(t, ""),
		"whitespace":   fullV2RawWithVersion(t, " 2.0 "),
		"unknown":      fullV2RawWithVersion(t, "3.0"),
		"number":       `{"protocol_version":2,"task_id":"t"}`,
		"true":         `{"protocol_version":true,"task_id":"t"}`,
		"false":        `{"protocol_version":false,"task_id":"t"}`,
		"object":       `{"protocol_version":{},"task_id":"t"}`,
		"array":        `{"protocol_version":[],"task_id":"t"}`,
		"top_null":     `null`,
		"top_array":    `[1,2]`,
		"top_string":   `"hello"`,
		"invalid_json": `{not-json`,
	}
	for name, raw := range cases {
		rq, hook := newContractQueue(t, raw)
		result, err := rq.PopURLDispatch()
		if err == nil {
			t.Fatalf("%s: expected rejection, got %#v", name, result)
		}
		hook.assertNoNetwork(t)
	}
}

func TestURLDispatchIllegalThenLegalV2(t *testing.T) {
	client := redis.NewClient(&redis.Options{Addr: "127.0.0.1:1"})
	hook := &urlDispatchSeqHook{
		results: []string{
			`{"protocol_version":null,"task_id":"bad"}`,
			validURLV2Raw(t),
		},
	}
	client.AddHook(hook)
	rq := &RedisQueue{client: client, urlQueue: contractURLQueue}

	if _, err := rq.PopURLDispatch(); err == nil {
		t.Fatal("expected first null message to be rejected")
	}
	result, err := rq.PopURLDispatch()
	if err != nil {
		t.Fatalf("second valid v2 should succeed: %v", err)
	}
	if result == nil || result.V2 == nil || result.Legacy != nil {
		t.Fatalf("unexpected second result: %#v", result)
	}
	if hook.brpopCalls != 2 {
		t.Fatalf("BRPOP calls = %d, want 2", hook.brpopCalls)
	}
	if hook.processCalls != 2 {
		t.Fatalf("process calls = %d, want 2", hook.processCalls)
	}
}

type urlDispatchSeqHook struct {
	results      []string
	calls        int
	brpopCalls   int
	processCalls int
	dialCalls    int
}

func (h *urlDispatchSeqHook) DialHook(next redis.DialHook) redis.DialHook {
	return func(ctx context.Context, network, addr string) (net.Conn, error) {
		h.dialCalls++
		return nil, fmt.Errorf("network dial is not allowed")
	}
}

func (h *urlDispatchSeqHook) ProcessHook(next redis.ProcessHook) redis.ProcessHook {
	return func(ctx context.Context, cmd redis.Cmder) error {
		h.processCalls++
		if cmd.Name() != "brpop" {
			return fmt.Errorf("unexpected command %q", cmd.Name())
		}
		stringCmd, ok := cmd.(*redis.StringSliceCmd)
		if !ok {
			return fmt.Errorf("unexpected cmd type %T", cmd)
		}
		if h.calls >= len(h.results) {
			return fmt.Errorf("no more results")
		}
		raw := h.results[h.calls]
		h.calls++
		h.brpopCalls++
		stringCmd.SetVal([]string{contractURLQueue, raw})
		return nil
	}
}

func (h *urlDispatchSeqHook) ProcessPipelineHook(next redis.ProcessPipelineHook) redis.ProcessPipelineHook {
	return next
}

func TestURLDispatchNoStringZeroValueTrapInSource(t *testing.T) {
	data, err := os.ReadFile("redis.go")
	if err != nil {
		t.Fatal(err)
	}
	source := string(data)
	if strings.Contains(source, "case \"\", protocol.Version:") {
		t.Fatalf("PopURLDispatch must not use empty string as legacy marker")
	}
}
