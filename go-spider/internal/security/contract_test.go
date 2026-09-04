package security

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
)

type urlCase struct {
	ID                    string `json:"id"`
	Raw                   string `json:"raw"`
	ExpectedReason        string `json:"expected_reason,omitempty"`
	ExpectedScheme        string `json:"expected_scheme,omitempty"`
	ExpectedHost          string `json:"expected_host,omitempty"`
	ExpectedPort          int    `json:"expected_port,omitempty"`
	ExpectedExplicitPort  bool   `json:"expected_explicit_port,omitempty"`
	ExpectedAuthority     string `json:"expected_authority,omitempty"`
	ExpectedNormalizedURL string `json:"expected_normalized_url,omitempty"`
	ExpectedIsIPLiteral   bool   `json:"expected_is_ip_literal,omitempty"`
	LabelLength           int    `json:"label_length,omitempty"`
	HostLength            int    `json:"host_length,omitempty"`
	PathLength            int    `json:"path_length,omitempty"`
}

type ipCase struct {
	ID               string `json:"id"`
	Address          string `json:"address"`
	ExpectedCategory string `json:"expected_category"`
	ExpectedAllowed  bool   `json:"expected_allowed"`
}

type dnsCase struct {
	ID                string   `json:"id"`
	Host              string   `json:"host"`
	Addresses         []string `json:"addresses"`
	ResolverBehavior  string   `json:"resolver_behavior,omitempty"`
	ExpectedReason    string   `json:"expected_reason"`
	ExpectedAddresses []string `json:"expected_addresses"`
	MaxDNSAddresses   int      `json:"max_dns_addresses,omitempty"`
}

type policyObject struct {
	AllowedHosts              []string         `json:"allowed_hosts"`
	AllowedHTTP               bool             `json:"allowed_http"`
	AllowedPortsByScheme      map[string][]int `json:"allowed_ports_by_scheme"`
	MaxDNSAddresses           int              `json:"max_dns_addresses"`
	AllowControlledSubdomains bool             `json:"allow_controlled_subdomains"`
}

type policyCase struct {
	ID                string       `json:"id"`
	Raw               string       `json:"raw"`
	Previous          string       `json:"previous,omitempty"`
	Addresses         []string     `json:"addresses"`
	Policy            policyObject `json:"policy"`
	ExpectedReason    string       `json:"expected_reason"`
	ExpectedAddresses []string     `json:"expected_addresses"`
}

type securityFixture struct {
	URLCases      []urlCase    `json:"url_cases"`
	IPCases       []ipCase     `json:"ip_cases"`
	DNSCases      []dnsCase    `json:"dns_cases"`
	PolicyCases   []policyCase `json:"policy_cases"`
	RedirectCases []policyCase `json:"redirect_cases"`
}

func fixturePath(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "tests", "fixtures", "outbound_request_security_contract.json")
}

func loadFixture(t *testing.T) securityFixture {
	t.Helper()
	data, err := os.ReadFile(fixturePath(t))
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	var fixture securityFixture
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode fixture: %v", err)
	}
	return fixture
}

type fakeResolver struct {
	addresses []string
	behavior  string
	calls     int32
}

func (f *fakeResolver) Resolve(_ context.Context, _ string) ([]string, error) {
	atomic.AddInt32(&f.calls, 1)
	switch f.behavior {
	case "timeout":
		return nil, context.DeadlineExceeded
	case "error":
		return nil, context.Canceled
	default:
		return append([]string(nil), f.addresses...), nil
	}
}

func (f *fakeResolver) callCount() int {
	return int(atomic.LoadInt32(&f.calls))
}

func expandRaw(tc urlCase) string {
	raw := tc.Raw
	if tc.LabelLength > 0 {
		raw = strings.ReplaceAll(raw, "@label@", strings.Repeat("a", tc.LabelLength))
	}
	if tc.HostLength > 0 {
		raw = strings.ReplaceAll(raw, "@host@", strings.Repeat("a", tc.HostLength))
	}
	if tc.PathLength > 0 {
		raw = strings.ReplaceAll(raw, "@path@", strings.Repeat("a", tc.PathLength))
	}
	return raw
}

func makePolicy(p policyObject) OutboundPolicy {
	return NewOutboundPolicy(OutboundPolicyConfig{
		AllowedHosts:              p.AllowedHosts,
		AllowedHTTP:               p.AllowedHTTP,
		AllowedPortsByScheme:      p.AllowedPortsByScheme,
		MaxDNSAddresses:           p.MaxDNSAddresses,
		AllowControlledSubdomains: p.AllowControlledSubdomains,
	})
}

func TestFixtureCaseCountAndUniqueIDs(t *testing.T) {
	fixture := loadFixture(t)
	total := len(fixture.URLCases) + len(fixture.IPCases) + len(fixture.DNSCases) + len(fixture.PolicyCases) + len(fixture.RedirectCases)
	if total < 120 {
		t.Fatalf("fixture has %d cases, want at least 120", total)
	}
	seen := make(map[string]struct{})
	for _, group := range [][]urlCase{} {
		_ = group
	}
	all := func(id string) {
		if _, ok := seen[id]; ok {
			t.Fatalf("duplicate fixture id %q", id)
		}
		seen[id] = struct{}{}
	}
	for _, c := range fixture.URLCases {
		all(c.ID)
	}
	for _, c := range fixture.IPCases {
		all(c.ID)
	}
	for _, c := range fixture.DNSCases {
		all(c.ID)
	}
	for _, c := range fixture.PolicyCases {
		all(c.ID)
	}
	for _, c := range fixture.RedirectCases {
		all(c.ID)
	}
}

func TestFixtureURLCases(t *testing.T) {
	fixture := loadFixture(t)
	for _, tc := range fixture.URLCases {
		t.Run(tc.ID, func(t *testing.T) {
			raw := expandRaw(tc)
			normalized, err := NormalizeOutboundURL(raw)
			if tc.ExpectedReason != "" {
				if err == nil {
					t.Fatalf("expected %q, got accepted URL %q", tc.ExpectedReason, normalized.NormalizedURL)
				}
				if got := reasonCode(err); got != tc.ExpectedReason {
					t.Fatalf("expected reason %q, got %q", tc.ExpectedReason, got)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error %v", err)
			}
			if normalized.Scheme != tc.ExpectedScheme || normalized.Host != tc.ExpectedHost || normalized.Port != tc.ExpectedPort || normalized.ExplicitPort != tc.ExpectedExplicitPort || normalized.Authority != tc.ExpectedAuthority || normalized.NormalizedURL != tc.ExpectedNormalizedURL || normalized.IsIPLiteral != tc.ExpectedIsIPLiteral {
				t.Fatalf("mismatch: %+v", normalized)
			}
		})
	}
}

func TestFixtureIPCases(t *testing.T) {
	fixture := loadFixture(t)
	for _, tc := range fixture.IPCases {
		t.Run(tc.ID, func(t *testing.T) {
			classification, err := ClassifyIP(tc.Address)
			if err != nil {
				t.Fatalf("classify %q: %v", tc.Address, err)
			}
			if classification.Category != tc.ExpectedCategory || classification.Allowed != tc.ExpectedAllowed {
				t.Fatalf("mismatch: %+v", classification)
			}
		})
	}
}

func TestFixtureDNSCases(t *testing.T) {
	fixture := loadFixture(t)
	for _, tc := range fixture.DNSCases {
		t.Run(tc.ID, func(t *testing.T) {
			resolver := &fakeResolver{addresses: tc.Addresses, behavior: tc.ResolverBehavior}
			max := tc.MaxDNSAddresses
			if max == 0 {
				max = 16
			}
			result, err := ResolveAndValidate(context.Background(), tc.Host, resolver, max)
			if tc.ExpectedReason != "" {
				if err == nil && result.Allowed {
					t.Fatalf("expected rejection %q", tc.ExpectedReason)
				}
				if err != nil {
					if got := reasonCode(err); got != tc.ExpectedReason {
						t.Fatalf("expected reason %q, got %q", tc.ExpectedReason, got)
					}
				} else if result.ReasonCode != tc.ExpectedReason {
					t.Fatalf("expected reason %q, got %q", tc.ExpectedReason, result.ReasonCode)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error %v", err)
			}
			if !result.Allowed || len(result.Addresses) != len(tc.ExpectedAddresses) {
				t.Fatalf("mismatch: %+v", result)
			}
			for i := range result.Addresses {
				if result.Addresses[i] != tc.ExpectedAddresses[i] {
					t.Fatalf("address order mismatch: %v", result.Addresses)
				}
			}
		})
	}
}

func TestFixturePolicyCases(t *testing.T) {
	fixture := loadFixture(t)
	for _, tc := range fixture.PolicyCases {
		t.Run(tc.ID, func(t *testing.T) {
			resolver := &fakeResolver{addresses: tc.Addresses}
			decision, err := DecidePolicy(tc.Raw, makePolicy(tc.Policy), resolver)
			if err != nil {
				t.Fatalf("decide error: %v", err)
			}
			if decision.ReasonCode != tc.ExpectedReason {
				t.Fatalf("expected reason %q, got %q", tc.ExpectedReason, decision.ReasonCode)
			}
			if len(decision.Addresses) != len(tc.ExpectedAddresses) {
				t.Fatalf("addresses mismatch: %v", decision.Addresses)
			}
			for i := range decision.Addresses {
				if decision.Addresses[i] != tc.ExpectedAddresses[i] {
					t.Fatalf("address order mismatch: %v", decision.Addresses)
				}
			}
		})
	}
}

func TestFixtureRedirectCases(t *testing.T) {
	fixture := loadFixture(t)
	for _, tc := range fixture.RedirectCases {
		t.Run(tc.ID, func(t *testing.T) {
			resolver := &fakeResolver{addresses: tc.Addresses}
			decision, err := DecideRedirect(tc.Previous, tc.Raw, makePolicy(tc.Policy), resolver)
			if err != nil {
				t.Fatalf("decide redirect error: %v", err)
			}
			if decision.ReasonCode != tc.ExpectedReason {
				t.Fatalf("expected reason %q, got %q", tc.ExpectedReason, decision.ReasonCode)
			}
			if len(decision.Addresses) != len(tc.ExpectedAddresses) {
				t.Fatalf("addresses mismatch: %v", decision.Addresses)
			}
			for i := range decision.Addresses {
				if decision.Addresses[i] != tc.ExpectedAddresses[i] {
					t.Fatalf("address order mismatch: %v", decision.Addresses)
				}
			}
		})
	}
}
