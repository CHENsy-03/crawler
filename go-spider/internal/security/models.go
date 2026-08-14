package security

// NormalizedURL is an immutable-style value produced by URL normalization.
type NormalizedURL struct {
	Scheme        string
	Host          string
	Port          int
	ExplicitPort  bool
	Authority     string
	NormalizedURL string
	IsIPLiteral   bool
}

// IPClassification is a pure IP classification result.
type IPClassification struct {
	Address  string
	Version  int
	Category string
	Allowed  bool
}

// DNSValidationResult carries the validated address set for a hostname.
type DNSValidationResult struct {
	Host       string
	Addresses  []string
	Allowed    bool
	ReasonCode string
}

// PolicyDecision is the pure result of outbound policy evaluation.
type PolicyDecision struct {
	Allowed    bool
	ReasonCode string
	Normalized *NormalizedURL
	Addresses  []string
}

// OutboundPolicyConfig is the mutable input shape used to construct an
// immutable OutboundPolicy. Callers may reuse slices/maps after construction.
type OutboundPolicyConfig struct {
	AllowedHosts              []string
	AllowedHTTP               bool
	AllowedPortsByScheme      map[string][]int
	MaxDNSAddresses           int
	AllowControlledSubdomains bool
}

// OutboundPolicy owns unexported state and never exposes mutable references.
type OutboundPolicy struct {
	allowedHosts              []string
	allowedHTTP               bool
	allowedPortsByScheme      map[string][]int
	maxDNSAddresses           int
	allowControlledSubdomains bool
}

// NewOutboundPolicy deep-copies all mutable inputs.
func NewOutboundPolicy(cfg OutboundPolicyConfig) OutboundPolicy {
	hosts := append([]string(nil), cfg.AllowedHosts...)
	ports := make(map[string][]int, len(cfg.AllowedPortsByScheme))
	for scheme, list := range cfg.AllowedPortsByScheme {
		ports[scheme] = append([]int(nil), list...)
	}
	maxDNS := cfg.MaxDNSAddresses
	if maxDNS <= 0 {
		maxDNS = 16
	}
	return OutboundPolicy{
		allowedHosts:              hosts,
		allowedHTTP:               cfg.AllowedHTTP,
		allowedPortsByScheme:      ports,
		maxDNSAddresses:           maxDNS,
		allowControlledSubdomains: cfg.AllowControlledSubdomains,
	}
}

// DefaultOutboundPolicy returns a fresh fail-closed policy.
func DefaultOutboundPolicy() OutboundPolicy {
	return NewOutboundPolicy(OutboundPolicyConfig{
		AllowedHosts:         []string{},
		AllowedHTTP:          false,
		AllowedPortsByScheme: map[string][]int{"http": {80}, "https": {443}},
		MaxDNSAddresses:      16,
	})
}

// AllowedHosts returns a defensive copy.
func (p OutboundPolicy) AllowedHosts() []string {
	return append([]string(nil), p.allowedHosts...)
}

// AllowedHTTP reports whether plain HTTP is allowed.
func (p OutboundPolicy) AllowedHTTP() bool { return p.allowedHTTP }

// AllowedPortsByScheme returns a deep copy.
func (p OutboundPolicy) AllowedPortsByScheme() map[string][]int {
	out := make(map[string][]int, len(p.allowedPortsByScheme))
	for scheme, list := range p.allowedPortsByScheme {
		out[scheme] = append([]int(nil), list...)
	}
	return out
}

// MaxDNSAddresses returns the configured DNS address budget.
func (p OutboundPolicy) MaxDNSAddresses() int { return p.maxDNSAddresses }

// AllowControlledSubdomains reports whether subdomain matching is enabled.
func (p OutboundPolicy) AllowControlledSubdomains() bool {
	return p.allowControlledSubdomains
}

// AllowsHost performs an exact normalized-host membership check.
func (p OutboundPolicy) AllowsHost(host string) bool {
	for _, candidate := range p.allowedHosts {
		if candidate == host {
			return true
		}
	}
	return false
}

// AllowsPort checks the exact port set for a scheme.
func (p OutboundPolicy) AllowsPort(scheme string, port int) bool {
	for _, candidate := range p.allowedPortsByScheme[scheme] {
		if candidate == port {
			return true
		}
	}
	return false
}
