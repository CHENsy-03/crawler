package protocol

import (
	"encoding/json"
	"testing"
)

func TestMarshalUnmarshalSearch(t *testing.T) {
  m := SearchMessage{
    Envelope: Envelope{ProtocolVersion: Version, TaskID: "t1", MessageID: "m1", Timestamp: "now"},
    Type:     "search", Site: "bj", Keyword: "kw", Level: 1, MaxPages: 1,
  }
	data, _ := json.Marshal(m)
	var dec SearchMessage
	json.Unmarshal(data, &dec)
	if dec.Site != "bj" || dec.Keyword != "kw" {
		t.Fatal("bad roundtrip")
	}
}

func TestMarshalUnmarshalResult(t *testing.T) {
	orig := ResultMessage{
		Envelope: Envelope{ProtocolVersion: Version, TaskID: "t1", MessageID: "m2", Timestamp: "now"},
		Type:     "result", URL: "https://x.com", Title: "T", PublishDate: "2026-01-01", Content: "C", Score: 85,
	}
	data, _ := json.Marshal(orig)
	var dec ResultMessage
	json.Unmarshal(data, &dec)
	if dec.Score != 85 {
		t.Fatal("score mismatch")
	}
}

func TestMarshalUnmarshalError(t *testing.T) {
	orig := ErrorMessage{
		Envelope: Envelope{ProtocolVersion: Version, TaskID: "t1", MessageID: "m3", Timestamp: "now"},
		Type:     "error", Stage: "download", URL: "https://x.com", ErrorCode: "HTTP_403", Error: "forbidden", Retryable: false,
	}
	data, _ := json.Marshal(orig)
	var dec ErrorMessage
	json.Unmarshal(data, &dec)
	if dec.ErrorCode != "HTTP_403" || dec.Retryable != false {
		t.Fatal("bad error roundtrip")
	}
}

func TestEnvelopePreservesVersion(t *testing.T) {
  orig := SearchMessage{
    Envelope: Envelope{ProtocolVersion: Version, TaskID: "t1", MessageID: "m4", Timestamp: "now"},
    Type:     "search", Site: "bj", Keyword: "kw", Level: 1, MaxPages: 1,
  }
	var result map[string]interface{}
	data, _ := json.Marshal(orig)
	json.Unmarshal(data, &result)
	if result["protocol_version"] != Version {
		t.Fatal("protocol_version preserved")
	}
	if result["type"] != "search" {
		t.Fatal("type field present")
	}
	if result["site"] != "bj" {
		t.Fatal("site field present")
	}
}

func TestOmitEmptyFieldStillSerialized(t *testing.T) {
	m := ErrorMessage{
		Envelope: Envelope{ProtocolVersion: Version, TaskID: "t1", MessageID: "m5", Timestamp: "now"},
		Type:     "error", Stage: "download", ErrorCode: "ERR", Error: "msg",
	}
	data, _ := json.Marshal(m)
	var result map[string]interface{}
	json.Unmarshal(data, &result)
	if _, exists := result["retryable"]; !exists {
		t.Fatal("retryable should be serialized even if false")
	}
	if _, exists := result["url"]; !exists {
		t.Fatal("url should be serialized even if empty")
	}
}

func TestFixtureMatchSearch(t *testing.T) {
  msg := SearchMessage{Envelope: Envelope{ProtocolVersion: "1.0", TaskID: "task-001", MessageID: "msg-001", Timestamp: "2026-07-27T16:00:00Z"}, Type: "search", Site: "czj_beijing", Keyword: "低空经济", Level: 1, MaxPages: 1}
	data, _ := json.Marshal(msg)
	var result map[string]interface{}
	json.Unmarshal(data, &result)
	if result["site"] != "czj_beijing" || result["keyword"] != "低空经济" {
		t.Fatal("search fixture mismatch")
	}
}

func TestFixtureMatchResult(t *testing.T) {
	msg := ResultMessage{Envelope: Envelope{ProtocolVersion: "1.0", TaskID: "task-001", MessageID: "msg-004", Timestamp: "2026-07-27T16:00:00Z"}, Type: "result", URL: "https://czj.beijing.gov.cn/art/1.html", Title: "低空经济政策解读", PublishDate: "2026-07-27", Content: "正文内容", Score: 85}
	data, _ := json.Marshal(msg)
	var result map[string]interface{}
	json.Unmarshal(data, &result)
	if result["score"].(float64) != 85 {
		t.Fatal("result fixture score mismatch")
	}
	if result["publish_date"] != "2026-07-27" {
		t.Fatal("result fixture date mismatch")
	}
}
func TestNewTaskIDNonEmpty(t *testing.T) {
	id := NewTaskID()
	if id == "" {
		t.Fatal("NewTaskID returned empty")
	}
}

func TestNewMessageIDNonEmpty(t *testing.T) {
	id := NewMessageID()
	if id == "" {
		t.Fatal("NewMessageID returned empty")
	}
}

func TestNewTaskIDUnique(t *testing.T) {
	seen := make(map[string]bool)
	for i := 0; i < 100; i++ {
		id := NewTaskID()
		if seen[id] {
			t.Fatalf("duplicate task id: %s", id)
		}
		seen[id] = true
	}
}

func TestNewMessageIDUnique(t *testing.T) {
	seen := make(map[string]bool)
	for i := 0; i < 100; i++ {
		id := NewMessageID()
		if seen[id] {
			t.Fatalf("duplicate message id: %s", id)
		}
		seen[id] = true
	}
}

func TestURLMessageWithTitle(t *testing.T) {
	m := URLMessage{
		Envelope: Envelope{ProtocolVersion: Version, TaskID: "t1", MessageID: "m1", Timestamp: "now"},
		Type:     "url", URL: "https://x.com", Site: "bj",
		Keyword: "kw", Level: 1, Title: "示例标题",
	}
	var result map[string]interface{}
	data, _ := json.Marshal(m)
	json.Unmarshal(data, &result)
	if result["title"] != "示例标题" {
		t.Fatalf("title = %v, want 示例标题", result["title"])
	}
	if result["type"] != "url" {
		t.Fatal("type field present")
	}
}
