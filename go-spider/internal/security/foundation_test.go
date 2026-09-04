package security

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
)

func TestNormalizationIdempotent(t *testing.T) {
	raw := "HTTPS://Example.COM/a/./b/../c?q=%2b"
	first, err := NormalizeOutboundURL(raw)
	if err != nil {
		t.Fatalf("normalize: %v", err)
	}
	second, err := NormalizeOutboundURL(first.NormalizedURL)
	if err != nil {
		t.Fatalf("second normalize: %v", err)
	}
	if first.NormalizedURL != second.NormalizedURL || first.Host != second.Host || first.Port != second.Port {
		t.Fatalf("not idempotent: %+v vs %+v", first, second)
	}
}

func TestIPLiteralDoesNotCallResolver(t *testing.T) {
	resolver := &fakeResolver{addresses: []string{"8.8.8.8"}}
	result, err := ResolveAndValidate(context.Background(), "8.8.8.8", resolver, 16)
	if err != nil {
		t.Fatalf("resolve: %v", err)
	}
	if !result.Allowed {
		t.Fatalf("expected allowed")
	}
	if resolver.callCount() != 0 {
		t.Fatalf("resolver called %d times for IP literal", resolver.callCount())
	}
}

func TestFakeResolverCalledOnce(t *testing.T) {
	resolver := &fakeResolver{addresses: []string{"8.8.8.8", "1.1.1.1"}}
	_, err := ResolveAndValidate(context.Background(), "example.com", resolver, 16)
	if err != nil {
		t.Fatalf("resolve: %v", err)
	}
	if resolver.callCount() != 1 {
		t.Fatalf("resolver called %d times, want 1", resolver.callCount())
	}
}

func TestResolverTimeout(t *testing.T) {
	resolver := &fakeResolver{addresses: []string{"8.8.8.8"}, behavior: "timeout"}
	_, err := ResolveAndValidate(context.Background(), "example.com", resolver, 16)
	if err == nil || reasonCode(err) != "dns_timeout" {
		t.Fatalf("expected dns_timeout, got %v", err)
	}
}

func TestConcurrentReadOnlySafe(t *testing.T) {
	policy := NewOutboundPolicy(OutboundPolicyConfig{
		AllowedHosts:         []string{"example.com"},
		AllowedPortsByScheme: map[string][]int{"http": {80}, "https": {443}},
		MaxDNSAddresses:      16,
	})
	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if _, err := NormalizeOutboundURL("https://example.com/a/./b"); err != nil {
				t.Errorf("normalize: %v", err)
			}
			if _, err := ClassifyIP("8.8.8.8"); err != nil {
				t.Errorf("classify: %v", err)
			}
			normalized, err := NormalizeOutboundURL("https://example.com/")
			if err != nil {
				t.Errorf("normalize: %v", err)
			}
			dns := DNSValidationResult{Host: "example.com", Addresses: []string{"8.8.8.8"}, Allowed: true}
			EvaluatePolicy(normalized, dns, policy, nil)
		}()
	}
	wg.Wait()
}

func TestPolicyInputNotMutated(t *testing.T) {
	policy := NewOutboundPolicy(OutboundPolicyConfig{
		AllowedHosts:         []string{"example.com"},
		AllowedHTTP:          false,
		AllowedPortsByScheme: map[string][]int{"http": {80}, "https": {443}},
		MaxDNSAddresses:      16,
	})
	normalized, err := NormalizeOutboundURL("https://example.com/")
	if err != nil {
		t.Fatalf("normalize: %v", err)
	}
	dns := DNSValidationResult{Host: "example.com", Addresses: []string{"8.8.8.8"}, Allowed: true}
	EvaluatePolicy(normalized, dns, policy, nil)
	if hosts := policy.AllowedHosts(); len(hosts) != 1 || hosts[0] != "example.com" {
		t.Fatalf("policy mutated: %v", hosts)
	}
	ports := policy.AllowedPortsByScheme()
	if len(ports["https"]) != 1 || ports["https"][0] != 443 {
		t.Fatalf("policy ports mutated")
	}
}

func TestPolicyExternalMutationIsolation(t *testing.T) {
	hosts := []string{"example.com"}
	ports := map[string][]int{"https": {443}}
	policy := NewOutboundPolicy(OutboundPolicyConfig{
		AllowedHosts:         hosts,
		AllowedPortsByScheme: ports,
		MaxDNSAddresses:      16,
	})
	hosts[0] = "evil.example"
	ports["https"][0] = 8080
	if !policy.AllowsHost("example.com") || policy.AllowsHost("evil.example") {
		t.Fatalf("host mutation leaked into policy")
	}
	if !policy.AllowsPort("https", 443) || policy.AllowsPort("https", 8080) {
		t.Fatalf("port mutation leaked into policy")
	}
}

func TestPolicyGettersReturnCopies(t *testing.T) {
	policy := NewOutboundPolicy(OutboundPolicyConfig{
		AllowedHosts:         []string{"example.com"},
		AllowedPortsByScheme: map[string][]int{"https": {443}},
		MaxDNSAddresses:      16,
	})
	hosts := policy.AllowedHosts()
	hosts[0] = "evil.example"
	ports := policy.AllowedPortsByScheme()
	ports["https"][0] = 8080
	if !policy.AllowsHost("example.com") || !policy.AllowsPort("https", 443) {
		t.Fatalf("getter leaked mutable state")
	}
}

func TestDefaultPoliciesIndependent(t *testing.T) {
	a := DefaultOutboundPolicy()
	b := DefaultOutboundPolicy()
	aHosts := a.AllowedHosts()
	aHosts = append(aHosts, "extra.example")
	aPorts := a.AllowedPortsByScheme()
	aPorts["https"] = append(aPorts["https"], 8443)
	if len(b.AllowedHosts()) != 0 {
		t.Fatalf("default policies share host state")
	}
	if len(b.AllowedPortsByScheme()["https"]) != 1 {
		t.Fatalf("default policies share port state")
	}
}

func TestZeroValuePolicyFailClosed(t *testing.T) {
	var policy OutboundPolicy
	normalized, err := NormalizeOutboundURL("https://example.com/")
	if err != nil {
		t.Fatalf("normalize: %v", err)
	}
	dns := DNSValidationResult{Host: "example.com", Addresses: []string{"8.8.8.8"}, Allowed: true}
	decision := EvaluatePolicy(normalized, dns, policy, nil)
	if decision.Allowed || decision.ReasonCode != "host_not_allowed" {
		t.Fatalf("zero policy did not fail closed: %+v", decision)
	}
}

func TestSecurityPackageNoForbiddenImports(t *testing.T) {
	files := []string{"models.go", "url_normalizer.go", "ip_policy.go", "dns_policy.go", "outbound_policy.go"}
	for _, name := range files {
		data, err := os.ReadFile(name)
		if err != nil {
			t.Fatalf("read %s: %v", name, err)
		}
		source := string(data)
		for _, forbidden := range []string{`"net/http"`, "github.com/go-resty/resty/v2", "os/exec", "net.Dial", "http.Client"} {
			if strings.Contains(source, forbidden) {
				t.Fatalf("%s contains forbidden import/call %q", name, forbidden)
			}
		}
	}
}

func TestNoProductionWiring(t *testing.T) {
	paths := []string{
		filepath.Join("..", "client", "resty.go"),
		filepath.Join("..", "worker", "pool.go"),
		filepath.Join("..", "queue", "redis.go"),
	}
	for _, path := range paths {
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatalf("read %s: %v", path, err)
		}
		if strings.Contains(string(data), "crawler-platform/internal/security") {
			t.Fatalf("%s imports internal/security", path)
		}
	}
}

func TestPolicyDenialsDoNotCallResolver(t *testing.T) {
	policy := NewOutboundPolicy(OutboundPolicyConfig{
		AllowedHosts:         []string{"example.com"},
		AllowedHTTP:          false,
		AllowedPortsByScheme: map[string][]int{"http": {80}, "https": {443}},
		MaxDNSAddresses:      16,
	})
	httpPolicy := NewOutboundPolicy(OutboundPolicyConfig{
		AllowedHosts:         []string{"example.com"},
		AllowedHTTP:          true,
		AllowedPortsByScheme: map[string][]int{"http": {80}, "https": {443}},
		MaxDNSAddresses:      16,
	})
	tests := []struct {
		policy   OutboundPolicy
		raw      string
		previous string
		want     string
	}{
		{policy, "https://sub.example.com/", "", "host_not_allowed"},
		{policy, "http://example.com/", "", "http_not_allowed"},
		{policy, "https://example.com:8080/", "", "port_not_allowed"},
		{httpPolicy, "http://example.com/b", "https://example.com/a", "https_downgrade"},
		{policy, "https://other.example/b", "https://example.com/a", "redirect_host_not_allowed"},
	}
	for _, tc := range tests {
		resolver := &fakeResolver{addresses: []string{"8.8.8.8"}}
		var decision PolicyDecision
		if tc.previous == "" {
			decision, _ = DecidePolicy(tc.raw, tc.policy, resolver)
		} else {
			decision, _ = DecideRedirect(tc.previous, tc.raw, tc.policy, resolver)
		}
		if decision.ReasonCode != tc.want {
			t.Fatalf("want %q, got %q", tc.want, decision.ReasonCode)
		}
		if resolver.callCount() != 0 {
			t.Fatalf("resolver called %d times for %q", resolver.callCount(), tc.want)
		}
	}
}
