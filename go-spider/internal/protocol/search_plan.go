package protocol

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
)

const (
	PlanStatusDraft   = "draft"
	PlanStatusReady   = "ready"
	PlanStatusActive  = "active"
	PlanStatusExpired = "expired"
)

const (
	SearchStrategyHTMLForm = "html_form"
	SearchStrategyJSONAPI  = "json_api"
	SearchStrategyRSS      = "rss"
	SearchStrategySitemap  = "sitemap"
	SearchStrategyUnknown  = "unknown"
)

type SearchPagination struct {
	MaxPages      int    `json:"max_pages"`
	PageParam     string `json:"page_param"`
	PageSizeParam string `json:"page_size_param"`
	PageSize      int    `json:"page_size"`
}

type SearchSelectors struct {
	ResultItem string `json:"result_item"`
	Title      string `json:"title"`
	URL        string `json:"url"`
	Snippet    string `json:"snippet"`
	Body       string `json:"body"`
}

type SearchScope struct {
	Domain              string   `json:"domain"`
	AllowedPathPrefixes []string `json:"allowed_path_prefixes"`
	MaxDepth            int      `json:"max_depth"`
}

type SearchDiscovery struct {
	Evidence   []string `json:"evidence"`
	Confidence int      `json:"confidence"`
	Source     string   `json:"source"`
}

type SearchPlan struct {
	PlanID              string            `json:"plan_id"`
	ProtocolVersion     string            `json:"protocol_version"`
	Status              string            `json:"status"`
	Strategy            string            `json:"strategy"`
	Endpoint            string            `json:"endpoint"`
	HTTPMethod          string            `json:"http_method"`
	QueryParams         map[string]string `json:"query_params"`
	RequestBodyTemplate string            `json:"request_body_template"`
	Pagination          SearchPagination  `json:"pagination"`
	Selectors           SearchSelectors   `json:"selectors"`
	Scope               SearchScope       `json:"scope"`
	Discovery           SearchDiscovery   `json:"discovery"`
	CreatedFrom         string            `json:"created_from"`
	CreatedAt           string            `json:"created_at"`
	ExpiresAt           string            `json:"expires_at"`
	InvalidReason       string            `json:"invalid_reason"`
}

type SearchHit struct {
	HitID           string   `json:"hit_id"`
	PlanID          string   `json:"plan_id"`
	URL             string   `json:"url"`
	Title           string   `json:"title"`
	Snippet         string   `json:"snippet"`
	PublishedAt     string   `json:"published_at"`
	Score           int      `json:"score"`
	MatchedKeywords []string `json:"matched_keywords"`
	Source          string   `json:"source"`
	DiscoveredAt    string   `json:"discovered_at"`
}

func marshalJSONNoEscape(v any) ([]byte, error) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(v); err != nil {
		return nil, err
	}
	return bytes.TrimSpace(buf.Bytes()), nil
}

type searchPlanAlias SearchPlan

func (p SearchPlan) MarshalJSON() ([]byte, error) {
	p.QueryParams = emptyStringMap(p.QueryParams)
	p.Scope.AllowedPathPrefixes = emptyStringSlice(p.Scope.AllowedPathPrefixes)
	p.Discovery.Evidence = emptyStringSlice(p.Discovery.Evidence)
	return marshalJSONNoEscape(searchPlanAlias(p))
}

func rejectNullInt(data []byte, parent, field string) error {
	var root map[string]json.RawMessage
	if err := json.Unmarshal(data, &root); err != nil {
		return err
	}
	nested := root
	if parent != "" {
		raw, ok := root[parent]
		if !ok {
			return nil
		}
		if err := json.Unmarshal(raw, &nested); err != nil {
			return nil
		}
	}
	raw, ok := nested[field]
	if !ok {
		return nil
	}
	if bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
		return fmt.Errorf("%s.%s must not be null", parent, field)
	}
	return nil
}

func (p *SearchPlan) UnmarshalJSON(data []byte) error {
	for _, intField := range [][2]string{
		{"pagination", "max_pages"},
		{"pagination", "page_size"},
		{"scope", "max_depth"},
		{"discovery", "confidence"},
	} {
		if err := rejectNullInt(data, intField[0], intField[1]); err != nil {
			return err
		}
	}
	var alias searchPlanAlias
	if err := json.Unmarshal(data, &alias); err != nil {
		return err
	}
	*p = SearchPlan(alias)
	p.QueryParams = emptyStringMap(p.QueryParams)
	p.Scope.AllowedPathPrefixes = emptyStringSlice(p.Scope.AllowedPathPrefixes)
	p.Discovery.Evidence = emptyStringSlice(p.Discovery.Evidence)
	return nil
}

type searchHitAlias SearchHit

func (h SearchHit) MarshalJSON() ([]byte, error) {
	h.MatchedKeywords = emptyStringSlice(h.MatchedKeywords)
	return marshalJSONNoEscape(searchHitAlias(h))
}

func (h *SearchHit) UnmarshalJSON(data []byte) error {
	if err := rejectNullInt(data, "", "score"); err != nil {
		return err
	}
	var alias searchHitAlias
	if err := json.Unmarshal(data, &alias); err != nil {
		return err
	}
	*h = SearchHit(alias)
	h.MatchedKeywords = emptyStringSlice(h.MatchedKeywords)
	return nil
}

func ValidateSearchPlan(p *SearchPlan) error {
	if p.ProtocolVersion != VersionV2 {
		return fmt.Errorf("search_plan protocol_version must be %q", VersionV2)
	}
	if p.PlanID == "" {
		return fmt.Errorf("search_plan plan_id is required")
	}
	if !isAllowedPlanStatus(p.Status) {
		return fmt.Errorf("search_plan status %q is not allowed", p.Status)
	}
	if !isAllowedSearchStrategy(p.Strategy) {
		return fmt.Errorf("search_plan strategy %q is not allowed", p.Strategy)
	}
	if p.HTTPMethod != "GET" && p.HTTPMethod != "POST" {
		return fmt.Errorf("search_plan http_method %q is not allowed", p.HTTPMethod)
	}
	if err := ValidateTargetURL(p.Endpoint); err != nil {
		return fmt.Errorf("search_plan endpoint: %w", err)
	}
	if p.Pagination.MaxPages < 1 {
		return fmt.Errorf("search_plan pagination.max_pages must be >= 1")
	}
	if p.Pagination.PageSize < 1 {
		return fmt.Errorf("search_plan pagination.page_size must be >= 1")
	}
	if p.Scope.Domain == "" {
		return fmt.Errorf("search_plan scope.domain is required")
	}
	if p.Scope.MaxDepth < 0 {
		return fmt.Errorf("search_plan scope.max_depth must be >= 0")
	}
	if p.Discovery.Confidence < 0 || p.Discovery.Confidence > 100 {
		return fmt.Errorf("search_plan discovery.confidence must be between 0 and 100")
	}
	return nil
}

func (h *SearchHit) Validate() error {
	if h.HitID == "" {
		return fmt.Errorf("search_hit hit_id is required")
	}
	if h.PlanID == "" {
		return fmt.Errorf("search_hit plan_id is required")
	}
	if err := ValidateTargetURL(h.URL); err != nil {
		return fmt.Errorf("search_hit url: %w", err)
	}
	return nil
}

// CanonicalPlanJSON returns the stable canonical JSON used for plan_id.
func CanonicalPlanJSON(p *SearchPlan) (string, error) {
	content := map[string]any{
		"protocol_version":      p.ProtocolVersion,
		"strategy":              p.Strategy,
		"endpoint":              p.Endpoint,
		"http_method":           p.HTTPMethod,
		"query_params":          emptyStringMap(p.QueryParams),
		"request_body_template": p.RequestBodyTemplate,
		"pagination": map[string]any{
			"max_pages":       p.Pagination.MaxPages,
			"page_param":      p.Pagination.PageParam,
			"page_size_param": p.Pagination.PageSizeParam,
			"page_size":       p.Pagination.PageSize,
		},
		"selectors": map[string]any{
			"result_item": p.Selectors.ResultItem,
			"title":       p.Selectors.Title,
			"url":         p.Selectors.URL,
			"snippet":     p.Selectors.Snippet,
			"body":        p.Selectors.Body,
		},
		"scope": map[string]any{
			"domain":                p.Scope.Domain,
			"allowed_path_prefixes": emptyStringSlice(p.Scope.AllowedPathPrefixes),
			"max_depth":             p.Scope.MaxDepth,
		},
		"discovery": map[string]any{
			"evidence":   emptyStringSlice(p.Discovery.Evidence),
			"confidence": p.Discovery.Confidence,
			"source":     p.Discovery.Source,
		},
		"created_from": p.CreatedFrom,
	}
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(content); err != nil {
		return "", fmt.Errorf("encode canonical plan content: %w", err)
	}
	return string(bytes.TrimSpace(buf.Bytes())), nil
}

// ComputePlanID hashes a stable canonical representation of the plan content.
// plan_id, status, created_at, expires_at and invalid_reason do not participate.
func ComputePlanID(p *SearchPlan) (string, error) {
	canonical, err := CanonicalPlanJSON(p)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256([]byte(canonical))
	return hex.EncodeToString(sum[:]), nil
}

func emptyStringMap(m map[string]string) map[string]string {
	if m == nil {
		return map[string]string{}
	}
	return m
}

func emptyStringSlice(values []string) []string {
	if values == nil {
		return []string{}
	}
	return values
}

func isAllowedPlanStatus(status string) bool {
	switch status {
	case PlanStatusDraft, PlanStatusReady, PlanStatusActive, PlanStatusExpired:
		return true
	default:
		return false
	}
}

func isAllowedSearchStrategy(strategy string) bool {
	switch strategy {
	case SearchStrategyHTMLForm, SearchStrategyJSONAPI, SearchStrategyRSS, SearchStrategySitemap, SearchStrategyUnknown:
		return true
	default:
		return false
	}
}
