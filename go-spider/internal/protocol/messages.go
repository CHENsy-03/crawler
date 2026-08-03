package protocol

import (
	"bytes"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"net/url"
	"strconv"
	"strings"
)

const (
	Version             = "1.0"
	VersionV2           = "2.0"
	TypeSearch          = "search"
	TypeSearchRequested = "search_requested"
	DefaultLevel        = 0
	DefaultMaxPages     = 1
)

func NewTaskID() string {
	b := make([]byte, 4)
	rand.Read(b)
	return fmt.Sprintf("task-%x", b)
}

func NewMessageID() string {
	b := make([]byte, 4)
	rand.Read(b)
	return fmt.Sprintf("msg-%x", b)
}

type Envelope struct {
	ProtocolVersion string `json:"protocol_version"`
	TaskID          string `json:"task_id"`
	MessageID       string `json:"message_id"`
	Timestamp       string `json:"timestamp"`
}

type SearchMessage struct {
	Envelope
	Type     string `json:"type"`
	Site     string `json:"site"`
	Keyword  string `json:"keyword"`
	Level    int    `json:"level"`
	MaxPages int    `json:"max_pages"`
}

type SearchRequestedMessage struct {
	Envelope
	Type      string   `json:"type"`
	TargetURL string   `json:"target_url"`
	Keywords  []string `json:"keywords"`
	Level     int      `json:"level"`
	MaxPages  int      `json:"max_pages"`
}

// ValidateTargetURL enforces the v2 target_url contract.
func ValidateTargetURL(raw string) error {
	if raw != strings.TrimSpace(raw) {
		return fmt.Errorf("target_url must not have leading or trailing whitespace")
	}
	if raw == "" {
		return fmt.Errorf("target_url is required")
	}
	u, err := url.Parse(raw)
	if err != nil {
		return fmt.Errorf("target_url must be a valid absolute URL: %w", err)
	}
	if strings.ToLower(u.Scheme) != "http" && strings.ToLower(u.Scheme) != "https" {
		return fmt.Errorf("target_url must use http or https")
	}
	if u.Host == "" {
		return fmt.Errorf("target_url must include a host")
	}
	if strings.HasSuffix(u.Host, ":") {
		return fmt.Errorf("target_url must not have an empty port")
	}
	if portStr := u.Port(); portStr != "" {
		port, err := strconv.Atoi(portStr)
		if err != nil || port < 0 || port > 65535 {
			return fmt.Errorf("target_url has invalid port")
		}
	}
	return nil
}

// NormalizeKeywords trims whitespace, drops blank values, and removes exact
// duplicates while preserving first-seen order.
func NormalizeKeywords(keywords []string) ([]string, error) {
	seen := make(map[string]struct{}, len(keywords))
	out := make([]string, 0, len(keywords))
	for _, keyword := range keywords {
		keyword = strings.TrimSpace(keyword)
		if keyword == "" {
			continue
		}
		if _, ok := seen[keyword]; ok {
			continue
		}
		seen[keyword] = struct{}{}
		out = append(out, keyword)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("keywords must contain at least one non-blank keyword")
	}
	return out, nil
}

func (m *SearchRequestedMessage) Validate() error {
	if m.ProtocolVersion != VersionV2 {
		return fmt.Errorf("search_requested protocol_version must be %q", VersionV2)
	}
	if m.Type != TypeSearchRequested {
		return fmt.Errorf("search_requested type must be %q", TypeSearchRequested)
	}
	if err := ValidateTargetURL(m.TargetURL); err != nil {
		return err
	}
	if _, err := NormalizeKeywords(m.Keywords); err != nil {
		return err
	}
	if m.MaxPages < 0 {
		return fmt.Errorf("max_pages must be >= 0")
	}
	return nil
}

var (
	v1SearchFields = map[string]bool{
		"protocol_version": true,
		"task_id":          true,
		"message_id":       true,
		"timestamp":        true,
		"type":             true,
		"site":             true,
		"keyword":          true,
		"level":            true,
		"max_pages":        true,
	}
	v2SearchFields = map[string]bool{
		"protocol_version": true,
		"task_id":          true,
		"message_id":       true,
		"timestamp":        true,
		"type":             true,
		"target_url":       true,
		"keywords":         true,
		"level":            true,
		"max_pages":        true,
	}
)

func rejectUnknownFields(fields map[string]json.RawMessage, allowed map[string]bool) error {
	for key := range fields {
		if !allowed[key] {
			return fmt.Errorf("unknown field %q", key)
		}
	}
	return nil
}

func rejectNullKeywords(raw json.RawMessage) error {
	trimmed := bytes.TrimSpace(raw)
	if bytes.Equal(trimmed, []byte("null")) {
		return fmt.Errorf("INVALID_KEYWORD: keywords must not be null")
	}
	var items []json.RawMessage
	if err := json.Unmarshal(trimmed, &items); err != nil {
		return fmt.Errorf("INVALID_KEYWORD: keywords must be a JSON array")
	}
	for _, item := range items {
		if bytes.Equal(bytes.TrimSpace(item), []byte("null")) {
			return fmt.Errorf("INVALID_KEYWORD: keywords must not contain null elements")
		}
	}
	return nil
}

func requireNonBlankStringField(fields map[string]json.RawMessage, key string) error {
	raw, ok := fields[key]
	if !ok {
		return fmt.Errorf("v1 search %s is required", key)
	}
	var value string
	if err := json.Unmarshal(raw, &value); err != nil {
		return fmt.Errorf("v1 search %s must be a string", key)
	}
	if strings.TrimSpace(value) == "" {
		return fmt.Errorf("v1 search %s must not be blank", key)
	}
	return nil
}

func applyOptionalInt(fields map[string]json.RawMessage, key string, target *int, defaultValue int) error {
	raw, ok := fields[key]
	if !ok {
		*target = defaultValue
		return nil
	}
	trimmed := bytes.TrimSpace(raw)
	if bytes.Equal(trimmed, []byte("null")) {
		return fmt.Errorf("%s must not be null", key)
	}
	if err := json.Unmarshal(trimmed, target); err != nil {
		return fmt.Errorf("%s must be an integer: %w", key, err)
	}
	return nil
}

// DecodeSearchRequest dispatches on protocol_version. The version is never
// inferred from other fields and unknown fields are rejected.
func DecodeSearchRequest(data []byte) (any, error) {
	var header struct {
		ProtocolVersion string `json:"protocol_version"`
		Type            string `json:"type"`
	}
	if err := json.Unmarshal(data, &header); err != nil {
		return nil, fmt.Errorf("decode search request header: %w", err)
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		return nil, fmt.Errorf("decode search request fields: %w", err)
	}
	if header.ProtocolVersion != "" {
		for _, field := range []string{"task_id", "message_id", "timestamp"} {
			if _, ok := fields[field]; !ok {
				return nil, fmt.Errorf("search request %s is required", field)
			}
		}
	}

	switch header.ProtocolVersion {
	case Version:
		if err := rejectUnknownFields(fields, v1SearchFields); err != nil {
			return nil, err
		}
		if header.Type != TypeSearch {
			return nil, fmt.Errorf("v1 search type must be %q", TypeSearch)
		}
		if err := requireNonBlankStringField(fields, "site"); err != nil {
			return nil, err
		}
		if err := requireNonBlankStringField(fields, "keyword"); err != nil {
			return nil, err
		}
		var msg SearchMessage
		if err := json.Unmarshal(data, &msg); err != nil {
			return nil, fmt.Errorf("decode v1 search request: %w", err)
		}
		msg.Site = strings.TrimSpace(msg.Site)
		msg.Keyword = strings.TrimSpace(msg.Keyword)
		if err := applyOptionalInt(fields, "level", &msg.Level, DefaultLevel); err != nil {
			return nil, err
		}
		if err := applyOptionalInt(fields, "max_pages", &msg.MaxPages, DefaultMaxPages); err != nil {
			return nil, err
		}
		return &msg, nil
	case VersionV2:
		if err := rejectUnknownFields(fields, v2SearchFields); err != nil {
			return nil, err
		}
		if header.Type != TypeSearchRequested {
			return nil, fmt.Errorf("v2 search type must be %q", TypeSearchRequested)
		}
		if _, ok := fields["target_url"]; !ok {
			return nil, fmt.Errorf("v2 search target_url is required")
		}
		if _, ok := fields["keywords"]; !ok {
			return nil, fmt.Errorf("v2 search keywords is required")
		}
		if err := rejectNullKeywords(fields["keywords"]); err != nil {
			return nil, err
		}
		var msg SearchRequestedMessage
		if err := json.Unmarshal(data, &msg); err != nil {
			return nil, fmt.Errorf("decode v2 search request: %w", err)
		}
		if err := applyOptionalInt(fields, "level", &msg.Level, DefaultLevel); err != nil {
			return nil, err
		}
		if err := applyOptionalInt(fields, "max_pages", &msg.MaxPages, DefaultMaxPages); err != nil {
			return nil, err
		}
		if err := ValidateTargetURL(msg.TargetURL); err != nil {
			return nil, err
		}
		normalized, err := NormalizeKeywords(msg.Keywords)
		if err != nil {
			return nil, err
		}
		msg.Keywords = normalized
		if err := msg.Validate(); err != nil {
			return nil, err
		}
		return &msg, nil
	case "":
		return nil, fmt.Errorf("protocol_version is required")
	default:
		return nil, fmt.Errorf("unsupported protocol_version %q", header.ProtocolVersion)
	}
}

type URLMessage struct {
	Envelope
	Type    string `json:"type"`
	URL     string `json:"url"`
	Site    string `json:"site"`
	Keyword string `json:"keyword"`
	Level   int    `json:"level"`
	Title   string `json:"title"`
}

type HTMLMessage struct {
	Envelope
	Type    string `json:"type"`
	URL     string `json:"url"`
	Site    string `json:"site"`
	Keyword string `json:"keyword"`
	Level   int    `json:"level"`
	Title   string `json:"title"`
	HTML    string `json:"html"`
}

type ResultMessage struct {
	Envelope
	Type            string   `json:"type"`
	Site            string   `json:"site"`
	Keyword         string   `json:"keyword"`
	Level           int      `json:"level"`
	URL             string   `json:"url"`
	Title           string   `json:"title"`
	PublishDate     string   `json:"publish_date"`
	Content         string   `json:"content"`
	Summary         string   `json:"summary"`
	Score           int      `json:"score"`
	MatchedKeywords []string `json:"matched_keywords"`
}

type SearchDoneMessage struct {
	Envelope
	Type     string `json:"type"`
	Site     string `json:"site"`
	Keyword  string `json:"keyword"`
	URLCount int    `json:"url_count"`
	Level    int    `json:"level"`
}

type ErrorMessage struct {
	Envelope
	Type      string `json:"type"`
	Site      string `json:"site"`
	Keyword   string `json:"keyword"`
	Level     int    `json:"level"`
	Stage     string `json:"stage"`
	URL       string `json:"url"`
	ErrorCode string `json:"error_code"`
	Error     string `json:"error"`
	Retryable bool   `json:"retryable"`
}
