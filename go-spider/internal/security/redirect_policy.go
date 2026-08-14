package security

import (
	"net/url"
	"strings"
	"unicode"
)

// RedirectPolicyError is a stable redirect planning failure.
type RedirectPolicyError struct {
	ReasonCode string
}

func (e *RedirectPolicyError) Error() string { return e.ReasonCode }

func redirectFail(reason string) error { return &RedirectPolicyError{ReasonCode: reason} }

// RedirectHop is one fully revalidated redirect hop.
type RedirectHop struct {
	Hop       int
	URL       string
	Decision  PolicyDecision
	Target    PinnedTarget
	Addresses []string
}

// RedirectPlan is an ordered list of planned redirect hops.
type RedirectPlan struct {
	Hops []RedirectHop
}

var redirectSyntaxReasons = map[string]bool{
	"absolute_url_required":    true,
	"ambiguous_ip_literal":     true,
	"authority_required":       true,
	"backslash_not_allowed":    true,
	"control_character":        true,
	"empty_url":                true,
	"host_too_long":            true,
	"invalid_host":             true,
	"invalid_idna":             true,
	"invalid_percent_encoding": true,
	"invalid_port":             true,
	"invalid_scheme":           true,
	"invalid_url":              true,
	"label_too_long":           true,
	"scheme_not_allowed":       true,
	"url_too_long":             true,
}

func normalizeRedirectReason(reason string) string {
	if redirectSyntaxReasons[reason] {
		return "redirect_location_invalid"
	}
	return reason
}

func containsControlOrFormat(value string) bool {
	for _, r := range value {
		if unicode.IsControl(r) || unicode.Is(unicode.Cf, r) {
			return true
		}
	}
	return false
}

// ResolveRedirectLocation resolves relative Locations against the current URL.
func ResolveRedirectLocation(currentURL, location string) (string, error) {
	if location == "" || strings.TrimSpace(location) == "" {
		return "", redirectFail("redirect_location_missing")
	}
	if location != strings.TrimSpace(location) {
		return "", redirectFail("redirect_location_invalid")
	}
	if containsControlOrFormat(location) {
		return "", redirectFail("redirect_location_invalid")
	}
	base, err := url.Parse(currentURL)
	if err != nil {
		return "", redirectFail("redirect_location_invalid")
	}
	ref, err := url.Parse(location)
	if err != nil {
		return "", redirectFail("redirect_location_invalid")
	}
	resolved := base.ResolveReference(ref)
	if !resolved.IsAbs() {
		return "", redirectFail("redirect_location_invalid")
	}
	return resolved.String(), nil
}

// ResolveRedirectLocationValue validates JSON-style Location values at the
// shared fixture boundary while keeping PlanRedirectHop strongly typed.
func ResolveRedirectLocationValue(currentURL string, location any) (string, error) {
	if location == nil {
		return "", redirectFail("redirect_location_missing")
	}
	text, ok := location.(string)
	if !ok {
		return "", redirectFail("redirect_location_invalid")
	}
	return ResolveRedirectLocation(currentURL, text)
}

// PlanRedirectHop revalidates one redirect hop with a fresh DNS/policy decision
// and a fresh PinnedTarget.
func PlanRedirectHop(currentURL, location string, policy OutboundPolicy, resolver Resolver, hop int) (RedirectHop, error) {
	if hop <= 0 {
		return RedirectHop{}, redirectFail("invalid_redirect_hop")
	}
	if hop > MaxRedirects {
		return RedirectHop{}, redirectFail("redirect_limit_exceeded")
	}
	targetRaw, err := ResolveRedirectLocation(currentURL, location)
	if err != nil {
		return RedirectHop{}, err
	}
	decision, err := DecideRedirect(currentURL, targetRaw, policy, resolver)
	if err != nil {
		return RedirectHop{}, redirectFail("redirect_location_invalid")
	}
	if !decision.Allowed {
		return RedirectHop{}, redirectFail(normalizeRedirectReason(decision.ReasonCode))
	}
	if decision.Normalized == nil {
		return RedirectHop{}, redirectFail("redirect_location_invalid")
	}
	target, err := NewPinnedTarget(decision, policy)
	if err != nil {
		return RedirectHop{}, err
	}
	return RedirectHop{
		Hop:       hop,
		URL:       decision.Normalized.NormalizedURL,
		Decision:  decision,
		Target:    target,
		Addresses: append([]string(nil), decision.Addresses...),
	}, nil
}

// PlanRedirects revalidates a sequence of redirect Locations.
func PlanRedirects(currentURL string, locations []string, policy OutboundPolicy, resolver Resolver) (RedirectPlan, error) {
	hops := make([]RedirectHop, 0, len(locations))
	current := currentURL
	for index, location := range locations {
		hopNumber := index + 1
		if hopNumber > MaxRedirects {
			return RedirectPlan{}, redirectFail("redirect_limit_exceeded")
		}
		hop, err := PlanRedirectHop(current, location, policy, resolver, hopNumber)
		if err != nil {
			return RedirectPlan{}, err
		}
		hops = append(hops, hop)
		current = hop.URL
	}
	return RedirectPlan{Hops: hops}, nil
}
