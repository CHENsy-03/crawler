package protocol

import (
	"encoding/json"
	"reflect"
	"strings"
	"testing"
)

func TestSearchPlanRoundTrip(t *testing.T) {
	plan := newFixturePlan(t)
	data, err := json.Marshal(plan)
	if err != nil {
		t.Fatalf("marshal plan: %v", err)
	}
	var dec SearchPlan
	if err := json.Unmarshal(data, &dec); err != nil {
		t.Fatalf("unmarshal plan: %v", err)
	}
	if dec.PlanID != plan.PlanID || dec.Endpoint != plan.Endpoint || dec.Strategy != plan.Strategy {
		t.Fatalf("roundtrip mismatch: %+v", dec)
	}
	if err := ValidateSearchPlan(&dec); err != nil {
		t.Fatalf("validate: %v", err)
	}
}

func TestComputePlanIDMatchesFixture(t *testing.T) {
	plan := newFixturePlan(t)
	got, err := ComputePlanID(plan)
	if err != nil {
		t.Fatalf("compute plan id: %v", err)
	}
	fixture := loadFixture(t, v2FixturePath(t))
	expected, ok := fixture["search_plan_id"].(string)
	if !ok || got != expected {
		t.Fatalf("plan_id = %s, want %s", got, expected)
	}
}

func TestUnicodePlanCanonicalAndID(t *testing.T) {
	fixture := loadFixture(t, v2FixturePath(t))
	raw, err := json.Marshal(fixture["unicode_plan"])
	if err != nil {
		t.Fatalf("marshal unicode plan fixture: %v", err)
	}
	var plan SearchPlan
	if err := json.Unmarshal(raw, &plan); err != nil {
		t.Fatalf("unmarshal unicode plan: %v", err)
	}
	canonical, err := CanonicalPlanJSON(&plan)
	if err != nil {
		t.Fatalf("canonical json: %v", err)
	}
	expectedJSON := fixture["unicode_plan_json"].(string)
	if canonical != expectedJSON {
		t.Fatalf("canonical json mismatch:\n got %s\nwant %s", canonical, expectedJSON)
	}
	got, err := ComputePlanID(&plan)
	if err != nil {
		t.Fatalf("compute unicode plan id: %v", err)
	}
	expectedID := fixture["unicode_plan_id"].(string)
	if got != expectedID {
		t.Fatalf("unicode plan_id = %s, want %s", got, expectedID)
	}
}

func TestComputePlanIDIgnoresRuntimeFields(t *testing.T) {
	plan := newFixturePlan(t)
	base, err := ComputePlanID(plan)
	if err != nil {
		t.Fatalf("compute base plan id: %v", err)
	}
	changed := *plan
	changed.PlanID = "different"
	changed.Status = PlanStatusReady
	changed.CreatedAt = "2030-01-01T00:00:00Z"
	changed.ExpiresAt = "2030-01-01T00:00:00Z"
	changed.InvalidReason = "changed"
	got, err := ComputePlanID(&changed)
	if err != nil {
		t.Fatalf("compute changed plan id: %v", err)
	}
	if got != base {
		t.Fatalf("runtime fields changed plan_id: %s != %s", got, base)
	}
}

func TestSearchHitRoundTrip(t *testing.T) {
	fixture := loadFixture(t, v2FixturePath(t))
	raw, err := json.Marshal(fixture["search_hit"])
	if err != nil {
		t.Fatalf("marshal hit fixture: %v", err)
	}
	var hit SearchHit
	if err := json.Unmarshal(raw, &hit); err != nil {
		t.Fatalf("unmarshal hit: %v", err)
	}
	if err := hit.Validate(); err != nil {
		t.Fatalf("validate hit: %v", err)
	}
	data, err := json.Marshal(hit)
	if err != nil {
		t.Fatalf("marshal hit: %v", err)
	}
	var dec SearchHit
	if err := json.Unmarshal(data, &dec); err != nil {
		t.Fatalf("unmarshal hit: %v", err)
	}
	if dec.HitID != hit.HitID || dec.PlanID != hit.PlanID || dec.URL != hit.URL || dec.Score != hit.Score {
		t.Fatalf("hit roundtrip mismatch: %+v", dec)
	}
}

func TestEmptyCollectionsMarshalAsEmptyNotNil(t *testing.T) {
	fixture := loadFixture(t, v2FixturePath(t))

	planRaw, err := json.Marshal(fixture["empty_collections_plan"])
	if err != nil {
		t.Fatalf("marshal empty plan fixture: %v", err)
	}
	var plan SearchPlan
	if err := json.Unmarshal(planRaw, &plan); err != nil {
		t.Fatalf("unmarshal empty plan: %v", err)
	}
	planData, err := json.Marshal(plan)
	if err != nil {
		t.Fatalf("marshal normalized plan: %v", err)
	}
	var planMap map[string]any
	if err := json.Unmarshal(planData, &planMap); err != nil {
		t.Fatalf("unmarshal normalized plan: %v", err)
	}
	queryParams := planMap["query_params"].(map[string]any)
	if len(queryParams) != 0 {
		t.Fatalf("query_params = %v", queryParams)
	}
	scope := planMap["scope"].(map[string]any)
	prefixes := scope["allowed_path_prefixes"].([]any)
	if len(prefixes) != 0 {
		t.Fatalf("allowed_path_prefixes = %v", prefixes)
	}
	discovery := planMap["discovery"].(map[string]any)
	evidence := discovery["evidence"].([]any)
	if len(evidence) != 0 {
		t.Fatalf("evidence = %v", evidence)
	}

	hitRaw, err := json.Marshal(fixture["empty_collections_hit"])
	if err != nil {
		t.Fatalf("marshal empty hit fixture: %v", err)
	}
	var hit SearchHit
	if err := json.Unmarshal(hitRaw, &hit); err != nil {
		t.Fatalf("unmarshal empty hit: %v", err)
	}
	hitData, err := json.Marshal(hit)
	if err != nil {
		t.Fatalf("marshal normalized hit: %v", err)
	}
	var hitMap map[string]any
	if err := json.Unmarshal(hitData, &hitMap); err != nil {
		t.Fatalf("unmarshal normalized hit: %v", err)
	}
	matched := hitMap["matched_keywords"].([]any)
	if len(matched) != 0 {
		t.Fatalf("matched_keywords = %v", matched)
	}
}

func TestZeroValueSearchPlanDoesNotEmitNull(t *testing.T) {
	var plan SearchPlan
	data, err := json.Marshal(plan)
	if err != nil {
		t.Fatalf("marshal zero plan: %v", err)
	}
	var m map[string]any
	if err := json.Unmarshal(data, &m); err != nil {
		t.Fatalf("unmarshal zero plan: %v", err)
	}
	if !reflect.DeepEqual(m["query_params"], map[string]any{}) {
		t.Fatalf("query_params = %#v", m["query_params"])
	}
	scope := m["scope"].(map[string]any)
	if !reflect.DeepEqual(scope["allowed_path_prefixes"], []any{}) {
		t.Fatalf("allowed_path_prefixes = %#v", scope["allowed_path_prefixes"])
	}
	discovery := m["discovery"].(map[string]any)
	if !reflect.DeepEqual(discovery["evidence"], []any{}) {
		t.Fatalf("evidence = %#v", discovery["evidence"])
	}
}

func newFixturePlan(t *testing.T) *SearchPlan {
	t.Helper()
	fixture := loadFixture(t, v2FixturePath(t))
	raw, err := json.Marshal(fixture["search_plan"])
	if err != nil {
		t.Fatalf("marshal plan fixture: %v", err)
	}
	var plan SearchPlan
	if err := json.Unmarshal(raw, &plan); err != nil {
		t.Fatalf("unmarshal plan fixture: %v", err)
	}
	return &plan
}

func TestSearchPlanMarshalEscapesHTML(t *testing.T) {
	fixture := loadFixture(t, v2FixturePath(t))
	raw, err := json.Marshal(fixture["unicode_plan"])
	if err != nil {
		t.Fatalf("marshal unicode plan fixture: %v", err)
	}
	var plan SearchPlan
	if err := json.Unmarshal(raw, &plan); err != nil {
		t.Fatalf("unmarshal unicode plan: %v", err)
	}
	data, err := json.Marshal(plan)
	if err != nil {
		t.Fatalf("marshal plan: %v", err)
	}
	text := string(data)
	if !strings.Contains(text, "\\u003c") || !strings.Contains(text, "\\u003e") || !strings.Contains(text, "\\u0026") {
		t.Fatalf("HTML chars not escaped like Go default: %s", text)
	}
	if !strings.Contains(text, "低空经济") || !strings.Contains(text, "\\u2028") || !strings.Contains(text, "\\u2029") {
		t.Fatalf("unicode escaping unexpected: %s", text)
	}
}

func TestMarshalJSONNoEscapeMap(t *testing.T) {
	data, err := marshalJSONNoEscape(map[string]any{"q": "a<b>&c"})
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if strings.Contains(string(data), "\\u003c") || strings.Contains(string(data), "\\u0026") {
		t.Fatalf("map escaped: %s", string(data))
	}
}

func TestMarshalJSONNoEscapeAlias(t *testing.T) {
	data, err := marshalJSONNoEscape(searchPlanAlias(SearchPlan{
		QueryParams: map[string]string{"q": "a<b>&c"},
	}))
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if strings.Contains(string(data), "\\u003c") || strings.Contains(string(data), "\\u0026") {
		t.Fatalf("alias escaped: %s", string(data))
	}
}

func TestUnmarshalRejectsNullInts(t *testing.T) {
	fixture := loadFixture(t, v2FixturePath(t))
	for _, key := range []string{"search_plan_null_int", "search_plan_null_pagination"} {
		raw, err := json.Marshal(fixture[key])
		if err != nil {
			t.Fatalf("marshal %s: %v", key, err)
		}
		var plan SearchPlan
		if err := json.Unmarshal(raw, &plan); err == nil {
			t.Fatalf("expected null int rejection for %s", key)
		}
	}
	hitRaw, err := json.Marshal(fixture["search_hit_null_score"])
	if err != nil {
		t.Fatalf("marshal search_hit_null_score: %v", err)
	}
	var hit SearchHit
	if err := json.Unmarshal(hitRaw, &hit); err == nil {
		t.Fatal("expected null score rejection")
	}
}
