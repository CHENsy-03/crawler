package security

import (
	"fmt"
	"net"
	"net/netip"
	"strconv"
	"strings"
)

const maxValidatedAddresses = 16

type PinnedConnectionError struct {
	ReasonCode string
}

func (e *PinnedConnectionError) Error() string { return e.ReasonCode }

func pinnedFail(reason string) error { return &PinnedConnectionError{ReasonCode: reason} }

type PinnedTarget struct {
	scheme             string
	normalizedHost     string
	port               int
	authority          string
	hostHeader         string
	serverName         string
	validatedAddresses []string
	isIPLiteral        bool
	policyIdentity     string
}

func hostHeaderFor(scheme, host string, port int) string {
	hostForAuthority := host
	if strings.Contains(host, ":") {
		hostForAuthority = "[" + host + "]"
	}
	defaultPort := 80
	if scheme == "https" {
		defaultPort = 443
	}
	if port == defaultPort {
		return hostForAuthority
	}
	return fmt.Sprintf("%s:%d", hostForAuthority, port)
}

func validatedAddresses(addresses []string) ([]string, error) {
	sorted, err := sortAddresses(addresses)
	if err != nil {
		return nil, err
	}
	if len(sorted) == 0 {
		return nil, pinnedFail("empty_addresses")
	}
	if len(sorted) > maxValidatedAddresses {
		return nil, pinnedFail("too_many_addresses")
	}
	for _, address := range sorted {
		classification, err := ClassifyIP(address)
		if err != nil {
			return nil, pinnedFail("invalid_address")
		}
		if !classification.Allowed {
			return nil, pinnedFail("ip_not_allowed")
		}
	}
	return sorted, nil
}

func NewPinnedTarget(decision PolicyDecision, policy OutboundPolicy) (PinnedTarget, error) {
	if !decision.Allowed || decision.ReasonCode != "" || decision.Normalized == nil {
		return PinnedTarget{}, pinnedFail("policy_not_allowed")
	}
	normalized := *decision.Normalized
	addresses, err := validatedAddresses(decision.Addresses)
	if err != nil {
		return PinnedTarget{}, err
	}
	dns := DNSValidationResult{
		Host:      normalized.Host,
		Addresses: addresses,
		Allowed:   true,
	}
	if !EvaluatePolicy(normalized, dns, policy, nil).Allowed {
		return PinnedTarget{}, pinnedFail("policy_not_allowed")
	}
	hostHeader := hostHeaderFor(normalized.Scheme, normalized.Host, normalized.Port)
	return PinnedTarget{
		scheme:             normalized.Scheme,
		normalizedHost:     normalized.Host,
		port:               normalized.Port,
		authority:          hostHeader,
		hostHeader:         hostHeader,
		serverName:         normalized.Host,
		validatedAddresses: addresses,
		isIPLiteral:        normalized.IsIPLiteral,
		policyIdentity:     "default",
	}, nil
}

func (t PinnedTarget) Scheme() string         { return t.scheme }
func (t PinnedTarget) NormalizedHost() string { return t.normalizedHost }
func (t PinnedTarget) Port() int              { return t.port }
func (t PinnedTarget) Authority() string      { return t.authority }
func (t PinnedTarget) HostHeader() string     { return t.hostHeader }
func (t PinnedTarget) ServerName() string     { return t.serverName }
func (t PinnedTarget) ValidatedAddresses() []string {
	return append([]string(nil), t.validatedAddresses...)
}
func (t PinnedTarget) IsIPLiteral() bool      { return t.isIPLiteral }
func (t PinnedTarget) PolicyIdentity() string { return t.policyIdentity }

func (t PinnedTarget) dialEndpoint(address string) (string, string, error) {
	addr, err := netip.ParseAddr(address)
	if err != nil {
		return "", "", pinnedFail("invalid_address")
	}
	network := "tcp4"
	if addr.Is6() {
		network = "tcp6"
	}
	return network, net.JoinHostPort(address, strconv.Itoa(t.port)), nil
}
