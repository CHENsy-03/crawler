package security

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"net"
	"net/http"
	"strconv"
)

type PinnedTransport struct {
	target    PinnedTarget
	dial      DialContextFunc
	tlsConfig *tls.Config
}

func ValidateTLSConfig(cfg *tls.Config, serverName string) error {
	if cfg == nil || cfg.InsecureSkipVerify {
		return pinnedFail("insecure_tls_context")
	}
	if cfg.ServerName != serverName {
		return pinnedFail("tls_server_name_mismatch")
	}
	return nil
}

func NewPinnedTransport(target PinnedTarget, dial DialContextFunc, rootCAs *x509.CertPool) *PinnedTransport {
	tlsConfig := &tls.Config{
		ServerName:         target.ServerName(),
		InsecureSkipVerify: false,
		MinVersion:         tls.VersionTLS12,
	}
	if rootCAs != nil {
		tlsConfig.RootCAs = rootCAs.Clone()
	}
	return &PinnedTransport{target: target, dial: dial, tlsConfig: tlsConfig}
}

func (p *PinnedTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	if req.URL.Scheme != p.target.Scheme() {
		return nil, pinnedFail("scheme_mismatch")
	}
	if req.URL.Hostname() != p.target.NormalizedHost() {
		return nil, pinnedFail("authority_mismatch")
	}
	requestPort := 80
	if req.URL.Scheme == "https" {
		requestPort = 443
	}
	if portStr := req.URL.Port(); portStr != "" {
		parsed, err := strconv.Atoi(portStr)
		if err != nil || parsed != p.target.Port() {
			return nil, pinnedFail("authority_mismatch")
		}
		requestPort = parsed
	}
	if requestPort != p.target.Port() {
		return nil, pinnedFail("authority_mismatch")
	}

	ctx := req.Context()
	cloned := req.Clone(ctx)
	if cloned.Host == "" {
		cloned.Host = p.target.HostHeader()
	} else if cloned.Host != p.target.HostHeader() {
		return nil, pinnedFail("host_header_mismatch")
	}

	transport := &http.Transport{
		Proxy:             nil,
		DisableKeepAlives: true,
		DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
			return DialPinned(ctx, p.target, p.dial)
		},
	}
	if p.target.Scheme() == "https" {
		transport.TLSClientConfig = p.tlsConfig
	}
	defer transport.CloseIdleConnections()
	return transport.RoundTrip(cloned)
}
