package security

import (
	"context"
	"net"
	"net/url"
	"strings"
)

type DialContextFunc func(ctx context.Context, network, address string) (net.Conn, error)

func defaultDialContext(ctx context.Context, network, address string) (net.Conn, error) {
	return (&net.Dialer{}).DialContext(ctx, network, address)
}

func PrepareRequestHostHeader(requestHost string, target PinnedTarget) (string, error) {
	if requestHost == "" {
		return target.HostHeader(), nil
	}
	if requestHost != target.HostHeader() {
		return "", pinnedFail("host_header_mismatch")
	}
	return target.HostHeader(), nil
}

func ValidateRequestAuthority(requestValue string, target PinnedTarget) error {
	if strings.Contains(requestValue, "://") {
		parsed, err := url.Parse(requestValue)
		if err != nil {
			return pinnedFail("authority_mismatch")
		}
		if parsed.Scheme != target.Scheme() {
			return pinnedFail("scheme_mismatch")
		}
		if parsed.Host != target.Authority() {
			return pinnedFail("authority_mismatch")
		}
		return nil
	}
	return ValidateAuthority(requestValue, target)
}

func ValidateAuthority(requestAuthority string, target PinnedTarget) error {
	if requestAuthority != target.Authority() {
		return pinnedFail("authority_mismatch")
	}
	return nil
}

func DialPinned(ctx context.Context, target PinnedTarget, dial DialContextFunc) (net.Conn, error) {
	if len(target.validatedAddresses) == 0 {
		return nil, pinnedFail("empty_addresses")
	}
	if dial == nil {
		dial = defaultDialContext
	}
	var lastErr error
	for _, address := range target.validatedAddresses {
		if err := ctx.Err(); err != nil {
			return nil, pinnedFail("connection_failed")
		}
		network, endpoint, err := target.dialEndpoint(address)
		if err != nil {
			lastErr = err
			continue
		}
		conn, err := dial(ctx, network, endpoint)
		if err == nil {
			return conn, nil
		}
		lastErr = err
	}
	if lastErr == nil {
		lastErr = pinnedFail("connection_failed")
	}
	return nil, pinnedFail("connection_failed")
}

func DialPinnedAuthority(ctx context.Context, requestAuthority string, target PinnedTarget, dial DialContextFunc) (net.Conn, error) {
	if err := ValidateAuthority(requestAuthority, target); err != nil {
		return nil, err
	}
	return DialPinned(ctx, target, dial)
}
