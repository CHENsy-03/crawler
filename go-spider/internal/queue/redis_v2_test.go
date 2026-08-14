package queue

import (
	"context"
	"encoding/json"
	"os"
	"testing"

	"crawler-platform/internal/protocol"

	"github.com/redis/go-redis/v9"
)

const (
	pythonArticleResultV2Fixture = "../../../tests/fixtures/article_result_v2_contract.json"
	pythonV1RedisFixture         = "../../../tests/fixtures/redis_protocol_v1.json"
	contractHTMLQueue            = "crawler:html"
)

func loadArticleV2Fixture(t *testing.T) map[string]any {
	t.Helper()
	data, err := os.ReadFile(pythonArticleResultV2Fixture)
	if err != nil {
		t.Fatalf("read article fixture: %v", err)
	}
	var fixture map[string]any
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode article fixture: %v", err)
	}
	return fixture
}

func TestURLMessageV2DispatchDecodesB1Fixture(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	raw, err := json.Marshal(fixture["url_v2"])
	if err != nil {
		t.Fatalf("marshal url_v2: %v", err)
	}
	rq, hook := newContractQueue(t, string(raw))
	result, err := rq.PopURLDispatch()
	if err != nil {
		t.Fatalf("PopURLDispatch: %v", err)
	}
	if result == nil || result.V2 == nil || result.Legacy != nil {
		t.Fatalf("unexpected dispatch result: %#v", result)
	}
	if result.V2.HitID != "hit-019b-1" || result.V2.URL != "https://example.gov.cn/news/1.html" {
		t.Fatalf("unexpected v2 fields: %+v", result.V2)
	}
	hook.assertNoNetwork(t)
}

func TestURLMessageV2DispatchRejectsTransitionalFixture(t *testing.T) {
	rq, hook := newContractQueue(t, readContractFixture(t))
	if _, err := rq.PopURLDispatch(); err == nil {
		t.Fatal("expected transitional 2.0 + site/keyword to be rejected")
	}
	hook.assertNoNetwork(t)
}

func TestURLMessageV2DispatchRejectsNull(t *testing.T) {
	raw := `{"protocol_version":"2.0","task_id":"t","message_id":"m","timestamp":"now","type":"url","hit_id":null,"plan_id":"p","original_query":"q","query_term":"q","url":"https://example.gov.cn/a","title":"","snippet":"","published_at":"","source":"s","level":0}`
	rq, hook := newContractQueue(t, raw)
	if _, err := rq.PopURLDispatch(); err == nil {
		t.Fatal("expected null hit_id rejection")
	}
	hook.assertNoNetwork(t)
}

func TestURLMessageV2DispatchRejectsUnknownField(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	payload := fixture["url_v2"].(map[string]any)
	payload["unexpected"] = true
	raw, _ := json.Marshal(payload)
	rq, hook := newContractQueue(t, string(raw))
	if _, err := rq.PopURLDispatch(); err == nil {
		t.Fatal("expected unknown field rejection")
	}
	hook.assertNoNetwork(t)
}

func TestURLMessageV2DispatchRejectsUnsupportedVersion(t *testing.T) {
	raw := `{"protocol_version":"9.9","task_id":"t","message_id":"m","timestamp":"now","type":"url"}`
	rq, hook := newContractQueue(t, raw)
	if _, err := rq.PopURLDispatch(); err == nil {
		t.Fatal("expected unsupported version rejection")
	}
	hook.assertNoNetwork(t)
}

func TestURLMessageV2DispatchRejectsWrongType(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	raw, _ := json.Marshal(fixture["html_v2"])
	rq, hook := newContractQueue(t, string(raw))
	if _, err := rq.PopURLDispatch(); err == nil {
		t.Fatal("expected non-url v2 type rejection")
	}
	hook.assertNoNetwork(t)
}

func TestURLMessageV1DispatchStillReturnsLegacy(t *testing.T) {
	data, err := os.ReadFile(pythonV1RedisFixture)
	if err != nil {
		t.Fatalf("read v1 fixture: %v", err)
	}
	var fixture map[string]any
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode v1 fixture: %v", err)
	}
	raw, err := json.Marshal(fixture["url"])
	if err != nil {
		t.Fatalf("marshal v1 url: %v", err)
	}
	rq, hook := newContractQueue(t, string(raw))
	result, err := rq.PopURLDispatch()
	if err != nil {
		t.Fatalf("PopURLDispatch v1: %v", err)
	}
	if result == nil || result.Legacy == nil || result.V2 != nil {
		t.Fatalf("unexpected v1 dispatch result: %#v", result)
	}
	hook.assertNoNetwork(t)
}

type pushHTMLHook struct {
	calls int
	queue string
	data  string
}

func (h *pushHTMLHook) DialHook(next redis.DialHook) redis.DialHook { return next }
func (h *pushHTMLHook) ProcessPipelineHook(next redis.ProcessPipelineHook) redis.ProcessPipelineHook {
	return next
}

func (h *pushHTMLHook) ProcessHook(next redis.ProcessHook) redis.ProcessHook {
	return func(ctx context.Context, cmd redis.Cmder) error {
		if cmd.Name() == "lpush" {
			args := cmd.Args()
			if len(args) >= 3 {
				h.queue, _ = args[1].(string)
				switch v := args[2].(type) {
				case string:
					h.data = v
				case []byte:
					h.data = string(v)
				}
			}
			h.calls++
			return nil
		}
		return next(ctx, cmd)
	}
}

func newPushQueue(t *testing.T) (*RedisQueue, *pushHTMLHook) {
	t.Helper()
	client := redis.NewClient(&redis.Options{Addr: "127.0.0.1:1"})
	hook := &pushHTMLHook{}
	client.AddHook(hook)
	return &RedisQueue{client: client, htmlQueue: contractHTMLQueue}, hook
}

func TestPushHTMLMessageV2WritesHTMLQueue(t *testing.T) {
	rq, hook := newPushQueue(t)
	msg := &protocol.HTMLMessageV2{
		ProtocolVersion: protocol.VersionV2,
		TaskID:          "task-1",
		MessageID:       "msg-1",
		Timestamp:       "2026-08-13T00:00:00Z",
		Type:            protocol.TypeHTMLV2,
		HitID:           "hit-1",
		PlanID:          "plan-1",
		OriginalQuery:   "k1",
		QueryTerm:       "k1",
		RequestedURL:    "https://example.gov.cn/a.html",
		FinalURL:        "https://example.gov.cn/a.html",
		ContentType:     "text/html",
		Title:           "T",
		Snippet:         "S",
		PublishedAt:     "2026-08-13",
		Source:          "example.gov.cn",
		Level:           0,
		HTML:            "<html><body>ok</body></html>",
	}
	if err := rq.PushHTMLMessageV2(msg); err != nil {
		t.Fatalf("PushHTMLMessageV2: %v", err)
	}
	if hook.calls != 1 || hook.queue != contractHTMLQueue || hook.data == "" {
		t.Fatalf("hook = calls:%d queue:%q data:%q", hook.calls, hook.queue, hook.data)
	}
	var decoded protocol.HTMLMessageV2
	if err := json.Unmarshal([]byte(hook.data), &decoded); err != nil {
		t.Fatalf("decode pushed html: %v", err)
	}
	if err := decoded.Validate(); err != nil {
		t.Fatalf("pushed html failed strict validation: %v", err)
	}
}

func TestURLMessageV1ExplicitVersionDispatchStillReturnsLegacy(t *testing.T) {
	raw := `{"protocol_version":"1.0","task_id":"t1","url":"https://example.gov.cn/a.html","site":"s","keyword":"k","level":1,"title":"T","time":"2026-08-13T00:00:00Z"}`
	rq, hook := newContractQueue(t, raw)
	result, err := rq.PopURLDispatch()
	if err != nil {
		t.Fatalf("PopURLDispatch v1 explicit: %v", err)
	}
	if result == nil || result.Legacy == nil || result.V2 != nil {
		t.Fatalf("unexpected result: %#v", result)
	}
	hook.assertNoNetwork(t)
}
