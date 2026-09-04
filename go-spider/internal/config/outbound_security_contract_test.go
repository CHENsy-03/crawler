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
	"unicode/utf8"
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

type vectorValid struct {
	Name                    string  `json:"name"`
	Target                  string  `json:"target"`
	InputJSONUTF8Hex        string  `json:"input_json_utf8_hex"`
	ExpectedCanonicalUTF8Hex string `json:"expected_canonical_utf8_hex"`
	ExpectedCaseSHA256      *string `json:"expected_case_sha256"`
}

type vectorReject struct {
	Name            string  `json:"name"`
	Target          string  `json:"target"`
	InputJSONUTF8Hex *string `json:"input_json_utf8_hex"`
	Recipe          *string `json:"recipe"`
	ExpectedStage   string  `json:"expected_stage"`
	ExpectedError   string  `json:"expected_error"`
}

type vectorRecipe struct {
	Name                string `json:"name"`
	Generator           string `json:"generator"`
	PrefixHex           string `json:"prefix_hex"`
	UnitHex             string `json:"unit_hex"`
	SeparatorHex        string `json:"separator_hex"`
	SuffixHex           string `json:"suffix_hex"`
	Count               int    `json:"count"`
	OutputKind          string `json:"output_kind"`
	ExpectedInputSHA256 string `json:"expected_input_sha256"`
	ExpectedStage       string `json:"expected_stage"`
	ExpectedError       string `json:"expected_error"`
}

type vectorProvenance struct {
	Method string `json:"method"`
}

type vectorFixture struct {
	FormatVersion   string          `json:"format_version"`
	Profile         string          `json:"profile"`
	Provenance      vectorProvenance `json:"provenance"`
	ValidVectors    []vectorValid    `json:"valid_vectors"`
	RejectVectors   []vectorReject   `json:"reject_vectors"`
	ResourceRecipes []vectorRecipe   `json:"resource_recipes"`
}

var vectorValidNames = map[string]bool{
	"canonical_case_minimal": true, "canonical_html_specials": true, "canonical_u2028": true, "canonical_u2029": true,
	"canonical_literal_backslash_u": true, "canonical_cjk": true, "canonical_quote_backslash": true, "canonical_control_short": true,
	"canonical_control_u00xx": true, "canonical_slash": true, "canonical_u007f_c1": true, "canonical_unicode_object_key": true,
	"canonical_nested_key_sort": true, "canonical_null_empty_distinction": true, "canonical_type_int_bool_string": true,
	"canonical_integer_zero": true, "canonical_negative_zero": true, "canonical_large_integer": true, "canonical_surrogate_pair": true,
	"canonical_internal_bom": true, "canonical_whitespace_equivalent": true, "canonical_crlf_equivalent": true,
	"canonical_key_sort_ascii_cjk_nonbmp": true, "canonical_depth_128": true, "canonical_case_id_64": true,
}

var vectorRejectNames = map[string]bool{
	"strict_bom": true, "strict_invalid_utf8": true, "strict_empty_input": true, "strict_whitespace_only": true,
	"strict_malformed_json": true, "strict_trailing_data": true, "strict_duplicate_literal_key": true,
	"strict_duplicate_decoded_key": true, "strict_lone_high_surrogate": true, "strict_lone_low_surrogate": true,
	"strict_high_high_surrogate": true, "strict_high_nonlow_surrogate": true, "strict_low_high_surrogate": true,
	"strict_nan": true, "strict_infinity": true, "strict_negative_infinity": true, "strict_leading_zero": true,
	"strict_truncated_exponent": true, "limit_file_size_16mib_plus_1": true, "limit_depth_129": true,
	"limit_integer_4097_digits": true, "limit_array_10001": true, "limit_object_1001_members": true,
	"limit_string_1mib_plus_1": true, "limit_case_count_10001": true, "canonical_noninteger_1_0": true,
	"canonical_noninteger_1e5": true, "canonical_noninteger_negative_zero": true, "canonical_root_non_object": true,
	"canonical_missing_id": true, "canonical_empty_id": true, "canonical_uppercase_id": true,
	"canonical_underscore_id": true, "canonical_id_65": true, "canonical_nonstring_id": true,
}

var vectorRecipeNames = map[string]bool{
	"recipe_integer_4097_digits": true, "recipe_array_10001": true, "recipe_string_1mib_plus_1": true,
	"recipe_file_size_16mib_plus_1": true, "recipe_depth_129": true, "recipe_object_1001_members": true,
	"recipe_case_count_10001": true,
}

var vectorGenerators = map[string]bool{
	"repeat_unit": true, "nested_container": true, "object_members": true, "file_size_pad": true, "case_dataset": true,
}

var vectorOutputKinds = map[string]bool{"raw_bytes": true, "typed_dataset": true}

var vectorErrorCodes = map[string]bool{
	"strict_decode_invalid_json": true, "strict_decode_invalid_utf8": true, "strict_decode_bom": true,
	"strict_decode_duplicate_key": true, "strict_decode_lone_surrogate": true, "strict_decode_trailing_data": true,
	"evidence_limit_file_size": true, "evidence_limit_nesting_depth": true, "evidence_limit_integer_digits": true,
	"evidence_limit_array_length": true, "evidence_limit_object_members": true, "evidence_limit_string_length": true,
	"evidence_limit_case_count": true, "canonical_invalid_value_type": true, "canonical_non_integer_number": true,
	"canonical_invalid_unicode": true, "canonical_root_not_object": true, "canonical_missing_id": true,
	"canonical_invalid_id": true, "aggregate_empty_set": true, "aggregate_duplicate_id": true,
	"aggregate_invalid_digest_length": true, "aggregate_unknown_algorithm": true, "aggregate_count_overflow": true,
	"aggregate_length_overflow": true, "manifest_invalid_structure": true, "manifest_unknown_field": true,
	"manifest_count_mismatch": true, "manifest_case_digest_mismatch": true, "manifest_category_mismatch": true,
	"manifest_aggregate_mismatch": true, "manifest_invalid_dataset": true, "manifest_invalid_category": true,
	"manifest_duplicate_category": true, "manifest_invalid_cohort": true, "manifest_duplicate_cohort": true,
	"manifest_cohort_mismatch": true, "seal_record_invalid_structure": true, "seal_record_hash_mismatch": true,
	"seal_record_git_binding_failed": true,
}

func vectorFixturePath(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "tests", "fixtures", "outbound_security_aggregate_vectors.json")
}

func loadVectorFixture(t *testing.T) vectorFixture {
	t.Helper()
	data, err := os.ReadFile(vectorFixturePath(t))
	if err != nil {
		t.Fatalf("read vector fixture: %v", err)
	}
	if len(data) >= 3 && data[0] == 0xEF && data[1] == 0xBB && data[2] == 0xBF {
		t.Fatalf("vector fixture has BOM")
	}
	if !utf8.Valid(data) {
		t.Fatalf("vector fixture not valid UTF-8")
	}
	if dup, err := findDuplicateRawJSONKey(string(data)); err != nil || dup != "" {
		t.Fatalf("vector fixture duplicate key: dup=%q err=%v", dup, err)
	}
	if err := validateRawJSON(string(data)); err != nil {
		t.Fatalf("vector fixture invalid JSON: %v", err)
	}
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	var fixture vectorFixture
	if err := dec.Decode(&fixture); err != nil {
		t.Fatalf("decode vector fixture: %v", err)
	}
	return fixture
}

func requireVectorHex(value string, label string, allowEmpty bool, requireUTF8 bool) ([]byte, error) {
	if !allowEmpty && value == "" {
		return nil, fmt.Errorf("%s empty", label)
	}
	if len(value)%2 != 0 {
		return nil, fmt.Errorf("%s odd hex length", label)
	}
	if value != strings.ToLower(value) {
		return nil, fmt.Errorf("%s not lowercase", label)
	}
	data, err := hex.DecodeString(value)
	if err != nil {
		return nil, fmt.Errorf("%s hex: %v", label, err)
	}
	if requireUTF8 && !utf8.Valid(data) {
		return nil, fmt.Errorf("%s not UTF-8", label)
	}
	return data, nil
}

func validateNestedZeroArray(data []byte, expectedDepth int) error {
	if expectedDepth < 1 {
		return fmt.Errorf("expected depth %d", expectedDepth)
	}
	if len(data) != 2*expectedDepth+1 {
		return fmt.Errorf("nested zero array length %d != %d", len(data), 2*expectedDepth+1)
	}
	depth := 0
	maxDepth := 0
	scalarSeen := false
	for i, b := range data {
		switch b {
		case '[':
			if scalarSeen {
				return fmt.Errorf("open bracket after scalar at %d", i)
			}
			depth++
			if depth > maxDepth {
				maxDepth = depth
			}
		case '0':
			if scalarSeen {
				return fmt.Errorf("duplicate scalar at %d", i)
			}
			scalarSeen = true
			if depth != expectedDepth {
				return fmt.Errorf("scalar depth %d != %d at %d", depth, expectedDepth, i)
			}
		case ']':
			if !scalarSeen {
				return fmt.Errorf("close bracket before scalar at %d", i)
			}
			depth--
			if depth < 0 {
				return fmt.Errorf("depth negative at %d", i)
			}
		default:
			return fmt.Errorf("unexpected byte 0x%02x at %d", b, i)
		}
	}
	if !scalarSeen {
		return fmt.Errorf("missing scalar")
	}
	if depth != 0 {
		return fmt.Errorf("unclosed brackets depth %d", depth)
	}
	if maxDepth != expectedDepth {
		return fmt.Errorf("max depth %d != %d", maxDepth, expectedDepth)
	}
	return nil
}

func generateVectorRecipeOutput(r vectorRecipe) ([]byte, error) {
	prefix, err := hex.DecodeString(r.PrefixHex)
	if err != nil {
		return nil, err
	}
	unit, err := hex.DecodeString(r.UnitHex)
	if err != nil {
		return nil, err
	}
	sep, err := hex.DecodeString(r.SeparatorHex)
	if err != nil {
		return nil, err
	}
	suffix, err := hex.DecodeString(r.SuffixHex)
	if err != nil {
		return nil, err
	}
	switch r.Generator {
	case "repeat_unit":
		out := append([]byte{}, prefix...)
		out = append(out, unit...)
		for i := 1; i < r.Count; i++ {
			out = append(out, sep...)
			out = append(out, unit...)
		}
		out = append(out, suffix...)
		return out, nil
	case "nested_container":
		out := []byte{}
		for i := 0; i < r.Count; i++ {
			out = append(out, prefix...)
		}
		out = append(out, unit...)
		for i := 0; i < r.Count; i++ {
			out = append(out, suffix...)
		}
		return out, nil
	case "object_members":
		out := append([]byte{}, prefix...)
		for i := 0; i < r.Count; i++ {
			if i > 0 {
				out = append(out, sep...)
			}
			out = append(out, fmt.Sprintf(`"k%d":0`, i)...)
		}
		out = append(out, suffix...)
		return out, nil
	case "file_size_pad":
		out := append([]byte{}, prefix...)
		for i := 0; i < r.Count; i++ {
			out = append(out, unit...)
		}
		out = append(out, suffix...)
		return out, nil
	case "case_dataset":
		out := append([]byte{}, prefix...)
		for i := 0; i < r.Count; i++ {
			if i > 0 {
				out = append(out, sep...)
			}
			out = append(out, fmt.Sprintf(`{"id":"c%d"}`, i)...)
		}
		out = append(out, suffix...)
		return out, nil
	default:
		return nil, fmt.Errorf("unknown generator %q", r.Generator)
	}
}

func validateRecipeDepth129(r vectorRecipe) error {
	data, err := generateVectorRecipeOutput(r)
	if err != nil {
		return err
	}
	sum := sha256.Sum256(data)
	if hex.EncodeToString(sum[:]) != r.ExpectedInputSHA256 {
		return fmt.Errorf("recipe %s sha mismatch", r.Name)
	}
	return validateNestedZeroArray(data, 129)
}

func validateVectorFixture(f *vectorFixture) error {
	if f.FormatVersion != "1.0" {
		return fmt.Errorf("format_version %q", f.FormatVersion)
	}
	if f.Profile != "OSEC-EVIDENCE-PROFILE-V2" {
		return fmt.Errorf("profile %q", f.Profile)
	}
	if f.Provenance.Method != "independently_constructed" {
		return fmt.Errorf("provenance %q", f.Provenance.Method)
	}
	if len(f.ValidVectors) != 25 || len(f.RejectVectors) != 35 || len(f.ResourceRecipes) != 7 {
		return fmt.Errorf("counts %d/%d/%d", len(f.ValidVectors), len(f.RejectVectors), len(f.ResourceRecipes))
	}
	seen := map[string]bool{}
	for _, v := range f.ValidVectors {
		if !vectorValidNames[v.Name] || seen[v.Name] {
			return fmt.Errorf("valid name %q", v.Name)
		}
		seen[v.Name] = true
		if v.Target != "canonical_json" && v.Target != "canonical_case" {
			return fmt.Errorf("valid target %q", v.Target)
		}
		if _, err := requireVectorHex(v.InputJSONUTF8Hex, v.Name+" input", false, true); err != nil {
			return err
		}
		exp, err := requireVectorHex(v.ExpectedCanonicalUTF8Hex, v.Name+" expected", false, true)
		if err != nil {
			return err
		}
		if bytes.HasPrefix(exp, []byte{0xEF, 0xBB, 0xBF}) || bytes.HasSuffix(exp, []byte("\n")) {
return fmt.Errorf("%s canonical BOM/newline", v.Name)
		}
		sum := sha256.Sum256(exp)
		if v.Target == "canonical_case" {
			if v.ExpectedCaseSHA256 == nil || *v.ExpectedCaseSHA256 != hex.EncodeToString(sum[:]) {
				return fmt.Errorf("%s case digest", v.Name)
			}
		} else if v.ExpectedCaseSHA256 != nil {
			return fmt.Errorf("%s unexpected case digest", v.Name)
		}
	}
	for _, rj := range f.RejectVectors {
		if !vectorRejectNames[rj.Name] || seen[rj.Name] {
			return fmt.Errorf("reject name %q", rj.Name)
		}
		seen[rj.Name] = true
		if rj.Target != "strict_decode" && rj.Target != "evidence_limits" && rj.Target != "canonical" {
			return fmt.Errorf("reject target %q", rj.Target)
		}
		if rj.ExpectedStage != rj.Target {
			return fmt.Errorf("reject stage %q target %q", rj.ExpectedStage, rj.Target)
		}
		if !vectorErrorCodes[rj.ExpectedError] {
			return fmt.Errorf("reject error %q", rj.ExpectedError)
		}
		if rj.Recipe == nil {
			if rj.InputJSONUTF8Hex == nil {
				return fmt.Errorf("reject %s missing inline", rj.Name)
			}
			if _, err := requireVectorHex(*rj.InputJSONUTF8Hex, rj.Name, true, false); err != nil {
				return err
			}
		} else {
			if rj.InputJSONUTF8Hex != nil {
				return fmt.Errorf("reject %s has both", rj.Name)
			}
		}
	}
	recipeNames := map[string]bool{}
	for _, r := range f.ResourceRecipes {
		if !vectorRecipeNames[r.Name] || seen[r.Name] {
			return fmt.Errorf("recipe name %q", r.Name)
		}
		seen[r.Name] = true
		recipeNames[r.Name] = true
		if !vectorGenerators[r.Generator] {
			return fmt.Errorf("generator %q", r.Generator)
		}
		if !vectorOutputKinds[r.OutputKind] {
			return fmt.Errorf("output kind %q", r.OutputKind)
		}
		if r.Count <= 0 {
			return fmt.Errorf("recipe %s count", r.Name)
		}
		if !vectorErrorCodes[r.ExpectedError] {
			return fmt.Errorf("recipe error %q", r.ExpectedError)
		}
	}
	for _, rj := range f.RejectVectors {
		if rj.Recipe == nil {
			continue
		}
		if !recipeNames[*rj.Recipe] {
			return fmt.Errorf("reject %s recipe missing", rj.Name)
		}
	}
	for _, r := range f.ResourceRecipes {
		refs := 0
		for _, rj := range f.RejectVectors {
			if rj.Recipe != nil && *rj.Recipe == r.Name {
				refs++
				if rj.ExpectedStage != r.ExpectedStage || rj.ExpectedError != r.ExpectedError {
					return fmt.Errorf("recipe %s mismatch", r.Name)
				}
			}
		}
		if refs != 1 {
			return fmt.Errorf("recipe %s refs %d", r.Name, refs)
		}
	}
	validByName := map[string]vectorValid{}
	for _, v := range f.ValidVectors {
		validByName[v.Name] = v
	}
	if validByName["canonical_integer_zero"].ExpectedCanonicalUTF8Hex != validByName["canonical_negative_zero"].ExpectedCanonicalUTF8Hex {
		return fmt.Errorf("zero canonical mismatch")
	}
	if validByName["canonical_whitespace_equivalent"].ExpectedCanonicalUTF8Hex != validByName["canonical_crlf_equivalent"].ExpectedCanonicalUTF8Hex {
		return fmt.Errorf("whitespace canonical mismatch")
	}
	depth128Input, err := hex.DecodeString(validByName["canonical_depth_128"].InputJSONUTF8Hex)
	if err != nil {
		return fmt.Errorf("depth 128 input hex: %w", err)
	}
	depth128Expected, err := hex.DecodeString(validByName["canonical_depth_128"].ExpectedCanonicalUTF8Hex)
	if err != nil {
		return fmt.Errorf("depth 128 expected hex: %w", err)
	}
	if err := validateNestedZeroArray(depth128Input, 128); err != nil {
		return fmt.Errorf("depth 128 input: %w", err)
	}
	if err := validateNestedZeroArray(depth128Expected, 128); err != nil {
		return fmt.Errorf("depth 128 expected: %w", err)
	}
	if !bytes.Equal(depth128Input, depth128Expected) {
		return fmt.Errorf("depth 128 canonical mismatch")
	}
	return nil
}

func TestOutboundSecurityAggregateVectors(t *testing.T) {
	fixture := loadVectorFixture(t)
	if err := validateVectorFixture(&fixture); err != nil {
		t.Fatalf("vector fixture validation: %v", err)
	}
	executed := map[string]bool{}
	for _, r := range fixture.ResourceRecipes {
		data, err := generateVectorRecipeOutput(r)
		if err != nil {
			t.Fatalf("recipe %s generate: %v", r.Name, err)
		}
		sum := sha256.Sum256(data)
		if hex.EncodeToString(sum[:]) != r.ExpectedInputSHA256 {
			t.Fatalf("recipe %s sha mismatch", r.Name)
		}
		switch r.Name {
		case "recipe_file_size_16mib_plus_1":
			if len(data) != 16777217 {
				t.Fatalf("file size bytes %d", len(data))
			}
		case "recipe_depth_129":
			if err := validateNestedZeroArray(data, 129); err != nil {
				t.Fatalf("depth structure: %v", err)
			}
		case "recipe_integer_4097_digits":
			if len(data) != 4097 {
				t.Fatalf("integer digits %d", len(data))
			}
		case "recipe_array_10001":
			if bytes.Count(data, []byte(",")) != 10000 {
				t.Fatalf("array count")
			}
		case "recipe_object_1001_members":
			var obj map[string]interface{}
			if err := json.Unmarshal(data, &obj); err != nil {
				t.Fatalf("object members parse: %v", err)
			}
			if len(obj) != 1001 {
				t.Fatalf("object members %d", len(obj))
			}
		case "recipe_string_1mib_plus_1":
			if len(data) != 1048585 {
				t.Fatalf("string bytes %d", len(data))
			}
		case "recipe_case_count_10001":
			var arr []interface{}
			if err := json.Unmarshal(data, &arr); err != nil {
				t.Fatalf("case dataset parse: %v", err)
			}
			if len(arr) != 10001 {
				t.Fatalf("case count %d", len(arr))
			}
		}
		executed[r.Name] = true
	}
	if len(executed) != len(vectorRecipeNames) {
		t.Fatalf("executed recipes %d != %d", len(executed), len(vectorRecipeNames))
	}
	for name := range vectorRecipeNames {
		if !executed[name] {
			t.Fatalf("recipe not executed: %s", name)
		}
	}
}

func TestOutboundSecurityAggregateVectorsUnknowns(t *testing.T) {
	// Unknown top-level field must fail strict decoding.
	data, err := os.ReadFile(vectorFixturePath(t))
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	s := string(data)
	insert := s[:len(s)-2] + `,"unknown_top":true}` + s[len(s)-1:]
	dec := json.NewDecoder(strings.NewReader(insert))
	dec.DisallowUnknownFields()
	var f vectorFixture
	if err := dec.Decode(&f); err == nil {
		t.Fatalf("unknown top-level field accepted")
	}
	// Unknown generator must fail validator.
	fixture := loadVectorFixture(t)
	fixture.ResourceRecipes[0].Generator = "unknown_generator"
	if err := validateVectorFixture(&fixture); err == nil {
		t.Fatalf("unknown generator accepted")
	}
	// Unknown output kind must fail validator.
	fixture = loadVectorFixture(t)
	fixture.ResourceRecipes[0].OutputKind = "unknown_kind"
	if err := validateVectorFixture(&fixture); err == nil {
		t.Fatalf("unknown output kind accepted")
	}
	// Unknown valid name must fail validator.
	fixture = loadVectorFixture(t)
	fixture.ValidVectors[0].Name = "unknown_valid_name"
	if err := validateVectorFixture(&fixture); err == nil {
		t.Fatalf("unknown valid name accepted")
	}
	// Unknown reject name must fail validator.
	fixture = loadVectorFixture(t)
	fixture.RejectVectors[0].Name = "unknown_reject_name"
	if err := validateVectorFixture(&fixture); err == nil {
		t.Fatalf("unknown reject name accepted")
	}
}

func TestOutboundSecurityAggregateVectorsDepthNegatives(t *testing.T) {
	mutateValid := func(fx *vectorFixture, data []byte) {
		encoded := hex.EncodeToString(data)
		for i := range fx.ValidVectors {
			if fx.ValidVectors[i].Name == "canonical_depth_128" {
				fx.ValidVectors[i].InputJSONUTF8Hex = encoded
				fx.ValidVectors[i].ExpectedCanonicalUTF8Hex = encoded
				return
			}
		}
		t.Fatal("canonical_depth_128 missing")
	}
	validCases := [][]byte{
		[]byte(strings.Repeat("[", 127) + "0" + strings.Repeat("]", 127)),
		[]byte(strings.Repeat("[", 129) + "0" + strings.Repeat("]", 129)),
		[]byte("0" + strings.Repeat("[", 128) + strings.Repeat("]", 128)),
		[]byte(strings.Repeat("[", 128) + strings.Repeat("]", 128) + "0"),
		[]byte(strings.Repeat("[", 128) + "0" + strings.Repeat("]", 127)),
		append([]byte(strings.Repeat("[", 128)+"0"+strings.Repeat("]", 128)), 'x'),
	}
	for i, data := range validCases {
		fx := loadVectorFixture(t)
		mutateValid(&fx, data)
		if err := validateVectorFixture(&fx); err == nil {
			t.Fatalf("valid depth case %d accepted", i)
		}
	}

	mutateRecipe := func(fx *vectorFixture, mutate func(*vectorRecipe)) {
		for i := range fx.ResourceRecipes {
			if fx.ResourceRecipes[i].Name == "recipe_depth_129" {
				mutate(&fx.ResourceRecipes[i])
				return
			}
		}
		t.Fatal("recipe_depth_129 missing")
	}
	vectorRecipeByName := func(fx *vectorFixture, name string) vectorRecipe {
		for _, r := range fx.ResourceRecipes {
			if r.Name == name {
				return r
			}
		}
		t.Fatalf("recipe missing %s", name)
		return vectorRecipe{}
	}

	fx := loadVectorFixture(t)
	mutateRecipe(&fx, func(r *vectorRecipe) { r.Count = 128 })
	if err := validateRecipeDepth129(vectorRecipeByName(&fx, "recipe_depth_129")); err == nil {
		t.Fatal("recipe depth 128 accepted")
	}

	fx = loadVectorFixture(t)
	mutateRecipe(&fx, func(r *vectorRecipe) { r.Count = 130 })
	if err := validateRecipeDepth129(vectorRecipeByName(&fx, "recipe_depth_129")); err == nil {
		t.Fatal("recipe depth 130 accepted")
	}

	fx = loadVectorFixture(t)
	mutateRecipe(&fx, func(r *vectorRecipe) { r.Count = 130 })
	if err := validateRecipeDepth129(vectorRecipeByName(&fx, "recipe_depth_129")); err == nil {
		t.Fatal("recipe count change without sha accepted")
	}

	fx = loadVectorFixture(t)
	mutateRecipe(&fx, func(r *vectorRecipe) {
		digest := r.ExpectedInputSHA256
		r.ExpectedInputSHA256 = "0" + digest[1:]
		if digest[0] == '0' {
			r.ExpectedInputSHA256 = "1" + digest[1:]
		}
	})
	if err := validateRecipeDepth129(vectorRecipeByName(&fx, "recipe_depth_129")); err == nil {
		t.Fatal("recipe sha mutation accepted")
	}

	fx = loadVectorFixture(t)
	mutateRecipe(&fx, func(r *vectorRecipe) { r.UnitHex = hex.EncodeToString([]byte("[]")) })
	if err := validateRecipeDepth129(vectorRecipeByName(&fx, "recipe_depth_129")); err == nil {
		t.Fatal("recipe extra container accepted")
	}

	fx = loadVectorFixture(t)
	wrongOrder := []byte(strings.Repeat("]", 129) + "0" + strings.Repeat("[", 129))
	wrongSum := sha256.Sum256(wrongOrder)
	mutateRecipe(&fx, func(r *vectorRecipe) {
		r.PrefixHex = hex.EncodeToString([]byte("]"))
		r.SuffixHex = hex.EncodeToString([]byte("["))
		r.ExpectedInputSHA256 = hex.EncodeToString(wrongSum[:])
	})
	if err := validateRecipeDepth129(vectorRecipeByName(&fx, "recipe_depth_129")); err == nil {
		t.Fatal("recipe wrong order with synced sha accepted")
	}
}

func TestOutboundSecurityAggregateVectorsUnknownMetadataNegatives(t *testing.T) {
	assertInvalid := func(name string, mutate func(*vectorFixture)) {
		fx := loadVectorFixture(t)
		mutate(&fx)
		if err := validateVectorFixture(&fx); err == nil {
			t.Fatalf("unknown metadata mutation accepted: %s", name)
		}
	}

	assertInvalid("valid target", func(fx *vectorFixture) {
		for i := range fx.ValidVectors {
			if fx.ValidVectors[i].Name == "canonical_case_minimal" {
				fx.ValidVectors[i].Target = "unknown_target"
				return
			}
		}
		t.Fatal("canonical_case_minimal missing")
	})
	assertInvalid("reject target", func(fx *vectorFixture) {
		for i := range fx.RejectVectors {
			if fx.RejectVectors[i].Name == "strict_bom" {
				fx.RejectVectors[i].Target = "unknown_target"
				return
			}
		}
		t.Fatal("strict_bom missing")
	})
	assertInvalid("reject stage", func(fx *vectorFixture) {
		for i := range fx.RejectVectors {
			if fx.RejectVectors[i].Name == "strict_bom" {
				fx.RejectVectors[i].ExpectedStage = "unknown_stage"
				return
			}
		}
		t.Fatal("strict_bom missing")
	})
	assertInvalid("recipe generator", func(fx *vectorFixture) {
		for i := range fx.ResourceRecipes {
			if fx.ResourceRecipes[i].Name == "recipe_depth_129" {
				fx.ResourceRecipes[i].Generator = "unknown_generator"
				return
			}
		}
		t.Fatal("recipe_depth_129 missing")
	})
	assertInvalid("recipe output kind", func(fx *vectorFixture) {
		for i := range fx.ResourceRecipes {
			if fx.ResourceRecipes[i].Name == "recipe_depth_129" {
				fx.ResourceRecipes[i].OutputKind = "unknown_kind"
				return
			}
		}
		t.Fatal("recipe_depth_129 missing")
	})
	assertInvalid("recipe stage", func(fx *vectorFixture) {
		for i := range fx.ResourceRecipes {
			if fx.ResourceRecipes[i].Name == "recipe_depth_129" {
				fx.ResourceRecipes[i].ExpectedStage = "unknown_stage"
				return
			}
		}
		t.Fatal("recipe_depth_129 missing")
	})
	data, err := os.ReadFile(vectorFixturePath(t))
	if err != nil {
		t.Fatalf("read vector fixture: %v", err)
	}
	raw := string(data)
	topWithField := strings.Replace(raw, `"format_version"`, `"unknown_top_level":true,"format_version"`, 1)
	if topWithField == raw {
		t.Fatal("top-level marker not found")
	}
	dec := json.NewDecoder(strings.NewReader(topWithField))
	dec.DisallowUnknownFields()
	var topFixture vectorFixture
	if err := dec.Decode(&topFixture); err == nil {
		t.Fatal("unknown top-level field accepted")
	}

	rejectWithField := strings.Replace(raw, `"name": "strict_bom"`, `"name": "strict_bom","unknown_reject_field":true`, 1)
	if rejectWithField == raw {
		t.Fatal("reject marker not found")
	}
	dec = json.NewDecoder(strings.NewReader(rejectWithField))
	dec.DisallowUnknownFields()
	var rejectFixture vectorFixture
	if err := dec.Decode(&rejectFixture); err == nil {
		t.Fatal("unknown reject field accepted")
	}

	recipeWithField := strings.Replace(raw, `"name": "recipe_integer_4097_digits"`, `"name": "recipe_integer_4097_digits","unknown_recipe_field":true`, 1)
	if recipeWithField == raw {
		t.Fatal("recipe marker not found")
	}
	dec = json.NewDecoder(strings.NewReader(recipeWithField))
	dec.DisallowUnknownFields()
	var recipeFixture vectorFixture
	if err := dec.Decode(&recipeFixture); err == nil {
		t.Fatal("unknown recipe field accepted")
	}
}

const expectedLegacyRecordSHA256 = "37A6EA15C1E7E7D80089AE0872992E2B405125EDD68C272739C2C09EF5001E81"

var expectedLegacyAggregates = map[string]string{
	"all125":      "75336a374cd9ee82a8c811f380fd9ce6893364d65eaf0fbed76424307b2baa5b",
	"base104":     "bc38711ddf559eb5319eac9b080eeec611e3742d9cf0bbdb09072317cfc975b8",
	"amendment21": "dfda4174b62f27b4132cf157e96b89be2982f9268724dc12f47ebc97c7df8850",
}

var legacyCohortOrder = []string{"all125", "base104", "amendment21"}

var legacyValidationRules = map[string]bool{
	"top_level": true, "provenance": true, "counts": true, "digest_format": true,
	"digest_sort": true, "cohort_order": true, "cohort_counts": true, "cohort_sets": true,
	"aggregate_recompute": true, "frozen_aggregates": true,
}

var legacyKnownActions = map[string]bool{
	"structure": true, "aggregate_recompute": true, "frozen_aggregates": true,
}

type legacyProvenance struct {
	Method                string `json:"method"`
	CanonicalLabel        string `json:"canonical_label"`
	LegacySourceCommit    string `json:"legacy_source_commit"`
	LegacySourceTree      string `json:"legacy_source_tree"`
	GitObjectFormat       string `json:"git_object_format"`
	FixturePath           string `json:"fixture_path"`
	FixtureBlobOID        string `json:"fixture_blob_oid"`
	PythonSourcePath      string `json:"python_source_path"`
	PythonSourceBlobOID   string `json:"python_source_blob_oid"`
	PythonImplementation  string `json:"python_implementation"`
	PythonVersion         string `json:"python_version"`
	AggregateAlgorithm    string `json:"aggregate_algorithm"`
}

type legacyCohort struct {
	Name         string   `json:"name"`
	CaseCount    int      `json:"case_count"`
	CaseIDs      []string `json:"case_ids"`
	AggregateV1  string   `json:"aggregate_v1"`
}

type legacyCaseDigest struct {
	ID     string `json:"id"`
	SHA256 string `json:"sha256"`
}

type legacyRecord struct {
	RecordVersion string            `json:"record_version"`
	Profile       string            `json:"profile"`
	Provenance    legacyProvenance  `json:"provenance"`
	CaseCount     int               `json:"case_count"`
	Cohorts       []legacyCohort    `json:"cohorts"`
	CaseDigests   []legacyCaseDigest `json:"case_digests"`
}

func legacyFixturePath(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "tests", "fixtures", "outbound_security_config_legacy_digests.json")
}

func findDuplicateJSONKeyAnywhere(dec *json.Decoder) (string, error) {
	tok, err := dec.Token()
	if err != nil {
		return "", err
	}
	delim, ok := tok.(json.Delim)
	if !ok {
		return "", nil
	}
	switch delim {
	case '{':
		seen := map[string]bool{}
		for dec.More() {
			keyTok, err := dec.Token()
			if err != nil {
				return "", err
			}
			key, ok := keyTok.(string)
			if !ok {
				return "", fmt.Errorf("object key is not string")
			}
			if seen[key] {
				return key, nil
			}
			seen[key] = true
			if dup, err := findDuplicateJSONKeyAnywhere(dec); err != nil || dup != "" {
				return dup, err
			}
		}
		if _, err := dec.Token(); err != nil {
			return "", err
		}
	case '[':
		for dec.More() {
			if dup, err := findDuplicateJSONKeyAnywhere(dec); err != nil || dup != "" {
				return dup, err
			}
		}
		if _, err := dec.Token(); err != nil {
			return "", err
		}
	}
	return "", nil
}

func loadLegacyRecord(t *testing.T) legacyRecord {
	t.Helper()
	data, err := os.ReadFile(legacyFixturePath(t))
	if err != nil {
		t.Fatalf("read legacy record: %v", err)
	}
	if len(data) >= 3 && data[0] == 0xEF && data[1] == 0xBB && data[2] == 0xBF {
		t.Fatalf("legacy record BOM")
	}
	if !utf8.Valid(data) {
		t.Fatalf("legacy record not UTF-8")
	}
	if dup, err := findDuplicateJSONKeyAnywhere(json.NewDecoder(bytes.NewReader(data))); err != nil || dup != "" {
		t.Fatalf("legacy record duplicate key: dup=%q err=%v", dup, err)
	}
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	var record legacyRecord
	if err := dec.Decode(&record); err != nil {
		t.Fatalf("decode legacy record: %v", err)
	}
	if _, err := dec.Token(); err != io.EOF {
		if err == nil {
			t.Fatalf("legacy record trailing JSON")
		}
		t.Fatalf("legacy record trailing decode: %v", err)
	}
	return record
}

func legacyAggregateFromDigests(items []legacyCaseDigest) (string, error) {
	type record struct {
		id     []byte
		digest []byte
	}
	records := make([]record, 0, len(items))
	for _, item := range items {
		digest, err := hex.DecodeString(item.SHA256)
		if err != nil || len(digest) != 32 {
			return "", fmt.Errorf("invalid digest %q", item.ID)
		}
		records = append(records, record{id: []byte(item.ID), digest: digest})
	}
	sort.Slice(records, func(i, j int) bool {
		return bytes.Compare(records[i].id, records[j].id) < 0
	})
	stream := []byte(aggregateV1Magic)
	var count [4]byte
	binary.BigEndian.PutUint32(count[:], uint32(len(records)))
	stream = append(stream, count[:]...)
	for _, rec := range records {
		var length [4]byte
		binary.BigEndian.PutUint32(length[:], uint32(len(rec.id)))
		stream = append(stream, length[:]...)
		stream = append(stream, rec.id...)
		stream = append(stream, rec.digest...)
	}
	sum := sha256.Sum256(stream)
	return hex.EncodeToString(sum[:]), nil
}

func validateLegacyActions(actions map[string]bool) error {
	for name := range actions {
		if !legacyKnownActions[name] {
			return fmt.Errorf("unknown validation action %q", name)
		}
	}
	return nil
}

func validateLegacyRecord(record *legacyRecord, executed map[string]bool) error {
	mark := func(name string) {
		if executed != nil {
			executed[name] = true
		}
	}
	if record.RecordVersion != "OSEC-LEGACY-DIGEST-RECORD-V1" {
		return fmt.Errorf("record version %q", record.RecordVersion)
	}
	if record.Profile != "OSEC-EVIDENCE-PROFILE-V2" {
		return fmt.Errorf("profile %q", record.Profile)
	}
	if record.CaseCount != 125 {
		return fmt.Errorf("case count %d", record.CaseCount)
	}
	mark("top_level")

	p := record.Provenance
	if p.Method != "recorded-from-legacy" ||
		p.CanonicalLabel != "LEGACY-PYTHON-CANONICAL-V1" ||
		p.LegacySourceCommit != "e6bdf4c863903fa7e2fdafd004fc94d0fbb766a3" ||
		p.LegacySourceTree != "242d27fd5f027a763ade7bcc1067ee0fc7ef9a67" ||
		p.GitObjectFormat != "sha1" ||
		p.FixturePath != "tests/fixtures/outbound_security_config_contract.json" ||
		p.FixtureBlobOID != "8b5c052c176b27b2b8530ddd464e00cf7de39b15" ||
		p.PythonSourcePath != "tests/test_outbound_security_config_contract.py" ||
		p.PythonSourceBlobOID != "9dd4968a691ede7433c3b7fd1a57221269f9c89b" ||
		p.PythonImplementation != "CPython" ||
		!regexp.MustCompile(`^[0-9]+\.[0-9]+\.[0-9]+$`).MatchString(p.PythonVersion) ||
		p.AggregateAlgorithm != "OSEC-CASE-AGGREGATE-V1" {
		return fmt.Errorf("provenance")
	}
	mark("provenance")

	if len(record.Cohorts) != 3 || len(record.CaseDigests) != 125 {
		return fmt.Errorf("counts")
	}
	mark("counts")

	for i, name := range legacyCohortOrder {
		if record.Cohorts[i].Name != name {
			return fmt.Errorf("cohort order")
		}
	}
	mark("cohort_order")

	digestIDs := map[string]bool{}
	prevID := ""
	for i, item := range record.CaseDigests {
		if len(item.SHA256) != 64 {
			return fmt.Errorf("digest format")
		}
		digest, err := hex.DecodeString(item.SHA256)
		if err != nil || len(digest) != 32 {
			return fmt.Errorf("digest decode")
		}
		if digestIDs[item.ID] {
			return fmt.Errorf("duplicate digest id")
		}
		digestIDs[item.ID] = true
		if i > 0 && bytes.Compare([]byte(prevID), []byte(item.ID)) >= 0 {
			return fmt.Errorf("digest sort")
		}
		prevID = item.ID
	}
	mark("digest_format")
	mark("digest_sort")

	cohorts := map[string]*legacyCohort{}
	for i := range record.Cohorts {
		cohort := &record.Cohorts[i]
		if cohort.CaseCount != len(cohort.CaseIDs) {
			return fmt.Errorf("cohort count %s", cohort.Name)
		}
		seen := map[string]bool{}
		prev := ""
		for j, id := range cohort.CaseIDs {
			if seen[id] {
				return fmt.Errorf("cohort duplicate %s", id)
			}
			seen[id] = true
			if j > 0 && bytes.Compare([]byte(prev), []byte(id)) >= 0 {
				return fmt.Errorf("cohort sort %s", cohort.Name)
			}
			prev = id
		}
		cohorts[cohort.Name] = cohort
	}
	mark("cohort_counts")

	allSet := map[string]bool{}
	for _, id := range cohorts["all125"].CaseIDs {
		allSet[id] = true
	}
	for id := range digestIDs {
		if !allSet[id] {
			return fmt.Errorf("all125 mismatch")
		}
	}
	for id := range allSet {
		if !digestIDs[id] {
			return fmt.Errorf("all125 mismatch")
		}
	}
	baseSet := map[string]bool{}
	amendmentSet := map[string]bool{}
	for _, id := range cohorts["base104"].CaseIDs {
		baseSet[id] = true
	}
	for _, id := range cohorts["amendment21"].CaseIDs {
		amendmentSet[id] = true
	}
	for id := range baseSet {
		if amendmentSet[id] {
			return fmt.Errorf("cohort overlap")
		}
	}
	if len(baseSet)+len(amendmentSet) != len(allSet) {
		return fmt.Errorf("cohort union")
	}
	mark("cohort_sets")

	digestByID := map[string]string{}
	for _, item := range record.CaseDigests {
		digestByID[item.ID] = item.SHA256
	}
	for _, name := range legacyCohortOrder {
		cohort := cohorts[name]
		items := make([]legacyCaseDigest, 0, len(cohort.CaseIDs))
		for _, id := range cohort.CaseIDs {
			items = append(items, legacyCaseDigest{ID: id, SHA256: digestByID[id]})
		}
		aggregate, err := legacyAggregateFromDigests(items)
		if err != nil || aggregate != cohort.AggregateV1 {
			return fmt.Errorf("cohort aggregate %s", name)
		}
		if expected := expectedLegacyAggregates[name]; aggregate != expected {
			return fmt.Errorf("frozen aggregate %s", name)
		}
	}
	mark("aggregate_recompute")
	mark("frozen_aggregates")
	return nil
}

func TestOutboundSecurityLegacyRecordPositive(t *testing.T) {
	data, err := os.ReadFile(legacyFixturePath(t))
	if err != nil {
		t.Fatalf("read legacy record: %v", err)
	}
	sum := sha256.Sum256(data)
	if !strings.EqualFold(hex.EncodeToString(sum[:]), expectedLegacyRecordSHA256) {
		t.Fatalf("legacy record sha mismatch")
	}
	if len(data) >= 3 && data[0] == 0xEF && data[1] == 0xBB && data[2] == 0xBF {
		t.Fatalf("legacy record BOM")
	}
	if !utf8.Valid(data) {
		t.Fatalf("legacy record UTF-8")
	}
	if bytes.Contains(data, []byte("\r")) {
		t.Fatalf("legacy record CR")
	}
	record := loadLegacyRecord(t)
	executed := map[string]bool{}
	if err := validateLegacyRecord(&record, executed); err != nil {
		t.Fatalf("legacy record validation: %v", err)
	}
	if len(executed) != len(legacyValidationRules) {
		t.Fatalf("executed rules %d != %d", len(executed), len(legacyValidationRules))
	}
	for name := range legacyValidationRules {
		if !executed[name] {
			t.Fatalf("rule not executed: %s", name)
		}
	}
	if err := validateLegacyActions(legacyKnownActions); err != nil {
		t.Fatalf("known actions: %v", err)
	}
}

func TestOutboundSecurityLegacyRecordNegative(t *testing.T) {
	runBad := func(name string, mutate func(*legacyRecord)) {
		record := loadLegacyRecord(t)
		mutate(&record)
		if err := validateLegacyRecord(&record, nil); err == nil {
			t.Fatalf("legacy mutation accepted: %s", name)
		}
	}

	runBad("record version", func(r *legacyRecord) { r.RecordVersion = "OSEC-LEGACY-DIGEST-RECORD-V2" })
	runBad("profile", func(r *legacyRecord) { r.Profile = "OSEC-EVIDENCE-PROFILE-V1" })
	runBad("method", func(r *legacyRecord) { r.Provenance.Method = "independently_constructed" })
	runBad("canonical label", func(r *legacyRecord) { r.Provenance.CanonicalLabel = "UNKNOWN" })
	runBad("aggregate algorithm", func(r *legacyRecord) { r.Provenance.AggregateAlgorithm = "UNKNOWN" })
	runBad("duplicate case id", func(r *legacyRecord) { r.CaseDigests = append(r.CaseDigests, r.CaseDigests[0]) })
	runBad("digest format", func(r *legacyRecord) { r.CaseDigests[0].SHA256 = "zz" })
	runBad("cohort order", func(r *legacyRecord) { r.Cohorts[0], r.Cohorts[1] = r.Cohorts[1], r.Cohorts[0] })
	runBad("cohort overlap", func(r *legacyRecord) {
		r.Cohorts[2].CaseIDs = append(r.Cohorts[2].CaseIDs, r.Cohorts[1].CaseIDs[0])
		r.Cohorts[2].CaseCount++
	})
	runBad("cohort union", func(r *legacyRecord) {
		r.Cohorts[0].CaseIDs = r.Cohorts[0].CaseIDs[1:]
		r.Cohorts[0].CaseCount--
	})
	runBad("aggregate bit", func(r *legacyRecord) {
		value := r.Cohorts[0].AggregateV1
		r.Cohorts[0].AggregateV1 = "0" + value[1:]
		if value[0] == '0' {
			r.Cohorts[0].AggregateV1 = "1" + value[1:]
		}
	})
	runBad("source commit", func(r *legacyRecord) {
		value := r.Provenance.LegacySourceCommit
		r.Provenance.LegacySourceCommit = "0" + value[1:]
		if value[0] == '0' {
			r.Provenance.LegacySourceCommit = "1" + value[1:]
		}
	})
	runBad("source tree", func(r *legacyRecord) {
		value := r.Provenance.LegacySourceTree
		r.Provenance.LegacySourceTree = "0" + value[1:]
		if value[0] == '0' {
			r.Provenance.LegacySourceTree = "1" + value[1:]
		}
	})
	runBad("fixture blob", func(r *legacyRecord) {
		value := r.Provenance.FixtureBlobOID
		r.Provenance.FixtureBlobOID = "0" + value[1:]
		if value[0] == '0' {
			r.Provenance.FixtureBlobOID = "1" + value[1:]
		}
	})
	runBad("python version empty", func(r *legacyRecord) { r.Provenance.PythonVersion = "" })
	runBad("python version short", func(r *legacyRecord) { r.Provenance.PythonVersion = "3.14" })

	if err := validateLegacyActions(map[string]bool{"unknown_validation_action": true}); err == nil {
		t.Fatal("unknown validation action accepted")
	}

	data, err := os.ReadFile(legacyFixturePath(t))
	if err != nil {
		t.Fatalf("read legacy record: %v", err)
	}
	raw := string(data)
	unknownCases := []struct {
		label       string
		marker      string
		replacement string
	}{
		{"top", `"record_version"`, `"unknown_top_level":true,"record_version"`},
		{"provenance", `"method": "recorded-from-legacy"`, `"method": "recorded-from-legacy","unknown_provenance_field":true`},
		{"cohort", `"name": "all125"`, `"name": "all125","unknown_cohort_field":true`},
		{"digest", `"id": "d-001"`, `"id": "d-001","unknown_digest_field":true`},
	}
	for _, tc := range unknownCases {
		if strings.Count(raw, tc.marker) != 1 {
			t.Fatalf("marker count for %s: %d", tc.label, strings.Count(raw, tc.marker))
		}
		injected := strings.Replace(raw, tc.marker, tc.replacement, 1)
		if !json.Valid([]byte(injected)) {
			t.Fatalf("injected %s JSON invalid", tc.label)
		}
		dec := json.NewDecoder(strings.NewReader(injected))
		dec.DisallowUnknownFields()
		var record legacyRecord
		if err := dec.Decode(&record); err == nil {
			t.Fatalf("unknown %s field accepted", tc.label)
		}
	}
}
