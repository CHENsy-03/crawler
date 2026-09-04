package security

import (
	"bytes"
	"context"
	"errors"
	"net/netip"
	"sort"
)

type Resolver interface {
	Resolve(ctx context.Context, host string) ([]string, error)
}

type DNSValidationError struct {
	ReasonCode string
}

func (e *DNSValidationError) Error() string { return e.ReasonCode }

type sortedAddr struct {
	canonical string
	version   int
	key       []byte
}

func sortAddresses(addresses []string) ([]string, error) {
	seen := make(map[string]struct{}, len(addresses))
	items := make([]sortedAddr, 0, len(addresses))
	for _, raw := range addresses {
		addr, err := netip.ParseAddr(raw)
		if err != nil {
			return nil, &DNSValidationError{ReasonCode: "invalid_dns_answer"}
		}
		canonical := addr.String()
		if _, ok := seen[canonical]; ok {
			continue
		}
		seen[canonical] = struct{}{}
		version := 4
		var key []byte
		if addr.Is4() {
			v4 := addr.As4()
			key = v4[:]
		} else {
			version = 6
			v6 := addr.As16()
			key = v6[:]
		}
		items = append(items, sortedAddr{canonical: canonical, version: version, key: key})
	}
	sort.SliceStable(items, func(i, j int) bool {
		if items[i].version != items[j].version {
			return items[i].version < items[j].version
		}
		return bytes.Compare(items[i].key, items[j].key) < 0
	})
	out := make([]string, 0, len(items))
	for _, item := range items {
		out = append(out, item.canonical)
	}
	return out, nil
}

func ResolveAndValidate(ctx context.Context, host string, resolver Resolver, maxAddresses int) (DNSValidationResult, error) {
	if host == "" {
		return DNSValidationResult{}, &DNSValidationError{ReasonCode: "invalid_host"}
	}
	var raw []string
	if _, err := netip.ParseAddr(host); err == nil {
		raw = []string{host}
	} else {
		if resolver == nil {
			return DNSValidationResult{}, &DNSValidationError{ReasonCode: "dns_failed"}
		}
		addresses, err := resolver.Resolve(ctx, host)
		if err != nil {
			if errors.Is(err, context.DeadlineExceeded) || errors.Is(ctx.Err(), context.DeadlineExceeded) {
				return DNSValidationResult{}, &DNSValidationError{ReasonCode: "dns_timeout"}
			}
			return DNSValidationResult{}, &DNSValidationError{ReasonCode: "dns_failed"}
		}
		raw = addresses
	}

	addresses, err := sortAddresses(raw)
	if err != nil {
		return DNSValidationResult{}, err
	}
	if len(addresses) == 0 {
		return DNSValidationResult{}, &DNSValidationError{ReasonCode: "dns_no_addresses"}
	}
	if len(addresses) > maxAddresses {
		return DNSValidationResult{}, &DNSValidationError{ReasonCode: "dns_too_many_addresses"}
	}
	for _, address := range addresses {
		classification, err := ClassifyIP(address)
		if err != nil {
			return DNSValidationResult{}, &DNSValidationError{ReasonCode: "invalid_dns_answer"}
		}
		if !classification.Allowed {
			return DNSValidationResult{
				Host:       host,
				Addresses:  addresses,
				Allowed:    false,
				ReasonCode: "ip_not_allowed",
			}, nil
		}
	}
	return DNSValidationResult{
		Host:      host,
		Addresses: addresses,
		Allowed:   true,
	}, nil
}
