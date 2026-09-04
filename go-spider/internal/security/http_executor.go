package security

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"net"
	"strings"
	"time"
)

// SecureHTTPExecutor combines pinned transport, redirect planning, budgets,
// and the shared concurrency limiter for isolated HTTP/1.1 execution.
type SecureHTTPExecutor struct {
	policy   OutboundPolicy
	resolver Resolver
	limiter  *ConcurrencyLimiter
	profile  BudgetProfile
	dial     DialContextFunc
	rootCAs  *x509.CertPool
}

// NewSecureHTTPExecutor constructs the isolated executor.
func NewSecureHTTPExecutor(policy OutboundPolicy, resolver Resolver, limiter *ConcurrencyLimiter, profile BudgetProfile, dial DialContextFunc, rootCAs *x509.CertPool) *SecureHTTPExecutor {
	return &SecureHTTPExecutor{policy: policy, resolver: resolver, limiter: limiter, profile: profile, dial: dial, rootCAs: rootCAs}
}

func (e *SecureHTTPExecutor) Execute(req SecureHTTPRequest) (SecureHTTPResponse, error) {
	if e.limiter == nil {
		return SecureHTTPResponse{}, secureHTTPFail("limiter_required")
	}
	if err := ValidateSecureRequest(req); err != nil {
		return SecureHTTPResponse{}, err
	}
	start := time.Now()
	currentURL := req.URL
	currentNormalized := req.URL
	headers := req.Headers
	hops := 0
	previousHost := ""

	for hopCount := 1; hopCount <= NewTransportBudget().MaxRedirects()+1; hopCount++ {
		var target PinnedTarget
		if hopCount == 1 {
			decision, err := DecidePolicy(currentURL, e.policy, e.resolver)
			if err != nil {
				return SecureHTTPResponse{}, secureReason(err)
			}
			if !decision.Allowed {
				return SecureHTTPResponse{}, secureHTTPFail(decision.ReasonCode)
			}
			currentNormalized = decision.Normalized.NormalizedURL
			target, err = NewPinnedTarget(decision, e.policy)
			if err != nil {
				return SecureHTTPResponse{}, secureReason(err)
			}
		} else {
			hop, err := PlanRedirectHop(currentNormalized, currentURL, e.policy, e.resolver, hopCount-1)
			if err != nil {
				return SecureHTTPResponse{}, secureReason(err)
			}
			if previousHost != "" && hop.Target.NormalizedHost() != previousHost {
				headers = stripSensitiveHeaders(headers)
			}
			currentNormalized = hop.URL
			target = hop.Target
			hops++
		}

		currentHost := target.NormalizedHost()
		elapsed := int64(time.Since(start).Milliseconds())
		remaining, err := RemainingDeadline(e.profile, int(elapsed))
		if err != nil {
			return SecureHTTPResponse{}, secureReason(err)
		}
		if remaining <= 0 {
			return SecureHTTPResponse{}, secureHTTPFail("total_timeout_exceeded")
		}
		lease, err := e.limiter.Acquire(target.NormalizedHost())
		if err != nil {
			return SecureHTTPResponse{}, secureReason(err)
		}
		conn, err := e.dialForTarget(target, remaining, start)
		if err != nil {
			lease.Release()
			return SecureHTTPResponse{}, err
		}
		status, responseHeaders, responseBody, rerr := e.roundTrip(conn, req, headers, target, currentNormalized, start, remaining)
		_ = conn.Close()
		lease.Release()
		if rerr != nil {
			return SecureHTTPResponse{}, rerr
		}
		if status == 301 || status == 302 || status == 303 || status == 307 || status == 308 {
			location := ""
			for _, header := range responseHeaders {
				if strings.EqualFold(header.Name, "Location") {
					location = header.Value
				}
			}
			if location == "" {
				return SecureHTTPResponse{}, secureHTTPFail("redirect_location_missing")
			}
			if req.Method == "POST" {
				return SecureHTTPResponse{}, secureHTTPFail("redirect_body_replay_not_allowed")
			}
			previousHost = currentHost
			currentURL = location
			continue
		}
		return SecureHTTPResponse{StatusCode: status, FinalURL: currentNormalized, Headers: responseHeaders, Body: responseBody, RedirectHops: hops}, nil
	}
	return SecureHTTPResponse{}, secureHTTPFail("redirect_limit_exceeded")
}

func (e *SecureHTTPExecutor) dialForTarget(target PinnedTarget, remaining int, start time.Time) (net.Conn, error) {
	if remaining <= 0 {
		return nil, secureHTTPFail("total_timeout_exceeded")
	}
	budget := NewTransportBudget()
	connectTimeout := budget.ConnectTimeoutMS()
	if remaining < connectTimeout {
		connectTimeout = remaining
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(connectTimeout)*time.Millisecond)
	defer cancel()
	conn, err := DialPinned(ctx, target, e.dial)
	if err != nil {
		return nil, secureReason(err)
	}
	if target.Scheme() != "https" {
		return conn, nil
	}
	elapsed := int64(time.Since(start).Milliseconds())
	remainingNow, err := RemainingDeadline(e.profile, int(elapsed))
	if err != nil {
		_ = conn.Close()
		return nil, secureReason(err)
	}
	if remainingNow <= 0 {
		_ = conn.Close()
		return nil, secureHTTPFail("total_timeout_exceeded")
	}
	tlsTimeout := budget.TLSTimeoutMS()
	if remainingNow < tlsTimeout {
		tlsTimeout = remainingNow
	}
	tlsConfig := &tls.Config{
		ServerName:         target.ServerName(),
		InsecureSkipVerify: false,
	}
	if e.rootCAs != nil {
		tlsConfig.RootCAs = e.rootCAs.Clone()
	}
	tlsConn := tls.Client(conn, tlsConfig)
	_ = tlsConn.SetDeadline(time.Now().Add(time.Duration(tlsTimeout) * time.Millisecond))
	if err := tlsConn.Handshake(); err != nil {
		_ = conn.Close()
		if ne, ok := err.(net.Error); ok && ne.Timeout() {
			return nil, secureHTTPFail("tls_timeout")
		}
		return nil, secureHTTPFail("transport_failed")
	}
	_ = tlsConn.SetDeadline(time.Time{})
	return tlsConn, nil
}

func (e *SecureHTTPExecutor) roundTrip(conn net.Conn, req SecureHTTPRequest, headers []Header, target PinnedTarget, normalizedURL string, start time.Time, remaining int) (int, []Header, []byte, error) {
	requestBytes, err := BuildRequestBytes(SecureHTTPRequest{Profile: req.Profile, Method: req.Method, URL: normalizedURL, Headers: headers, Body: req.Body}, target.HostHeader())
	if err != nil {
		return 0, nil, nil, err
	}
	_ = conn.SetWriteDeadline(time.Now().Add(time.Duration(remaining) * time.Millisecond))
	if _, err := conn.Write(requestBytes); err != nil {
		return 0, nil, nil, secureHTTPFail("transport_failed")
	}
	elapsedBeforeRead := int64(time.Since(start).Milliseconds())
	remainingNow, err := RemainingDeadline(e.profile, int(elapsedBeforeRead))
	if err != nil {
		return 0, nil, nil, secureReason(err)
	}
	if remainingNow <= 0 {
		return 0, nil, nil, secureHTTPFail("total_timeout_exceeded")
	}
	clock := func() int64 { return int64(time.Since(start).Milliseconds()) }
	return ReadRawResponse(conn, req.Method, e.profile, elapsedBeforeRead, int64(remainingNow), clock)
}

func stripSensitiveHeaders(headers []Header) []Header {
	out := make([]Header, 0, len(headers))
	for _, header := range headers {
		switch strings.ToLower(header.Name) {
		case "authorization", "proxy-authorization", "cookie":
			continue
		}
		out = append(out, header)
	}
	return out
}

func secureReason(err error) error {
	if err == nil {
		return nil
	}
	if _, ok := err.(*SecureHTTPError); ok {
		return err
	}
	return secureHTTPFail(reasonCodeFromError(err))
}

func reasonCodeFromError(err error) string {
	if e, ok := err.(*SecureHTTPError); ok {
		return e.ReasonCode
	}
	if e, ok := err.(*BoundedIOError); ok {
		return e.ReasonCode
	}
	if e, ok := err.(*BudgetError); ok {
		return e.ReasonCode
	}
	if e, ok := err.(*PinnedConnectionError); ok {
		return e.ReasonCode
	}
	if e, ok := err.(*RedirectPolicyError); ok {
		return e.ReasonCode
	}
	if e, ok := err.(*DNSValidationError); ok {
		return e.ReasonCode
	}
	if e, ok := err.(*URLNormalizationError); ok {
		return e.ReasonCode
	}
	if e, ok := err.(*ConcurrencyError); ok {
		return e.ReasonCode
	}
	return "transport_failed"
}
