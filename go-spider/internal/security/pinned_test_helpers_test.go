package security

func newPinnedTargetForTest(scheme, host string, port int, addresses []string) (PinnedTarget, error) {
	sorted, err := sortAddresses(addresses)
	if err != nil {
		return PinnedTarget{}, err
	}
	if len(sorted) == 0 {
		return PinnedTarget{}, pinnedFail("empty_addresses")
	}
	hostHeader := hostHeaderFor(scheme, host, port)
	return PinnedTarget{
		scheme:             scheme,
		normalizedHost:     host,
		port:               port,
		authority:          hostHeader,
		hostHeader:         hostHeader,
		serverName:         host,
		validatedAddresses: sorted,
		isIPLiteral:        false,
		policyIdentity:     "test",
	}, nil
}
