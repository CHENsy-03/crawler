package security

import (
	"context"
	"testing"
)

type d1FakeResolver struct {
	addresses map[string][]string
	calls     int
}

func (r *d1FakeResolver) Resolve(_ context.Context, host string) ([]string, error) {
	r.calls++
	return append([]string(nil), r.addresses[host]...), nil
}

func TestD1RedirectCases(t *testing.T) {
	fixture := loadD1Fixture(t)
	executed := make(map[string]bool)
	expected := make(map[string]bool)
	for _, tc := range fixture.RedirectCases {
		expected[tc.ID] = true
	}
	for _, tc := range fixture.RedirectCases {
		t.Run(tc.ID, func(t *testing.T) {
			policy := makePolicy(tc.Policy)
			resolver := &d1FakeResolver{addresses: tc.Addresses}
			action := tc.Action
			if action == "multi_hop" {
				plan, err := PlanRedirects(tc.Current, tc.Locations, policy, resolver)
				if tc.ExpectedReason != "" {
					if d1Reason(t, err) != tc.ExpectedReason {
						t.Fatalf("reason = %q, want %q", d1Reason(t, err), tc.ExpectedReason)
					}
				} else {
					if err != nil {
						t.Fatalf("plan redirects: %v", err)
					}
					if len(plan.Hops) != len(tc.Locations) {
						t.Fatalf("hops = %d, want %d", len(plan.Hops), len(tc.Locations))
					}
					last := plan.Hops[len(plan.Hops)-1]
					if last.URL != tc.ExpectedFinalURL {
						t.Fatalf("final URL = %q, want %q", last.URL, tc.ExpectedFinalURL)
					}
					if len(plan.Hops) >= 2 && &plan.Hops[0].Target == &plan.Hops[1].Target {
						t.Fatalf("hops reused the same PinnedTarget storage")
					}
				}
				if resolver.calls != tc.ExpectedResolverCalls {
					t.Fatalf("resolver calls = %d, want %d", resolver.calls, tc.ExpectedResolverCalls)
				}
				executed[tc.ID] = true
				return
			}

			location, ok := tc.Location.(string)
			if !ok {
				_, err := ResolveRedirectLocationValue(tc.Current, tc.Location)
				if d1Reason(t, err) != tc.ExpectedReason {
					t.Fatalf("reason = %q, want %q", d1Reason(t, err), tc.ExpectedReason)
				}
				if resolver.calls != 0 {
					t.Fatalf("resolver called for non-string location")
				}
				executed[tc.ID] = true
				return
			}

			hop, err := PlanRedirectHop(tc.Current, location, policy, resolver, tc.Hop)
			if tc.ExpectedReason != "" {
				if d1Reason(t, err) != tc.ExpectedReason {
					t.Fatalf("reason = %q, want %q", d1Reason(t, err), tc.ExpectedReason)
				}
				if resolver.calls != tc.ExpectedResolverCalls {
					t.Fatalf("resolver calls = %d, want %d", resolver.calls, tc.ExpectedResolverCalls)
				}
				executed[tc.ID] = true
				return
			}
			if err != nil {
				t.Fatalf("plan hop: %v", err)
			}
			if hop.URL != tc.ExpectedURL {
				t.Fatalf("URL = %q, want %q", hop.URL, tc.ExpectedURL)
			}
			if len(hop.Addresses) != len(tc.ExpectedAddresses) {
				t.Fatalf("addresses = %v, want %v", hop.Addresses, tc.ExpectedAddresses)
			}
			for i := range tc.ExpectedAddresses {
				if hop.Addresses[i] != tc.ExpectedAddresses[i] {
					t.Fatalf("addresses = %v, want %v", hop.Addresses, tc.ExpectedAddresses)
				}
			}
			if !hop.Decision.Allowed {
				t.Fatalf("decision not allowed")
			}
			if resolver.calls != tc.ExpectedResolverCalls {
				t.Fatalf("resolver calls = %d, want %d", resolver.calls, tc.ExpectedResolverCalls)
			}
			executed[tc.ID] = true
		})
	}
	for id := range expected {
		if !executed[id] {
			t.Fatalf("redirect case %s was not executed", id)
		}
	}
}

func TestD1RedirectDeterministic(t *testing.T) {
	fixture := loadD1Fixture(t)
	var tc d1RedirectCase
	for _, candidate := range fixture.RedirectCases {
		if candidate.ID == "redirect-001" {
			tc = candidate
			break
		}
	}
	location, ok := tc.Location.(string)
	if !ok {
		t.Fatalf("redirect-001 location is not a string")
	}
	policy := makePolicy(tc.Policy)
	first, err := PlanRedirectHop(tc.Current, location, policy, &d1FakeResolver{addresses: tc.Addresses}, 1)
	if err != nil {
		t.Fatalf("first: %v", err)
	}
	second, err := PlanRedirectHop(tc.Current, location, policy, &d1FakeResolver{addresses: tc.Addresses}, 1)
	if err != nil {
		t.Fatalf("second: %v", err)
	}
	if first.URL != second.URL {
		t.Fatalf("urls differ: %q vs %q", first.URL, second.URL)
	}
	if len(first.Addresses) != len(second.Addresses) {
		t.Fatalf("addresses differ")
	}
	for i := range first.Addresses {
		if first.Addresses[i] != second.Addresses[i] {
			t.Fatalf("addresses differ")
		}
	}
}
