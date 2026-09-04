package security

import (
	"fmt"
	"net/netip"
	"sort"
)

type cidrRule struct {
	prefix   netip.Prefix
	category string
}

func mustPrefix(s string) netip.Prefix {
	p, err := netip.ParsePrefix(s)
	if err != nil {
		panic(err)
	}
	return p
}

var classificationRules = func() []cidrRule {
	raw := []struct {
		cidr     string
		category string
	}{
		{"0.0.0.0/8", "protocol"},
		{"10.0.0.0/8", "private"},
		{"100.64.0.0/10", "shared"},
		{"127.0.0.0/8", "loopback"},
		{"169.254.0.0/16", "link_local"},
		{"172.16.0.0/12", "private"},
		{"192.0.0.0/24", "protocol"},
		{"192.0.2.0/24", "documentation"},
		{"192.168.0.0/16", "private"},
		{"198.18.0.0/15", "benchmark"},
		{"198.51.100.0/24", "documentation"},
		{"203.0.113.0/24", "documentation"},
		{"224.0.0.0/4", "multicast"},
		{"240.0.0.0/4", "reserved"},
		{"255.255.255.255/32", "reserved"},
		{"::/128", "unspecified"},
		{"::1/128", "loopback"},
		{"::/96", "transition"},
		{"64:ff9b::/96", "transition"},
		{"64:ff9b:1::/48", "transition"},
		{"100::/64", "reserved"},
		{"2001::/32", "transition"},
		{"2001:2::/48", "benchmark"},
		{"2001:db8::/32", "documentation"},
		{"2001::/23", "reserved"},
		{"2002::/16", "transition"},
		{"3fff::/20", "documentation"},
		{"fc00::/7", "private"},
		{"fe80::/10", "link_local"},
		{"fec0::/10", "reserved"},
		{"ff00::/8", "multicast"},
	}
	rules := make([]cidrRule, 0, len(raw))
	for _, r := range raw {
		rules = append(rules, cidrRule{prefix: mustPrefix(r.cidr), category: r.category})
	}
	sort.SliceStable(rules, func(i, j int) bool {
		return rules[i].prefix.Bits() > rules[j].prefix.Bits()
	})
	return rules
}()

func ClassifyIP(address string) (IPClassification, error) {
	addr, err := netip.ParseAddr(address)
	if err != nil {
		return IPClassification{}, fmt.Errorf("invalid IP address %q", address)
	}
	canonical := addr.String()
	version := 6
	if addr.Is4() {
		version = 4
	}
	if addr.Is4In6() {
		return IPClassification{
			Address:  canonical,
			Version:  version,
			Category: "mapped_ipv4",
			Allowed:  false,
		}, nil
	}
	for _, rule := range classificationRules {
		if rule.prefix.Contains(addr) {
			return IPClassification{
				Address:  canonical,
				Version:  version,
				Category: rule.category,
				Allowed:  rule.category == "global",
			}, nil
		}
	}
	return IPClassification{
		Address:  canonical,
		Version:  version,
		Category: "global",
		Allowed:  true,
	}, nil
}
