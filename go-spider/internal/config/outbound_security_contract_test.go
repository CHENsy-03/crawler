package config

import (
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

// This test validates the shared TASK-022E-B configuration contract fixture
// only. It must not load production config or use the production loader.

type configContractCase struct {
	ID                string                 `json:"id"`
	Action            string                 `json:"action"`
	Allowed           bool                   `json:"allowed"`
	Reason            *string                `json:"reason"`
	Description       string                 `json:"description"`
	Canonical         interface{}            `json:"canonical,omitempty"`
	PayloadText       string                 `json:"payload_text,omitempty"`
	Field             string                 `json:"field,omitempty"`
	Hostname          interface{}            `json:"hostname,omitempty"`
	LoggingRule       string                 `json:"logging_rule,omitempty"`
	RawInput          string                 `json:"raw_input,omitempty"`
	ExpectedLog       map[string]interface{} `json:"expected_log,omitempty"`
	RequiredLogFields []string               `json:"required_log_fields,omitempty"`
	ForbiddenValues   []string               `json:"forbidden_values,omitempty"`
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
