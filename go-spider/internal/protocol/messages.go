package protocol

import (
	"bytes"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
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

const (
	TypeURLV2           = "url"
	TypeHTMLV2          = "html"
	TypeArticleResultV2 = "article_result"
)

var (
	v2URLMessageFields = map[string]bool{
		"protocol_version": true, "task_id": true, "message_id": true, "timestamp": true,
		"type": true, "hit_id": true, "plan_id": true, "original_query": true,
		"query_term": true, "url": true, "title": true, "snippet": true,
		"published_at": true, "source": true, "level": true,
	}
	v2HTMLMessageFields = map[string]bool{
		"protocol_version": true, "task_id": true, "message_id": true, "timestamp": true,
		"type": true, "hit_id": true, "plan_id": true, "original_query": true,
		"query_term": true, "requested_url": true, "final_url": true, "content_type": true,
		"title": true, "snippet": true, "published_at": true, "source": true,
		"level": true, "html": true,
	}
	v2ArticleFields = map[string]bool{
		"protocol_version": true, "task_id": true, "message_id": true, "timestamp": true,
		"type": true, "hit_id": true, "plan_id": true, "original_query": true,
		"query_term": true, "requested_url": true, "final_url": true, "canonical_url": true,
		"title": true, "publish_date": true, "source": true, "summary": true,
		"content": true, "content_hash": true, "score": true, "matched_evidence": true,
		"status": true, "extraction_method": true,
	}
	v2MatchedEvidenceFields = map[string]bool{
		"term": true, "origin": true, "field": true, "weight": true,
	}
	articleResultStatuses = map[string]bool{
		"accepted": true, "review_required": true, "irrelevant": true,
		"extract_failed": true, "unsupported_format": true,
	}
	extractionMethods = map[string]bool{
		"site_selector": true, "cms_rule": true, "ai": true, "density": true,
		"fallback": true, "pdf": true, "docx": true, "xlsx": true, "none": true,
	}
	evidenceOrigins = map[string]bool{"original": true, "expanded": true}
	evidenceFields  = map[string]bool{"title": true, "summary": true, "content": true, "url": true}
)

func requireV2Field(fields map[string]json.RawMessage, key string) error {
	if _, ok := fields[key]; !ok {
		return fmt.Errorf("v2 article %s is required", key)
	}
	return nil
}

func rejectNullField(fields map[string]json.RawMessage, key string) error {
	raw, ok := fields[key]
	if !ok {
		return nil
	}
	if bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
		return fmt.Errorf("v2 article %s must not be null", key)
	}
	return nil
}

func requireV2NonBlank(value, field string) error {
	if strings.TrimSpace(value) == "" {
		return fmt.Errorf("v2 article %s must be a non-blank string", field)
	}
	return nil
}

func validateHTMLContentType(value string) error {
	base := strings.ToLower(strings.TrimSpace(strings.SplitN(value, ";", 2)[0]))
	if base != "text/html" && base != "application/xhtml+xml" {
		return fmt.Errorf("v2 article content_type must be an HTML MIME type")
	}
	return nil
}

func validateOptionalAbsoluteURL(value, field string) error {
	if value == "" {
		return nil
	}
	return ValidateTargetURL(value)
}

type URLMessageV2 struct {
	ProtocolVersion string `json:"protocol_version"`
	TaskID          string `json:"task_id"`
	MessageID       string `json:"message_id"`
	Timestamp       string `json:"timestamp"`
	Type            string `json:"type"`
	HitID           string `json:"hit_id"`
	PlanID          string `json:"plan_id"`
	OriginalQuery   string `json:"original_query"`
	QueryTerm       string `json:"query_term"`
	URL             string `json:"url"`
	Title           string `json:"title"`
	Snippet         string `json:"snippet"`
	PublishedAt     string `json:"published_at"`
	Source          string `json:"source"`
	Level           int    `json:"level"`
}

type urlMessageV2Alias URLMessageV2

func (m URLMessageV2) MarshalJSON() ([]byte, error) {
	return marshalJSONNoEscape(urlMessageV2Alias(m))
}

func (m *URLMessageV2) UnmarshalJSON(data []byte) error {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		return fmt.Errorf("decode url_v2 fields: %w", err)
	}
	if err := rejectUnknownFields(fields, v2URLMessageFields); err != nil {
		return err
	}
	for _, key := range []string{
		"protocol_version", "task_id", "message_id", "timestamp", "type", "hit_id",
		"plan_id", "original_query", "query_term", "url", "title", "snippet",
		"published_at", "source", "level",
	} {
		if err := requireV2Field(fields, key); err != nil {
			return err
		}
	}
	for key := range v2URLMessageFields {
		if err := rejectNullField(fields, key); err != nil {
			return err
		}
	}
	var alias urlMessageV2Alias
	if err := json.Unmarshal(data, &alias); err != nil {
		return fmt.Errorf("decode url_v2: %w", err)
	}
	*m = URLMessageV2(alias)
	return m.Validate()
}

func (m *URLMessageV2) Validate() error {
	if m.ProtocolVersion != VersionV2 {
		return fmt.Errorf("url_v2 protocol_version must be %q", VersionV2)
	}
	if m.Type != TypeURLV2 {
		return fmt.Errorf("url_v2 type must be %q", TypeURLV2)
	}
	for _, field := range []struct{ value, name string }{
		{m.HitID, "hit_id"}, {m.PlanID, "plan_id"}, {m.OriginalQuery, "original_query"},
		{m.QueryTerm, "query_term"}, {m.Source, "source"},
	} {
		if err := requireV2NonBlank(field.value, field.name); err != nil {
			return err
		}
	}
	if err := ValidateTargetURL(m.URL); err != nil {
		return err
	}
	if m.Level < 0 {
		return fmt.Errorf("url_v2 level must be non-negative")
	}
	return nil
}

type HTMLMessageV2 struct {
	ProtocolVersion string `json:"protocol_version"`
	TaskID          string `json:"task_id"`
	MessageID       string `json:"message_id"`
	Timestamp       string `json:"timestamp"`
	Type            string `json:"type"`
	HitID           string `json:"hit_id"`
	PlanID          string `json:"plan_id"`
	OriginalQuery   string `json:"original_query"`
	QueryTerm       string `json:"query_term"`
	RequestedURL    string `json:"requested_url"`
	FinalURL        string `json:"final_url"`
	ContentType     string `json:"content_type"`
	Title           string `json:"title"`
	Snippet         string `json:"snippet"`
	PublishedAt     string `json:"published_at"`
	Source          string `json:"source"`
	Level           int    `json:"level"`
	HTML            string `json:"html"`
}

type htmlMessageV2Alias HTMLMessageV2

func (m HTMLMessageV2) MarshalJSON() ([]byte, error) {
	return marshalJSONNoEscape(htmlMessageV2Alias(m))
}

func (m *HTMLMessageV2) UnmarshalJSON(data []byte) error {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		return fmt.Errorf("decode html_v2 fields: %w", err)
	}
	if err := rejectUnknownFields(fields, v2HTMLMessageFields); err != nil {
		return err
	}
	for _, key := range []string{
		"protocol_version", "task_id", "message_id", "timestamp", "type", "hit_id",
		"plan_id", "original_query", "query_term", "requested_url", "final_url",
		"content_type", "title", "snippet", "published_at", "source", "level", "html",
	} {
		if err := requireV2Field(fields, key); err != nil {
			return err
		}
	}
	for key := range v2HTMLMessageFields {
		if err := rejectNullField(fields, key); err != nil {
			return err
		}
	}
	var alias htmlMessageV2Alias
	if err := json.Unmarshal(data, &alias); err != nil {
		return fmt.Errorf("decode html_v2: %w", err)
	}
	*m = HTMLMessageV2(alias)
	return m.Validate()
}

func (m *HTMLMessageV2) Validate() error {
	if m.ProtocolVersion != VersionV2 {
		return fmt.Errorf("html_v2 protocol_version must be %q", VersionV2)
	}
	if m.Type != TypeHTMLV2 {
		return fmt.Errorf("html_v2 type must be %q", TypeHTMLV2)
	}
	for _, field := range []struct{ value, name string }{
		{m.HitID, "hit_id"}, {m.PlanID, "plan_id"}, {m.OriginalQuery, "original_query"},
		{m.QueryTerm, "query_term"}, {m.Source, "source"},
	} {
		if err := requireV2NonBlank(field.value, field.name); err != nil {
			return err
		}
	}
	if err := ValidateTargetURL(m.RequestedURL); err != nil {
		return err
	}
	if err := ValidateTargetURL(m.FinalURL); err != nil {
		return err
	}
	if err := validateHTMLContentType(m.ContentType); err != nil {
		return err
	}
	if m.Level < 0 {
		return fmt.Errorf("html_v2 level must be non-negative")
	}
	return nil
}

type MatchedEvidence struct {
	Term   string  `json:"term"`
	Origin string  `json:"origin"`
	Field  string  `json:"field"`
	Weight float64 `json:"weight"`
}

type matchedEvidenceAlias MatchedEvidence

func (e MatchedEvidence) MarshalJSON() ([]byte, error) {
	return marshalJSONNoEscape(matchedEvidenceAlias(e))
}

func (e *MatchedEvidence) UnmarshalJSON(data []byte) error {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		return fmt.Errorf("decode matched_evidence fields: %w", err)
	}
	if err := rejectUnknownFields(fields, v2MatchedEvidenceFields); err != nil {
		return err
	}
	for _, key := range []string{"term", "origin", "field", "weight"} {
		if err := requireV2Field(fields, key); err != nil {
			return err
		}
		if err := rejectNullField(fields, key); err != nil {
			return err
		}
	}
	var alias matchedEvidenceAlias
	if err := json.Unmarshal(data, &alias); err != nil {
		return fmt.Errorf("decode matched_evidence: %w", err)
	}
	*e = MatchedEvidence(alias)
	return e.Validate()
}

func (e *MatchedEvidence) Validate() error {
	if err := requireV2NonBlank(e.Term, "matched_evidence.term"); err != nil {
		return err
	}
	if !evidenceOrigins[e.Origin] {
		return fmt.Errorf("matched_evidence.origin %q is invalid", e.Origin)
	}
	if !evidenceFields[e.Field] {
		return fmt.Errorf("matched_evidence.field %q is invalid", e.Field)
	}
	if math.IsNaN(e.Weight) || math.IsInf(e.Weight, 0) || e.Weight < 0 {
		return fmt.Errorf("matched_evidence.weight must be a finite non-negative number")
	}
	return nil
}

type ArticleResultV2 struct {
	ProtocolVersion  string            `json:"protocol_version"`
	TaskID           string            `json:"task_id"`
	MessageID        string            `json:"message_id"`
	Timestamp        string            `json:"timestamp"`
	Type             string            `json:"type"`
	HitID            string            `json:"hit_id"`
	PlanID           string            `json:"plan_id"`
	OriginalQuery    string            `json:"original_query"`
	QueryTerm        string            `json:"query_term"`
	RequestedURL     string            `json:"requested_url"`
	FinalURL         string            `json:"final_url"`
	CanonicalURL     string            `json:"canonical_url"`
	Title            string            `json:"title"`
	PublishDate      string            `json:"publish_date"`
	Source           string            `json:"source"`
	Summary          string            `json:"summary"`
	Content          string            `json:"content"`
	ContentHash      string            `json:"content_hash"`
	Score            int               `json:"score"`
	MatchedEvidence  []MatchedEvidence `json:"matched_evidence"`
	Status           string            `json:"status"`
	ExtractionMethod string            `json:"extraction_method"`
}

type articleResultV2Alias ArticleResultV2

func (m ArticleResultV2) MarshalJSON() ([]byte, error) {
	if m.MatchedEvidence == nil {
		m.MatchedEvidence = []MatchedEvidence{}
	}
	return marshalJSONNoEscape(articleResultV2Alias(m))
}

func (m *ArticleResultV2) UnmarshalJSON(data []byte) error {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		return fmt.Errorf("decode article_result fields: %w", err)
	}
	if err := rejectUnknownFields(fields, v2ArticleFields); err != nil {
		return err
	}
	for _, key := range []string{
		"protocol_version", "task_id", "message_id", "timestamp", "type", "hit_id",
		"plan_id", "original_query", "query_term", "requested_url", "final_url",
		"source", "score", "matched_evidence", "status", "extraction_method",
	} {
		if err := requireV2Field(fields, key); err != nil {
			return err
		}
	}
	for key := range v2ArticleFields {
		if err := rejectNullField(fields, key); err != nil {
			return err
		}
	}
	var alias articleResultV2Alias
	if err := json.Unmarshal(data, &alias); err != nil {
		return fmt.Errorf("decode article_result: %w", err)
	}
	*m = ArticleResultV2(alias)
	if m.MatchedEvidence == nil {
		m.MatchedEvidence = []MatchedEvidence{}
	}
	return m.Validate()
}

func (m *ArticleResultV2) Validate() error {
	if m.ProtocolVersion != VersionV2 {
		return fmt.Errorf("article_result protocol_version must be %q", VersionV2)
	}
	if m.Type != TypeArticleResultV2 {
		return fmt.Errorf("article_result type must be %q", TypeArticleResultV2)
	}
	for _, field := range []struct{ value, name string }{
		{m.HitID, "hit_id"}, {m.PlanID, "plan_id"}, {m.OriginalQuery, "original_query"},
		{m.QueryTerm, "query_term"}, {m.Source, "source"},
	} {
		if err := requireV2NonBlank(field.value, field.name); err != nil {
			return err
		}
	}
	if err := ValidateTargetURL(m.RequestedURL); err != nil {
		return err
	}
	if err := ValidateTargetURL(m.FinalURL); err != nil {
		return err
	}
	if err := validateOptionalAbsoluteURL(m.CanonicalURL, "canonical_url"); err != nil {
		return err
	}
	if m.Score < 0 {
		return fmt.Errorf("article_result score must be a non-negative integer")
	}
	if m.Content != "" {
		sum := sha256.Sum256([]byte(m.Content))
		expected := hex.EncodeToString(sum[:])
		if m.ContentHash != expected {
			return fmt.Errorf("article_result content_hash must be the SHA-256 of content")
		}
	} else if m.ContentHash != "" {
		return fmt.Errorf("article_result content_hash must be empty when content is empty")
	}
	if !articleResultStatuses[m.Status] {
		return fmt.Errorf("article_result status %q is invalid", m.Status)
	}
	if !extractionMethods[m.ExtractionMethod] {
		return fmt.Errorf("article_result extraction_method %q is invalid", m.ExtractionMethod)
	}
	return nil
}

func DecodeV2ArticleMessage(data []byte) (any, error) {
	var header struct {
		ProtocolVersion string `json:"protocol_version"`
		Type            string `json:"type"`
	}
	if err := json.Unmarshal(data, &header); err != nil {
		return nil, fmt.Errorf("decode v2 article header: %w", err)
	}
	if header.ProtocolVersion != VersionV2 {
		return nil, fmt.Errorf("v2 article protocol_version must be %q", VersionV2)
	}
	switch header.Type {
	case TypeURLV2:
		var msg URLMessageV2
		if err := json.Unmarshal(data, &msg); err != nil {
			return nil, err
		}
		return &msg, nil
	case TypeHTMLV2:
		var msg HTMLMessageV2
		if err := json.Unmarshal(data, &msg); err != nil {
			return nil, err
		}
		return &msg, nil
	case TypeArticleResultV2:
		var msg ArticleResultV2
		if err := json.Unmarshal(data, &msg); err != nil {
			return nil, err
		}
		return &msg, nil
	default:
		return nil, fmt.Errorf("unknown v2 article message type %q", header.Type)
	}
}
