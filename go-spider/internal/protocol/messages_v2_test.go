package protocol

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func v2FixturePath(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Join(filepath.Dir(file), "..", "..", "..", "tests", "fixtures", "redis_protocol_v2.json")
}

func v1FixturePath(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Join(filepath.Dir(file), "..", "..", "..", "tests", "fixtures", "redis_protocol_v1.json")
}

func loadFixture(t *testing.T, path string) map[string]any {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read fixture %s: %v", path, err)
	}
	var fixture map[string]any
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode fixture %s: %v", path, err)
	}
	return fixture
}

func TestV2FixturePathDoesNotDependOnCWD(t *testing.T) {
	if !isFile(v2FixturePath(t)) {
		t.Fatalf("v2 fixture missing: %s", v2FixturePath(t))
	}
}

func TestV2FixtureMatchesSearchRequested(t *testing.T) {
	fixture := loadFixture(t, v2FixturePath(t))
	envelope := fixture["_envelope"].(map[string]any)
	msg := SearchRequestedMessage{
		Envelope: Envelope{
			ProtocolVersion: VersionV2,
			TaskID:          envelope["task_id"].(string),
			MessageID:       envelope["message_id"].(string),
			Timestamp:       envelope["timestamp"].(string),
		},
		Type:      TypeSearchRequested,
		TargetURL: "https://example.gov.cn/search",
		Keywords:  []string{" 低空经济 ", "无人机", "低空经济", "   "},
		Level:     1,
		MaxPages:  5,
	}
	data, err := json.Marshal(msg)
	if err != nil {
		t.Fatalf("marshal v2 message: %v", err)
	}
	var actual map[string]any
	if err := json.Unmarshal(data, &actual); err != nil {
		t.Fatalf("unmarshal v2 message: %v", err)
	}
	expected := fixture["search_requested"].(map[string]any)
	for key, value := range expected {
		got, exists := actual[key]
		if !exists {
			t.Fatalf("search_requested missing field %s", key)
		}
		if !jsonEqual(got, value) {
			t.Fatalf("search_requested.%s: %v != %v", key, got, value)
		}
	}
}

func TestV2DecodeNormalizesKeywords(t *testing.T) {
	fixture := loadFixture(t, v2FixturePath(t))
	raw, err := json.Marshal(fixture["search_requested"])
	if err != nil {
		t.Fatalf("marshal fixture: %v", err)
	}
	decoded, err := DecodeSearchRequest(raw)
	if err != nil {
		t.Fatalf("decode v2: %v", err)
	}
	msg, ok := decoded.(*SearchRequestedMessage)
	if !ok {
		t.Fatalf("decoded type = %T, want *SearchRequestedMessage", decoded)
	}
	want := []string{"低空经济", "无人机"}
	if len(msg.Keywords) != len(want) || msg.Keywords[0] != want[0] || msg.Keywords[1] != want[1] {
		t.Fatalf("keywords = %v, want %v", msg.Keywords, want)
	}
}

func TestV2DecodeAppliesOptionalDefaults(t *testing.T) {
	fixture := loadFixture(t, v2FixturePath(t))
	raw, err := json.Marshal(fixture["search_requested_minimal"])
	if err != nil {
		t.Fatalf("marshal fixture: %v", err)
	}
	decoded, err := DecodeSearchRequest(raw)
	if err != nil {
		t.Fatalf("decode v2 minimal: %v", err)
	}
	msg := decoded.(*SearchRequestedMessage)
	if msg.Level != DefaultLevel || msg.MaxPages != DefaultMaxPages {
		t.Fatalf("defaults = level:%d max_pages:%d", msg.Level, msg.MaxPages)
	}
}

func TestV1FixtureStillDecodes(t *testing.T) {
	fixture := loadFixture(t, v1FixturePath(t))
	raw, err := json.Marshal(fixture["search"])
	if err != nil {
		t.Fatalf("marshal v1 fixture: %v", err)
	}
	decoded, err := DecodeSearchRequest(raw)
	if err != nil {
		t.Fatalf("decode v1: %v", err)
	}
	msg, ok := decoded.(*SearchMessage)
	if !ok {
		t.Fatalf("decoded type = %T, want *SearchMessage", decoded)
	}
	if msg.ProtocolVersion != Version || msg.Site != "czj_beijing" {
		t.Fatalf("v1 fields not preserved: %+v", msg)
	}
}

func TestDecodeSearchRequestMissingVersion(t *testing.T) {
	_, err := DecodeSearchRequest([]byte(`{"type":"search_requested","target_url":"https://x.test","keywords":["k"]}`))
	if err == nil || err.Error() != "protocol_version is required" {
		t.Fatalf("err = %v", err)
	}
}

func TestDecodeSearchRequestUnknownVersion(t *testing.T) {
	raw := []byte(`{"protocol_version":"9.9","task_id":"t","message_id":"m","timestamp":"now","type":"search_requested","target_url":"https://x.test","keywords":["k"]}`)
	if _, err := DecodeSearchRequest(raw); err == nil || !strings.Contains(err.Error(), "unsupported protocol_version") {
		t.Fatalf("err = %v", err)
	}
}

func TestSearchRequestedRoundTrip(t *testing.T) {
	orig := SearchRequestedMessage{
		Envelope:  Envelope{ProtocolVersion: VersionV2, TaskID: "t", MessageID: "m", Timestamp: "now"},
		Type:      TypeSearchRequested,
		TargetURL: "https://example.gov.cn/search",
		Keywords:  []string{"低空经济", "无人机"},
		Level:     1,
		MaxPages:  5,
	}
	if err := orig.Validate(); err != nil {
		t.Fatalf("validate: %v", err)
	}
	data, err := json.Marshal(orig)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var dec SearchRequestedMessage
	if err := json.Unmarshal(data, &dec); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if dec.TargetURL != orig.TargetURL || len(dec.Keywords) != 2 || dec.MaxPages != 5 {
		t.Fatalf("roundtrip mismatch: %+v", dec)
	}
}

func TestV1DecodeRejectsMissingRequiredFields(t *testing.T) {
	for _, payload := range []string{
		`{"protocol_version":"1.0","task_id":"t","message_id":"m","timestamp":"now","type":"search","keyword":"k","level":1,"max_pages":1}`,
		`{"protocol_version":"1.0","task_id":"t","message_id":"m","timestamp":"now","type":"search","site":"s","level":1,"max_pages":1}`,
	} {
		if _, err := DecodeSearchRequest([]byte(payload)); err == nil {
			t.Fatalf("expected error for %s", payload)
		}
	}
}

func TestV1DecodeRejectsV2Fields(t *testing.T) {
	for _, payload := range []string{
		`{"protocol_version":"1.0","task_id":"t","message_id":"m","timestamp":"now","type":"search","site":"s","keyword":"k","level":1,"max_pages":1,"target_url":"https://x"}`,
		`{"protocol_version":"1.0","task_id":"t","message_id":"m","timestamp":"now","type":"search","site":"s","keyword":"k","level":1,"max_pages":1,"keywords":["k"]}`,
	} {
		if _, err := DecodeSearchRequest([]byte(payload)); err == nil || !strings.Contains(err.Error(), "unknown field") {
			t.Fatalf("expected unknown field error for %s, got %v", payload, err)
		}
	}
}

func TestV2DecodeRejectsV1Fields(t *testing.T) {
	for _, field := range []string{`"site":"s"`, `"profile":"p"`, `"keyword":"k"`} {
		payload := `{"protocol_version":"2.0","task_id":"t","message_id":"m","timestamp":"now","type":"search_requested","target_url":"https://x","keywords":["k"],` + field + `}`
		if _, err := DecodeSearchRequest([]byte(payload)); err == nil || !strings.Contains(err.Error(), "unknown field") {
			t.Fatalf("expected unknown field error for %s, got %v", field, err)
		}
	}
}

func TestDecodeSearchRequestRejectsUnknownField(t *testing.T) {
	payload := `{"protocol_version":"2.0","task_id":"t","message_id":"m","timestamp":"now","type":"search_requested","target_url":"https://x","keywords":["k"],"bogus":1}`
	if _, err := DecodeSearchRequest([]byte(payload)); err == nil || !strings.Contains(err.Error(), "unknown field") {
		t.Fatalf("err = %v", err)
	}
}

func TestDecodeSearchRequestRejectsNullOptional(t *testing.T) {
	for _, field := range []string{`"level":null`, `"max_pages":null`} {
		payload := `{"protocol_version":"2.0","task_id":"t","message_id":"m","timestamp":"now","type":"search_requested","target_url":"https://x","keywords":["k"],` + field + `}`
		if _, err := DecodeSearchRequest([]byte(payload)); err == nil || !strings.Contains(err.Error(), "must not be null") {
			t.Fatalf("err = %v for %s", err, payload)
		}
	}
}

func TestValidateTargetURLPortRules(t *testing.T) {
	for _, raw := range []string{"https://example.gov.cn:443", "https://example.gov.cn:65535"} {
		if err := ValidateTargetURL(raw); err != nil {
			t.Fatalf("valid port rejected: %s: %v", raw, err)
		}
	}
	for _, raw := range []string{
		"https://example.gov.cn:abc",
		"https://example.gov.cn:99999",
		"https://example.gov.cn:",
		" https://example.gov.cn",
		"https://example.gov.cn ",
	} {
		if err := ValidateTargetURL(raw); err == nil {
			t.Fatalf("invalid url accepted: %q", raw)
		}
	}
}

func TestSearchRequestedValidateDoesNotMutateKeywords(t *testing.T) {
	msg := SearchRequestedMessage{
		Envelope:  Envelope{ProtocolVersion: VersionV2, TaskID: "t", MessageID: "m", Timestamp: "now"},
		Type:      TypeSearchRequested,
		TargetURL: "https://example.gov.cn/search",
		Keywords:  []string{" 低空经济 ", "低空经济"},
		Level:     1,
		MaxPages:  1,
	}
	before := append([]string(nil), msg.Keywords...)
	if err := msg.Validate(); err != nil {
		t.Fatalf("validate: %v", err)
	}
	if len(msg.Keywords) != len(before) || msg.Keywords[0] != before[0] || msg.Keywords[1] != before[1] {
		t.Fatalf("Validate mutated keywords: %v", msg.Keywords)
	}
}

func isFile(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

func jsonEqual(a, b any) bool {
	ab, err := json.Marshal(a)
	if err != nil {
		return false
	}
	bb, err := json.Marshal(b)
	if err != nil {
		return false
	}
	return string(ab) == string(bb)
}

func TestV2DecodeRejectsNonArrayKeywords(t *testing.T) {
	for _, keywords := range []string{`"k"`, `{"k":1}`, `null`} {
		payload := `{"protocol_version":"2.0","task_id":"t","message_id":"m","timestamp":"now","type":"search_requested","target_url":"https://x","keywords":` + keywords + `}`
		if _, err := DecodeSearchRequest([]byte(payload)); err == nil {
			t.Fatalf("expected error for keywords=%s", keywords)
		}
	}
}

func TestV1DecodeRejectsBlankOrNonStringRequired(t *testing.T) {
	base := `{"protocol_version":"1.0","task_id":"t","message_id":"m","timestamp":"now","type":"search","level":1,"max_pages":1`
	cases := []string{
		`,"site":null,"keyword":"k"}`,
		`,"site":"","keyword":"k"}`,
		`,"site":"   ","keyword":"k"}`,
		`,"site":1,"keyword":"k"}`,
		`,"site":"s","keyword":null}`,
		`,"site":"s","keyword":""}`,
		`,"site":"s","keyword":"   "}`,
		`,"site":"s","keyword":[]}`,
	}
	for _, suffix := range cases {
		payload := base + suffix
		if _, err := DecodeSearchRequest([]byte(payload)); err == nil {
			t.Fatalf("expected error for %s", suffix)
		}
	}
}

func TestV1DecodeTrimsSiteAndKeyword(t *testing.T) {
	payload := `{"protocol_version":"1.0","task_id":"t","message_id":"m","timestamp":"now","type":"search","site":"  s  ","keyword":"  k  ","level":1,"max_pages":1}`
	decoded, err := DecodeSearchRequest([]byte(payload))
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	msg := decoded.(*SearchMessage)
	if msg.Site != "s" || msg.Keyword != "k" {
		t.Fatalf("site=%q keyword=%q", msg.Site, msg.Keyword)
	}
}

func TestV1InvalidFixtureCasesRejected(t *testing.T) {
	fixture := loadFixture(t, v2FixturePath(t))
	cases := fixture["invalid_v1_cases"].([]any)
	for _, c := range cases {
		raw, err := json.Marshal(c)
		if err != nil {
			t.Fatalf("marshal invalid v1 case: %v", err)
		}
		if _, err := DecodeSearchRequest(raw); err == nil {
			t.Fatalf("expected rejection for %s", string(raw))
		}
	}
}

func TestV2RejectsNullKeywordElementsFromFixture(t *testing.T) {
	fixture := loadFixture(t, v2FixturePath(t))
	for _, c := range fixture["invalid_keywords_cases"].([]any) {
		raw, err := json.Marshal(c)
		if err != nil {
			t.Fatalf("marshal invalid keywords case: %v", err)
		}
		if _, err := DecodeSearchRequest(raw); err == nil {
			t.Fatalf("expected rejection for %s", string(raw))
		}
	}
}

func TestV2AcceptsStringNullKeywordFromFixture(t *testing.T) {
	fixture := loadFixture(t, v2FixturePath(t))
	raw, err := json.Marshal(fixture["valid_keywords_null_string"])
	if err != nil {
		t.Fatalf("marshal valid case: %v", err)
	}
	decoded, err := DecodeSearchRequest(raw)
	if err != nil {
		t.Fatalf("decode valid case: %v", err)
	}
	msg := decoded.(*SearchRequestedMessage)
	if len(msg.Keywords) != 1 || msg.Keywords[0] != "null" {
		t.Fatalf("keywords=%v", msg.Keywords)
	}
}

func TestValidateTargetURLRejectsMalformedIPv6(t *testing.T) {
	for _, raw := range []string{"https://[::1", "https://[invalid]"} {
		if err := ValidateTargetURL(raw); err == nil || !strings.Contains(err.Error(), "target_url") {
			t.Fatalf("err = %v for %q", err, raw)
		}
	}
}
