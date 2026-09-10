package protocol

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"math/big"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const (
	V3Version                = "3.0"
	CapacityControlVersion   = "1.0"
	MaxArtifactBytes         = 20 * 1024 * 1024
	MaxAttemptNo             = 4294967295
	MaxScore                 = 4294967295
	MaxLevel                 = 4294967295
	MaxStateVersion          = 9007199254740991
	MaxEmergencyReserveBytes = 9007199254740991
)

type StreamCodeError struct {
	Code string
	Msg  string
}

func (e *StreamCodeError) Error() string {
	return e.Code + ": " + e.Msg
}

func streamCodeError(code, msg string) error {
	return &StreamCodeError{Code: code, Msg: msg}
}

func streamCodeOf(err error) string {
	var target *StreamCodeError
	if errors.As(err, &target) {
		return target.Code
	}
	return ""
}

var (
	ulidPattern            = regexp.MustCompile(`^[0-7][0-9A-HJKMNP-TV-Z]{25}$`)
	messageIDPattern       = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$`)
	associationIDPattern   = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`)
	idempotencyPattern     = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$`)
	lowerHex64Pattern      = regexp.MustCompile(`^[a-f0-9]{64}$`)
	datePattern            = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)
	contentTypePattern     = regexp.MustCompile(`^[^/\s]+/[^/\s]+$`)
	artifactSegmentPattern = regexp.MustCompile(`^[A-Za-z0-9._:-]+$`)
	drivePrefixPattern     = regexp.MustCompile(`^[A-Za-z]:`)
)

var v3StreamByType = map[string]string{
	"search_requested": "crawler:search",
	"url":              "crawler:url",
	"html":             "crawler:html",
	"result":           "crawler:result",
	"error":            "crawler:error",
}

var v3WorkClassByType = map[string]string{
	"search_requested": "ROOT",
	"url":              "ROOT",
	"html":             "CONTINUATION",
	"result":           "CONTINUATION",
	"error":            "TERMINAL",
}

var v3RootFields = map[string]bool{
	"protocol_version": true,
	"type":             true,
	"event_id":         true,
	"message_id":       true,
	"task_id":          true,
	"aggregate_id":     true,
	"idempotency_key":  true,
	"causation_id":     true,
	"correlation_id":   true,
	"attempt_no":       true,
	"timestamp":        true,
	"work_class":       true,
	"payload":          true,
}

var v3RootRequired = []string{
	"protocol_version", "type", "event_id", "message_id", "task_id",
	"idempotency_key", "correlation_id", "attempt_no", "timestamp",
	"work_class", "payload",
}

type V3Envelope struct {
	ProtocolVersion string  `json:"protocol_version"`
	Type            string  `json:"type"`
	EventID         string  `json:"event_id"`
	MessageID       string  `json:"message_id"`
	TaskID          string  `json:"task_id"`
	AggregateID     *string `json:"aggregate_id,omitempty"`
	IdempotencyKey  string  `json:"idempotency_key"`
	CausationID     *string `json:"causation_id,omitempty"`
	CorrelationID   string  `json:"correlation_id"`
	AttemptNo       uint64  `json:"attempt_no"`
	Timestamp       string  `json:"timestamp"`
	WorkClass       string  `json:"work_class"`
}

type SearchRequestedPayload struct {
	TargetURL string   `json:"target_url"`
	Keywords  []string `json:"keywords"`
	Level     uint64   `json:"level"`
	MaxPages  uint64   `json:"max_pages"`
}

type URLPayload struct {
	HitID         string `json:"hit_id"`
	PlanID        string `json:"plan_id"`
	OriginalQuery string `json:"original_query"`
	QueryTerm     string `json:"query_term"`
	URL           string `json:"url"`
	Title         string `json:"title"`
	Snippet       string `json:"snippet"`
	PublishedAt   string `json:"published_at"`
	Source        string `json:"source"`
	Level         uint64 `json:"level"`
}

type HTMLPayload struct {
	HitID         string `json:"hit_id"`
	PlanID        string `json:"plan_id"`
	OriginalQuery string `json:"original_query"`
	QueryTerm     string `json:"query_term"`
	RequestedURL  string `json:"requested_url"`
	FinalURL      string `json:"final_url"`
	Title         string `json:"title"`
	Snippet       string `json:"snippet"`
	PublishedAt   string `json:"published_at"`
	Source        string `json:"source"`
	Level         uint64 `json:"level"`
	ArtifactRef   string `json:"artifact_ref"`
	Checksum      string `json:"checksum"`
	ContentType   string `json:"content_type"`
	ByteSize      uint64 `json:"byte_size"`
}

type MatchedEvidenceV3 struct {
	Term   string  `json:"term"`
	Origin string  `json:"origin"`
	Field  string  `json:"field"`
	Weight float64 `json:"weight"`
}

type ResultPayload struct {
	HitID            string              `json:"hit_id"`
	PlanID           string              `json:"plan_id"`
	OriginalQuery    string              `json:"original_query"`
	QueryTerm        string              `json:"query_term"`
	RequestedURL     string              `json:"requested_url"`
	FinalURL         string              `json:"final_url"`
	CanonicalURL     string              `json:"canonical_url"`
	Title            string              `json:"title"`
	PublishDate      string              `json:"publish_date"`
	Source           string              `json:"source"`
	Summary          string              `json:"summary"`
	Content          string              `json:"content"`
	ContentHash      string              `json:"content_hash"`
	Score            uint64              `json:"score"`
	MatchedEvidence  []MatchedEvidenceV3 `json:"matched_evidence"`
	Status           string              `json:"status"`
	ExtractionMethod string              `json:"extraction_method"`
}

type ErrorPayload struct {
	Stage     string `json:"stage"`
	Site      string `json:"site"`
	Keyword   string `json:"keyword"`
	Level     uint64 `json:"level"`
	URL       string `json:"url"`
	ErrorCode string `json:"error_code"`
	Error     string `json:"error"`
	Retryable bool   `json:"retryable"`
}

type V3Message struct {
	Envelope V3Envelope
	Payload  any
}

type CapacityStateV1 struct {
	ProtocolVersion       string `json:"protocol_version"`
	EventType             string `json:"event_type"`
	State                 string `json:"state"`
	StateVersion          uint64 `json:"state_version"`
	EmergencyReserveBytes uint64 `json:"emergency_reserve_bytes"`
	EffectiveAt           string `json:"effective_at"`
}

func requireFields(fields map[string]json.RawMessage, required []string, label string) error {
	for _, field := range required {
		if _, ok := fields[field]; !ok {
			return streamCodeError("INVALID_MESSAGE", label+" missing required field "+field)
		}
		if string(fields[field]) == "null" {
			return streamCodeError("INVALID_MESSAGE", label+"."+field+" must not be null")
		}
	}
	return nil
}

func rejectNull(fields map[string]json.RawMessage, keys []string, label string) error {
	for _, key := range keys {
		if raw, ok := fields[key]; ok && string(raw) == "null" {
			return streamCodeError("INVALID_MESSAGE", label+"."+key+" must not be null")
		}
	}
	return nil
}

func rejectUnknownWithName(fields map[string]json.RawMessage, allowed map[string]bool, label string) error {
	for key := range fields {
		if !allowed[key] {
			return streamCodeError("UNKNOWN_FIELD", label+" contains unknown field "+key)
		}
	}
	return nil
}

func decodeString(fields map[string]json.RawMessage, key string) (string, error) {
	raw, ok := fields[key]
	if !ok {
		return "", streamCodeError("INVALID_MESSAGE", key+" is required")
	}
	var value string
	if err := json.Unmarshal(raw, &value); err != nil {
		return "", streamCodeError("INVALID_MESSAGE", key+" must be a string")
	}
	return value, nil
}

func decodeOptionalString(fields map[string]json.RawMessage, key string) (*string, error) {
	raw, ok := fields[key]
	if !ok {
		return nil, nil
	}
	var value string
	if err := json.Unmarshal(raw, &value); err != nil {
		return nil, streamCodeError("INVALID_MESSAGE", key+" must be a string")
	}
	return &value, nil
}

func decodeNonBlankString(fields map[string]json.RawMessage, key string) (string, error) {
	value, err := decodeString(fields, key)
	if err != nil {
		return "", err
	}
	if strings.TrimSpace(value) == "" {
		return "", streamCodeError("INVALID_MESSAGE", key+" must not be blank")
	}
	return value, nil
}

func parseJSONRat(raw string) (*big.Rat, bool) {
	text := strings.TrimSpace(raw)
	if text == "" {
		return nil, false
	}
	negative := false
	if text[0] == '-' {
		negative = true
		text = text[1:]
	} else if text[0] == '+' {
		return nil, false
	}
	parts := strings.SplitN(text, "e", 2)
	if len(parts) == 1 {
		parts = strings.SplitN(text, "E", 2)
	}
	mantissa := parts[0]
	exponent := 0
	if len(parts) == 2 {
		parsedExp, err := strconv.Atoi(parts[1])
		if err != nil {
			return nil, false
		}
		exponent = parsedExp
	}
	intPart := mantissa
	fracPart := ""
	if dot := strings.IndexByte(mantissa, '.'); dot >= 0 {
		intPart = mantissa[:dot]
		fracPart = mantissa[dot+1:]
		if strings.IndexByte(fracPart, '.') >= 0 {
			return nil, false
		}
	}
	digits := intPart + fracPart
	if digits == "" {
		return nil, false
	}
	for _, r := range digits {
		if r < '0' || r > '9' {
			return nil, false
		}
	}
	scale := exponent - len(fracPart)
	numerator := new(big.Int)
	if _, ok := numerator.SetString(digits, 10); !ok {
		return nil, false
	}
	denominator := big.NewInt(1)
	if scale >= 0 {
		numerator.Mul(numerator, pow10(scale))
	} else {
		denominator = pow10(-scale)
	}
	if negative {
		numerator.Neg(numerator)
	}
	return new(big.Rat).SetFrac(numerator, denominator), true
}

func pow10(n int) *big.Int {
	value := big.NewInt(1)
	ten := big.NewInt(10)
	for i := 0; i < n; i++ {
		value.Mul(value, ten)
	}
	return value
}

func decodeInt(fields map[string]json.RawMessage, key string, minimum, maximum uint64) (uint64, error) {
	raw, ok := fields[key]
	if !ok {
		return 0, streamCodeError("INVALID_MESSAGE", key+" is required")
	}
	rat, valid := parseJSONRat(string(raw))
	if !valid {
		return 0, streamCodeError("INVALID_INTEGER", key+" must be a finite JSON number")
	}
	if !rat.IsInt() {
		return 0, streamCodeError("INVALID_INTEGER", key+" must be a mathematical integer")
	}
	num := rat.Num()
	if !num.IsUint64() {
		return 0, streamCodeError("INVALID_INTEGER", key+" is outside the exact integer range")
	}
	value := num.Uint64()
	if value < minimum {
		return 0, streamCodeError("INVALID_INTEGER", key+" must be >= "+fmt.Sprint(minimum))
	}
	if value > maximum {
		return 0, streamCodeError("INVALID_INTEGER", key+" must be <= "+fmt.Sprint(maximum))
	}
	return value, nil
}

func decodeBool(fields map[string]json.RawMessage, key string) (bool, error) {
	raw, ok := fields[key]
	if !ok {
		return false, streamCodeError("INVALID_MESSAGE", key+" is required")
	}
	var value bool
	if err := json.Unmarshal(raw, &value); err != nil {
		return false, streamCodeError("INVALID_BOOLEAN", key+" must be a boolean")
	}
	return value, nil
}

func decodeTimestamp(fields map[string]json.RawMessage, key string) (string, error) {
	value, err := decodeString(fields, key)
	if err != nil {
		return "", err
	}
	if _, err := time.Parse(time.RFC3339, value); err != nil {
		return "", streamCodeError("INVALID_MESSAGE", key+" must be RFC3339 UTC")
	}
	return value, nil
}

func decodeDateOrEmpty(fields map[string]json.RawMessage, key string) (string, error) {
	value, err := decodeString(fields, key)
	if err != nil {
		return "", err
	}
	if value != "" && !datePattern.MatchString(value) {
		return "", streamCodeError("INVALID_MESSAGE", key+" must be YYYY-MM-DD or empty")
	}
	return value, nil
}

func decodeURL(fields map[string]json.RawMessage, key string, allowEmpty bool) (string, error) {
	value, err := decodeString(fields, key)
	if err != nil {
		return "", err
	}
	if allowEmpty && value == "" {
		return "", nil
	}
	if err := ValidateTargetURL(value); err != nil {
		return "", streamCodeError("INVALID_TARGET_URL", key+": "+err.Error())
	}
	return value, nil
}

func decodeArray(raw json.RawMessage, label string) ([]json.RawMessage, error) {
	var values []json.RawMessage
	if err := json.Unmarshal(raw, &values); err != nil {
		return nil, streamCodeError("INVALID_MESSAGE", label+" must be an array")
	}
	return values, nil
}

func decodeFloat(fields map[string]json.RawMessage, key string) (float64, error) {
	raw, ok := fields[key]
	if !ok {
		return 0, streamCodeError("INVALID_MESSAGE", key+" is required")
	}
	rat, valid := parseJSONRat(string(raw))
	if !valid {
		return 0, streamCodeError("INVALID_MESSAGE", key+" must be a finite JSON number")
	}
	if rat.Sign() < 0 {
		return 0, streamCodeError("INVALID_MESSAGE", key+" must be finite and non-negative")
	}
	value, _ := rat.Float64()
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return 0, streamCodeError("INVALID_MESSAGE", key+" must be finite and non-negative")
	}
	return value, nil
}

func decodeEnvelope(fields map[string]json.RawMessage) (V3Envelope, error) {
	var env V3Envelope
	if err := requireFields(fields, v3RootRequired, "v3 envelope"); err != nil {
		return env, err
	}
	if err := rejectNull(fields, []string{
		"protocol_version", "type", "event_id", "message_id", "task_id",
		"aggregate_id", "idempotency_key", "causation_id", "correlation_id",
		"attempt_no", "timestamp", "work_class", "payload",
	}, "v3 envelope"); err != nil {
		return env, err
	}
	var err error
	env.ProtocolVersion, err = decodeString(fields, "protocol_version")
	if err != nil {
		return env, err
	}
	if env.ProtocolVersion != V3Version {
		return env, streamCodeError("UNKNOWN_PROTOCOL_VERSION", "protocol_version must be 3.0")
	}
	env.Type, err = decodeNonBlankString(fields, "type")
	if err != nil {
		return env, err
	}
	if _, ok := v3StreamByType[env.Type]; !ok {
		return env, streamCodeError("INVALID_TYPE", env.Type+" is not a v3 stream type")
	}
	env.EventID, err = decodeString(fields, "event_id")
	if err != nil {
		return env, err
	}
	if !ulidPattern.MatchString(env.EventID) {
		return env, streamCodeError("INVALID_MESSAGE", "event_id must be a canonical ULID")
	}
	env.MessageID, err = decodeString(fields, "message_id")
	if err != nil {
		return env, err
	}
	if !messageIDPattern.MatchString(env.MessageID) {
		return env, streamCodeError("INVALID_MESSAGE", "message_id has invalid format")
	}
	env.TaskID, err = decodeString(fields, "task_id")
	if err != nil {
		return env, err
	}
	if !ulidPattern.MatchString(env.TaskID) {
		return env, streamCodeError("INVALID_MESSAGE", "task_id must be a canonical ULID")
	}
	if env.AggregateID, err = decodeOptionalString(fields, "aggregate_id"); err != nil {
		return env, err
	}
	if env.AggregateID != nil && !ulidPattern.MatchString(*env.AggregateID) {
		return env, streamCodeError("INVALID_MESSAGE", "aggregate_id must be a canonical ULID")
	}
	env.IdempotencyKey, err = decodeString(fields, "idempotency_key")
	if err != nil {
		return env, err
	}
	if !idempotencyPattern.MatchString(env.IdempotencyKey) {
		return env, streamCodeError("INVALID_MESSAGE", "idempotency_key has invalid format")
	}
	if env.CausationID, err = decodeOptionalString(fields, "causation_id"); err != nil {
		return env, err
	}
	if env.CausationID != nil && !messageIDPattern.MatchString(*env.CausationID) {
		return env, streamCodeError("INVALID_MESSAGE", "causation_id has invalid format")
	}
	env.CorrelationID, err = decodeString(fields, "correlation_id")
	if err != nil {
		return env, err
	}
	if !associationIDPattern.MatchString(env.CorrelationID) {
		return env, streamCodeError("INVALID_MESSAGE", "correlation_id has invalid format")
	}
	env.AttemptNo, err = decodeInt(fields, "attempt_no", 0, MaxAttemptNo)
	if err != nil {
		return env, err
	}
	env.Timestamp, err = decodeTimestamp(fields, "timestamp")
	if err != nil {
		return env, err
	}
	env.WorkClass, err = decodeString(fields, "work_class")
	if err != nil {
		return env, err
	}
	if env.WorkClass != v3WorkClassByType[env.Type] {
		return env, streamCodeError("INVALID_MESSAGE", "work_class does not match v3 message type")
	}
	return env, nil
}

func validResultStatus(value string) bool {
	switch value {
	case "accepted", "review_required", "irrelevant", "extract_failed", "unsupported_format":
		return true
	}
	return false
}

func validExtractionMethod(value string) bool {
	switch value {
	case "site_selector", "cms_rule", "ai", "density", "fallback", "pdf", "docx", "xlsx", "none":
		return true
	}
	return false
}

func canonicalErrorCode(value string) bool {
	for _, code := range ErrorCodeValues() {
		if code == value {
			return true
		}
	}
	return false
}

func decodePayloadByType(msgType string, payloadRaw json.RawMessage) (any, error) {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(payloadRaw, &fields); err != nil {
		return nil, streamCodeError("INVALID_MESSAGE", "payload must be a JSON object")
	}
	switch msgType {
	case "search_requested":
		allowed := map[string]bool{"target_url": true, "keywords": true, "level": true, "max_pages": true}
		if err := rejectUnknownWithName(fields, allowed, "payload"); err != nil {
			return nil, err
		}
		if err := requireFields(fields, []string{"target_url", "keywords", "level", "max_pages"}, "payload"); err != nil {
			return nil, err
		}
		targetURL, err := decodeURL(fields, "target_url", false)
		if err != nil {
			return nil, err
		}
		items, err := decodeArray(fields["keywords"], "keywords")
		if err != nil {
			return nil, err
		}
		if len(items) == 0 || len(items) > 20 {
			return nil, streamCodeError("EMPTY_KEYWORDS", "keywords must be non-empty and at most 20")
		}
		keywords := make([]string, 0, len(items))
		for _, item := range items {
			if string(item) == "null" {
				return nil, streamCodeError("INVALID_MESSAGE", "keywords item must not be null")
			}
			var keyword string
			if err := json.Unmarshal(item, &keyword); err != nil {
				return nil, streamCodeError("INVALID_MESSAGE", "keywords item must not be null")
			}
			if strings.TrimSpace(keyword) == "" {
				return nil, streamCodeError("INVALID_MESSAGE", "keywords item must be a non-blank string")
			}
			keywords = append(keywords, keyword)
		}
		level, err := decodeInt(fields, "level", 0, MaxLevel)
		if err != nil {
			return nil, err
		}
		maxPages, err := decodeInt(fields, "max_pages", 1, 100)
		if err != nil {
			return nil, err
		}
		if maxPages > 100 {
			return nil, streamCodeError("INVALID_INTEGER", "max_pages must be <= 100")
		}
		return &SearchRequestedPayload{TargetURL: targetURL, Keywords: keywords, Level: level, MaxPages: maxPages}, nil
	case "url":
		allowed := map[string]bool{
			"hit_id": true, "plan_id": true, "original_query": true, "query_term": true,
			"url": true, "title": true, "snippet": true, "published_at": true,
			"source": true, "level": true,
		}
		if err := rejectUnknownWithName(fields, allowed, "payload"); err != nil {
			return nil, err
		}
		if err := requireFields(fields, []string{
			"hit_id", "plan_id", "original_query", "query_term", "url", "title",
			"snippet", "published_at", "source", "level",
		}, "payload"); err != nil {
			return nil, err
		}
		hit, err := decodeNonBlankString(fields, "hit_id")
		if err != nil {
			return nil, err
		}
		plan, err := decodeNonBlankString(fields, "plan_id")
		if err != nil {
			return nil, err
		}
		original, err := decodeNonBlankString(fields, "original_query")
		if err != nil {
			return nil, err
		}
		term, err := decodeNonBlankString(fields, "query_term")
		if err != nil {
			return nil, err
		}
		urlValue, err := decodeURL(fields, "url", false)
		if err != nil {
			return nil, err
		}
		title, err := decodeString(fields, "title")
		if err != nil {
			return nil, err
		}
		snippet, err := decodeString(fields, "snippet")
		if err != nil {
			return nil, err
		}
		published, err := decodeDateOrEmpty(fields, "published_at")
		if err != nil {
			return nil, err
		}
		source, err := decodeNonBlankString(fields, "source")
		if err != nil {
			return nil, err
		}
		level, err := decodeInt(fields, "level", 0, MaxLevel)
		if err != nil {
			return nil, err
		}
		return &URLPayload{HitID: hit, PlanID: plan, OriginalQuery: original, QueryTerm: term, URL: urlValue, Title: title, Snippet: snippet, PublishedAt: published, Source: source, Level: level}, nil
	case "html":
		allowed := map[string]bool{
			"hit_id": true, "plan_id": true, "original_query": true, "query_term": true,
			"requested_url": true, "final_url": true, "title": true, "snippet": true,
			"published_at": true, "source": true, "level": true, "artifact_ref": true,
			"checksum": true, "content_type": true, "byte_size": true,
		}
		if err := rejectUnknownWithName(fields, allowed, "payload"); err != nil {
			return nil, err
		}
		if err := requireFields(fields, []string{
			"hit_id", "plan_id", "original_query", "query_term", "requested_url",
			"final_url", "title", "snippet", "published_at", "source", "level",
			"artifact_ref", "checksum", "content_type", "byte_size",
		}, "payload"); err != nil {
			return nil, err
		}
		hit, err := decodeNonBlankString(fields, "hit_id")
		if err != nil {
			return nil, err
		}
		plan, err := decodeNonBlankString(fields, "plan_id")
		if err != nil {
			return nil, err
		}
		original, err := decodeNonBlankString(fields, "original_query")
		if err != nil {
			return nil, err
		}
		term, err := decodeNonBlankString(fields, "query_term")
		if err != nil {
			return nil, err
		}
		requested, err := decodeURL(fields, "requested_url", false)
		if err != nil {
			return nil, err
		}
		finalURL, err := decodeURL(fields, "final_url", false)
		if err != nil {
			return nil, err
		}
		title, err := decodeString(fields, "title")
		if err != nil {
			return nil, err
		}
		snippet, err := decodeString(fields, "snippet")
		if err != nil {
			return nil, err
		}
		published, err := decodeDateOrEmpty(fields, "published_at")
		if err != nil {
			return nil, err
		}
		source, err := decodeNonBlankString(fields, "source")
		if err != nil {
			return nil, err
		}
		level, err := decodeInt(fields, "level", 0, MaxLevel)
		if err != nil {
			return nil, err
		}
		artifactRef, err := decodeNonBlankString(fields, "artifact_ref")
		if err != nil {
			return nil, err
		}
		segments := strings.Split(artifactRef, "/")
		for _, segment := range segments {
			if !artifactSegmentPattern.MatchString(segment) {
				return nil, streamCodeError("INVALID_PATH", "artifact_ref must be an internal relative object key")
			}
		}
		for _, segment := range segments {
			if segment == "." || segment == ".." {
				return nil, streamCodeError("INVALID_PATH", "artifact_ref must not contain . or .. path segments")
			}
		}
		if drivePrefixPattern.MatchString(segments[0]) {
			return nil, streamCodeError("INVALID_PATH", "artifact_ref must be an internal content-addressed reference")
		}
		checksum, err := decodeString(fields, "checksum")
		if err != nil {
			return nil, err
		}
		if !lowerHex64Pattern.MatchString(checksum) {
			return nil, streamCodeError("INVALID_MESSAGE", "checksum must be lowercase SHA-256 hex")
		}
		contentType, err := decodeString(fields, "content_type")
		if err != nil {
			return nil, err
		}
		if !contentTypePattern.MatchString(contentType) {
			return nil, streamCodeError("INVALID_MESSAGE", "content_type must be a valid media type")
		}
		byteSize, err := decodeInt(fields, "byte_size", 0, MaxArtifactBytes)
		if err != nil {
			return nil, err
		}
		if byteSize > MaxArtifactBytes {
			return nil, streamCodeError("INVALID_MESSAGE", "byte_size exceeds detail artifact limit")
		}
		return &HTMLPayload{
			HitID: hit, PlanID: plan, OriginalQuery: original, QueryTerm: term,
			RequestedURL: requested, FinalURL: finalURL, Title: title, Snippet: snippet,
			PublishedAt: published, Source: source, Level: level, ArtifactRef: artifactRef,
			Checksum: checksum, ContentType: contentType, ByteSize: byteSize,
		}, nil
	case "result":
		allowed := map[string]bool{
			"hit_id": true, "plan_id": true, "original_query": true, "query_term": true,
			"requested_url": true, "final_url": true, "canonical_url": true, "title": true,
			"publish_date": true, "source": true, "summary": true, "content": true,
			"content_hash": true, "score": true, "matched_evidence": true, "status": true,
			"extraction_method": true,
		}
		if err := rejectUnknownWithName(fields, allowed, "payload"); err != nil {
			return nil, err
		}
		if err := requireFields(fields, []string{
			"hit_id", "plan_id", "original_query", "query_term", "requested_url",
			"final_url", "canonical_url", "title", "publish_date", "source", "summary",
			"content", "content_hash", "score", "matched_evidence", "status",
			"extraction_method",
		}, "payload"); err != nil {
			return nil, err
		}
		hit, err := decodeNonBlankString(fields, "hit_id")
		if err != nil {
			return nil, err
		}
		plan, err := decodeNonBlankString(fields, "plan_id")
		if err != nil {
			return nil, err
		}
		original, err := decodeNonBlankString(fields, "original_query")
		if err != nil {
			return nil, err
		}
		term, err := decodeNonBlankString(fields, "query_term")
		if err != nil {
			return nil, err
		}
		requested, err := decodeURL(fields, "requested_url", false)
		if err != nil {
			return nil, err
		}
		finalURL, err := decodeURL(fields, "final_url", false)
		if err != nil {
			return nil, err
		}
		canonical, err := decodeURL(fields, "canonical_url", true)
		if err != nil {
			return nil, err
		}
		title, err := decodeString(fields, "title")
		if err != nil {
			return nil, err
		}
		publishDate, err := decodeDateOrEmpty(fields, "publish_date")
		if err != nil {
			return nil, err
		}
		source, err := decodeNonBlankString(fields, "source")
		if err != nil {
			return nil, err
		}
		summary, err := decodeString(fields, "summary")
		if err != nil {
			return nil, err
		}
		content, err := decodeString(fields, "content")
		if err != nil {
			return nil, err
		}
		contentHash, err := decodeString(fields, "content_hash")
		if err != nil {
			return nil, err
		}
		if content != "" {
			sum := sha256.Sum256([]byte(content))
			if contentHash != hex.EncodeToString(sum[:]) {
				return nil, streamCodeError("INVALID_MESSAGE", "content_hash must be SHA-256 of content")
			}
		} else if contentHash != "" {
			return nil, streamCodeError("INVALID_MESSAGE", "content_hash must be empty when content is empty")
		}
		score, err := decodeInt(fields, "score", 0, MaxScore)
		if err != nil {
			return nil, err
		}
		evidence := make([]MatchedEvidenceV3, 0)
		evidenceItems, err := decodeArray(fields["matched_evidence"], "matched_evidence")
		if err != nil {
			return nil, err
		}
		for _, itemRaw := range evidenceItems {
			var item map[string]json.RawMessage
			if err := json.Unmarshal(itemRaw, &item); err != nil {
				return nil, streamCodeError("INVALID_MESSAGE", "matched_evidence item must be an object")
			}
			evidenceAllowed := map[string]bool{"term": true, "origin": true, "field": true, "weight": true}
			if err := rejectUnknownWithName(item, evidenceAllowed, "matched_evidence"); err != nil {
				return nil, err
			}
			if err := requireFields(item, []string{"term", "origin", "field", "weight"}, "matched_evidence"); err != nil {
				return nil, err
			}
			termValue, err := decodeNonBlankString(item, "term")
			if err != nil {
				return nil, err
			}
			originValue, err := decodeString(item, "origin")
			if err != nil {
				return nil, err
			}
			fieldValue, err := decodeString(item, "field")
			if err != nil {
				return nil, err
			}
			weight, err := decodeFloat(item, "weight")
			if err != nil {
				return nil, err
			}
			if originValue != "original" && originValue != "expanded" {
				return nil, streamCodeError("INVALID_MESSAGE", "matched_evidence.origin is invalid")
			}
			if fieldValue != "title" && fieldValue != "summary" && fieldValue != "content" && fieldValue != "url" {
				return nil, streamCodeError("INVALID_MESSAGE", "matched_evidence.field is invalid")
			}
			evidence = append(evidence, MatchedEvidenceV3{Term: termValue, Origin: originValue, Field: fieldValue, Weight: weight})
		}
		status, err := decodeString(fields, "status")
		if err != nil {
			return nil, err
		}
		method, err := decodeString(fields, "extraction_method")
		if err != nil {
			return nil, err
		}
		if !validResultStatus(status) || !validExtractionMethod(method) {
			return nil, streamCodeError("INVALID_MESSAGE", "result status or extraction_method is invalid")
		}
		return &ResultPayload{
			HitID: hit, PlanID: plan, OriginalQuery: original, QueryTerm: term,
			RequestedURL: requested, FinalURL: finalURL, CanonicalURL: canonical,
			Title: title, PublishDate: publishDate, Source: source, Summary: summary,
			Content: content, ContentHash: contentHash, Score: score,
			MatchedEvidence: evidence, Status: status, ExtractionMethod: method,
		}, nil
	case "error":
		allowed := map[string]bool{
			"stage": true, "site": true, "keyword": true, "level": true, "url": true,
			"error_code": true, "error": true, "retryable": true,
		}
		if err := rejectUnknownWithName(fields, allowed, "payload"); err != nil {
			return nil, err
		}
		if err := requireFields(fields, []string{"stage", "site", "keyword", "level", "url", "error_code", "error", "retryable"}, "payload"); err != nil {
			return nil, err
		}
		stage, err := decodeString(fields, "stage")
		if err != nil {
			return nil, err
		}
		if stage != "search" && stage != "download" && stage != "parse" && stage != "store" {
			return nil, streamCodeError("INVALID_MESSAGE", "stage is invalid")
		}
		site, err := decodeNonBlankString(fields, "site")
		if err != nil {
			return nil, err
		}
		keyword, err := decodeString(fields, "keyword")
		if err != nil {
			return nil, err
		}
		level, err := decodeInt(fields, "level", 0, MaxLevel)
		if err != nil {
			return nil, err
		}
		urlValue, err := decodeString(fields, "url")
		if err != nil {
			return nil, err
		}
		errorCode, err := decodeString(fields, "error_code")
		if err != nil {
			return nil, err
		}
		if !canonicalErrorCode(errorCode) {
			return nil, streamCodeError("INVALID_MESSAGE", "error_code is not canonical")
		}
		errorText, err := decodeNonBlankString(fields, "error")
		if err != nil {
			return nil, err
		}
		retryable, err := decodeBool(fields, "retryable")
		if err != nil {
			return nil, err
		}
		return &ErrorPayload{Stage: stage, Site: site, Keyword: keyword, Level: level, URL: urlValue, ErrorCode: errorCode, Error: errorText, Retryable: retryable}, nil
	}
	return nil, streamCodeError("INVALID_TYPE", msgType+" has no payload decoder")
}

func DecodeV3Message(data []byte, stream string) (V3Message, error) {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		return V3Message{}, streamCodeError("INVALID_JSON", "v3 message is not valid JSON")
	}
	if fields == nil {
		return V3Message{}, streamCodeError("INVALID_MESSAGE", "v3 message must be a JSON object")
	}
	protocolRaw, ok := fields["protocol_version"]
	if !ok {
		return V3Message{}, streamCodeError("UNKNOWN_PROTOCOL_VERSION", "protocol_version must be 3.0")
	}
	var protocolVersion string
	if err := json.Unmarshal(protocolRaw, &protocolVersion); err != nil || protocolVersion != V3Version {
		return V3Message{}, streamCodeError("UNKNOWN_PROTOCOL_VERSION", "protocol_version must be 3.0")
	}
	if err := rejectUnknownWithName(fields, v3RootFields, "v3 envelope"); err != nil {
		return V3Message{}, err
	}
	env, err := decodeEnvelope(fields)
	if err != nil {
		return V3Message{}, err
	}
	if v3StreamByType[env.Type] != stream {
		return V3Message{}, streamCodeError("INVALID_TYPE", env.Type+" is not valid on stream "+stream)
	}
	payload, err := decodePayloadByType(env.Type, fields["payload"])
	if err != nil {
		return V3Message{}, err
	}
	return V3Message{Envelope: env, Payload: payload}, nil
}

func EncodeV3Message(message V3Message) ([]byte, error) {
	payload, err := json.Marshal(message.Payload)
	if err != nil {
		return nil, err
	}
	root := map[string]any{
		"protocol_version": message.Envelope.ProtocolVersion,
		"type":             message.Envelope.Type,
		"event_id":         message.Envelope.EventID,
		"message_id":       message.Envelope.MessageID,
		"task_id":          message.Envelope.TaskID,
		"idempotency_key":  message.Envelope.IdempotencyKey,
		"correlation_id":   message.Envelope.CorrelationID,
		"attempt_no":       message.Envelope.AttemptNo,
		"timestamp":        message.Envelope.Timestamp,
		"work_class":       message.Envelope.WorkClass,
		"payload":          json.RawMessage(payload),
	}
	if message.Envelope.AggregateID != nil {
		root["aggregate_id"] = *message.Envelope.AggregateID
	}
	if message.Envelope.CausationID != nil {
		root["causation_id"] = *message.Envelope.CausationID
	}
	return json.Marshal(root)
}

var capacityStateByEvent = map[string]string{
	"capacity_normal":   "NORMAL",
	"capacity_warning":  "WARNING",
	"capacity_blocked":  "BLOCKED",
	"stream_drain_only": "DRAIN_ONLY",
}

var capacityFields = map[string]bool{
	"protocol_version": true, "event_type": true, "state": true,
	"state_version": true, "emergency_reserve_bytes": true, "effective_at": true,
}

func DecodeCapacityState(data []byte) (CapacityStateV1, error) {
	var state CapacityStateV1
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		return state, streamCodeError("INVALID_JSON", "capacity state is not valid JSON")
	}
	if err := rejectUnknownWithName(fields, capacityFields, "capacity state"); err != nil {
		return state, err
	}
	if err := requireFields(fields, []string{"protocol_version", "event_type", "state", "state_version", "emergency_reserve_bytes", "effective_at"}, "capacity state"); err != nil {
		return state, err
	}
	var err error
	state.ProtocolVersion, err = decodeString(fields, "protocol_version")
	if err != nil {
		return state, err
	}
	if state.ProtocolVersion != CapacityControlVersion {
		return state, streamCodeError("UNKNOWN_PROTOCOL_VERSION", "capacity protocol_version must be 1.0")
	}
	state.EventType, err = decodeString(fields, "event_type")
	if err != nil {
		return state, err
	}
	expectedState, ok := capacityStateByEvent[state.EventType]
	if !ok {
		return state, streamCodeError("INVALID_TYPE", "capacity event_type is invalid")
	}
	state.State, err = decodeString(fields, "state")
	if err != nil {
		return state, err
	}
	if state.State != expectedState {
		return state, streamCodeError("INVALID_MESSAGE", "capacity event_type/state mismatch")
	}
	version, err := decodeInt(fields, "state_version", 0, MaxStateVersion)
	if err != nil {
		return state, err
	}
	if version < 1 {
		return state, streamCodeError("INVALID_MESSAGE", "state_version must be >= 1")
	}
	reserve, err := decodeInt(fields, "emergency_reserve_bytes", 0, MaxEmergencyReserveBytes)
	if err != nil {
		return state, err
	}
	if reserve < 1 {
		return state, streamCodeError("INVALID_MESSAGE", "emergency_reserve_bytes must be > 0")
	}
	state.StateVersion = version
	state.EmergencyReserveBytes = reserve
	state.EffectiveAt, err = decodeTimestamp(fields, "effective_at")
	if err != nil {
		return state, err
	}
	return state, nil
}

func EncodeCapacityState(state CapacityStateV1) ([]byte, error) {
	return json.Marshal(state)
}
