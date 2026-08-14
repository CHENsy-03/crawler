package security

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

type d1BudgetCase struct {
	ID                string         `json:"id"`
	Action            string         `json:"action"`
	Profile           string         `json:"profile,omitempty"`
	Field             string         `json:"field,omitempty"`
	Expected          any            `json:"expected,omitempty"`
	Kind              string         `json:"kind,omitempty"`
	Value             any            `json:"value,omitempty"`
	Allowed           bool           `json:"allowed,omitempty"`
	ExpectedReason    string         `json:"expected_reason,omitempty"`
	ElapsedMS         any            `json:"elapsed_ms,omitempty"`
	ExpectedRemaining int            `json:"expected_remaining,omitempty"`
	StageTimeoutMS    int            `json:"stage_timeout_ms,omitempty"`
	Common            map[string]int `json:"common,omitempty"`
}

type d1RedirectCase struct {
	ID                    string              `json:"id"`
	Action                string              `json:"action"`
	Current               string              `json:"current"`
	Location              any                 `json:"location,omitempty"`
	Locations             []string            `json:"locations,omitempty"`
	Hop                   int                 `json:"hop,omitempty"`
	Policy                policyObject        `json:"policy"`
	Addresses             map[string][]string `json:"addresses"`
	ExpectedURL           string              `json:"expected_url,omitempty"`
	ExpectedFinalURL      string              `json:"expected_final_url,omitempty"`
	ExpectedReason        string              `json:"expected_reason,omitempty"`
	ExpectedAddresses     []string            `json:"expected_addresses,omitempty"`
	ExpectedResolverCalls int                 `json:"expected_resolver_calls"`
}

type d1ProxyCase struct {
	ID             string  `json:"id"`
	Proxy          *string `json:"proxy"`
	Allowed        bool    `json:"allowed"`
	ExpectedReason string  `json:"expected_reason,omitempty"`
}

type d1Fixture struct {
	BudgetCases   []d1BudgetCase   `json:"budget_cases"`
	RedirectCases []d1RedirectCase `json:"redirect_cases"`
	ProxyCases    []d1ProxyCase    `json:"proxy_cases"`
}

func d1FixturePath(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "tests", "fixtures", "outbound_transport_policy_contract.json")
}

func loadD1Fixture(t *testing.T) d1Fixture {
	t.Helper()
	data, err := os.ReadFile(d1FixturePath(t))
	if err != nil {
		t.Fatalf("read d1 fixture: %v", err)
	}
	var fixture d1Fixture
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode d1 fixture: %v", err)
	}
	return fixture
}

func d1Reason(t *testing.T, err error) string {
	t.Helper()
	if err == nil {
		return ""
	}
	if e, ok := err.(*BudgetError); ok {
		return e.ReasonCode
	}
	if e, ok := err.(*RedirectPolicyError); ok {
		return e.ReasonCode
	}
	if e, ok := err.(*PinnedConnectionError); ok {
		return e.ReasonCode
	}
	return err.Error()
}

func d1Int(t *testing.T, value any) int {
	t.Helper()
	got, err := d1IntFromAny(value)
	if err != nil {
		t.Fatalf("budget value %v is not an int: %v", value, err)
	}
	return got
}

func d1IntFromAny(value any) (int, error) {
	switch v := value.(type) {
	case int:
		return v, nil
	case float64:
		if v != float64(int(v)) {
			return 0, budgetFail("invalid_budget_value")
		}
		return int(v), nil
	default:
		return 0, budgetFail("invalid_budget_value")
	}
}

func TestD1BudgetCases(t *testing.T) {
	fixture := loadD1Fixture(t)
	executed := make(map[string]bool)
	expected := make(map[string]bool)
	for _, tc := range fixture.BudgetCases {
		expected[tc.ID] = true
	}
	for _, tc := range fixture.BudgetCases {
		t.Run(tc.ID, func(t *testing.T) {
			switch tc.Action {
			case "profile_value":
				profile, err := BudgetForProfile(tc.Profile)
				if err != nil {
					t.Fatalf("budget_for: %v", err)
				}
				switch tc.Field {
				case "total_timeout_ms":
					if profile.TotalTimeoutMS() != d1Int(t, tc.Expected) {
						t.Fatalf("total = %d, want %d", profile.TotalTimeoutMS(), d1Int(t, tc.Expected))
					}
				case "response_body_bytes":
					if profile.ResponseBodyBytes() != d1Int(t, tc.Expected) {
						t.Fatalf("body = %d, want %d", profile.ResponseBodyBytes(), d1Int(t, tc.Expected))
					}
				}
			case "unknown_profile":
				_, err := BudgetForProfile(tc.Profile)
				if d1Reason(t, err) != tc.ExpectedReason {
					t.Fatalf("reason = %q, want %q", d1Reason(t, err), tc.ExpectedReason)
				}
			case "limit":
				value, err := d1IntFromAny(tc.Value)
				if err != nil {
					t.Fatalf("value conversion: %v", err)
				}
				var lerr error
				switch tc.Kind {
				case "request_body":
					lerr = CheckRequestBodyLimit(value)
				case "response_headers":
					lerr = CheckResponseHeadersLimit(value)
				case "response_body":
					profile, perr := BudgetForProfile(tc.Profile)
					if perr != nil {
						t.Fatalf("budget_for: %v", perr)
					}
					lerr = CheckResponseBodyLimit(profile, value)
				}
				if tc.Allowed {
					if lerr != nil {
						t.Fatalf("unexpected error: %v", lerr)
					}
				} else if d1Reason(t, lerr) != tc.ExpectedReason {
					t.Fatalf("reason = %q, want %q", d1Reason(t, lerr), tc.ExpectedReason)
				}
			case "remaining":
				profile, perr := BudgetForProfile(tc.Profile)
				if perr != nil {
					t.Fatalf("budget_for: %v", perr)
				}
				elapsed, err := d1IntFromAny(tc.ElapsedMS)
				if err != nil {
					if d1Reason(t, err) != tc.ExpectedReason {
						t.Fatalf("reason = %q, want %q", d1Reason(t, err), tc.ExpectedReason)
					}
					break
				}
				remaining, rerr := RemainingDeadline(profile, elapsed)
				if tc.ExpectedReason != "" {
					if d1Reason(t, rerr) != tc.ExpectedReason {
						t.Fatalf("reason = %q, want %q", d1Reason(t, rerr), tc.ExpectedReason)
					}
				} else if rerr != nil || remaining != tc.ExpectedRemaining {
					t.Fatalf("remaining = %d, err=%v, want %d", remaining, rerr, tc.ExpectedRemaining)
				}
			case "stage_zero":
				profile, perr := BudgetForProfile(tc.Profile)
				if perr != nil {
					t.Fatalf("budget_for: %v", perr)
				}
				_, err := CappedStageTimeout(profile, tc.StageTimeoutMS, d1Int(t, tc.ElapsedMS))
				if d1Reason(t, err) != tc.ExpectedReason {
					t.Fatalf("reason = %q, want %q", d1Reason(t, err), tc.ExpectedReason)
				}
			case "capped_stage":
				profile, perr := BudgetForProfile(tc.Profile)
				if perr != nil {
					t.Fatalf("budget_for: %v", perr)
				}
				got, err := CappedStageTimeout(profile, tc.StageTimeoutMS, d1Int(t, tc.ElapsedMS))
				if err != nil || got != d1Int(t, tc.Expected) {
					t.Fatalf("got=%d err=%v want %d", got, err, d1Int(t, tc.Expected))
				}
			case "remaining_capped_zero":
				profile, perr := BudgetForProfile(tc.Profile)
				if perr != nil {
					t.Fatalf("budget_for: %v", perr)
				}
				_, err := CappedStageTimeout(profile, tc.StageTimeoutMS, d1Int(t, tc.ElapsedMS))
				if d1Reason(t, err) != tc.ExpectedReason {
					t.Fatalf("reason = %q, want %q", d1Reason(t, err), tc.ExpectedReason)
				}
			case "remaining_one", "stage_equals_remaining":
				profile, perr := BudgetForProfile(tc.Profile)
				if perr != nil {
					t.Fatalf("budget_for: %v", perr)
				}
				got, err := CappedStageTimeout(profile, tc.StageTimeoutMS, d1Int(t, tc.ElapsedMS))
				if err != nil || got != d1Int(t, tc.Expected) {
					t.Fatalf("got=%d err=%v want %d", got, err, d1Int(t, tc.Expected))
				}
			case "bool_remaining":
				if _, ok := tc.ElapsedMS.(bool); !ok {
					t.Fatalf("elapsed is %T, want bool", tc.ElapsedMS)
				}
				_, err := d1IntFromAny(tc.ElapsedMS)
				if d1Reason(t, err) != tc.ExpectedReason {
					t.Fatalf("reason = %q, want %q", d1Reason(t, err), tc.ExpectedReason)
				}
			case "negative_remaining":
				profile, perr := BudgetForProfile(tc.Profile)
				if perr != nil {
					t.Fatalf("budget_for: %v", perr)
				}
				_, err := RemainingDeadline(profile, d1Int(t, tc.ElapsedMS))
				if d1Reason(t, err) != tc.ExpectedReason {
					t.Fatalf("reason = %q, want %q", d1Reason(t, err), tc.ExpectedReason)
				}
			case "negative":
				value, err := d1IntFromAny(tc.Value)
				if err != nil {
					t.Fatalf("value conversion: %v", err)
				}
				if d1Reason(t, CheckRequestBodyLimit(value)) != tc.ExpectedReason {
					t.Fatalf("reason = %q, want %q", d1Reason(t, CheckRequestBodyLimit(value)), tc.ExpectedReason)
				}
			case "bool":
				if _, ok := tc.Value.(bool); !ok {
					t.Fatalf("value is %T, want bool", tc.Value)
				}
				_, err := d1IntFromAny(tc.Value)
				if d1Reason(t, err) != tc.ExpectedReason {
					t.Fatalf("reason = %q, want %q", d1Reason(t, err), tc.ExpectedReason)
				}
			case "common":
				budget := NewTransportBudget()
				checks := map[string]int{
					"dns_timeout_ms":             budget.DNSTimeoutMS(),
					"connect_timeout_ms":         budget.ConnectTimeoutMS(),
					"tls_timeout_ms":             budget.TLSTimeoutMS(),
					"response_header_timeout_ms": budget.ResponseHeaderTimeoutMS(),
					"read_idle_timeout_ms":       budget.ReadIdleTimeoutMS(),
					"request_body_bytes":         budget.RequestBodyBytes(),
					"response_headers_bytes":     budget.ResponseHeadersBytes(),
					"max_redirects":              budget.MaxRedirects(),
					"global_active":              budget.GlobalActive(),
					"per_host_active":            budget.PerHostActive(),
					"per_host_idle":              budget.PerHostIdle(),
				}
				for field, expected := range tc.Common {
					if checks[field] != expected {
						t.Fatalf("%s = %d, want %d", field, checks[field], expected)
					}
				}
			default:
				t.Fatalf("unknown budget action %q", tc.Action)
			}
			executed[tc.ID] = true
		})
	}
	if len(executed) != len(expected) {
		t.Fatalf("executed %d budget cases, want %d", len(executed), len(expected))
	}
	for id := range expected {
		if !executed[id] {
			t.Fatalf("budget case %s was not executed", id)
		}
	}
}

func TestD1ProxyCases(t *testing.T) {
	fixture := loadD1Fixture(t)
	executed := make(map[string]bool)
	expected := make(map[string]bool)
	for _, tc := range fixture.ProxyCases {
		expected[tc.ID] = true
	}
	for _, tc := range fixture.ProxyCases {
		t.Run(tc.ID, func(t *testing.T) {
			var proxy string
			if tc.Proxy != nil {
				proxy = *tc.Proxy
			}
			err := ValidateProxy(proxy)
			if tc.Allowed {
				if err != nil {
					t.Fatalf("unexpected error: %v", err)
				}
			} else if d1Reason(t, err) != tc.ExpectedReason {
				t.Fatalf("reason = %q, want %q", d1Reason(t, err), tc.ExpectedReason)
			}
			executed[tc.ID] = true
		})
	}
	for id := range expected {
		if !executed[id] {
			t.Fatalf("proxy case %s was not executed", id)
		}
	}
}
