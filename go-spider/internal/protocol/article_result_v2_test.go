package protocol

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func articleV2FixturePath(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Join(filepath.Dir(file), "..", "..", "..", "tests", "fixtures", "article_result_v2_contract.json")
}

func loadArticleV2Fixture(t *testing.T) map[string]any {
	t.Helper()
	data, err := os.ReadFile(articleV2FixturePath(t))
	if err != nil {
		t.Fatalf("read article v2 fixture: %v", err)
	}
	var fixture map[string]any
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode article v2 fixture: %v", err)
	}
	return fixture
}

func assertV2MessageMatchesFixture(t *testing.T, key string) {
	t.Helper()
	fixture := loadArticleV2Fixture(t)
	raw, err := json.Marshal(fixture[key])
	if err != nil {
		t.Fatalf("marshal fixture %s: %v", key, err)
	}
	decoded, err := DecodeV2ArticleMessage(raw)
	if err != nil {
		t.Fatalf("decode %s: %v", key, err)
	}
	data, err := json.Marshal(decoded)
	if err != nil {
		t.Fatalf("marshal decoded %s: %v", key, err)
	}
	var actual map[string]any
	if err := json.Unmarshal(data, &actual); err != nil {
		t.Fatalf("unmarshal decoded %s: %v", key, err)
	}
	if !jsonEqual(actual, fixture[key]) {
		t.Fatalf("%s fixture mismatch:\n got %s\nwant %s", key, string(data), string(raw))
	}
}

func TestArticleV2FixturePathExists(t *testing.T) {
	if !isFile(articleV2FixturePath(t)) {
		t.Fatalf("article v2 fixture missing: %s", articleV2FixturePath(t))
	}
}

func TestURLMessageV2MatchesFixture(t *testing.T) {
	assertV2MessageMatchesFixture(t, "url_v2")
}

func TestHTMLMessageV2MatchesFixture(t *testing.T) {
	assertV2MessageMatchesFixture(t, "html_v2")
}

func TestArticleResultV2MatchesFixture(t *testing.T) {
	assertV2MessageMatchesFixture(t, "article_result_v2")
}

func TestV2ArticleMessagesRoundTrip(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	for _, key := range []string{"url_v2", "html_v2", "article_result_v2"} {
		raw, err := json.Marshal(fixture[key])
		if err != nil {
			t.Fatalf("marshal %s: %v", key, err)
		}
		decoded, err := DecodeV2ArticleMessage(raw)
		if err != nil {
			t.Fatalf("decode %s: %v", key, err)
		}
		again, err := json.Marshal(decoded)
		if err != nil {
			t.Fatalf("marshal decoded %s: %v", key, err)
		}
		round, err := DecodeV2ArticleMessage(again)
		if err != nil {
			t.Fatalf("second decode %s: %v", key, err)
		}
		if !jsonEqual(round, decoded) {
			t.Fatalf("%s roundtrip mismatch", key)
		}
	}
}

func TestEmptyMatchedEvidenceSerializesAsArray(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	raw, err := json.Marshal(fixture["article_result_v2_empty_evidence"])
	if err != nil {
		t.Fatalf("marshal fixture: %v", err)
	}
	decoded, err := DecodeV2ArticleMessage(raw)
	if err != nil {
		t.Fatalf("decode empty evidence: %v", err)
	}
	data, err := json.Marshal(decoded)
	if err != nil {
		t.Fatalf("marshal decoded: %v", err)
	}
	if !strings.Contains(string(data), `"matched_evidence":[]`) {
		t.Fatalf("matched_evidence should serialize as []: %s", string(data))
	}
}

func TestExtractFailedAllowsEmptyContentAndHash(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	raw, err := json.Marshal(fixture["article_result_v2_extract_failed"])
	if err != nil {
		t.Fatalf("marshal fixture: %v", err)
	}
	decoded, err := DecodeV2ArticleMessage(raw)
	if err != nil {
		t.Fatalf("decode extract_failed: %v", err)
	}
	msg := decoded.(*ArticleResultV2)
	if msg.Status != "extract_failed" || msg.Content != "" || msg.ContentHash != "" {
		t.Fatalf("extract_failed fields mismatch: %+v", msg)
	}
}

func mustRejectV2Article(t *testing.T, payload map[string]any) {
	t.Helper()
	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal invalid payload: %v", err)
	}
	if _, err := DecodeV2ArticleMessage(raw); err == nil {
		t.Fatalf("expected rejection for %s", string(raw))
	}
}

func TestV2ArticleExplicitNullRejected(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	payload := cloneMap(fixture["article_result_v2"].(map[string]any))
	payload["score"] = nil
	mustRejectV2Article(t, payload)
}

func TestV2ArticleUnknownFieldRejected(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	payload := cloneMap(fixture["article_result_v2"].(map[string]any))
	payload["unexpected"] = true
	mustRejectV2Article(t, payload)
}

func TestV2ArticleInvalidStatusRejected(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	payload := cloneMap(fixture["article_result_v2"].(map[string]any))
	payload["status"] = "not_a_status"
	mustRejectV2Article(t, payload)
}

func TestV2ArticleInvalidExtractionMethodRejected(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	payload := cloneMap(fixture["article_result_v2"].(map[string]any))
	payload["extraction_method"] = "not_a_method"
	mustRejectV2Article(t, payload)
}

func TestV2ArticleNegativeScoreRejected(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	payload := cloneMap(fixture["article_result_v2"].(map[string]any))
	payload["score"] = -1
	mustRejectV2Article(t, payload)
}

func TestV2ArticleBooleanScoreRejected(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	payload := cloneMap(fixture["article_result_v2"].(map[string]any))
	payload["score"] = true
	mustRejectV2Article(t, payload)
}

func TestV2ArticleInvalidContentHashRejected(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	payload := cloneMap(fixture["article_result_v2"].(map[string]any))
	payload["content_hash"] = strings.Repeat("0", 64)
	mustRejectV2Article(t, payload)
}

func TestV2ArticleMissingContentHashRejected(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	payload := cloneMap(fixture["article_result_v2"].(map[string]any))
	payload["content_hash"] = ""
	mustRejectV2Article(t, payload)
}

func TestV2ArticleInvalidURLRejected(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	payload := cloneMap(fixture["article_result_v2"].(map[string]any))
	payload["requested_url"] = "javascript:alert(1)"
	mustRejectV2Article(t, payload)
}

func TestV2ArticleInvalidEvidenceRejected(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	payload := cloneMap(fixture["article_result_v2"].(map[string]any))
	payload["matched_evidence"] = []any{
		map[string]any{"term": "低空经济", "origin": "original", "field": "title", "weight": -1},
	}
	mustRejectV2Article(t, payload)
}

func TestV2ArticleUnknownEvidenceFieldRejected(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	payload := cloneMap(fixture["article_result_v2"].(map[string]any))
	payload["matched_evidence"] = []any{
		map[string]any{"term": "低空经济", "origin": "original", "field": "title", "weight": 1, "extra": true},
	}
	mustRejectV2Article(t, payload)
}

func TestV2ArticleWrongProtocolVersionRejected(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	payload := cloneMap(fixture["article_result_v2"].(map[string]any))
	payload["protocol_version"] = "1.0"
	mustRejectV2Article(t, payload)
}

func TestV2ArticleUnknownTypeRejected(t *testing.T) {
	fixture := loadArticleV2Fixture(t)
	payload := cloneMap(fixture["article_result_v2"].(map[string]any))
	payload["type"] = "unknown"
	mustRejectV2Article(t, payload)
}

func cloneMap(input map[string]any) map[string]any {
	out := make(map[string]any, len(input))
	for key, value := range input {
		out[key] = value
	}
	return out
}
