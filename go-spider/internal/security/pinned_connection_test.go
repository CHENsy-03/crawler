package security

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"errors"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type pinnedPlanCase struct {
	ID                  string       `json:"id"`
	Raw                 string       `json:"raw"`
	Addresses           []string     `json:"addresses"`
	Forged              bool         `json:"forged,omitempty"`
	Policy              policyObject `json:"policy"`
	ExpectedScheme      string       `json:"expected_scheme,omitempty"`
	ExpectedHost        string       `json:"expected_host,omitempty"`
	ExpectedPort        int          `json:"expected_port,omitempty"`
	ExpectedAuthority   string       `json:"expected_authority,omitempty"`
	ExpectedHostHeader  string       `json:"expected_host_header,omitempty"`
	ExpectedServerName  string       `json:"expected_server_name,omitempty"`
	ExpectedAddresses   []string     `json:"expected_addresses,omitempty"`
	ExpectedIsIPLiteral bool         `json:"expected_is_ip_literal,omitempty"`
	ExpectedReason      string       `json:"expected_reason,omitempty"`
}

type pinnedHostHeaderCase struct {
	ID             string `json:"id"`
	Scheme         string `json:"scheme"`
	Host           string `json:"host"`
	Port           int    `json:"port"`
	RequestHost    string `json:"request_host"`
	Expected       string `json:"expected,omitempty"`
	ExpectedReason string `json:"expected_reason,omitempty"`
}

type pinnedDialCase struct {
	ID               string   `json:"id"`
	Addresses        []string `json:"addresses"`
	Port             int      `json:"port"`
	FailFirst        bool     `json:"fail_first,omitempty"`
	FailAll          bool     `json:"fail_all,omitempty"`
	ExpectedSequence []string `json:"expected_sequence"`
	ExpectedReason   string   `json:"expected_reason,omitempty"`
}

type pinnedAuthorityCase struct {
	ID               string `json:"id"`
	RequestAuthority string `json:"request_authority"`
	Scheme           string `json:"scheme"`
	Host             string `json:"host"`
	Port             int    `json:"port"`
	ExpectedReason   string `json:"expected_reason"`
}

type pinnedTLSCase struct {
	ID                 string `json:"id"`
	ServerName         string `json:"server_name"`
	ExpectedServerName string `json:"expected_server_name"`
	InsecureSkipVerify bool   `json:"insecure_skip_verify"`
	ExpectedReason     string `json:"expected_reason"`
}

type pinnedFixture struct {
	PlanCases       []pinnedPlanCase       `json:"plan_cases"`
	HostHeaderCases []pinnedHostHeaderCase `json:"host_header_cases"`
	DialCases       []pinnedDialCase       `json:"dial_cases"`
	AuthorityCases  []pinnedAuthorityCase  `json:"authority_cases"`
	TLSCases        []pinnedTLSCase        `json:"tls_cases"`
}

func pinnedFixturePath(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "tests", "fixtures", "pinned_connection_contract.json")
}

func loadPinnedFixture(t *testing.T) pinnedFixture {
	t.Helper()
	data, err := os.ReadFile(pinnedFixturePath(t))
	if err != nil {
		t.Fatalf("read pinned fixture: %v", err)
	}
	var fixture pinnedFixture
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode pinned fixture: %v", err)
	}
	return fixture
}

func TestPinnedPlanCases(t *testing.T) {
	fixture := loadPinnedFixture(t)
	for _, tc := range fixture.PlanCases {
		t.Run(tc.ID, func(t *testing.T) {
			policy := makePolicy(tc.Policy)
			var decision PolicyDecision
			if tc.Forged {
				normalized, err := NormalizeOutboundURL(tc.Raw)
				if err != nil {
					t.Fatalf("normalize: %v", err)
				}
				decision = PolicyDecision{Allowed: true, Normalized: &normalized, Addresses: tc.Addresses}
			} else {
				resolver := &fakeResolver{addresses: tc.Addresses}
				var err error
				decision, err = DecidePolicy(tc.Raw, policy, resolver)
				if err != nil {
					t.Fatalf("decide: %v", err)
				}
			}
			target, err := NewPinnedTarget(decision, policy)
			if tc.ExpectedReason != "" {
				if err == nil || pinnedReason(err) != tc.ExpectedReason {
					t.Fatalf("want %q, got %v", tc.ExpectedReason, err)
				}
				return
			}
			if err != nil {
				t.Fatalf("build target: %v", err)
			}
			if target.Scheme() != tc.ExpectedScheme || target.NormalizedHost() != tc.ExpectedHost || target.Port() != tc.ExpectedPort || target.Authority() != tc.ExpectedAuthority || target.HostHeader() != tc.ExpectedHostHeader || target.ServerName() != tc.ExpectedServerName || target.IsIPLiteral() != tc.ExpectedIsIPLiteral {
				t.Fatalf("target mismatch: %+v", target)
			}
			got := target.ValidatedAddresses()
			if len(got) != len(tc.ExpectedAddresses) {
				t.Fatalf("addresses mismatch: %v", got)
			}
			for i := range got {
				if got[i] != tc.ExpectedAddresses[i] {
					t.Fatalf("address order mismatch: %v", got)
				}
			}
		})
	}
}

func TestPinnedHostHeaderCases(t *testing.T) {
	fixture := loadPinnedFixture(t)
	for _, tc := range fixture.HostHeaderCases {
		t.Run(tc.ID, func(t *testing.T) {
			addresses := []string{"93.184.216.34"}
			if strings.Contains(tc.Host, ":") {
				addresses = []string{"2606:4700:4700::1111"}
			}
			target, err := newPinnedTargetForTest(tc.Scheme, tc.Host, tc.Port, addresses)
			if err != nil {
				t.Fatalf("target: %v", err)
			}
			header, err := PrepareRequestHostHeader(tc.RequestHost, target)
			if tc.ExpectedReason != "" {
				if err == nil || pinnedReason(err) != tc.ExpectedReason {
					t.Fatalf("want %q, got %v", tc.ExpectedReason, err)
				}
				return
			}
			if err != nil || header != tc.Expected {
				t.Fatalf("header mismatch: %q %v", header, err)
			}
		})
	}
}

type recordingDialer struct {
	records   []string
	networks  []string
	failFirst bool
	failAll   bool
}

func (d *recordingDialer) DialContext(ctx context.Context, network, address string) (net.Conn, error) {
	d.records = append(d.records, address)
	d.networks = append(d.networks, network)
	if d.failAll || (d.failFirst && len(d.records) == 1) {
		return nil, errors.New("dial failed")
	}
	c1, _ := net.Pipe()
	return c1, nil
}

func TestPinnedDialCases(t *testing.T) {
	fixture := loadPinnedFixture(t)
	for _, tc := range fixture.DialCases {
		t.Run(tc.ID, func(t *testing.T) {
			var target PinnedTarget
			var err error
			if len(tc.Addresses) == 0 {
				target = PinnedTarget{}
			} else {
				target, err = newPinnedTargetForTest("https", "fixture.example", tc.Port, tc.Addresses)
				if err != nil {
					t.Fatalf("target: %v", err)
				}
			}
			dialer := &recordingDialer{failFirst: tc.FailFirst, failAll: tc.FailAll}
			_, err = DialPinned(context.Background(), target, dialer.DialContext)
			if tc.ExpectedReason != "" {
				if err == nil || pinnedReason(err) != tc.ExpectedReason {
					t.Fatalf("want %q, got %v", tc.ExpectedReason, err)
				}
				return
			}
			if err != nil {
				t.Fatalf("dial: %v", err)
			}
			sequence := make([]string, 0, len(dialer.records))
			for _, record := range dialer.records {
				host, _, splitErr := net.SplitHostPort(record)
				if splitErr != nil {
					t.Fatalf("split record: %v", splitErr)
				}
				sequence = append(sequence, host)
			}
			if len(sequence) != len(tc.ExpectedSequence) {
				t.Fatalf("sequence mismatch: %v", sequence)
			}
			for i := range sequence {
				if sequence[i] != tc.ExpectedSequence[i] {
					t.Fatalf("sequence mismatch: %v", sequence)
				}
			}
		})
	}
}

func TestPinnedAuthorityCases(t *testing.T) {
	fixture := loadPinnedFixture(t)
	for _, tc := range fixture.AuthorityCases {
		t.Run(tc.ID, func(t *testing.T) {
			target, err := newPinnedTargetForTest(tc.Scheme, tc.Host, tc.Port, []string{"93.184.216.34"})
			if err != nil {
				t.Fatalf("target: %v", err)
			}
			err = ValidateRequestAuthority(tc.RequestAuthority, target)
			if tc.ExpectedReason == "" {
				if err != nil {
					t.Fatalf("unexpected error: %v", err)
				}
				return
			}
			if err == nil || pinnedReason(err) != tc.ExpectedReason {
				t.Fatalf("want %q, got %v", tc.ExpectedReason, err)
			}
		})
	}
}

func TestPinnedTLSCases(t *testing.T) {
	fixture := loadPinnedFixture(t)
	for _, tc := range fixture.TLSCases {
		t.Run(tc.ID, func(t *testing.T) {
			cfg := &tls.Config{ServerName: tc.ServerName, InsecureSkipVerify: tc.InsecureSkipVerify}
			err := ValidateTLSConfig(cfg, tc.ExpectedServerName)
			if tc.ExpectedReason == "" {
				if err != nil {
					t.Fatalf("unexpected error: %v", err)
				}
				return
			}
			if err == nil || pinnedReason(err) != tc.ExpectedReason {
				t.Fatalf("want %q, got %v", tc.ExpectedReason, err)
			}
		})
	}
}

func TestPinnedDialContextCancel(t *testing.T) {
	target, err := newPinnedTargetForTest("https", "fixture.example", 443, []string{"93.184.216.34"})
	if err != nil {
		t.Fatalf("target: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	dialer := &recordingDialer{}
	_, err = DialPinned(ctx, target, dialer.DialContext)
	if err == nil || pinnedReason(err) != "connection_failed" {
		t.Fatalf("expected connection_failed, got %v", err)
	}
	if dialer.records != nil {
		t.Fatalf("dialer was called after cancellation")
	}
}

func TestPinnedDialNetworkVersion(t *testing.T) {
	v4, err := newPinnedTargetForTest("https", "fixture.example", 443, []string{"93.184.216.34"})
	if err != nil {
		t.Fatalf("target: %v", err)
	}
	dialer := &recordingDialer{}
	conn, err := DialPinned(context.Background(), v4, dialer.DialContext)
	if err != nil {
		t.Fatalf("dial v4: %v", err)
	}
	_ = conn.Close()
	if len(dialer.networks) != 1 || dialer.networks[0] != "tcp4" {
		t.Fatalf("network = %v", dialer.networks)
	}

	v6, err := newPinnedTargetForTest("https", "fixture.example", 443, []string{"2606:4700:4700::1111"})
	if err != nil {
		t.Fatalf("target: %v", err)
	}
	dialer = &recordingDialer{}
	conn, err = DialPinned(context.Background(), v6, dialer.DialContext)
	if err != nil {
		t.Fatalf("dial v6: %v", err)
	}
	_ = conn.Close()
	if len(dialer.networks) != 1 || dialer.networks[0] != "tcp6" {
		t.Fatalf("network = %v", dialer.networks)
	}
}

func pinnedReason(err error) string {
	if e, ok := err.(*PinnedConnectionError); ok {
		return e.ReasonCode
	}
	return ""
}

func TestProductionHasNoTestHelper(t *testing.T) {
	for _, name := range []string{"pinned_target.go", "pinned_dialer.go", "pinned_transport.go"} {
		data, err := os.ReadFile(name)
		if err != nil {
			t.Fatalf("read %s: %v", name, err)
		}
		if strings.Contains(string(data), "newPinnedTargetForTest") {
			t.Fatalf("%s contains test helper", name)
		}
	}
}

func TestProductionBuilderRejectsLoopback(t *testing.T) {
	normalized, err := NormalizeOutboundURL("https://example.com/")
	if err != nil {
		t.Fatalf("normalize: %v", err)
	}
	decision := PolicyDecision{Allowed: true, Normalized: &normalized, Addresses: []string{"127.0.0.1"}}
	_, err = NewPinnedTarget(decision, DefaultOutboundPolicy())
	if err == nil || pinnedReason(err) != "ip_not_allowed" {
		t.Fatalf("expected ip_not_allowed, got %v", err)
	}
}
