package security

import (
	"context"
	"time"
)

func preDNSDecision(normalized NormalizedURL, policy OutboundPolicy, previous *NormalizedURL) *PolicyDecision {
	if normalized.Scheme != "http" && normalized.Scheme != "https" {
		return &PolicyDecision{Allowed: false, ReasonCode: "scheme_not_allowed", Normalized: &normalized, Addresses: []string{}}
	}
	if normalized.Scheme == "http" && !policy.AllowedHTTP() {
		return &PolicyDecision{Allowed: false, ReasonCode: "http_not_allowed", Normalized: &normalized, Addresses: []string{}}
	}

	if previous == nil {
		if !policy.AllowsHost(normalized.Host) {
			return &PolicyDecision{Allowed: false, ReasonCode: "host_not_allowed", Normalized: &normalized, Addresses: []string{}}
		}
	} else {
		if !policy.AllowsHost(normalized.Host) {
			return &PolicyDecision{Allowed: false, ReasonCode: "redirect_host_not_allowed", Normalized: &normalized, Addresses: []string{}}
		}
	}

	if !policy.AllowsPort(normalized.Scheme, normalized.Port) {
		return &PolicyDecision{Allowed: false, ReasonCode: "port_not_allowed", Normalized: &normalized, Addresses: []string{}}
	}
	if previous != nil && previous.Scheme == "https" && normalized.Scheme == "http" {
		return &PolicyDecision{Allowed: false, ReasonCode: "https_downgrade", Normalized: &normalized, Addresses: []string{}}
	}
	return nil
}

func postDNSDecision(normalized NormalizedURL, dns DNSValidationResult) PolicyDecision {
	if !dns.Allowed {
		reason := dns.ReasonCode
		if reason == "" {
			reason = "ip_not_allowed"
		}
		return PolicyDecision{Allowed: false, ReasonCode: reason, Normalized: &normalized, Addresses: dns.Addresses}
	}
	return PolicyDecision{Allowed: true, Normalized: &normalized, Addresses: dns.Addresses}
}

func EvaluatePolicy(normalized NormalizedURL, dns DNSValidationResult, policy OutboundPolicy, previous *NormalizedURL) PolicyDecision {
	if pre := preDNSDecision(normalized, policy, previous); pre != nil {
		return *pre
	}
	return postDNSDecision(normalized, dns)
}

func DecidePolicy(raw string, policy OutboundPolicy, resolver Resolver) (PolicyDecision, error) {
	normalized, err := NormalizeOutboundURL(raw)
	if err != nil {
		return PolicyDecision{Allowed: false, ReasonCode: reasonCode(err), Normalized: nil}, nil
	}
	if pre := preDNSDecision(normalized, policy, nil); pre != nil {
		return *pre, nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	dns, err := ResolveAndValidate(ctx, normalized.Host, resolver, policy.MaxDNSAddresses())
	if err != nil {
		return PolicyDecision{Allowed: false, ReasonCode: reasonCode(err), Normalized: &normalized}, nil
	}
	return postDNSDecision(normalized, dns), nil
}

func DecideRedirect(previousRaw, targetRaw string, policy OutboundPolicy, resolver Resolver) (PolicyDecision, error) {
	previous, err := NormalizeOutboundURL(previousRaw)
	if err != nil {
		return PolicyDecision{Allowed: false, ReasonCode: reasonCode(err), Normalized: nil}, nil
	}
	target, err := NormalizeOutboundURL(targetRaw)
	if err != nil {
		return PolicyDecision{Allowed: false, ReasonCode: reasonCode(err), Normalized: nil}, nil
	}
	if pre := preDNSDecision(target, policy, &previous); pre != nil {
		return *pre, nil
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	dns, err := ResolveAndValidate(ctx, target.Host, resolver, policy.MaxDNSAddresses())
	if err != nil {
		return PolicyDecision{Allowed: false, ReasonCode: reasonCode(err), Normalized: &target}, nil
	}
	return postDNSDecision(target, dns), nil
}

func reasonCode(err error) string {
	if e, ok := err.(*URLNormalizationError); ok {
		return e.ReasonCode
	}
	if e, ok := err.(*DNSValidationError); ok {
		return e.ReasonCode
	}
	return "invalid_url"
}
