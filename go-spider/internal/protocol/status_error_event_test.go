package protocol

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"testing"
)

type fixtureStatus struct {
	Domain             string `json:"domain"`
	CanonicalSymbol    string `json:"canonical_symbol"`
	WireValue          string `json:"wire_value"`
	Type               string `json:"type"`
	Terminal           bool   `json:"terminal"`
	NormativeSource    string `json:"normative_source"`
	CompatibilityClass string `json:"compatibility_class"`
	Semantics          string `json:"semantics"`
}

type fixtureError struct {
	CanonicalCode      string `json:"canonical_code"`
	Retryability       string `json:"retryability"`
	HTTPStatus         *int   `json:"http_status"`
	ClientExposable    bool   `json:"client_exposable"`
	NormativeSource    string `json:"normative_source"`
	Namespace          string `json:"namespace"`
	Meaning            string `json:"meaning"`
	CompatibilityClass string `json:"compatibility_class"`
}

type fixtureEvent struct {
	EventType            string  `json:"event_type"`
	Family               string  `json:"family"`
	Transport            string  `json:"transport"`
	Version              string  `json:"version"`
	Producer             string  `json:"producer"`
	Consumer             string  `json:"consumer"`
	NormativeSource      string  `json:"normative_source"`
	PayloadContractOwner string  `json:"payload_contract_owner"`
	PersistenceTarget    *string `json:"persistence_target"`
	CompatibilityClass   string  `json:"compatibility_class"`
}

type fixtureAlias struct {
	Legacy         string `json:"legacy"`
	Target         string `json:"target"`
	Classification string `json:"classification"`
	Source         string `json:"source"`
}

type fixtureDecision struct {
	ID           string `json:"id"`
	Decision     string `json:"decision"`
	Source       string `json:"source"`
	CurrentValue string `json:"current_value"`
	TargetValue  string `json:"target_value"`
	Scope        string `json:"scope"`
	WorkPackage  string `json:"work_package"`
}

type fixtureFile struct {
	ContractVersion        string                `json:"contract_version"`
	BaselineBundle         fixtureBaselineBundle `json:"baseline_bundle"`
	Statuses               []fixtureStatus       `json:"statuses"`
	Errors                 []fixtureError        `json:"errors"`
	Events                 []fixtureEvent        `json:"events"`
	LegacyAliases          []fixtureAlias        `json:"legacy_aliases"`
	CompatibilityDecisions []fixtureDecision     `json:"compatibility_decisions"`
}

type fixtureBaselineBundle struct {
	V10 fixtureBaseline `json:"v1_0"`
	V11 fixtureBaseline `json:"v1_1"`
}

type fixtureBaseline struct {
	File   string `json:"file"`
	Bytes  int    `json:"bytes"`
	SHA256 string `json:"sha256"`
}

func loadDictionaryFixture(t *testing.T) fixtureFile {
	t.Helper()
	path := filepath.Join("..", "..", "..", "tests", "fixtures", "status_error_event_dictionary_v1.json")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	var fixture fixtureFile
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&fixture); err != nil {
		t.Fatalf("decode fixture: %v", err)
	}
	if decoder.More() {
		t.Fatalf("fixture contains trailing JSON value")
	}
	return fixture
}

func uniqueCount(values []string) int {
	set := map[string]struct{}{}
	for _, value := range values {
		set[value] = struct{}{}
	}
	return len(set)
}

func TestStatusErrorEventDictionaryFixtureUniqueness(t *testing.T) {
	fixture := loadDictionaryFixture(t)

	statusKeys := make([]string, 0, len(fixture.Statuses))
	for _, item := range fixture.Statuses {
		statusKeys = append(statusKeys, item.Domain+"\x00"+item.CanonicalSymbol)
	}
	if len(statusKeys) != uniqueCount(statusKeys) {
		t.Fatalf("duplicate status key")
	}

	errorKeys := make([]string, 0, len(fixture.Errors))
	for _, item := range fixture.Errors {
		errorKeys = append(errorKeys, item.CanonicalCode)
	}
	if len(errorKeys) != uniqueCount(errorKeys) {
		t.Fatalf("duplicate error code")
	}

	eventKeys := make([]string, 0, len(fixture.Events))
	for _, item := range fixture.Events {
		eventKeys = append(eventKeys, item.Family+"\x00"+item.Version+"\x00"+item.EventType)
	}
	if len(eventKeys) != uniqueCount(eventKeys) {
		t.Fatalf("duplicate event key")
	}

	aliasKeys := make([]string, 0, len(fixture.LegacyAliases))
	for _, item := range fixture.LegacyAliases {
		aliasKeys = append(aliasKeys, item.Legacy)
	}
	if len(aliasKeys) != uniqueCount(aliasKeys) {
		t.Fatalf("duplicate legacy alias")
	}

	decisionKeys := make([]string, 0, len(fixture.CompatibilityDecisions))
	for _, item := range fixture.CompatibilityDecisions {
		decisionKeys = append(decisionKeys, item.ID)
	}
	if len(decisionKeys) != uniqueCount(decisionKeys) {
		t.Fatalf("duplicate compatibility decision")
	}
}

func TestStatusErrorEventDictionaryDuplicateNegativeCases(t *testing.T) {
	fixture := loadDictionaryFixture(t)

	dupStatus := fixture.Statuses[0]
	dupStatus.WireValue = "DIFFERENT_WIRE"
	if reflect.DeepEqual(dupStatus, fixture.Statuses[0]) {
		t.Fatalf("status duplicate not meaningfully different")
	}
	statusKeys := []string{fixture.Statuses[0].Domain + "\x00" + fixture.Statuses[0].CanonicalSymbol, dupStatus.Domain + "\x00" + dupStatus.CanonicalSymbol}

	dupError := fixture.Errors[0]
	dupError.Retryability = "ALWAYS"
	if reflect.DeepEqual(dupError, fixture.Errors[0]) {
		t.Fatalf("error duplicate not meaningfully different")
	}
	errorKeys := []string{fixture.Errors[0].CanonicalCode, dupError.CanonicalCode}

	dupEvent := fixture.Events[0]
	dupEvent.Producer = "different_producer"
	if reflect.DeepEqual(dupEvent, fixture.Events[0]) {
		t.Fatalf("event duplicate not meaningfully different")
	}
	eventKeys := []string{
		fixture.Events[0].Family + "\x00" + fixture.Events[0].Version + "\x00" + fixture.Events[0].EventType,
		dupEvent.Family + "\x00" + dupEvent.Version + "\x00" + dupEvent.EventType,
	}

	dupAlias := fixture.LegacyAliases[0]
	dupAlias.Target = "different_target"
	if reflect.DeepEqual(dupAlias, fixture.LegacyAliases[0]) {
		t.Fatalf("alias duplicate not meaningfully different")
	}
	aliasKeys := []string{fixture.LegacyAliases[0].Legacy, dupAlias.Legacy}

	dupDecision := fixture.CompatibilityDecisions[0]
	dupDecision.Decision = "different decision"
	if reflect.DeepEqual(dupDecision, fixture.CompatibilityDecisions[0]) {
		t.Fatalf("decision duplicate not meaningfully different")
	}
	decisionKeys := []string{fixture.CompatibilityDecisions[0].ID, dupDecision.ID}

	tests := []struct {
		name       string
		keys       []string
		wantUnique int
	}{
		{"status", statusKeys, 1},
		{"error", errorKeys, 1},
		{"event", eventKeys, 1},
		{"alias", aliasKeys, 1},
		{"decision", decisionKeys, 1},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if uniqueCount(tt.keys) != tt.wantUnique {
				t.Fatalf("duplicate %s not detected", tt.name)
			}
		})
	}
}

func TestStatusErrorEventDictionaryStatusMetadata(t *testing.T) {
	fixture := loadDictionaryFixture(t)
	expectedByDomain := map[string]map[string]struct{}{}
	for _, item := range fixture.Statuses {
		if item.Domain == "" || item.CanonicalSymbol == "" || item.WireValue == "" ||
			item.Type == "" || item.NormativeSource == "" || item.CompatibilityClass == "" {
			t.Fatalf("empty status metadata: %+v", item)
		}
		if expectedByDomain[item.Domain] == nil {
			expectedByDomain[item.Domain] = map[string]struct{}{}
		}
		expectedByDomain[item.Domain][item.WireValue] = struct{}{}
	}
	for domain, expected := range expectedByDomain {
		actual := StatusDomainValues(domain)
		if len(actual) != len(expected) {
			t.Fatalf("domain %s count mismatch", domain)
		}
		for _, value := range actual {
			if _, ok := expected[value]; !ok {
				t.Fatalf("domain %s extra value %q", domain, value)
			}
		}
	}
}

func TestStatusErrorEventDictionaryErrorMetadataAndCounts(t *testing.T) {
	fixture := loadDictionaryFixture(t)
	if len(fixture.Errors) != 63 {
		t.Fatalf("error count %d", len(fixture.Errors))
	}
	counts := map[string]int{}
	for _, item := range fixture.Errors {
		if item.Retryability == "" || item.NormativeSource == "" {
			t.Fatalf("empty error metadata")
		}
		counts[item.Retryability]++
		if item.HTTPStatus != nil && (*item.HTTPStatus < 100 || *item.HTTPStatus > 599) {
			t.Fatalf("invalid http status")
		}
		if item.ClientExposable && item.HTTPStatus == nil {
			t.Fatalf("client exposable error missing http status")
		}
	}
	if counts["NEVER"] != 46 || counts["ALWAYS"] != 8 || counts["CONDITIONAL"] != 9 {
		t.Fatalf("retryability counts: %v", counts)
	}
}

func TestStatusErrorEventDictionaryScenarioErrorMetadata(t *testing.T) {
	fixture := loadDictionaryFixture(t)
	if fixture.ContractVersion != "1.2" {
		t.Fatalf("contract version %q", fixture.ContractVersion)
	}
	byCode := map[string]fixtureError{}
	for _, item := range fixture.Errors {
		byCode[item.CanonicalCode] = item
	}
	for code, wantStatus := range map[string]int{
		"validation_error":      400,
		"task_limit_exceeded":   422,
		"event_history_expired": 410,
		"over_limit":            429,
		"export_expired":        410,
	} {
		item, ok := byCode[code]
		if !ok {
			t.Fatalf("missing canonical error %s", code)
		}
		if !item.ClientExposable || item.Namespace == "" || item.CompatibilityClass != "CANONICAL" {
			t.Fatalf("metadata mismatch for %s: %+v", code, item)
		}
		if item.HTTPStatus == nil || *item.HTTPStatus != wantStatus {
			t.Fatalf("http status mismatch for %s: %+v", code, item)
		}
	}
	if len(fixture.CompatibilityDecisions) != 6 {
		t.Fatalf("compatibility decision count %d", len(fixture.CompatibilityDecisions))
	}
}

func TestStatusErrorEventDictionaryEventMetadataAndCounts(t *testing.T) {
	fixture := loadDictionaryFixture(t)
	if len(fixture.Events) != 27 {
		t.Fatalf("event count %d", len(fixture.Events))
	}
	counts := map[string]int{}
	for _, item := range fixture.Events {
		if item.Family == "" || item.Transport == "" || item.Version == "" ||
			item.Producer == "" || item.Consumer == "" || item.NormativeSource == "" ||
			item.PayloadContractOwner == "" {
			t.Fatalf("empty event metadata")
		}
		counts[item.Family]++
	}
	expected := map[string]int{"TASK_EVENT": 7, "STREAM_MESSAGE": 11, "AUDIT_EVENT": 1, "CONTROL_EVENT": 4, "OPERATIONAL_EVENT": 4}
	for family, count := range expected {
		if counts[family] != count {
			t.Fatalf("family %s count %d want %d", family, counts[family], count)
		}
	}
	for _, item := range fixture.Events {
		if item.Family == "AUDIT_EVENT" {
			if item.PersistenceTarget == nil || *item.PersistenceTarget != "mysql_audit_log" {
				t.Fatalf("audit event persistence target mismatch: %+v", item)
			}
			if item.EventType != "global_block_legal_request_activated" ||
				item.Producer != "go_api" || item.Consumer != "go_api" ||
				item.Transport != "in_process" || item.PayloadContractOwner != "DEV-004" ||
				item.NormativeSource != "V1.1 10.3" {
				t.Fatalf("audit event metadata mismatch: %+v", item)
			}
		} else if item.PersistenceTarget != nil {
			t.Fatalf("non-audit event must not carry persistence_target: %+v", item)
		}
	}
}

func TestStatusErrorEventDictionaryPersistenceAndTransportNegative(t *testing.T) {
	fixture := loadDictionaryFixture(t)
	audit := fixture.Events[0]
	control := fixture.Events[0]
	task := fixture.Events[0]
	for _, item := range fixture.Events {
		switch item.Family {
		case "AUDIT_EVENT":
			audit = item
		case "CONTROL_EVENT":
			control = item
		case "TASK_EVENT":
			task = item
		}
	}

	controlValue := control
	controlValue.PersistenceTarget = strPtr("mysql_audit_log")
	if persistenceTargetError(controlValue) == "" {
		t.Fatalf("control event with persistence_target was accepted")
	}

	taskValue := task
	taskValue.PersistenceTarget = strPtr("some_target")
	if persistenceTargetError(taskValue) == "" {
		t.Fatalf("task event with persistence_target was accepted")
	}

	missingAudit := audit
	missingAudit.PersistenceTarget = nil
	if persistenceTargetError(missingAudit) == "" {
		t.Fatalf("audit event missing persistence_target was accepted")
	}

	unknownAudit := audit
	unknownAudit.PersistenceTarget = strPtr("unknown_target")
	if persistenceTargetError(unknownAudit) == "" {
		t.Fatalf("audit event with unknown persistence_target was accepted")
	}

	if !validTransport("SSE") || validTransport("sse") {
		t.Fatalf("transport case sensitivity mismatch")
	}
	lowerSSE := task
	lowerSSE.Transport = "sse"
	if validTransport(lowerSSE.Transport) {
		t.Fatalf("lowercase sse accepted")
	}
}

func persistenceTargetError(item fixtureEvent) string {
	if item.Family == "AUDIT_EVENT" {
		if item.PersistenceTarget == nil {
			return "audit persistence_target missing"
		}
		if *item.PersistenceTarget != "mysql_audit_log" {
			return "audit persistence_target invalid"
		}
		return ""
	}
	if item.PersistenceTarget != nil {
		return "non-audit persistence_target forbidden"
	}
	return ""
}

func validTransport(transport string) bool {
	switch transport {
	case "SSE", "redis_stream", "internal_control", "in_process":
		return true
	default:
		return false
	}
}

func strPtr(value string) *string {
	return &value
}

func TestStatusErrorEventDictionaryGoEnumsMatchFixture(t *testing.T) {
	fixture := loadDictionaryFixture(t)
	expectedEvents := map[string]struct{}{}
	for _, item := range fixture.Events {
		expectedEvents[item.EventType] = struct{}{}
	}
	actualEvents := sortedSet(EventTypeValues())
	if len(actualEvents) != len(expectedEvents) {
		t.Fatalf("event count mismatch fixture=%d go=%d", len(expectedEvents), len(actualEvents))
	}
	for _, value := range actualEvents {
		if _, ok := expectedEvents[value]; !ok {
			t.Fatalf("extra event %q", value)
		}
	}

	expectedErrors := map[string]struct{}{}
	for _, item := range fixture.Errors {
		expectedErrors[item.CanonicalCode] = struct{}{}
	}
	actualErrors := sortedSet(ErrorCodeValues())
	if len(actualErrors) != len(expectedErrors) {
		t.Fatalf("error count mismatch fixture=%d go=%d", len(expectedErrors), len(actualErrors))
	}
	for _, value := range actualErrors {
		if _, ok := expectedErrors[value]; !ok {
			t.Fatalf("extra error %q", value)
		}
	}

	if EventType(EventGlobalBlockLegalRequestActivated) != "global_block_legal_request_activated" {
		t.Fatalf("audit event constant mismatch")
	}
}

func sortedSet(values []string) []string {
	out := append([]string(nil), values...)
	sort.Strings(out)
	return out
}
