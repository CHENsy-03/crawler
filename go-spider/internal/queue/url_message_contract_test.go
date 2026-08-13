package queue

import (
	"encoding/json"
	"os"
	"testing"
)

const pythonURLMessageContractFixture = "../../../tests/fixtures/url_message_contract.json"

func TestPythonURLMessageContractDecodesWithProductionHTMLPayload(t *testing.T) {
	data, err := os.ReadFile(pythonURLMessageContractFixture)
	if err != nil {
		t.Fatalf("read shared fixture: %v", err)
	}

	// PopURL -> pop decodes crawler:url entries with json.Unmarshal into
	// HTMLPayload. Use that same production type without connecting to Redis.
	var payload HTMLPayload
	if err := json.Unmarshal(data, &payload); err != nil {
		t.Fatalf("json.Unmarshal HTMLPayload: %v", err)
	}
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
	data, err := os.ReadFile(pythonURLMessageContractFixture)
	if err != nil {
		t.Fatalf("read shared fixture: %v", err)
	}
	var root map[string]any
	if err := json.Unmarshal(data, &root); err != nil {
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
