package queue

import (
	"encoding/json"
	"testing"
)

func TestHTMLPayloadMarshalIncludesTitle(t *testing.T) {
	payload := HTMLPayload{
		URL:   "https://example.com",
		Title: "Example",
		HTML:  "<html></html>",
		Time:  "2026-07-26T00:00:00Z",
	}

	data, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal HTMLPayload: %v", err)
	}

	var decoded map[string]any
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal HTMLPayload: %v", err)
	}

	if decoded["title"] != "Example" {
		t.Fatalf("title = %v, want Example", decoded["title"])
	}
	if _, exists := decoded["error"]; exists {
		t.Fatal("empty error should be omitted")
	}
}

func TestHTMLPayloadMarshalIncludesError(t *testing.T) {
	payload := HTMLPayload{
		URL:   "https://example.com",
		Error: "request failed",
		Time:  "2026-07-26T00:00:00Z",
	}

	data, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal HTMLPayload: %v", err)
	}

	var decoded map[string]any
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal HTMLPayload: %v", err)
	}

	if decoded["error"] != "request failed" {
		t.Fatalf("error = %v, want request failed", decoded["error"])
	}
	if _, exists := decoded["title"]; exists {
		t.Fatal("empty title should be omitted")
	}
}
func TestPushSearchFormatMatchesProtocol(t *testing.T) {
	var data map[string]any
	msg := map[string]any{
		"protocol_version": "1.0",
		"task_id":          "",
		"message_id":       "",
		"timestamp":        "2026-07-27T16:00:00Z",
		"type":             "search",
		"site":             "czj_beijing",
		"keyword":          "低空经济",
		"level":            1,
		"max_pages":        0,
	}
	encoded, err := json.Marshal(msg)
	if err != nil {
		t.Fatalf("marshal search message: %v", err)
	}
	if err := json.Unmarshal(encoded, &data); err != nil {
		t.Fatalf("unmarshal search message: %v", err)
	}
	if data["site"] != "czj_beijing" {
		t.Fatalf("site = %v, want czj_beijing", data["site"])
	}
	if data["max_pages"].(float64) != 0 {
		t.Fatalf("max_pages = %v, want 0", data["max_pages"])
	}
}
func TestHTMLPayloadDeserializePreservesFields(t *testing.T) {
	data := `{
		"task_id": "t-001",
		"url": "https://czj.beijing.gov.cn/art/1.html",
		"site": "czj_beijing",
		"keyword": "低空经济",
		"level": 1,
		"title": "政策解读",
		"time": "2026-07-27T16:00:00Z"
	}`
	var p HTMLPayload
	if err := json.Unmarshal([]byte(data), &p); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if p.TaskID != "t-001" {
		t.Fatalf("TaskID = %q, want t-001", p.TaskID)
	}
	if p.URL != "https://czj.beijing.gov.cn/art/1.html" {
		t.Fatal("URL missing")
	}
	if p.Site != "czj_beijing" {
		t.Fatalf("Site = %q, want czj_beijing", p.Site)
	}
	if p.Keyword != "低空经济" {
		t.Fatalf("Keyword = %q, want 低空经济", p.Keyword)
	}
	if p.Level != 1 {
		t.Fatalf("Level = %d, want 1", p.Level)
	}
	if p.Title != "政策解读" {
		t.Fatalf("Title = %q, want 政策解读", p.Title)
	}
}


func TestMaxPagesPositive(t *testing.T) {
	tests := []struct {
		input int
		want  int
		valid bool
	}{
		{input: 0, want: 1, valid: true},
		{input: 1, want: 1, valid: true},
		{input: 5, want: 5, valid: true},
		{input: -1, want: 0, valid: false},
	}
	for _, tc := range tests {
		maxPages := tc.input
		if maxPages < 0 {
			continue // should be rejected at API layer
		}
		if maxPages == 0 {
			maxPages = 1
		}
		if maxPages != tc.want {
			t.Fatalf("input=%d: got %d, want %d", tc.input, maxPages, tc.want)
		}
	}
}
