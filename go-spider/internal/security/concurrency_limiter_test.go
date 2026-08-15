package security

import (
	"sync"
	"testing"
)

func TestD2ConcurrencyCases(t *testing.T) {
	fixture := loadRuntimeLimitsFixture(t)
	executed := make(map[string]bool)
	expected := make(map[string]bool)
	for _, tc := range fixture.ConcurrencyCases {
		expected[tc.ID] = true
	}
	for _, tc := range fixture.ConcurrencyCases {
		t.Run(tc.ID, func(t *testing.T) {
			limiter := NewConcurrencyLimiter()
			switch tc.Action {
			case "same_host_1":
				lease, err := limiter.Acquire("example.com")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				if limiter.ActiveCount() != 1 {
					t.Fatalf("active = %d", limiter.ActiveCount())
				}
				lease.Release()
				if limiter.ActiveCount() != 0 {
					t.Fatalf("active after release = %d", limiter.ActiveCount())
				}
			case "same_host_5", "same_host_6":
				leases := make([]Lease, 0, 5)
				for i := 0; i < 5; i++ {
					lease, err := limiter.Acquire("example.com")
					if err != nil {
						t.Fatalf("acquire %d: %v", i, err)
					}
					leases = append(leases, lease)
				}
				_, err := limiter.Acquire("example.com")
				if d2Reason(t, err) != "host_concurrency_exceeded" {
					t.Fatalf("reason = %q", d2Reason(t, err))
				}
				for i := range leases {
					leases[i].Release()
				}
			case "multi_host_20", "multi_host_21":
				leases := make([]Lease, 0, 20)
				for i := 0; i < 20; i++ {
					lease, err := limiter.Acquire(string(rune('a'+i)) + ".example")
					if err != nil {
						t.Fatalf("acquire %d: %v", i, err)
					}
					leases = append(leases, lease)
				}
				_, err := limiter.Acquire("extra.example")
				if d2Reason(t, err) != "global_concurrency_exceeded" {
					t.Fatalf("reason = %q", d2Reason(t, err))
				}
				for i := range leases {
					leases[i].Release()
				}
			case "case_normalization":
				a, err := limiter.Acquire("Example.COM")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				b, err := limiter.Acquire("example.com")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				if limiter.HostCount("example.com") != 2 {
					t.Fatalf("host count = %d", limiter.HostCount("example.com"))
				}
				a.Release()
				b.Release()
			case "port_independent":
				_, err := limiter.Acquire("example.com:8443")
				if d2Reason(t, err) != "invalid_host_key" {
					t.Fatalf("reason = %q", d2Reason(t, err))
				}
			case "invalid_empty", "invalid_space", "invalid_control", "invalid_unicode", "leading_hyphen", "trailing_hyphen", "nested_leading_hyphen", "nested_trailing_hyphen", "single_hyphen", "hyphen_root_dot", "hyphen_leading_root_dot", "bare_punycode", "root_dot_invalid_hyphen":
				_, err := limiter.Acquire(tc.Host)
				if d2Reason(t, err) != "invalid_host_key" {
					t.Fatalf("reason = %q", d2Reason(t, err))
				}
			case "release_reacquire":
				lease, err := limiter.Acquire("example.com")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				lease.Release()
				lease2, err := limiter.Acquire("example.com")
				if err != nil {
					t.Fatalf("reacquire: %v", err)
				}
				if limiter.ActiveCount() != 1 {
					t.Fatalf("active = %d", limiter.ActiveCount())
				}
				lease2.Release()
			case "double_release":
				lease, err := limiter.Acquire("example.com")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				lease.Release()
				lease.Release()
				if limiter.ActiveCount() != 0 {
					t.Fatalf("active = %d", limiter.ActiveCount())
				}
			case "host_entry_cleanup":
				lease, err := limiter.Acquire("example.com")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				lease.Release()
				if limiter.HostCount("example.com") != 0 {
					t.Fatalf("host count = %d", limiter.HostCount("example.com"))
				}
			case "ip_literal":
				lease, err := limiter.Acquire("2606:4700:4700::1111")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				if limiter.HostCount("2606:4700:4700::1111") != 1 {
					t.Fatalf("host count = %d", limiter.HostCount("2606:4700:4700::1111"))
				}
				lease.Release()
			case "forged_lease":
				lease := Lease{}
				lease.Release()
				if limiter.ActiveCount() != 0 {
					t.Fatalf("active = %d", limiter.ActiveCount())
				}
			case "copied_lease", "deepcopy_lease":
				lease, err := limiter.Acquire("example.com")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				cloned := lease
				lease.Release()
				cloned.Release()
				if limiter.ActiveCount() != 0 {
					t.Fatalf("active = %d", limiter.ActiveCount())
				}
			case "cross_limiter":
				other := NewConcurrencyLimiter()
				lease := Lease{}
				lease.Release()
				if limiter.ActiveCount() != 0 || other.ActiveCount() != 0 {
					t.Fatalf("cross limiter counts changed")
				}
			case "context_normal":
				lease, err := limiter.Acquire("example.com")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				func() {
					defer lease.Release()
					if limiter.ActiveCount() != 1 {
						t.Fatalf("active = %d", limiter.ActiveCount())
					}
				}()
				if limiter.ActiveCount() != 0 {
					t.Fatalf("active = %d", limiter.ActiveCount())
				}
			case "context_exception":
				lease, err := limiter.Acquire("example.com")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				func() {
					defer func() {
						lease.Release()
						_ = recover()
					}()
					panic("boom")
				}()
				if limiter.ActiveCount() != 0 {
					t.Fatalf("active = %d", limiter.ActiveCount())
				}
			case "root_dot_alias":
				a, err := limiter.Acquire("example.com")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				b, err := limiter.Acquire("example.com.")
				if err != nil {
					t.Fatalf("acquire root dot: %v", err)
				}
				if limiter.HostCount("example.com") != 2 {
					t.Fatalf("host count = %d", limiter.HostCount("example.com"))
				}
				a.Release()
				b.Release()
			case "ambiguous_ipv4":
				_, err := limiter.Acquire(tc.Host)
				if d2Reason(t, err) != "invalid_host_key" {
					t.Fatalf("reason = %q", d2Reason(t, err))
				}
			case "equivalent_ipv6":
				a, err := limiter.Acquire("2606:4700:4700::1111")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				b, err := limiter.Acquire("2606:4700:4700:0:0:0:0:1111")
				if err != nil {
					t.Fatalf("acquire expanded: %v", err)
				}
				if limiter.HostCount("2606:4700:4700::1111") != 2 {
					t.Fatalf("host count = %d", limiter.HostCount("2606:4700:4700::1111"))
				}
				a.Release()
				b.Release()
			case "concurrent_release":
				lease, err := limiter.Acquire("example.com")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				var wg sync.WaitGroup
				for i := 0; i < 2; i++ {
					wg.Add(1)
					go func() {
						defer wg.Done()
						lease.Release()
					}()
				}
				wg.Wait()
				if limiter.ActiveCount() != 0 {
					t.Fatalf("active = %d", limiter.ActiveCount())
				}
			case "valid_internal_hyphen", "valid_punycode":
				lease, err := limiter.Acquire(tc.Host)
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				if limiter.HostCount(tc.Host) != 1 {
					t.Fatalf("host count = %d", limiter.HostCount(tc.Host))
				}
				lease.Release()
			case "lease_host_mutation":
				a, err := limiter.Acquire("example.com")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				b, err := limiter.Acquire("other.example")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				a.Release()
				if limiter.ActiveCount() != 1 || limiter.HostCount("example.com") != 0 || limiter.HostCount("other.example") != 1 {
					t.Fatalf("counts corrupted")
				}
				b.Release()
				if limiter.ActiveCount() != 0 {
					t.Fatalf("active = %d", limiter.ActiveCount())
				}
			case "lease_owner_mutation":
				other := NewConcurrencyLimiter()
				lease, err := limiter.Acquire("example.com")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				lease.Release()
				if other.ActiveCount() != 0 {
					t.Fatalf("other limiter corrupted")
				}
			case "exact_registry_identity":
				lease, err := limiter.Acquire("example.com")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				if lease.token == nil || lease.token.host != "example.com" {
					t.Fatalf("token binding missing")
				}
				lease.Release()
				if limiter.ActiveCount() != 0 {
					t.Fatalf("active = %d", limiter.ActiveCount())
				}
			default:
				t.Fatalf("unknown concurrency action %q", tc.Action)
			}
			executed[tc.ID] = true
		})
	}
	for id := range expected {
		if !executed[id] {
			t.Fatalf("concurrency case %s not executed", id)
		}
	}
}
