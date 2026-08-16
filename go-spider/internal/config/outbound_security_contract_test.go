package config

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"testing"
)

// This test validates the shared TASK-022E-B configuration contract fixture
// only. It must not load production config or use the production loader.
const aggregateV1Magic = "OSEC-CASE-AGGREGATE-V1\x00"
const expectedBase104V1 = "bc38711ddf559eb5319eac9b080eeec611e3742d9cf0bbdb09072317cfc975b8"
const expectedNew21V1 = "dfda4174b62f27b4132cf157e96b89be2982f9268724dc12f47ebc97c7df8850"
const expectedAll125V1 = "75336a374cd9ee82a8c811f380fd9ce6893364d65eaf0fbed76424307b2baa5b"

type rawDuplicateExpectation struct {
	Action         string
	Scenario       *string
	Reason         string
	ValidationMode string
}

func strPtr(value string) *string {
	return &value
}

var rawDuplicateCases = map[string]rawDuplicateExpectation{
	"t-017": {Action: "reject", Scenario: strPtr("malformed_json_apparent_duplicate"), Reason: "config_invalid_json", ValidationMode: "malformed_json"},
	"d-001": {Action: "marker", Scenario: nil, Reason: "config_duplicate", ValidationMode: "raw_duplicate_json"},
	"d-008": {Action: "reject", Scenario: strPtr("duplicate_json_key_invalid_type"), Reason: "config_duplicate", ValidationMode: "raw_duplicate_json"},
	"d-009": {Action: "reject", Scenario: strPtr("semantic_duplicate_invalid_type"), Reason: "config_invalid_type", ValidationMode: "policy_id_type"},
	"d-010": {Action: "reject", Scenario: strPtr("duplicate_conflict"), Reason: "config_duplicate", ValidationMode: "duplicate_port"},
}

type scenarioRegistryMeta struct {
	Action   string
	Scenario string
	Reason   string
}

var scenarioRegistry = map[string]scenarioRegistryMeta{
	"t-017": {Action: "reject", Scenario: "malformed_json_apparent_duplicate", Reason: "config_invalid_json"},
	"t-018": {Action: "reject", Scenario: "unknown_field_missing_required", Reason: "config_unknown_field"},
	"h-019": {Action: "reject", Scenario: "ip_literal_invalid_hostname", Reason: "config_forbidden_ip_literal"},
	"d-008": {Action: "reject", Scenario: "duplicate_json_key_invalid_type", Reason: "config_duplicate"},
	"d-009": {Action: "reject", Scenario: "semantic_duplicate_invalid_type", Reason: "config_invalid_type"},
	"d-010": {Action: "reject", Scenario: "duplicate_conflict", Reason: "config_duplicate"},
	"pr-006": {Action: "reference", Scenario: "unknown_policy_reference_site_host_uncovered", Reason: "config_invalid_policy_reference"},
}

type payloadTextRegistryMeta struct {
	Action          string
	ScenarioPresent bool
	Scenario        *string
	Reason          string
}

var payloadTextRegistry = map[string]payloadTextRegistryMeta{
	"t-004": {Action: "reject", ScenarioPresent: false, Scenario: nil, Reason: "config_invalid_top_level"},
	"t-005": {Action: "reject", ScenarioPresent: false, Scenario: nil, Reason: "config_invalid_top_level"},
	"t-007": {Action: "reject", ScenarioPresent: false, Scenario: nil, Reason: "config_invalid_json"},
	"t-013": {Action: "reject", ScenarioPresent: false, Scenario: nil, Reason: "config_invalid_json"},
	"t-016": {Action: "reject", ScenarioPresent: false, Scenario: nil, Reason: "config_invalid_json"},
	"t-017": {Action: "reject", ScenarioPresent: true, Scenario: strPtr("malformed_json_apparent_duplicate"), Reason: "config_invalid_json"},
	"t-018": {Action: "reject", ScenarioPresent: true, Scenario: strPtr("unknown_field_missing_required"), Reason: "config_unknown_field"},
	"d-001": {Action: "marker", ScenarioPresent: false, Scenario: nil, Reason: "config_duplicate"},
	"d-008": {Action: "reject", ScenarioPresent: true, Scenario: strPtr("duplicate_json_key_invalid_type"), Reason: "config_duplicate"},
	"pr-003": {Action: "reference", ScenarioPresent: false, Scenario: nil, Reason: "config_conflict"},
}



type configContractCase struct {
	ID                  string                 `json:"id"`
	Action              string                 `json:"action"`
	Allowed             bool                   `json:"allowed"`
	Reason              *string                `json:"reason"`
	Description         string                 `json:"description"`
	Canonical           interface{}            `json:"canonical,omitempty"`
	PayloadText         string                 `json:"payload_text,omitempty"`
	Field               string                 `json:"field,omitempty"`
	Hostname            interface{}            `json:"hostname,omitempty"`
	LoggingRule         string                 `json:"logging_rule,omitempty"`
	RawInput            string                 `json:"raw_input,omitempty"`
	ExpectedLog         map[string]interface{} `json:"expected_log,omitempty"`
	RequiredLogFields   []string               `json:"required_log_fields,omitempty"`
	ForbiddenValues     []string               `json:"forbidden_values,omitempty"`
	SourceState         string                 `json:"source_state,omitempty"`
	SourceSize          int                    `json:"source_size,omitempty"`
	Depth               int                    `json:"depth,omitempty"`
	PayloadHex          string                 `json:"payload_hex,omitempty"`
	ExpectedFieldOrder  []string               `json:"expected_field_order,omitempty"`
	ExpectedSiteOrder   []string               `json:"expected_site_order,omitempty"`
	ExpectedPolicyOrder []string               `json:"expected_policy_order,omitempty"`
	Scenario            string                 `json:"scenario,omitempty"`
}

type configSiteDraft struct {
	SiteKey           string   `json:"site_key"`
	Hosts             []string `json:"hosts"`
	Schemes           []string `json:"schemes"`
	Ports             []int    `json:"ports"`
	SuggestedPolicyID string   `json:"suggested_policy_id"`
	MultiHost         bool     `json:"multi_host"`
	HTTP              bool     `json:"http"`
	Notes             string   `json:"notes"`
}

type configContractFixture struct {
	FrozenReasons      []string                        `json:"frozen_reasons"`
	Categories         map[string][]configContractCase `json:"categories"`
	SiteMigrationDraft []configSiteDraft               `json:"site_migration_draft"`
}

func contractFixturePath(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "tests", "fixtures", "outbound_security_config_contract.json")
}

func loadConfigContractFixture(t *testing.T) configContractFixture {
	t.Helper()
	data, err := os.ReadFile(contractFixturePath(t))
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	var fixture configContractFixture
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode fixture: %v", err)
	}
	return fixture
}

func TestOutboundSecurityContractFixtureIntegrity(t *testing.T) {
	fixture := loadConfigContractFixture(t)
	expectedReasons := map[string]bool{
		"config_missing": true, "config_invalid_json": true, "config_invalid_top_level": true,
		"config_unsupported_version": true, "config_unknown_field": true, "config_missing_field": true,
		"config_invalid_type": true, "config_duplicate": true, "config_invalid_policy_id": true,
		"config_invalid_hostname": true, "config_forbidden_ip_literal": true, "config_invalid_scheme": true,
		"config_invalid_port": true, "config_invalid_policy_reference": true,
		"config_site_host_not_covered": true, "config_conflict": true,
		"config_unreadable": true, "config_limit_exceeded": true,
	}
	if len(fixture.FrozenReasons) != len(expectedReasons) {
		t.Fatalf("frozen reasons count %d != %d", len(fixture.FrozenReasons), len(expectedReasons))
	}
	reasonUsed := map[string]bool{}
	for _, category := range fixture.Categories {
		for _, c := range category {
			if c.Reason != nil {
				reasonUsed[*c.Reason] = true
			}
		}
	}
	for reason := range expectedReasons {
		if !reasonUsed[reason] {
			t.Fatalf("frozen reason %q has no replayable case", reason)
		}
	}
	if len(fixture.Categories["logging"]) != 6 {
		t.Fatalf("logging cases %d != 6", len(fixture.Categories["logging"]))
	}
	assertParameterizedCases(t, fixture)
	hostnameCases := fixture.Categories["hostname"]
	byHost := map[string]configContractCase{}
	for _, c := range hostnameCases {
		if h, ok := c.Hostname.(string); ok && h != "" && !strings.Contains(h, ".") && h != "2001:db8::1" {
			byHost[h] = c
		}
	}
	if c, ok := byHost["localhost"]; !ok || c.Reason == nil || *c.Reason != "config_invalid_hostname" {
		t.Fatalf("localhost single-label hostname not rejected")
	}
	if c, ok := byHost["example"]; !ok || c.Reason == nil || *c.Reason != "config_invalid_hostname" {
		t.Fatalf("example single-label hostname not rejected")
	}
	expectedCategories := map[string]bool{
		"valid_config": true, "top_level": true, "version": true, "policy_id": true,
		"hostname": true, "scheme": true, "port": true, "duplicate": true,
		"policy_reference": true, "site_cross_validation": true, "logging": true, "forbidden_field": true,
	}
	if len(fixture.Categories) != len(expectedCategories) {
		t.Fatalf("category count %d != %d", len(fixture.Categories), len(expectedCategories))
	}
	for category := range fixture.Categories {
		if !expectedCategories[category] {
			t.Fatalf("unexpected category %q", category)
		}
	}
	executed := map[string]bool{}
	expected := map[string]bool{}
	for _, cases := range fixture.Categories {
		for _, c := range cases {
			expected[c.ID] = true
		}
	}
	for category, cases := range fixture.Categories {
		for _, c := range cases {
			switch c.Action {
			case "accept":
				if !c.Allowed || c.Reason != nil {
					t.Fatalf("case %s invalid accept", c.ID)
				}
			case "reject", "marker":
				if c.Allowed || c.Reason == nil {
					t.Fatalf("case %s invalid reject/marker", c.ID)
				}
			case "reference", "cross_validation":
				if c.Allowed {
					if c.Reason != nil {
						t.Fatalf("case %s allowed with reason", c.ID)
					}
				} else if c.Reason == nil {
					t.Fatalf("case %s rejected without reason", c.ID)
				}
			case "logging":
				if !c.Allowed {
					t.Fatalf("case %s logging must be allowed", c.ID)
				}
				assertLoggingCase(t, c)
			case "ordering":
				if !c.Allowed || c.Reason != nil {
					t.Fatalf("case %s invalid ordering marker", c.ID)
				}
				assertOrderingCase(t, c)
			default:
				t.Fatalf("unknown action %q in %s", c.Action, c.ID)
			}
			if c.Reason != nil {
				if !expectedReasons[*c.Reason] {
					t.Fatalf("case %s reason %q not frozen", c.ID, *c.Reason)
				}
			}
			_ = category
			executed[c.ID] = true
		}
	}
	if len(executed) != len(expected) {
		t.Fatalf("executed %d != expected %d", len(executed), len(expected))
	}
	for id := range expected {
		if !executed[id] {
			t.Fatalf("case not executed: %s", id)
		}
	}
	if len(fixture.SiteMigrationDraft) != 5 {
		t.Fatalf("site draft count %d != 5", len(fixture.SiteMigrationDraft))
	}
	for _, entry := range fixture.SiteMigrationDraft {
		if entry.SiteKey == "" || len(entry.Hosts) == 0 || len(entry.Schemes) == 0 || len(entry.Ports) == 0 || entry.SuggestedPolicyID == "" {
			t.Fatalf("incomplete site draft: %+v", entry)
		}
	}
}

func TestOutboundSecurityContractForbiddenFields(t *testing.T) {
	fixture := loadConfigContractFixture(t)
	forbidden := map[string]bool{
		"allowed_subdomain_roots": true, "redirect_allowed_domains": true,
		"redirect_allowed_subdomain_roots": true, "allow_http": true,
		"allow_controlled_subdomains": true, "proxy": true, "allow_private": true,
		"insecure_tls": true, "budget_override": true, "profile_override": true,
		"credentials": true, "url": true,
	}
	for _, c := range fixture.Categories["forbidden_field"] {
		if !forbidden[c.Field] {
			t.Fatalf("unexpected forbidden field %q", c.Field)
		}
		if c.Reason == nil || *c.Reason != "config_unknown_field" {
			t.Fatalf("case %s expected config_unknown_field", c.ID)
		}
	}
}

func TestOutboundSecurityContractSchemaHostnamePattern(t *testing.T) {
	data, err := os.ReadFile(filepath.Join("..", "..", "..", "config", "outbound_security.schema.json"))
	if err != nil {
		t.Fatalf("read schema: %v", err)
	}
	var schema map[string]interface{}
	if err := json.Unmarshal(data, &schema); err != nil {
		t.Fatalf("decode schema: %v", err)
	}
	pattern := schema["properties"].(map[string]interface{})["policies"].(map[string]interface{})["items"].(map[string]interface{})["properties"].(map[string]interface{})["allowed_domains"].(map[string]interface{})["items"].(map[string]interface{})["pattern"].(string)
	re := regexp.MustCompile("^" + pattern + "$")
	for _, host := range []string{"localhost", "example", "example-.com"} {
		if re.MatchString(host) {
			t.Fatalf("single-label or invalid hostname %q matched schema pattern", host)
		}
	}
	for _, host := range []string{"example.com", "a-b.example"} {
		if !re.MatchString(host) {
			t.Fatalf("valid hostname %q rejected by schema pattern", host)
		}
	}
}

var loggingRules = map[string]bool{
	"no_raw_config": true, "no_full_url": true, "no_credentials": true,
	"allow_reason_field_path": true, "allow_policy_id_no_policy": true, "allow_hostname_no_url": true,
}

var allowedLogFields = map[string]bool{"reason": true, "field_path": true, "policy_id": true, "hostname": true}

func assertLoggingCase(t *testing.T, c configContractCase) {
	t.Helper()
	if !loggingRules[c.LoggingRule] {
		t.Fatalf("case %s unknown logging rule %q", c.ID, c.LoggingRule)
	}
	if c.RawInput == "" {
		t.Fatalf("case %s empty raw_input", c.ID)
	}
	if len(c.ExpectedLog) == 0 {
		t.Fatalf("case %s empty expected_log", c.ID)
	}
	if len(c.RequiredLogFields) == 0 {
		t.Fatalf("case %s empty required_log_fields", c.ID)
	}
	for _, value := range c.ForbiddenValues {
		if value == "" {
			t.Fatalf("case %s empty forbidden value", c.ID)
		}
		if !strings.Contains(c.RawInput, value) {
			t.Fatalf("case %s forbidden value %q not from raw_input", c.ID, value)
		}
	}
	serialized, err := json.Marshal(c.ExpectedLog)
	if err != nil {
		t.Fatalf("case %s marshal expected_log: %v", c.ID, err)
	}
	for _, value := range c.ForbiddenValues {
		if strings.Contains(string(serialized), value) {
			t.Fatalf("case %s forbidden value %q appears in expected_log", c.ID, value)
		}
	}
	for key := range c.ExpectedLog {
		if !allowedLogFields[key] {
			t.Fatalf("case %s unexpected log field %q", c.ID, key)
		}
	}
	for _, field := range c.RequiredLogFields {
		if _, ok := c.ExpectedLog[field]; !ok {
			t.Fatalf("case %s missing required log field %q", c.ID, field)
		}
	}
	if reason, ok := c.ExpectedLog["reason"]; ok {
		text, ok := reason.(string)
		if !ok {
			t.Fatalf("case %s reason not string", c.ID)
		}
		expectedReasons := map[string]bool{
			"config_missing": true, "config_invalid_json": true, "config_invalid_top_level": true,
			"config_unsupported_version": true, "config_unknown_field": true, "config_missing_field": true,
			"config_invalid_type": true, "config_duplicate": true, "config_invalid_policy_id": true,
			"config_invalid_hostname": true, "config_forbidden_ip_literal": true, "config_invalid_scheme": true,
			"config_invalid_port": true, "config_invalid_policy_reference": true,
			"config_site_host_not_covered": true, "config_conflict": true,
			"config_unreadable": true, "config_limit_exceeded": true,
		}
		if !expectedReasons[text] {
			t.Fatalf("case %s unexpected reason %q", c.ID, text)
		}
	}
	if host, ok := c.ExpectedLog["hostname"]; ok {
		text, ok := host.(string)
		if !ok {
			t.Fatalf("case %s hostname not string", c.ID)
		}
		re := regexp.MustCompile(`^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$`)
		if !re.MatchString(text) || strings.Contains(text, "://") || strings.ContainsAny(text, "/?#") {
			t.Fatalf("case %s invalid hostname %q", c.ID, text)
		}
	}
	if pid, ok := c.ExpectedLog["policy_id"]; ok {
		text, ok := pid.(string)
		if !ok {
			t.Fatalf("case %s policy_id not string", c.ID)
		}
		re := regexp.MustCompile(`^[a-z][a-z0-9_-]{0,63}$`)
		if !re.MatchString(text) {
			t.Fatalf("case %s invalid policy_id %q", c.ID, text)
		}
	}
}

func TestOutboundSecurityContractLoggingRules(t *testing.T) {
	fixture := loadConfigContractFixture(t)
	executed := map[string]bool{}
	for _, c := range fixture.Categories["logging"] {
		assertLoggingCase(t, c)
		executed[c.LoggingRule] = true
	}
	for rule := range loggingRules {
		if !executed[rule] {
			t.Fatalf("logging rule not executed: %s", rule)
		}
	}
	if len(executed) != len(loggingRules) {
		t.Fatalf("executed logging rules %d != %d", len(executed), len(loggingRules))
	}
}

func assertOrderingCase(t *testing.T, c configContractCase) {
	t.Helper()
	orders := [][]string{c.ExpectedFieldOrder, c.ExpectedSiteOrder, c.ExpectedPolicyOrder}
	found := false
	for _, order := range orders {
		if len(order) > 0 {
			found = true
			seen := map[string]bool{}
			for _, item := range order {
				if seen[item] {
					t.Fatalf("case %s duplicate order item %q", c.ID, item)
				}
				seen[item] = true
			}
		}
	}
	if !found {
		t.Fatalf("case %s ordering marker has no order list", c.ID)
	}
}

func assertParameterizedCases(t *testing.T, fixture configContractFixture) {
	t.Helper()
	byID := map[string]configContractCase{}
	for _, cases := range fixture.Categories {
		for _, c := range cases {
			byID[c.ID] = c
		}
	}
	if byID["t-011"].SourceSize != 1048577 {
		t.Fatalf("t-011 source_size %d != 1048577", byID["t-011"].SourceSize)
	}
	if byID["t-012"].Depth != 33 {
		t.Fatalf("t-012 depth %d != 33", byID["t-012"].Depth)
	}
	for _, cid := range []string{"t-014", "t-015"} {
		if byID[cid].PayloadHex == "" {
			t.Fatalf("case %s empty payload_hex", cid)
		}
		if _, err := hex.DecodeString(byID[cid].PayloadHex); err != nil {
			t.Fatalf("case %s invalid payload_hex: %v", cid, err)
		}
	}
	for _, cid := range []string{"t-008", "t-009", "t-010"} {
		state := byID[cid].SourceState
		if state != "unreadable" && state != "directory" && state != "non_regular_source" {
			t.Fatalf("case %s unexpected source_state %q", cid, state)
		}
	}
}

func loadConfigContractFixtureRaw(t *testing.T) map[string]interface{} {
	t.Helper()
	data, err := os.ReadFile(contractFixturePath(t))
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.UseNumber()
	var fixture map[string]interface{}
	if err := dec.Decode(&fixture); err != nil {
		t.Fatalf("decode raw fixture: %v", err)
	}
	return fixture
}

func rawFixtureCases(t *testing.T, fixture map[string]interface{}) (map[string]map[string]interface{}, []map[string]interface{}) {
	t.Helper()
	categories, ok := fixture["categories"].(map[string]interface{})
	if !ok {
		t.Fatalf("fixture categories not object")
	}
	byID := map[string]map[string]interface{}{}
	var all []map[string]interface{}
	for _, rawCategory := range categories {
		cases, ok := rawCategory.([]interface{})
		if !ok {
			t.Fatalf("category cases not array")
		}
		for _, item := range cases {
			rawCase, ok := item.(map[string]interface{})
			if !ok {
				t.Fatalf("case not object")
			}
			id, ok := rawCase["id"].(string)
			if !ok {
				t.Fatalf("case id not string")
			}
			byID[id] = rawCase
			all = append(all, rawCase)
		}
	}
	return byID, all
}

func canonicalCaseJSON(rawCase map[string]interface{}) ([]byte, error) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(rawCase); err != nil {
		return nil, err
	}
	return bytes.TrimSuffix(buf.Bytes(), []byte("\n")), nil
}

func aggregateV1(t *testing.T, rawCases []map[string]interface{}) string {
	t.Helper()
	type record struct {
		id      string
		idBytes []byte
		digest  [sha256.Size]byte
	}
	records := make([]record, 0, len(rawCases))
	for _, rawCase := range rawCases {
		id, ok := rawCase["id"].(string)
		if !ok {
			t.Fatalf("case id not string")
		}
		canonical, err := canonicalCaseJSON(rawCase)
		if err != nil {
			t.Fatalf("canonical case %s: %v", id, err)
		}
		records = append(records, record{id: id, idBytes: []byte(id), digest: sha256.Sum256(canonical)})
	}
	sort.Slice(records, func(i, j int) bool {
		return bytes.Compare(records[i].idBytes, records[j].idBytes) < 0
	})
	var stream bytes.Buffer
	stream.WriteString(aggregateV1Magic)
	if err := binary.Write(&stream, binary.BigEndian, uint32(len(records))); err != nil {
		t.Fatalf("write count: %v", err)
	}
	for _, r := range records {
		if err := binary.Write(&stream, binary.BigEndian, uint32(len(r.idBytes))); err != nil {
			t.Fatalf("write id length: %v", err)
		}
		stream.Write(r.idBytes)
		stream.Write(r.digest[:])
	}
	sum := sha256.Sum256(stream.Bytes())
	return hex.EncodeToString(sum[:])
}

func cloneRawCases(src []map[string]interface{}) []map[string]interface{} {
	out := make([]map[string]interface{}, len(src))
	for i, rawCase := range src {
		cloned := make(map[string]interface{}, len(rawCase))
		for k, v := range rawCase {
			cloned[k] = v
		}
		out[i] = cloned
	}
	return out
}

func fixtureString(t *testing.T, fixture map[string]interface{}, key string) string {
	t.Helper()
	value, ok := fixture[key].(string)
	if !ok {
		t.Fatalf("fixture field %q not string", key)
	}
	return value
}

func TestOutboundSecurityContractAggregateV1(t *testing.T) {
	fixture := loadConfigContractFixtureRaw(t)
	if algorithm := fixtureString(t, fixture, "algorithm"); algorithm != "OSEC-CASE-AGGREGATE-V1" {
		t.Fatalf("unknown aggregate algorithm %q", algorithm)
	}
	byID, all := rawFixtureCases(t, fixture)
	if len(all) != 125 {
		t.Fatalf("all cases %d != 125", len(all))
	}
	seenIDs := map[string]bool{}
	for _, rawCase := range all {
		id, _ := rawCase["id"].(string)
		if seenIDs[id] {
			t.Fatalf("duplicate case id %q", id)
		}
		seenIDs[id] = true
	}
	baselineRaw, ok := fixture["baseline_case_ids"].([]interface{})
	if !ok {
		t.Fatalf("baseline_case_ids not array")
	}
	baseline := make([]string, 0, len(baselineRaw))
	for _, item := range baselineRaw {
		id, ok := item.(string)
		if !ok {
			t.Fatalf("baseline id not string")
		}
		baseline = append(baseline, id)
	}
	if len(baseline) != 104 {
		t.Fatalf("baseline ids %d != 104", len(baseline))
	}
	baselineSet := map[string]bool{}
	for _, id := range baseline {
		if baselineSet[id] {
			t.Fatalf("duplicate baseline id %q", id)
		}
		if _, exists := byID[id]; !exists {
			t.Fatalf("baseline id %q not in fixture", id)
		}
		baselineSet[id] = true
	}
	var newIDs []string
	for id := range byID {
		if !baselineSet[id] {
			newIDs = append(newIDs, id)
		}
	}
	if len(newIDs) != 21 {
		t.Fatalf("new ids %d != 21", len(newIDs))
	}
	if len(baselineSet) != 104 || len(baselineSet)+len(newIDs) != len(byID) {
		t.Fatalf("BASE104/NEW21/ALL125 set relation mismatch")
	}
	baseCases := make([]map[string]interface{}, 0, len(baseline))
	newCases := make([]map[string]interface{}, 0, len(newIDs))
	for _, id := range baseline {
		baseCases = append(baseCases, byID[id])
	}
	for _, id := range newIDs {
		newCases = append(newCases, byID[id])
	}
	actualBase := aggregateV1(t, baseCases)
	actualNew := aggregateV1(t, newCases)
	actualAll := aggregateV1(t, all)
	if actualBase != expectedBase104V1 || actualBase != fixtureString(t, fixture, "expected_base104_v1") {
		t.Fatalf("BASE104_V1 mismatch: got %s", actualBase)
	}
	if actualNew != expectedNew21V1 || actualNew != fixtureString(t, fixture, "expected_new21_v1") {
		t.Fatalf("NEW21_V1 mismatch: got %s", actualNew)
	}
	if actualAll != expectedAll125V1 || actualAll != fixtureString(t, fixture, "expected_all125_v1") {
		t.Fatalf("ALL125_V1 mismatch: got %s", actualAll)
	}
	reversed := make([]map[string]interface{}, len(all))
	for i := range all {
		reversed[len(all)-1-i] = all[i]
	}
	if aggregateV1(t, reversed) != actualAll {
		t.Fatalf("aggregate changed under fixture order")
	}
	mutatedBase := cloneRawCases(baseCases)
	mutatedBase[0]["description"] = mutatedBase[0]["description"].(string) + " MUTATED"
	if aggregateV1(t, mutatedBase) == actualBase {
		t.Fatalf("BASE104 aggregate insensitive to case mutation")
	}
	mutatedNew := cloneRawCases(newCases)
	mutatedNew[0]["description"] = mutatedNew[0]["description"].(string) + " MUTATED"
	if aggregateV1(t, mutatedNew) == actualNew {
		t.Fatalf("NEW21 aggregate insensitive to case mutation")
	}
	mutatedAll := cloneRawCases(all)
	mutatedAll[0]["description"] = mutatedAll[0]["description"].(string) + " MUTATED"
	if aggregateV1(t, mutatedAll) == actualAll {
		t.Fatalf("ALL125 aggregate insensitive to case mutation")
	}
}


func skipRawJSONValue(dec *json.Decoder) error {
	tok, err := dec.Token()
	if err != nil {
		return err
	}
	if delim, ok := tok.(json.Delim); ok {
		if delim == '{' || delim == '[' {
			for dec.More() {
				if err := skipRawJSONValue(dec); err != nil {
					return err
				}
			}
			if _, err := dec.Token(); err != nil {
				return err
			}
		}
	}
	return nil
}

func findDuplicateRawJSONKey(payload string) (string, error) {
	dec := json.NewDecoder(strings.NewReader(payload))
	tok, err := dec.Token()
	if err != nil {
		return "", err
	}
	delim, ok := tok.(json.Delim)
	if !ok || delim != '{' {
		return "", fmt.Errorf("raw payload top level is not object")
	}
	seen := map[string]bool{}
	for dec.More() {
		keyTok, err := dec.Token()
		if err != nil {
			return "", err
		}
		key, ok := keyTok.(string)
		if !ok {
			return "", fmt.Errorf("raw payload key is not string")
		}
		if seen[key] {
			return key, nil
		}
		seen[key] = true
		if err := skipRawJSONValue(dec); err != nil {
			return "", err
		}
	}
	if _, err := dec.Token(); err != nil {
		return "", err
	}
	return "", nil
}

func validateRawJSON(payload string) error {
	dec := json.NewDecoder(strings.NewReader(payload))
	dec.UseNumber()
	if err := skipRawJSONValue(dec); err != nil {
		return err
	}
	if _, err := dec.Token(); err != io.EOF {
		if err == nil {
			return fmt.Errorf("trailing JSON value")
		}
		return err
	}
	return nil
}


func rawDuplicateMeta(id string) (rawDuplicateExpectation, bool) {
	meta, ok := rawDuplicateCases[id]
	return meta, ok
}

func validateScenarioCase(rawCase map[string]interface{}) error {
	caseID, _ := rawCase["id"].(string)
	expected, ok := scenarioRegistry[caseID]
	if !ok {
		return fmt.Errorf("unknown scenario case %q", caseID)
	}
	action, _ := rawCase["action"].(string)
	scenario, _ := rawCase["scenario"].(string)
	reason, _ := rawCase["reason"].(string)
	if action != expected.Action || scenario != expected.Scenario || reason != expected.Reason {
		return fmt.Errorf("scenario metadata mismatch for %s", caseID)
	}
	return nil
}

func validatePayloadTextCase(rawCase map[string]interface{}) error {
	caseID, _ := rawCase["id"].(string)
	expected, ok := payloadTextRegistry[caseID]
	if !ok {
		return fmt.Errorf("unknown payload_text case %q", caseID)
	}
	action, _ := rawCase["action"].(string)
	_, scenarioPresent := rawCase["scenario"]
	var scenario *string
	if value, ok := rawCase["scenario"].(string); ok {
		scenario = &value
	}
	reason, _ := rawCase["reason"].(string)
	if action != expected.Action || scenarioPresent != expected.ScenarioPresent || reason != expected.Reason {
		return fmt.Errorf("payload metadata mismatch for %s", caseID)
	}
	if expected.Scenario == nil {
		if scenario != nil {
			return fmt.Errorf("payload scenario not expected for %s", caseID)
		}
	} else if scenario == nil || *scenario != *expected.Scenario {
		return fmt.Errorf("payload scenario mismatch for %s", caseID)
	}
	return nil
}

func assertMetadataRegistries(t *testing.T, byID map[string]map[string]interface{}) {
	t.Helper()
	actualScenario := map[string]bool{}
	actualPayload := map[string]bool{}
	for id, rawCase := range byID {
		if _, ok := rawCase["scenario"]; ok {
			actualScenario[id] = true
		}
		if _, ok := rawCase["payload_text"]; ok {
			actualPayload[id] = true
		}
	}
	if len(actualScenario) != len(scenarioRegistry) {
		t.Fatalf("scenario registry count %d != %d", len(actualScenario), len(scenarioRegistry))
	}
	for id := range scenarioRegistry {
		if !actualScenario[id] {
			t.Fatalf("scenario case %s missing", id)
		}
		if err := validateScenarioCase(byID[id]); err != nil {
			t.Fatalf("scenario case %s: %v", id, err)
		}
	}
	if len(actualPayload) != len(payloadTextRegistry) {
		t.Fatalf("payload registry count %d != %d", len(actualPayload), len(payloadTextRegistry))
	}
	for id := range payloadTextRegistry {
		if !actualPayload[id] {
			t.Fatalf("payload_text case %s missing", id)
		}
		if err := validatePayloadTextCase(byID[id]); err != nil {
			t.Fatalf("payload_text case %s: %v", id, err)
		}
	}
}


func assertRawDuplicateCase(t *testing.T, rawCase map[string]interface{}, id string) {
	t.Helper()
	meta, ok := rawDuplicateMeta(id)
	if !ok {
		t.Fatalf("unknown raw duplicate case %q", id)
	}
	action, _ := rawCase["action"].(string)
	if action != meta.Action {
		t.Fatalf("case %s action %q != %q", id, action, meta.Action)
	}
	_, scenarioPresent := rawCase["scenario"]
	if scenarioPresent != (meta.Scenario != nil) {
		t.Fatalf("case %s scenario presence mismatch", id)
	}
	if meta.Scenario != nil {
		scenario, _ := rawCase["scenario"].(string)
		if scenario != *meta.Scenario {
			t.Fatalf("case %s scenario %q != %q", id, scenario, *meta.Scenario)
		}
	}
	reason, _ := rawCase["reason"].(string)
	if reason != meta.Reason {
		t.Fatalf("case %s reason %q != %q", id, reason, meta.Reason)
	}
	switch meta.ValidationMode {
	case "malformed_json":
		payload, _ := rawCase["payload_text"].(string)
		if payload == "" {
			t.Fatalf("case t-017 empty payload_text")
		}
		if strings.Count(payload, `"config_version"`) < 2 {
			t.Fatalf("case t-017 missing apparent duplicate keys")
		}
		if err := validateRawJSON(payload); err == nil {
			t.Fatalf("case t-017 malformed JSON must fail parsing")
		}
	case "raw_duplicate_json":
		payload, _ := rawCase["payload_text"].(string)
		if payload == "" {
			t.Fatalf("case %s empty payload_text", id)
		}
		if err := validateRawJSON(payload); err != nil {
			t.Fatalf("case %s valid JSON must parse: %v", id, err)
		}
		dup, err := findDuplicateRawJSONKey(payload)
		if err != nil {
			t.Fatalf("case %s duplicate scan: %v", id, err)
		}
		if dup == "" {
			t.Fatalf("case %s duplicate key not detected", id)
		}
	case "policy_id_type":
		values, _ := rawCase["policy_id_values"].([]interface{})
		if len(values) == 0 {
			t.Fatalf("case d-009 empty policy_id_values")
		}
		invalidType := false
		for _, item := range values {
			obj, ok := item.(map[string]interface{})
			if !ok {
				invalidType = true
				continue
			}
			if _, ok := obj["policy_id"].(string); !ok {
				invalidType = true
			}
		}
		if !invalidType {
			t.Fatalf("case d-009 invalid policy_id type not detected")
		}
	case "duplicate_port":
		portsObj, ok := rawCase["ports"].(map[string]interface{})
		if !ok {
			t.Fatalf("case d-010 ports not object")
		}
		ports, ok := portsObj["https"].([]interface{})
		if !ok || len(ports) != 2 {
			t.Fatalf("case d-010 https ports invalid")
		}
		first, ok1 := ports[0].(json.Number)
		second, ok2 := ports[1].(json.Number)
		if !ok1 || !ok2 || first != second {
			t.Fatalf("case d-010 duplicate port not detected")
		}
	default:
		t.Fatalf("unknown validation mode %q", meta.ValidationMode)
	}
}


func TestOutboundSecurityContractRawDuplicateBoundaries(t *testing.T) {
	fixture := loadConfigContractFixtureRaw(t)
	byID, _ := rawFixtureCases(t, fixture)
	assertMetadataRegistries(t, byID)
	executed := map[string]bool{}
	for id := range rawDuplicateCases {
		rawCase, ok := byID[id]
		if !ok {
			t.Fatalf("raw duplicate case %s missing", id)
		}
		assertRawDuplicateCase(t, rawCase, id)
		executed[id] = true
	}
	if len(executed) != len(rawDuplicateCases) {
		t.Fatalf("executed raw duplicate cases %d != %d", len(executed), len(rawDuplicateCases))
	}
	if _, ok := rawDuplicateMeta("unknown-raw-action"); ok {
		t.Fatalf("unknown raw action accepted")
	}
	if err := validateScenarioCase(map[string]interface{}{
		"id": "synthetic-unknown-scenario", "action": "reject",
		"scenario": "unknown_raw_scenario_for_contract_test", "reason": "config_unknown_field",
	}); err == nil {
		t.Fatalf("unknown scenario accepted")
	}
	if err := validateScenarioCase(map[string]interface{}{
		"id": "t-017", "action": "accept",
		"scenario": "malformed_json_apparent_duplicate", "reason": "config_invalid_json",
	}); err == nil {
		t.Fatalf("changed action accepted")
	}
	if err := validateScenarioCase(map[string]interface{}{
		"id": "t-017", "action": "reject",
		"scenario": "unknown_raw_scenario_for_contract_test", "reason": "config_invalid_json",
	}); err == nil {
		t.Fatalf("changed scenario accepted")
	}
	if err := validateScenarioCase(map[string]interface{}{
		"id": "t-017", "action": "reject",
		"scenario": "malformed_json_apparent_duplicate", "reason": "config_duplicate",
	}); err == nil {
		t.Fatalf("changed reason accepted")
	}
	if err := validatePayloadTextCase(map[string]interface{}{
		"id": "synthetic-unknown-payload", "action": "reject", "reason": "config_invalid_json",
	}); err == nil {
		t.Fatalf("unknown payload case accepted")
	}
	if err := validatePayloadTextCase(map[string]interface{}{
		"id": "d-001", "action": "reject", "reason": "config_duplicate",
	}); err == nil {
		t.Fatalf("payload changed action accepted")
	}
	if err := validatePayloadTextCase(map[string]interface{}{
		"id": "d-001", "action": "marker", "scenario": "unknown_raw_scenario_for_contract_test", "reason": "config_duplicate",
	}); err == nil {
		t.Fatalf("payload unexpected scenario accepted")
	}
	if err := validatePayloadTextCase(map[string]interface{}{
		"id": "d-001", "action": "marker", "reason": "config_invalid_json",
	}); err == nil {
		t.Fatalf("payload changed reason accepted")
	}
	dup, err := findDuplicateRawJSONKey(`{"a":1,"\u0061":2}`)
	if err != nil {
		t.Fatalf("escaped key payload parse: %v", err)
	}
	if dup != "a" {
		t.Fatalf("escaped equivalent key not detected: %q", dup)
	}
	trailing := `{"a":1,"a":2} trailing`
	if dup, err := findDuplicateRawJSONKey(trailing); err != nil || dup != "a" {
		t.Fatalf("trailing payload duplicate not observable: dup=%q err=%v", dup, err)
	}
	if err := validateRawJSON(trailing); err == nil {
		t.Fatalf("trailing payload must fail full JSON validation")
	}
}
