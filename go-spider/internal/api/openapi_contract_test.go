package api

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"

	"github.com/goccy/go-yaml"
)

type contractOperation struct {
	Method         string   `json:"method"`
	Path           string   `json:"path"`
	OperationID    string   `json:"operationId"`
	SuccessStatus  string   `json:"success_status"`
	MediaType      string   `json:"media_type"`
	ResponseSchema string   `json:"response_schema"`
	Errors         []string `json:"errors"`
	Security       string   `json:"security"`
	IdempotencyKey bool     `json:"idempotency_key"`
}

type operationContract struct {
	OperationCount int                 `json:"operation_count"`
	Operations     []contractOperation `json:"operations"`
}

func repoRoot(t *testing.T) string {
	t.Helper()
	dir, err := filepath.Abs(filepath.Join("..", "..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	return dir
}

func TestOpenAPIContractMatchesFixture(t *testing.T) {
	root := repoRoot(t)
	fixturePath := filepath.Join(root, "tests", "fixtures", "openapi_v1_contract.json")
	rawFixture, err := os.ReadFile(fixturePath)
	if err != nil {
		t.Fatal(err)
	}
	var fixture operationContract
	if err := json.Unmarshal(rawFixture, &fixture); err != nil {
		t.Fatal(err)
	}
	if len(fixture.Operations) != 43 {
		t.Fatalf("fixture operation count = %d", len(fixture.Operations))
	}

	specPath := filepath.Join(root, "go-spider", "openapi", "v1", "openapi.yaml")
	rawSpec, err := os.ReadFile(specPath)
	if err != nil {
		t.Fatal(err)
	}
	var doc struct {
		Paths map[string]map[string]struct {
			OperationID string                `yaml:"operationId"`
			Security    []map[string][]string `yaml:"security"`
			XSSESchemas map[string]string     `yaml:"x-sse-event-schemas"`
		} `yaml:"paths"`
		Components struct {
			Schemas map[string]any `yaml:"schemas"`
		} `yaml:"components"`
	}
	if err := yaml.Unmarshal(rawSpec, &doc); err != nil {
		t.Fatalf("openapi yaml parse: %v", err)
	}
	if len(doc.Paths) == 0 {
		t.Fatal("openapi paths empty")
	}
	seen := map[string]bool{}
	for _, op := range fixture.Operations {
		methods, ok := doc.Paths[op.Path]
		if !ok {
			t.Fatalf("missing path %s", op.Path)
		}
		got, ok := methods[op.Method]
		if !ok {
			t.Fatalf("missing method %s %s", op.Method, op.Path)
		}
		if got.OperationID != op.OperationID {
			t.Fatalf("operationId mismatch for %s %s: got %s want %s", op.Method, op.Path, got.OperationID, op.OperationID)
		}
		if seen[op.OperationID] {
			t.Fatalf("duplicate operationId %s", op.OperationID)
		}
		seen[op.OperationID] = true
		publicNoAuth := op.Path == "/bootstrap/status" || op.Path == "/bootstrap" || op.Path == "/auth/login"
		if len(got.Security) == 0 && !publicNoAuth {
			t.Fatalf("operation %s has no explicit security", op.OperationID)
		}
	}
	if doc.Components.Schemas["ULID"] == nil || doc.Components.Schemas["ErrorEnvelope"] == nil {
		t.Fatal("required component schemas missing")
	}
}

func TestSSEExtensionReferencesExist(t *testing.T) {
	root := repoRoot(t)
	specPath := filepath.Join(root, "go-spider", "openapi", "v1", "openapi.yaml")
	raw, err := os.ReadFile(specPath)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(raw), "x-sse-event-schemas:") {
		t.Fatal("missing x-sse-event-schemas")
	}
	for _, event := range []string{"task_status_changed", "stage_progress", "worker_lost", "result_persisted", "task_error", "export_finished"} {
		p := filepath.Join(root, "go-spider", "openapi", "v1", "sse", event+".schema.json")
		if _, err := os.Stat(p); err != nil {
			t.Fatalf("missing SSE schema %s: %v", event, err)
		}
	}
}

func TestOpenAPILocalRefsResolve(t *testing.T) {
	root := repoRoot(t)
	specPath := filepath.Join(root, "go-spider", "openapi", "v1", "openapi.yaml")
	raw, err := os.ReadFile(specPath)
	if err != nil {
		t.Fatal(err)
	}
	var doc map[string]any
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	components := map[string]any{}
	if c, ok := doc["components"].(map[string]any); ok {
		if s, ok := c["schemas"].(map[string]any); ok {
			components = s
		}
	}
	var walk func(any)
	walk = func(v any) {
		switch x := v.(type) {
		case map[string]any:
			if ref, ok := x["$ref"].(string); ok {
				if !strings.HasPrefix(ref, "#/components/") {
					t.Fatalf("non-local ref %s", ref)
				}
				parts := strings.Split(strings.TrimPrefix(ref, "#/components/"), "/")
				if len(parts) == 2 && parts[0] == "schemas" {
					if _, ok := components[parts[1]]; !ok {
						t.Fatalf("undefined ref schema %s", ref)
					}
				}
			}
			for _, child := range x {
				walk(child)
			}
		case []any:
			for _, child := range x {
				walk(child)
			}
		}
	}
	walk(doc)
}

func TestJSONSuccessResponsesUseConcreteDTOs(t *testing.T) {
	root := repoRoot(t)
	rawFixture, err := os.ReadFile(filepath.Join(root, "tests", "fixtures", "openapi_v1_contract.json"))
	if err != nil {
		t.Fatal(err)
	}
	var fixture operationContract
	if err := json.Unmarshal(rawFixture, &fixture); err != nil {
		t.Fatal(err)
	}
	rawSpec, err := os.ReadFile(filepath.Join(root, "go-spider", "openapi", "v1", "openapi.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var doc map[string]any
	if err := yaml.Unmarshal(rawSpec, &doc); err != nil {
		t.Fatal(err)
	}
	paths, _ := doc["paths"].(map[string]any)
	comps, _ := doc["components"].(map[string]any)
	compSchemas, _ := comps["schemas"].(map[string]any)
	for _, op := range fixture.Operations {
		if op.MediaType != "application/json" || op.ResponseSchema == "" {
			continue
		}
		methods, _ := paths[op.Path].(map[string]any)
		operation, _ := methods[op.Method].(map[string]any)
		responses, _ := operation["responses"].(map[string]any)
		resp, ok := responses[op.SuccessStatus].(map[string]any)
		if !ok {
			t.Fatalf("%s missing success response %s", op.OperationID, op.SuccessStatus)
		}
		content, _ := resp["content"].(map[string]any)
		jsonContent, ok := content["application/json"].(map[string]any)
		if !ok {
			t.Fatalf("%s JSON success missing media", op.OperationID)
		}
		schema, _ := jsonContent["schema"].(map[string]any)
		ref, ok := schema["$ref"].(string)
		if !ok || ref != "#/components/schemas/"+op.ResponseSchema {
			t.Fatalf("%s response schema ref = %v, want %s", op.OperationID, ref, op.ResponseSchema)
		}
		responseSchema, ok := compSchemas[op.ResponseSchema].(map[string]any)
		if !ok {
			t.Fatalf("%s component %s missing", op.OperationID, op.ResponseSchema)
		}
		props, _ := responseSchema["properties"].(map[string]any)
		data, _ := props["data"].(map[string]any)
		if dataRef, ok := data["$ref"].(string); !ok || dataRef == "" {
			t.Fatalf("%s data is not a concrete schema", op.OperationID)
		}
	}
}

func TestOperationErrorResponsesMatchMatrix(t *testing.T) {
	root := repoRoot(t)
	rawFixture, err := os.ReadFile(filepath.Join(root, "tests", "fixtures", "openapi_v1_contract.json"))
	if err != nil {
		t.Fatal(err)
	}
	var fixture operationContract
	if err := json.Unmarshal(rawFixture, &fixture); err != nil {
		t.Fatal(err)
	}
	rawSpec, err := os.ReadFile(filepath.Join(root, "go-spider", "openapi", "v1", "openapi.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var doc map[string]any
	if err := yaml.Unmarshal(rawSpec, &doc); err != nil {
		t.Fatal(err)
	}
	paths, _ := doc["paths"].(map[string]any)
	expected := map[string]string{
		"validation_error": "400", "unauthorized": "401", "csrf_failed": "403",
		"state_conflict": "409", "idempotency_conflict": "409", "site_not_found": "404",
		"task_not_found": "404", "not_found": "404", "already_initialized": "409",
		"invalid_credentials": "401", "token_limit_exceeded": "429", "task_limit_exceeded": "422",
		"over_limit": "429", "event_history_expired": "410", "export_expired": "410",
		"evidence_missing": "409", "evidence_hold_unavailable": "503", "dependency_not_ready": "503",
		"not_ready": "503", "export_not_supported": "422", "no_results": "404", "already_terminal": "409",
		"security_policy_rejected": "403",
	}
	for _, op := range fixture.Operations {
		methods, _ := paths[op.Path].(map[string]any)
		operation, _ := methods[op.Method].(map[string]any)
		responses, _ := operation["responses"].(map[string]any)
		for _, code := range op.Errors {
			status := expected[code]
			if _, ok := responses[status]; !ok {
				t.Fatalf("%s missing error response %s for %s", op.OperationID, status, code)
			}
		}
	}
}

func TestULIDPatternRejectsOverflowAndInvalidChars(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join(repoRoot(t), "go-spider", "openapi", "v1", "openapi.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(raw), `[0-7][0-9A-HJKMNP-TV-Z]{25}$`) {
		t.Fatal("ULID canonical pattern not found")
	}
	valid := "01HX3Y8Z2K6N9Q4RV7T0A5BCDE"
	max := "7ZZZZZZZZZZZZZZZZZZZZZZZZZ"
	invalid := []string{"8ZZZZZZZZZZZZZZZZZZZZZZZZZ", strings.ToLower(valid), "01HX3Y8Z2K6N9Q4RV7T0A5BCDI", "01HX3Y8Z2K6N9Q4RV7T0A5BC\n"}
	for _, s := range invalid {
		if regexp.MustCompile(`^[0-7][0-9A-HJKMNP-TV-Z]{25}$`).MatchString(s) {
			t.Fatalf("invalid ULID accepted: %q", s)
		}
	}
	if !regexp.MustCompile(`^[0-7][0-9A-HJKMNP-TV-Z]{25}$`).MatchString(valid) || !regexp.MustCompile(`^[0-7][0-9A-HJKMNP-TV-Z]{25}$`).MatchString(max) {
		t.Fatal("valid ULIDs rejected")
	}
}

func TestResultsPaginationAndDomainErrorsDeclared(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join(repoRoot(t), "go-spider", "openapi", "v1", "openapi.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	for _, marker := range []string{
		"x-mutually-exclusive-parameters: [page, cursor]",
		"RESULT_NEXT_CURSOR_NULL_WHEN_NO_NEXT",
		"RESULT_TOTAL_EXACT_REQUIRES_COUNTED_AT",
		"RESULT_SORT_UNIQUE_TASK_ARTICLE_ID_TAIL",
		"persisted_at, relevance_score, quality_score",
	} {
		if !strings.Contains(string(raw), marker) {
			t.Fatalf("missing results contract marker %s", marker)
		}
	}
	fixtureRaw, _ := os.ReadFile(filepath.Join(repoRoot(t), "tests", "fixtures", "openapi_v1_contract.json"))
	var fixture operationContract
	_ = json.Unmarshal(fixtureRaw, &fixture)
	for _, op := range fixture.Operations {
		if op.OperationID == "downloadExportJob" && !contains(op.Errors, "export_expired") {
			t.Fatal("downloadExportJob missing export_expired")
		}
		if op.OperationID == "streamTaskEvents" && !contains(op.Errors, "event_history_expired") {
			t.Fatal("streamTaskEvents missing event_history_expired")
		}
		if op.OperationID == "createResultReview" && !contains(op.Errors, "evidence_hold_unavailable") {
			t.Fatal("createResultReview missing evidence_hold_unavailable")
		}
	}
}

func contains(values []string, want string) bool {
	for _, v := range values {
		if v == want {
			return true
		}
	}
	return false
}

func TestLastEventIDOnlyOnStreamTaskEvents(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join(repoRoot(t), "go-spider", "openapi", "v1", "openapi.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var doc map[string]any
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	paths, _ := doc["paths"].(map[string]any)
	for path, pv := range paths {
		methods, _ := pv.(map[string]any)
		for method, opAny := range methods {
			op, _ := opAny.(map[string]any)
			opid, _ := op["operationId"].(string)
			params, _ := op["parameters"].([]any)
			hasLast := false
			for _, pAny := range params {
				p, _ := pAny.(map[string]any)
				if name, _ := p["name"].(string); name == "Last-Event-ID" {
					hasLast = true
				}
			}
			if opid == "streamTaskEvents" && !hasLast {
				t.Fatalf("streamTaskEvents missing Last-Event-ID for %s %s", method, path)
			}
			if opid != "streamTaskEvents" && hasLast {
				t.Fatalf("Last-Event-ID present on %s", opid)
			}
		}
	}
}

func TestTaskLimitsAndReviewStatus(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join(repoRoot(t), "go-spider", "openapi", "v1", "openapi.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	spec := string(raw)
	if !strings.Contains(spec, `"max_candidates":{"type":"integer","minimum":1,"maximum":10000}`) {
		t.Fatal("max_candidates must be maximum 10000")
	}
	if !strings.Contains(spec, `"max_keywords":{"type":"integer","minimum":1,"maximum":20}`) ||
		!strings.Contains(spec, `"max_pages":{"type":"integer","minimum":1,"maximum":100}`) {
		t.Fatal("TaskLimits keyword/page bounds incorrect")
	}
	// Review success must be 200 per approved P4 manifest; locate by operation.
	var doc map[string]any
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	paths, _ := doc["paths"].(map[string]any)
	reviewMethods, _ := paths["/results/{taskArticleId}/review"].(map[string]any)
	op, _ := reviewMethods["post"].(map[string]any)
	resps, _ := op["responses"].(map[string]any)
	if _, ok := resps["201"]; ok {
		t.Fatal("createResultReview must not use 201")
	}
	if _, ok := resps["200"]; !ok {
		t.Fatal("createResultReview missing 200")
	}
}

type behaviorSample struct {
	Name  string         `json:"name"`
	Rule  string         `json:"rule"`
	Valid bool           `json:"valid"`
	Data  map[string]any `json:"data"`
}

func sampleValid(s behaviorSample) bool {
	switch s.Rule {
	case "page_mode":
		_, hasCursor := s.Data["cursor"]
		page, ok := s.Data["page"].(float64)
		return ok && page >= 1 && !hasCursor
	case "cursor_mode":
		cursor, ok := s.Data["cursor"].(string)
		return ok && cursor != ""
	case "cursor_type":
		_, ok := s.Data["cursor"].(string)
		return ok
	case "page_cursor_exclusive":
		_, hasPage := s.Data["page"]
		_, hasCursor := s.Data["cursor"]
		return !(hasPage && hasCursor)
	case "sort_whitelist":
		v, ok := s.Data["sort"].(string)
		return ok && (v == "persisted_at" || v == "relevance_score" || v == "quality_score")
	case "next_cursor_terminal":
		v, ok := s.Data["next_cursor"]
		return ok && v == nil
	case "total_exact_counted_at":
		exact, _ := s.Data["total_exact"].(bool)
		_, hasCounted := s.Data["counted_at"]
		return exact || hasCounted
	case "review_alias_equality":
		current, _ := s.Data["current_review_decision"].(string)
		status, present := s.Data["review_status"]
		if !present || status == nil {
			return true
		}
		alias, _ := status.(string)
		return current == alias
	case "review_null_relation":
		hasDecision, present := s.Data["has_review_decision"].(bool)
		current, _ := s.Data["current_review_decision"]
		return !present || !hasDecision || current != nil
	}
	return false
}

func TestBehaviorSamples(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join(repoRoot(t), "tests", "fixtures", "openapi_v1_contract.json"))
	if err != nil {
		t.Fatal(err)
	}
	var doc struct {
		BehaviorSamples []behaviorSample `json:"behavior_samples"`
	}
	if err := json.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	for _, s := range doc.BehaviorSamples {
		got := sampleValid(s)
		if s.Name == "results-page-valid" || s.Name == "results-cursor-valid" {
			_, hasPage := s.Data["page"]
			_, hasCursor := s.Data["cursor"]
			exclusive := !(hasPage && hasCursor)
			if sortVal, ok := s.Data["sort"].(string); ok {
				exclusive = exclusive && (sortVal == "persisted_at" || sortVal == "relevance_score" || sortVal == "quality_score")
			}
			got = got && exclusive
		}
		if got != s.Valid {
			t.Fatalf("behavior %s expected valid=%v got %v", s.Name, s.Valid, got)
		}
	}
}

func TestAuthModesAndPolicyErrors(t *testing.T) {
	root := repoRoot(t)
	rawFixture, _ := os.ReadFile(filepath.Join(root, "tests", "fixtures", "openapi_v1_contract.json"))
	var fixture operationContract
	_ = json.Unmarshal(rawFixture, &fixture)
	specRaw, _ := os.ReadFile(filepath.Join(root, "go-spider", "openapi", "v1", "openapi.yaml"))
	var doc map[string]any
	if err := yaml.Unmarshal(specRaw, &doc); err != nil {
		t.Fatal(err)
	}
	paths, _ := doc["paths"].(map[string]any)
	for _, op := range fixture.Operations {
		methods, _ := paths[op.Path].(map[string]any)
		operation, _ := methods[op.Method].(map[string]any)
		if op.OperationID == "createSite" || op.OperationID == "updateSite" || op.OperationID == "deleteSite" || op.OperationID == "analyzeSite" || op.OperationID == "updatePlugin" {
			if op.Security != "session" {
				t.Fatalf("%s must be Session-only", op.OperationID)
			}
			if raw, ok := operation["x-required-api-token-scopes"]; ok && raw != nil {
				t.Fatalf("%s must not carry token scopes", op.OperationID)
			}
			security, _ := operation["security"].([]any)
			if len(security) != 1 {
				t.Fatalf("%s must only contain SessionCookie+Csrf", op.OperationID)
			}
		}
		if op.Security == "sessionBearer" && !contains(op.Errors, "security_policy_rejected") {
			t.Fatalf("%s missing scope policy error", op.OperationID)
		}
		if op.OperationID == "bootstrapSystem" && !contains(op.Errors, "unauthorized") {
			t.Fatal("bootstrapSystem missing bootstrap unauthorized")
		}
	}
}

func TestAuditLogAndExportBoundaries(t *testing.T) {
	root := repoRoot(t)
	raw, _ := os.ReadFile(filepath.Join(root, "go-spider", "openapi", "v1", "openapi.yaml"))
	spec := string(raw)
	if strings.Contains(spec, `"audit_log_id"`) {
		t.Fatal("public AuditLog DTO must not expose audit_log_id")
	}
	var doc map[string]any
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	comps, _ := doc["components"].(map[string]any)
	schemas, _ := comps["schemas"].(map[string]any)
	exportJob, _ := schemas["ExportJob"].(map[string]any)
	props, _ := exportJob["properties"].(map[string]any)
	statusSchema, _ := props["status"].(map[string]any)
	exportEnums, _ := statusSchema["enum"].([]any)
	foundExpired := false
	for _, v := range exportEnums {
		if v == "EXPIRED" {
			foundExpired = true
		}
	}
	if !foundExpired {
		t.Fatal("ExportJob DTO must retain EXPIRED")
	}
	rawFixture, _ := os.ReadFile(filepath.Join(root, "tests", "fixtures", "openapi_v1_contract.json"))
	var fixture operationContract
	_ = json.Unmarshal(rawFixture, &fixture)
	for _, op := range fixture.Operations {
		if op.OperationID == "downloadExportJob" && !contains(op.Errors, "export_expired") {
			t.Fatal("downloadExportJob must expose export_expired/410")
		}
	}
	rawEvent, _ := os.ReadFile(filepath.Join(root, "go-spider", "openapi", "v1", "sse", "export_finished.schema.json"))
	var event map[string]any
	if err := json.Unmarshal(rawEvent, &event); err != nil {
		t.Fatal(err)
	}
	eventProps, _ := event["properties"].(map[string]any)
	status, _ := eventProps["status"].(map[string]any)
	eventEnums, _ := status["enum"].([]any)
	if len(eventEnums) != 2 || eventEnums[0] != "SUCCEEDED" || eventEnums[1] != "FAILED" {
		t.Fatal("export_finished status must be SUCCEEDED/FAILED only")
	}
}

func expectedScope(operationID string) []string {
	m := map[string][]string{
		"getDashboardOverview":   {"dashboard:read"},
		"listTasks":              {"tasks:read"},
		"getTask":                {"tasks:read"},
		"streamTaskEvents":       {"tasks:read"},
		"createTask":             {"tasks:write"},
		"suggestTaskScope":       {"tasks:write"},
		"confirmTask":            {"tasks:write"},
		"cancelTask":             {"tasks:write"},
		"retryTask":              {"tasks:write"},
		"listResults":            {"results:read"},
		"getResult":              {"results:read"},
		"downloadResultEvidence": {"results:read"},
		"listResultReviews":      {"results:read"},
		"listExportJobs":         {"exports:read"},
		"getExportJob":           {"exports:read"},
		"downloadExportJob":      {"exports:read"},
		"createExportJob":        {"exports:write"},
		"listSites":              {"sites:read"},
		"getSite":                {"sites:read"},
		"listPlugins":            {"plugins:read"},
	}
	return m[operationID]
}

type contractDiagnostic struct {
	Category  string
	Operation string
	Status    string
	Code      string
}

var knownStatus = map[string]string{
	"validation_error": "400", "unauthorized": "401", "csrf_failed": "403",
	"security_policy_rejected": "403", "state_conflict": "409", "idempotency_conflict": "409",
	"site_not_found": "404", "task_not_found": "404", "not_found": "404",
	"already_initialized": "409", "invalid_credentials": "401", "token_limit_exceeded": "429",
	"task_limit_exceeded": "422", "over_limit": "429", "event_history_expired": "410",
	"export_expired": "410", "evidence_missing": "409", "evidence_hold_unavailable": "503",
	"dependency_not_ready": "503", "not_ready": "503", "export_not_supported": "422",
	"no_results": "404", "already_terminal": "409",
}

func opFromPaths(doc map[string]any, path, method string) (map[string]any, bool) {
	paths, _ := doc["paths"].(map[string]any)
	pathMap, ok := paths[path].(map[string]any)
	if !ok {
		return nil, false
	}
	op, ok := pathMap[method].(map[string]any)
	return op, ok
}

func securityHasCsrf(op map[string]any) bool {
	security, ok := op["security"].([]any)
	if !ok {
		return false
	}
	for _, a := range security {
		req, ok := a.(map[string]any)
		if !ok {
			continue
		}
		_, hasSession := req["SessionCookie"]
		_, hasCsrf := req["CsrfHeader"]
		if hasSession && hasCsrf {
			return true
		}
	}
	return false
}

func actualCodesForStatus(doc map[string]any, path, method, status string) ([]string, bool) {
	op, ok := opFromPaths(doc, path, method)
	if !ok {
		return nil, false
	}
	responses, _ := op["responses"].(map[string]any)
	response, ok := responses[status].(map[string]any)
	if !ok {
		return nil, false
	}
	content, _ := response["content"].(map[string]any)
	jsonContent, ok := content["application/json"].(map[string]any)
	if !ok {
		return nil, false
	}
	schema, _ := jsonContent["schema"].(map[string]any)
	ref, _ := schema["$ref"].(string)
	if ref == "" {
		return nil, false
	}
	return derivedEnum(doc, ref[strings.LastIndex(ref, "/")+1:])
}

func fixtureErrorsByStatus(op contractOperation) (map[string][]string, []contractDiagnostic) {
	out := map[string][]string{}
	var problems []contractDiagnostic
	for _, code := range op.Errors {
		st := knownStatus[code]
		if st == "" {
			problems = append(problems, contractDiagnostic{Category: "unknown-fixture", Operation: op.OperationID, Code: code})
			continue
		}
		out[st] = append(out[st], code)
	}
	return out, problems
}

func xErrorsByStatus(op map[string]any, operationID string) (map[string][]string, []contractDiagnostic) {
	out := map[string][]string{}
	var problems []contractDiagnostic
	raw, _ := op["x-errors"].([]any)
	for _, codeAny := range raw {
		code, _ := codeAny.(string)
		st := knownStatus[code]
		if st == "" {
			problems = append(problems, contractDiagnostic{Category: "unknown-xerrors", Operation: operationID, Code: code})
			continue
		}
		out[st] = append(out[st], code)
	}
	return out, problems
}

func actualErrorsByStatus(doc map[string]any, path, method string) (map[string][]string, []contractDiagnostic) {
	out := map[string][]string{}
	var problems []contractDiagnostic
	op, ok := opFromPaths(doc, path, method)
	if !ok {
		return out, problems
	}
	responses, _ := op["responses"].(map[string]any)
	for status := range responses {
		if strings.HasPrefix(status, "2") {
			continue
		}
		codes, ok := actualCodesForStatus(doc, path, method, status)
		if !ok {
			problems = append(problems, contractDiagnostic{Category: "unresolved", Status: status})
			continue
		}
		out[status] = append(out[status], codes...)
	}
	return out, problems
}

func sameSet(a, b []string) bool {
	ma, mb := map[string]bool{}, map[string]bool{}
	for _, v := range a {
		ma[v] = true
	}
	for _, v := range b {
		mb[v] = true
	}
	if len(ma) != len(mb) {
		return false
	}
	for k := range ma {
		if !mb[k] {
			return false
		}
	}
	return true
}

func validateCSRFAndScopes(doc map[string]any) []contractDiagnostic {
	var problems []contractDiagnostic
	paths, _ := doc["paths"].(map[string]any)
	for path, pathValue := range paths {
		methods, _ := pathValue.(map[string]any)
		for method, opAny := range methods {
			op, _ := opAny.(map[string]any)
			opid, _ := op["operationId"].(string)
			if opid == "" {
				continue
			}
			want := expectedScope(opid)
			if len(want) > 0 {
				raw, ok := op["x-required-api-token-scopes"].([]any)
				if !ok || len(raw) != 1 || raw[0] != want[0] {
					problems = append(problems, contractDiagnostic{Category: "scope", Operation: opid})
					continue
				}
				codes, ok := actualCodesForStatus(doc, path, method, "403")
				if !ok || !contains(codes, "security_policy_rejected") {
					problems = append(problems, contractDiagnostic{Category: "scope403", Operation: opid, Status: "403", Code: "security_policy_rejected"})
				}
			}
			csrf := securityHasCsrf(op)
			if csrf {
				codes, ok := actualCodesForStatus(doc, path, method, "403")
				if !ok || !contains(codes, "csrf_failed") {
					problems = append(problems, contractDiagnostic{Category: "csrf", Operation: opid, Status: "403", Code: "csrf_failed"})
				}
			} else if method == "get" {
				codes, ok := actualCodesForStatus(doc, path, method, "403")
				if ok && contains(codes, "csrf_failed") {
					problems = append(problems, contractDiagnostic{Category: "csrf-get", Operation: opid, Status: "403", Code: "csrf_failed"})
				}
			}
		}
	}
	return problems
}

func validateThreeWay(doc map[string]any, fixture []contractOperation) []contractDiagnostic {
	var problems []contractDiagnostic
	paths, _ := doc["paths"].(map[string]any)
	for _, opFixture := range fixture {
		methods, ok := paths[opFixture.Path].(map[string]any)
		if !ok {
			problems = append(problems, contractDiagnostic{Category: "missing-path", Operation: opFixture.OperationID})
			continue
		}
		op, ok := methods[opFixture.Method].(map[string]any)
		if !ok {
			problems = append(problems, contractDiagnostic{Category: "missing-op", Operation: opFixture.OperationID})
			continue
		}
		fixtureMap, fixtureUnknown := fixtureErrorsByStatus(opFixture)
		xMap, xUnknown := xErrorsByStatus(op, opFixture.OperationID)
		problems = append(problems, fixtureUnknown...)
		problems = append(problems, xUnknown...)
		actualMap, resolveProblems := actualErrorsByStatus(doc, opFixture.Path, opFixture.Method)
		problems = append(problems, resolveProblems...)
		statuses := map[string]bool{}
		for st := range fixtureMap {
			statuses[st] = true
		}
		for st := range xMap {
			statuses[st] = true
		}
		for st := range actualMap {
			statuses[st] = true
		}
		for st := range statuses {
			if !sameSet(fixtureMap[st], xMap[st]) {
				problems = append(problems, contractDiagnostic{Category: "fixture-x", Operation: opFixture.OperationID, Status: st})
			}
			if !sameSet(fixtureMap[st], actualMap[st]) {
				problems = append(problems, contractDiagnostic{Category: "fixture-schema", Operation: opFixture.OperationID, Status: st})
			}
			if !sameSet(xMap[st], actualMap[st]) {
				problems = append(problems, contractDiagnostic{Category: "x-schema", Operation: opFixture.OperationID, Status: st})
			}
		}
	}
	return problems
}

func hasDiag(problems []contractDiagnostic, category, opid, status, code string) bool {
	for _, p := range problems {
		if p.Category == category && p.Operation == opid && p.Status == status && p.Code == code {
			return true
		}
	}
	return false
}

func setDerivedEnum(doc map[string]any, schemaName string, enum []any) {
	comps, _ := doc["components"].(map[string]any)
	schemas, _ := comps["schemas"].(map[string]any)
	s, _ := schemas[schemaName].(map[string]any)
	allOf, _ := s["allOf"].([]any)
	second, _ := allOf[1].(map[string]any)
	errObj, _ := second["properties"].(map[string]any)["error"].(map[string]any)
	code, _ := errObj["properties"].(map[string]any)["code"].(map[string]any)
	code["enum"] = enum
}

func TestCSRFAndThreeWayChecks(t *testing.T) {
	root := repoRoot(t)
	rawSpec, _ := os.ReadFile(filepath.Join(root, "go-spider", "openapi", "v1", "openapi.yaml"))
	var doc map[string]any
	if err := yaml.Unmarshal(rawSpec, &doc); err != nil {
		t.Fatal(err)
	}
	rawFixture, _ := os.ReadFile(filepath.Join(root, "tests", "fixtures", "openapi_v1_contract.json"))
	var fixture operationContract
	if err := json.Unmarshal(rawFixture, &fixture); err != nil {
		t.Fatal(err)
	}
	if problems := validateCSRFAndScopes(doc); len(problems) != 0 {
		t.Fatalf("correct doc csrf problems: %v", problems)
	}
	if problems := validateThreeWay(doc, fixture.Operations); len(problems) != 0 {
		t.Fatalf("correct doc three-way problems: %v", problems)
	}
	// D: remove csrf_failed from createTask 403
	mut := cloneDoc(t, doc)
	codes, _ := derivedEnum(mut, "ErrorEnvelope_createTask_403")
	kept := codes[:0]
	for _, c := range codes {
		if c != "csrf_failed" {
			kept = append(kept, c)
		}
	}
	setDerivedEnum(mut, "ErrorEnvelope_createTask_403", toAny(kept))
	if !hasDiag(validateCSRFAndScopes(mut), "csrf", "createTask", "403", "csrf_failed") {
		t.Fatal("variant D not detected")
	}
	// E: GET allows csrf_failed
	mut = cloneDoc(t, doc)
	codes, _ = derivedEnum(mut, "ErrorEnvelope_getTask_403")
	setDerivedEnum(mut, "ErrorEnvelope_getTask_403", toAny(append(codes, "csrf_failed")))
	if !hasDiag(validateCSRFAndScopes(mut), "csrf-get", "getTask", "403", "csrf_failed") {
		t.Fatal("variant E not detected")
	}
	// F1: fixture changed only
	fixtureMut := cloneFixture(fixture.Operations)
	for i := range fixtureMut {
		if fixtureMut[i].OperationID == "createTask" {
			fixtureMut[i].Errors = []string{"unauthorized", "validation_error", "site_not_found", "task_limit_exceeded", "idempotency_conflict", "csrf_failed"}
		}
	}
	if !hasDiag(validateThreeWay(doc, fixtureMut), "fixture-x", "createTask", "403", "") {
		t.Fatal("variant F1 not detected")
	}
	// F2: x-errors changed only
	mut = cloneDoc(t, doc)
	methods, _ := mut["paths"].(map[string]any)["/tasks"].(map[string]any)
	op := methods["post"].(map[string]any)
	xe, _ := op["x-errors"].([]any)
	var filtered []any
	for _, v := range xe {
		if v != "security_policy_rejected" {
			filtered = append(filtered, v)
		}
	}
	op["x-errors"] = filtered
	if !hasDiag(validateThreeWay(mut, fixture.Operations), "fixture-x", "createTask", "403", "") {
		t.Fatal("variant F2 not detected")
	}
	// F3: swap 401 and 403 response schema refs for getTask
	mut = cloneDoc(t, doc)
	paths, _ := mut["paths"].(map[string]any)
	taskPath, _ := paths["/tasks/{taskId}"].(map[string]any)
	getOp := taskPath["get"].(map[string]any)
	responses := getOp["responses"].(map[string]any)
	resp401 := responses["401"].(map[string]any)
	resp403 := responses["403"].(map[string]any)
	content401 := resp401["content"].(map[string]any)["application/json"].(map[string]any)
	content403 := resp403["content"].(map[string]any)["application/json"].(map[string]any)
	ref401 := content401["schema"].(map[string]any)["$ref"]
	ref403 := content403["schema"].(map[string]any)["$ref"]
	content401["schema"].(map[string]any)["$ref"] = ref403
	content403["schema"].(map[string]any)["$ref"] = ref401
	if !hasDiag(validateThreeWay(mut, fixture.Operations), "fixture-schema", "getTask", "401", "") {
		t.Fatal("variant F3 not detected")
	}
}

func TestUnknownErrorCodeDiagnostics(t *testing.T) {
	root := repoRoot(t)
	rawSpec, _ := os.ReadFile(filepath.Join(root, "go-spider", "openapi", "v1", "openapi.yaml"))
	var doc map[string]any
	if err := yaml.Unmarshal(rawSpec, &doc); err != nil {
		t.Fatal(err)
	}
	rawFixture, _ := os.ReadFile(filepath.Join(root, "tests", "fixtures", "openapi_v1_contract.json"))
	var fixture operationContract
	if err := json.Unmarshal(rawFixture, &fixture); err != nil {
		t.Fatal(err)
	}
	if problems := validateThreeWay(doc, fixture.Operations); len(problems) != 0 {
		t.Fatalf("original doc must pass: %v", problems)
	}
	sentinel := "b7e1_unknown_marker"
	// U1 fixture only
	fix := cloneFixture(fixture.Operations)
	for i := range fix {
		if fix[i].OperationID == "createTask" {
			fix[i].Errors = append(fix[i].Errors, sentinel)
		}
	}
	p := validateThreeWay(doc, fix)
	if !hasDiag(p, "unknown-fixture", "createTask", "", sentinel) {
		t.Fatalf("U1 not detected: %v", p)
	}
	// U2 x-errors only
	mut := cloneDoc(t, doc)
	methods, _ := mut["paths"].(map[string]any)["/tasks"].(map[string]any)
	op := methods["post"].(map[string]any)
	xe, _ := op["x-errors"].([]any)
	op["x-errors"] = append(xe, sentinel)
	p = validateThreeWay(mut, fixture.Operations)
	if !hasDiag(p, "unknown-xerrors", "createTask", "", sentinel) {
		t.Fatalf("U2 not detected: %v", p)
	}
	// U3 fixture and x-errors
	fix = cloneFixture(fixture.Operations)
	for i := range fix {
		if fix[i].OperationID == "createTask" {
			fix[i].Errors = append(fix[i].Errors, sentinel)
		}
	}
	mut = cloneDoc(t, doc)
	methods, _ = mut["paths"].(map[string]any)["/tasks"].(map[string]any)
	op = methods["post"].(map[string]any)
	xe, _ = op["x-errors"].([]any)
	op["x-errors"] = append(xe, sentinel)
	p = validateThreeWay(mut, fix)
	if !hasDiag(p, "unknown-fixture", "createTask", "", sentinel) || !hasDiag(p, "unknown-xerrors", "createTask", "", sentinel) {
		t.Fatalf("U3 not fully detected: %v", p)
	}
}

func cloneFixture(in []contractOperation) []contractOperation {
	raw, _ := json.Marshal(in)
	var out []contractOperation
	_ = json.Unmarshal(raw, &out)
	return out
}

func toAny(in []string) []any {
	out := make([]any, len(in))
	for i, v := range in {
		out[i] = v
	}
	return out
}

func cloneDoc(t *testing.T, doc map[string]any) map[string]any {
	t.Helper()
	raw, err := json.Marshal(doc)
	if err != nil {
		t.Fatal(err)
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		t.Fatal(err)
	}
	return out
}

func derivedEnum(doc map[string]any, schemaName string) ([]string, bool) {
	comps, _ := doc["components"].(map[string]any)
	schemas, _ := comps["schemas"].(map[string]any)
	s, ok := schemas[schemaName].(map[string]any)
	if !ok {
		return nil, false
	}
	allOf, ok := s["allOf"].([]any)
	if !ok || len(allOf) < 2 {
		return nil, false
	}
	second, _ := allOf[1].(map[string]any)
	props, _ := second["properties"].(map[string]any)
	errSchema, _ := props["error"].(map[string]any)
	errProps, _ := errSchema["properties"].(map[string]any)
	code, _ := errProps["code"].(map[string]any)
	enum, ok := code["enum"].([]any)
	if !ok {
		return nil, false
	}
	out := make([]string, 0, len(enum))
	for _, v := range enum {
		s, _ := v.(string)
		out = append(out, s)
	}
	return out, true
}

func bearerScopeAnd403Errors(doc map[string]any) []string {
	var problems []string
	paths, _ := doc["paths"].(map[string]any)
	comps, _ := doc["components"].(map[string]any)
	allSchemas, _ := comps["schemas"].(map[string]any)
	for _, pathValue := range paths {
		methods, _ := pathValue.(map[string]any)
		for _, opAny := range methods {
			op, _ := opAny.(map[string]any)
			opid, _ := op["operationId"].(string)
			want := expectedScope(opid)
			if len(want) == 0 {
				continue
			}
			rawScopes, ok := op["x-required-api-token-scopes"].([]any)
			if !ok || len(rawScopes) == 0 {
				problems = append(problems, "missing scope: "+opid)
				continue
			}
			var got []string
			for _, v := range rawScopes {
				s, _ := v.(string)
				got = append(got, s)
			}
			if len(got) != len(want) || got[0] != want[0] {
				problems = append(problems, "wrong scope: "+opid)
			}
			responses, _ := op["responses"].(map[string]any)
			resp403, ok := responses["403"].(map[string]any)
			if !ok {
				problems = append(problems, "missing 403 response: "+opid)
				continue
			}
			content, _ := resp403["content"].(map[string]any)
			jsonContent, ok := content["application/json"].(map[string]any)
			if !ok {
				problems = append(problems, "missing json 403: "+opid)
				continue
			}
			schema, _ := jsonContent["schema"].(map[string]any)
			ref, _ := schema["$ref"].(string)
			if ref == "" {
				problems = append(problems, "403 has no schema ref: "+opid)
				continue
			}
			name := ref[strings.LastIndex(ref, "/")+1:]
			codes, ok := derivedEnum(doc, name)
			if !ok {
				problems = append(problems, "cannot resolve derived schema: "+opid)
				continue
			}
			if !contains(codes, "security_policy_rejected") {
				problems = append(problems, "403 schema missing security_policy_rejected: "+opid)
			}
			if opid == "createExportJob" && !contains(codes, "csrf_failed") {
				problems = append(problems, "mutation 403 schema missing csrf_failed: "+opid)
			}
			_ = allSchemas
		}
	}
	return problems
}

func TestBearerScopesAndDerived403Variants(t *testing.T) {
	root := repoRoot(t)
	raw, _ := os.ReadFile(filepath.Join(root, "go-spider", "openapi", "v1", "openapi.yaml"))
	var doc map[string]any
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	if problems := bearerScopeAnd403Errors(doc); len(problems) != 0 {
		t.Fatalf("correct doc rejected: %v", problems)
	}
	// A: remove security_policy_rejected from listTasks 403 derived schema
	mut := cloneDoc(t, doc)
	comps, _ := mut["components"].(map[string]any)
	schemas, _ := comps["schemas"].(map[string]any)
	sch, _ := schemas["ErrorEnvelope_listTasks_403"].(map[string]any)
	allOf, _ := sch["allOf"].([]any)
	second, _ := allOf[1].(map[string]any)
	errObj, _ := second["properties"].(map[string]any)["error"].(map[string]any)
	code, _ := errObj["properties"].(map[string]any)["code"].(map[string]any)
	code["enum"] = []any{"csrf_failed"}
	if problems := bearerScopeAnd403Errors(mut); len(problems) == 0 {
		t.Fatal("variant A not detected")
	}
	// B: remove listSites x-required
	mut = cloneDoc(t, doc)
	paths, _ := mut["paths"].(map[string]any)
	siteMethods, _ := paths["/sites"].(map[string]any)
	delete(siteMethods["get"].(map[string]any), "x-required-api-token-scopes")
	if problems := bearerScopeAnd403Errors(mut); len(problems) == 0 {
		t.Fatal("variant B not detected")
	}
	// C: wrong scope for listPlugins
	mut = cloneDoc(t, doc)
	paths, _ = mut["paths"].(map[string]any)
	pluginMethods, _ := paths["/plugins"].(map[string]any)
	pluginMethods["get"].(map[string]any)["x-required-api-token-scopes"] = []any{"tasks:read"}
	if problems := bearerScopeAnd403Errors(mut); len(problems) == 0 {
		t.Fatal("variant C not detected")
	}
}

func TestRESTEntityIDsUseCanonicalULID(t *testing.T) {
	root := repoRoot(t)
	raw, err := os.ReadFile(filepath.Join(root, "go-spider", "openapi", "v1", "openapi.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var doc map[string]any
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	comps, _ := doc["components"].(map[string]any)
	schemas, _ := comps["schemas"].(map[string]any)
	check := func(dto string, fields ...string) {
		s, ok := schemas[dto].(map[string]any)
		if !ok {
			t.Fatalf("schema %s missing", dto)
		}
		props, _ := s["properties"].(map[string]any)
		for _, field := range fields {
			p, ok := props[field].(map[string]any)
			if !ok {
				t.Fatalf("%s.%s missing", dto, field)
			}
			if p["type"] != "string" || fmt.Sprint(p["minLength"]) != "26" || fmt.Sprint(p["maxLength"]) != "26" {
				t.Fatalf("%s.%s not canonical ULID", dto, field)
			}
			if pattern, _ := p["pattern"].(string); pattern != `^[0-7][0-9A-HJKMNP-TV-Z]{25}$` {
				t.Fatalf("%s.%s has wrong pattern", dto, field)
			}
		}
	}
	check("Task", "task_id", "site_code")
	check("Result", "task_article_id", "task_id")
	check("ExportJob", "job_id")
	check("Site", "site_code")
	check("ApiToken", "token_id")
	check("Session", "admin_id", "session_id")
	check("ReviewDecision", "decision_id", "task_article_id")
	check("GlobalBlockEntry", "block_entry_id")
}
