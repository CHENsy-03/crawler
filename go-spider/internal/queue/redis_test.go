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
