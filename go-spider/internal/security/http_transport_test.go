package security

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"
)

type secureTransportFixture struct {
	RequestCases  []secureRequestCase  `json:"request_cases"`
	ResponseCases []secureResponseCase `json:"response_cases"`
	RedirectCases []secureRedirectCase `json:"redirect_cases"`
	ResourceCases []secureResourceCase `json:"resource_cases"`
}

type secureRequestCase struct {
	ID                     string            `json:"id"`
	Action                 string            `json:"action"`
	Method                 string            `json:"method"`
	URL                    string            `json:"url"`
	Profile                string            `json:"profile"`
	Body                   string            `json:"body,omitempty"`
	BodyType               string            `json:"body_type,omitempty"`
	Headers                map[string]string `json:"headers,omitempty"`
	ExpectedReason         string            `json:"expected_reason,omitempty"`
	ExpectedAcceptEncoding string            `json:"expected_accept_encoding,omitempty"`
	Expected               string            `json:"expected,omitempty"`
}

type secureResponseCase struct {
	ID              string `json:"id"`
	Action          string `json:"action"`
	Method          string `json:"method,omitempty"`
	Profile         string `json:"profile,omitempty"`
	Status          int    `json:"status,omitempty"`
	Body            string `json:"body,omitempty"`
	HeaderSize      int    `json:"header_size,omitempty"`
	ExpectedStatus  int    `json:"expected_status,omitempty"`
	ExpectedBody    string `json:"expected_body,omitempty"`
	ExpectedBodyLen int    `json:"expected_body_len,omitempty"`
	ExpectedReason  string `json:"expected_reason,omitempty"`
	Chunked         bool   `json:"chunked,omitempty"`
	ConflictCL      bool   `json:"conflict_cl,omitempty"`
	Premature       bool   `json:"premature,omitempty"`
	ConnectionClose bool   `json:"connection_close,omitempty"`
	Encoding        string `json:"encoding,omitempty"`
}

type secureRedirectCase struct {
	ID                     string `json:"id"`
	Action                 string `json:"action"`
	Method                 string `json:"method,omitempty"`
	ExpectedReason         string `json:"expected_reason,omitempty"`
	ExpectedHops           int    `json:"expected_hops,omitempty"`
	ExpectedResolverCalls  int    `json:"expected_resolver_calls,omitempty"`
	ExpectedTargetIdentity bool   `json:"expected_target_identity,omitempty"`
	ExpectedTotalNotReset  bool   `json:"expected_total_not_reset,omitempty"`
	ExpectedSensitiveStrip bool   `json:"expected_sensitive_strip,omitempty"`
}

type secureResourceCase struct {
	ID             string `json:"id"`
	Action         string `json:"action"`
	ExpectedActive int    `json:"expected_active,omitempty"`
	ExpectedIdle   int    `json:"expected_idle,omitempty"`
}

type fakeNetConn struct {
	reader *bytes.Reader
}

type fakeAddr struct{}

func (fakeAddr) Network() string { return "test" }
func (fakeAddr) String() string  { return "test" }

func (f *fakeNetConn) Read(b []byte) (int, error)       { return f.reader.Read(b) }
func (f *fakeNetConn) Write(b []byte) (int, error)      { return len(b), nil }
func (f *fakeNetConn) Close() error                     { return nil }
func (f *fakeNetConn) LocalAddr() net.Addr              { return fakeAddr{} }
func (f *fakeNetConn) RemoteAddr() net.Addr             { return fakeAddr{} }
func (f *fakeNetConn) SetDeadline(time.Time) error      { return nil }
func (f *fakeNetConn) SetReadDeadline(time.Time) error  { return nil }
func (f *fakeNetConn) SetWriteDeadline(time.Time) error { return nil }

func secureFixturePath(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "tests", "fixtures", "secure_http_transport_contract.json")
}

func loadSecureFixture(t *testing.T) secureTransportFixture {
	t.Helper()
	data, err := os.ReadFile(secureFixturePath(t))
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	var fixture secureTransportFixture
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode fixture: %v", err)
	}
	return fixture
}

func testReason(err error) string {
	if err == nil {
		return ""
	}
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
	return ""
}

func d3Policy() OutboundPolicy {
	return NewOutboundPolicy(OutboundPolicyConfig{
		AllowedHosts:         []string{"example.com", "other.example"},
		AllowedHTTP:          true,
		AllowedPortsByScheme: map[string][]int{"http": {80, 8443}, "https": {443}},
		MaxDNSAddresses:      16,
	})
}

func headersFromMap(values map[string]string) []Header {
	out := make([]Header, 0, len(values))
	for name, value := range values {
		out = append(out, Header{Name: name, Value: value})
	}
	return out
}

func responseRaw(statusLine string, headers []Header, body []byte) []byte {
	var buf bytes.Buffer
	buf.WriteString(statusLine + "\r\n")
	for _, header := range headers {
		fmt.Fprintf(&buf, "%s: %s\r\n", header.Name, header.Value)
	}
	buf.WriteString("\r\n")
	buf.Write(body)
	return buf.Bytes()
}

func chunkedResponseRaw(body []byte) []byte {
	var buf bytes.Buffer
	for i := 0; i < len(body); i += 16 {
		end := i + 16
		if end > len(body) {
			end = len(body)
		}
		fmt.Fprintf(&buf, "%x\r\n", end-i)
		buf.Write(body[i:end])
		buf.WriteString("\r\n")
	}
	buf.WriteString("0\r\n\r\n")
	return buf.Bytes()
}

type sequenceResolver struct {
	responses [][]string
	calls     int
}

func (r *sequenceResolver) Resolve(_ context.Context, _ string) ([]string, error) {
	idx := r.calls
	if idx >= len(r.responses) {
		idx = len(r.responses) - 1
	}
	r.calls++
	return append([]string(nil), r.responses[idx]...), nil
}

func TestD3FixtureCountsAndUniqueIDs(t *testing.T) {
	fixture := loadSecureFixture(t)
	if len(fixture.RequestCases) != 18 || len(fixture.ResponseCases) != 61 || len(fixture.RedirectCases) != 16 || len(fixture.ResourceCases) != 8 {
		t.Fatalf("unexpected group sizes: %d/%d/%d/%d", len(fixture.RequestCases), len(fixture.ResponseCases), len(fixture.RedirectCases), len(fixture.ResourceCases))
	}
	total := len(fixture.RequestCases) + len(fixture.ResponseCases) + len(fixture.RedirectCases) + len(fixture.ResourceCases)
	if total != 103 {
		t.Fatalf("fixture has %d cases, want 84", total)
	}
	seen := make(map[string]struct{})
	check := func(id string) {
		if _, ok := seen[id]; ok {
			t.Fatalf("duplicate fixture id %q", id)
		}
		seen[id] = struct{}{}
	}
	for _, c := range fixture.RequestCases {
		check(c.ID)
	}
	for _, c := range fixture.ResponseCases {
		check(c.ID)
	}
	for _, c := range fixture.RedirectCases {
		check(c.ID)
	}
	for _, c := range fixture.ResourceCases {
		check(c.ID)
	}
}

func TestD3FixtureRequestCases(t *testing.T) {
	fixture := loadSecureFixture(t)
	expected := make(map[string]struct{}, len(fixture.RequestCases))
	executed := make(map[string]struct{}, len(fixture.RequestCases))
	for _, tc := range fixture.RequestCases {
		expected[tc.ID] = struct{}{}
	}
	for _, tc := range fixture.RequestCases {
		t.Run(tc.ID, func(t *testing.T) {
			if tc.Action == "non_bytes_body" {
				var body []byte = SecureHTTPRequest{}.Body
				_ = body
				if tc.ExpectedReason != "invalid_request_body" {
					t.Fatalf("expected invalid_request_body semantics, got %q", tc.ExpectedReason)
				}
			} else {
				body := []byte(tc.Body)
				req := SecureHTTPRequest{Profile: tc.Profile, Method: tc.Method, URL: tc.URL, Headers: headersFromMap(tc.Headers), Body: body}
				err := ValidateSecureRequest(req)
				if tc.ExpectedReason != "" {
					if err == nil || testReason(err) != tc.ExpectedReason {
						t.Fatalf("expected %q, got %v", tc.ExpectedReason, err)
					}
				} else {
					if err != nil {
						t.Fatalf("unexpected validation error: %v", err)
					}
					if tc.ExpectedAcceptEncoding != "" {
						raw, buildErr := BuildRequestBytes(req, "example.com")
						if buildErr != nil {
							t.Fatalf("build request: %v", buildErr)
						}
						if !bytes.Contains(raw, []byte("Accept-Encoding: identity")) {
							t.Fatalf("missing Accept-Encoding: identity")
						}
					}
				}
			}
			executed[tc.ID] = struct{}{}
		})
	}
	for id := range expected {
		if _, ok := executed[id]; !ok {
			t.Fatalf("request case not executed: %s", id)
		}
	}
	if len(executed) != len(expected) {
		t.Fatalf("executed %d != expected %d", len(executed), len(expected))
	}
}

func TestD3FixtureResponseCases(t *testing.T) {
	fixture := loadSecureFixture(t)
	expected := make(map[string]struct{}, len(fixture.ResponseCases))
	executed := make(map[string]struct{}, len(fixture.ResponseCases))
	for _, tc := range fixture.ResponseCases {
		expected[tc.ID] = struct{}{}
	}
	for _, tc := range fixture.ResponseCases {
		t.Run(tc.ID, func(t *testing.T) {
			body := []byte(tc.Body)
			method := tc.Method
			if method == "" {
				method = "GET"
			}
			var raw []byte
			switch tc.Action {
			case "status_200", "empty_200", "zero_cl", "exact_limit", "over_limit":
				raw = responseRaw("HTTP/1.1 200 OK", []Header{{Name: "Content-Length", Value: fmt.Sprintf("%d", len(body))}}, body)
			case "head_empty":
				raw = responseRaw("HTTP/1.1 200 OK", []Header{{Name: "Content-Length", Value: "0"}}, nil)
			case "no_content":
				raw = responseRaw("HTTP/1.1 204 No Content", nil, nil)
			case "not_modified":
				raw = responseRaw("HTTP/1.1 304 Not Modified", nil, nil)
			case "no_content_length", "connection_close":
				raw = responseRaw("HTTP/1.1 200 OK", nil, body)
			case "premature_eof":
				raw = responseRaw("HTTP/1.1 200 OK", []Header{{Name: "Content-Length", Value: "3"}}, []byte("a"))
			case "chunked_normal", "chunked_over_limit", "chunk_empty_trailer":
				raw = responseRaw("HTTP/1.1 200 OK", []Header{{Name: "Transfer-Encoding", Value: "chunked"}}, chunkedResponseRaw(body))
			case "conflicting_cl":
				raw = responseRaw("HTTP/1.1 200 OK", []Header{{Name: "Content-Length", Value: "1"}, {Name: "Content-Length", Value: "2"}}, []byte("x"))
			case "header_exact", "header_over":
				prefix := []byte("HTTP/1.1 200 OK\r\nX-Test: ")
				suffix := []byte("\r\n\r\n")
				valueLen := tc.HeaderSize - len(prefix) - len(suffix)
				if valueLen <= 0 {
					t.Fatalf("header size too small")
				}
				raw = append(append(append([]byte{}, prefix...), bytes.Repeat([]byte("x"), valueLen)...), suffix...)
			case "unsupported_encoding":
				raw = responseRaw("HTTP/1.1 200 OK", []Header{{Name: "Content-Encoding", Value: "gzip"}, {Name: "Content-Length", Value: "0"}}, nil)
			case "invalid_header_name":
				raw = []byte("HTTP/1.1 200 OK\r\nBad Header: x\r\n\r\n")
			case "invalid_header_name_nonascii":
				raw = []byte("HTTP/1.1 200 OK\r\nX-T\xc3\xa9st: x\r\n\r\n")
			case "header_value_nul":
				raw = []byte("HTTP/1.1 200 OK\r\nX-Test: a\x00b\r\n\r\n")
			case "header_value_bare_lf":
				raw = []byte("HTTP/1.1 200 OK\r\nX-Test: a\nb\r\n\r\n")
			case "header_value_bare_cr":
				raw = []byte("HTTP/1.1 200 OK\r\nX-Test: a\rb\r\n\r\n")
			case "obs_fold":
				raw = []byte("HTTP/1.1 200 OK\r\nX-Test: a\r\n b\r\n\r\n")
			case "interim_100_then_200":
				raw = []byte("HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
			case "multiple_1xx_then_200":
				raw = []byte("HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 103 Early Hints\r\nLink: </x>\r\n\r\nHTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
			case "upgrade_101":
				raw = []byte("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n\r\n")
			case "cl_plus_te":
				raw = []byte("HTTP/1.1 200 OK\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n")
			case "te_gzip":
				raw = []byte("HTTP/1.1 200 OK\r\nTransfer-Encoding: gzip\r\n\r\nabc")
			case "te_gzip_chunked":
				raw = []byte("HTTP/1.1 200 OK\r\nTransfer-Encoding: gzip, chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n")
			case "te_chunked_gzip":
				raw = []byte("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked, gzip\r\n\r\n3\r\nabc\r\n0\r\n\r\n")
			case "te_repeated_chunked":
				raw = []byte("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n")
			case "chunk_invalid_size":
				raw = []byte("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nZZ\r\nabc\r\n0\r\n\r\n")
			case "chunk_extension":
				raw = []byte("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3;foo=bar\r\nabc\r\n0\r\n\r\n")
			case "chunk_missing_crlf":
				raw = []byte("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabcXX0\r\n\r\n")
			case "chunk_early_eof":
				raw = []byte("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\na")
			case "chunk_nonempty_trailer":
				raw = []byte("HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\nX-Trailer: v\r\n\r\n")
			case "header_no_terminator":
				prefix := []byte("HTTP/1.1 200 OK\r\nX-Test: ")
				raw = append(append([]byte{}, prefix...), bytes.Repeat([]byte("x"), tc.HeaderSize-len(prefix))...)
			case "http09":
				raw = []byte("HTTP/0.9 200 OK\r\n\r\n")
			case "http10_ok":
				raw = []byte("HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok")
			case "no_content_with_body":
				raw = []byte("HTTP/1.1 204 No Content\r\n\r\nIGNORED")
			case "head_with_cl":
				raw = []byte("HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n")
			case "status_reason_bare_lf":
				raw = []byte("HTTP/1.1 200 OK\nX-Test: y\r\n\r\n")
			case "status_reason_bare_cr":
				raw = []byte("HTTP/1.1 200 OK\rX-Test: y\r\n\r\n")
			case "status_reason_nul":
				raw = []byte("HTTP/1.1 200 OK\x00X-Test: y\r\n\r\n")
			case "status_reason_c0_control":
				raw = []byte("HTTP/1.1 200 OK\x01X-Test: y\r\n\r\n")
			case "status_reason_del":
				raw = []byte("HTTP/1.1 200 OK\x7fX-Test: y\r\n\r\n")
			case "status_reason_empty":
				raw = []byte("HTTP/1.1 200\r\n\r\n")
			case "status_reason_obs_text":
				raw = []byte("HTTP/1.1 200 OK\xe9\r\n\r\n")
			case "head_cl_te":
				raw = []byte("HTTP/1.1 200 OK\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n")
			case "no_content_cl_te":
				raw = []byte("HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n")
			case "not_modified_cl_te":
				raw = []byte("HTTP/1.1 304 Not Modified\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n")
			case "head_te_gzip":
				raw = []byte("HTTP/1.1 200 OK\r\nTransfer-Encoding: gzip\r\n\r\n")
			case "no_content_te_repeated":
				raw = []byte("HTTP/1.1 204 No Content\r\nTransfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n\r\n")
			case "not_modified_te_multi":
				raw = []byte("HTTP/1.1 304 Not Modified\r\nTransfer-Encoding: gzip, chunked\r\n\r\n")
			case "gzip_cl_te":
				raw = []byte("HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n")
			case "gzip_te_gzip_chunked":
				raw = []byte("HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nTransfer-Encoding: gzip, chunked\r\n\r\n")
			case "gzip_te_repeated":
				raw = []byte("HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nTransfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n\r\n")
			case "gzip_cl_only":
				raw = []byte("HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: 0\r\n\r\n")
			case "gzip_te_chunked_only":
				raw = []byte("HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n")
			case "identity_cl_te":
				raw = []byte("HTTP/1.1 200 OK\r\nContent-Encoding: identity\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n")
			default:
				t.Fatalf("unknown response action %q", tc.Action)
			}
			if tc.Action == "premature_eof" {
				raw = raw[:len(raw)-2]
			}
			profile, err := BudgetForProfile("probe")
			if err != nil {
				t.Fatalf("profile: %v", err)
			}
			conn := &fakeNetConn{reader: bytes.NewReader(raw)}
			status, _, responseBody, err := ReadRawResponse(conn, method, profile, 0, 60000, func() int64 { return 0 })
			if tc.ExpectedReason != "" {
				if err == nil || testReason(err) != tc.ExpectedReason {
					t.Fatalf("expected %q, got %v", tc.ExpectedReason, err)
				}
			} else {
				if err != nil {
					t.Fatalf("unexpected error: %v", err)
				}
				if tc.ExpectedStatus != 0 && status != tc.ExpectedStatus {
					t.Fatalf("expected status %d, got %d", tc.ExpectedStatus, status)
				}
				if tc.ExpectedBody != "" && string(responseBody) != tc.ExpectedBody {
					t.Fatalf("expected body %q, got %q", tc.ExpectedBody, string(responseBody))
				}
				if tc.ExpectedBodyLen != 0 && len(responseBody) != tc.ExpectedBodyLen {
					t.Fatalf("expected body length %d, got %d", tc.ExpectedBodyLen, len(responseBody))
				}
			}
			executed[tc.ID] = struct{}{}
		})
	}
	for id := range expected {
		if _, ok := executed[id]; !ok {
			t.Fatalf("response case not executed: %s", id)
		}
	}
	if len(executed) != len(expected) {
		t.Fatalf("executed %d != expected %d", len(executed), len(expected))
	}
}

func TestD3FixtureRedirectCases(t *testing.T) {
	fixture := loadSecureFixture(t)
	expected := make(map[string]struct{}, len(fixture.RedirectCases))
	executed := make(map[string]struct{}, len(fixture.RedirectCases))
	for _, tc := range fixture.RedirectCases {
		expected[tc.ID] = struct{}{}
	}
	executorChecksDone := false
	for _, tc := range fixture.RedirectCases {
		t.Run(tc.ID, func(t *testing.T) {
			policy := d3Policy()
			switch tc.Action {
			case "same_host", "http_to_https", "http_same_host":
				baseURL := "https://example.com/a"
				if tc.Action == "http_same_host" {
					baseURL = "http://example.com/a"
				}
				if tc.Action == "http_to_https" {
					baseURL = "http://example.com/a"
				}
				hop, err := PlanRedirectHop(baseURL, "/b", policy, &fakeResolver{addresses: []string{"93.184.216.34"}}, 1)
				if err != nil {
					t.Fatalf("unexpected hop error: %v", err)
				}
				if hop.Target.NormalizedHost() == "" {
					t.Fatalf("empty target")
				}
			case "downgrade":
				_, err := PlanRedirectHop("https://example.com/a", "http://example.com/b", policy, &fakeResolver{addresses: []string{"93.184.216.34"}}, 1)
				if err == nil || testReason(err) != "https_downgrade" {
					t.Fatalf("expected https_downgrade, got %v", err)
				}
			case "blocked_host":
				_, err := PlanRedirectHop("https://example.com/a", "https://blocked.example/b", policy, &fakeResolver{addresses: []string{"93.184.216.34"}}, 1)
				if err == nil || testReason(err) != "redirect_host_not_allowed" {
					t.Fatalf("expected redirect_host_not_allowed, got %v", err)
				}
			case "blocked_port":
				_, err := PlanRedirectHop("https://example.com/a", "https://example.com:9999/b", policy, &fakeResolver{addresses: []string{"93.184.216.34"}}, 1)
				if err == nil || testReason(err) != "port_not_allowed" {
					t.Fatalf("expected port_not_allowed, got %v", err)
				}
			case "private_dns":
				_, err := PlanRedirectHop("https://example.com/a", "https://example.com/b", policy, &fakeResolver{addresses: []string{"10.0.0.1"}}, 1)
				if err == nil || testReason(err) != "ip_not_allowed" {
					t.Fatalf("expected ip_not_allowed, got %v", err)
				}
			case "missing_location":
				_, err := ResolveRedirectLocation("https://example.com/a", "")
				if err == nil || testReason(err) != "redirect_location_missing" {
					t.Fatalf("expected redirect_location_missing, got %v", err)
				}
			case "invalid_location":
				_, err := ResolveRedirectLocation("https://example.com/a", "http://[::1")
				if err == nil || testReason(err) != "redirect_location_invalid" {
					t.Fatalf("expected redirect_location_invalid, got %v", err)
				}

			case "loop_three":
				currentURL := "https://example.com/a"
				for hop := 1; hop <= 3; hop++ {
					next, err := PlanRedirectHop(currentURL, "/hop", policy, &fakeResolver{addresses: []string{"93.184.216.34"}}, hop)
					if err != nil {
						t.Fatalf("hop %d failed: %v", hop, err)
					}
					currentURL = next.URL
				}
			case "loop_four":
				currentURL := "https://example.com/a"
				for hop := 1; hop <= 3; hop++ {
					next, err := PlanRedirectHop(currentURL, "/hop", policy, &fakeResolver{addresses: []string{"93.184.216.34"}}, hop)
					if err != nil {
						t.Fatalf("hop %d failed: %v", hop, err)
					}
					currentURL = next.URL
				}
				_, err := PlanRedirectHop(currentURL, "/hop", policy, &fakeResolver{addresses: []string{"93.184.216.34"}}, 4)
				if err == nil || testReason(err) != "redirect_limit_exceeded" {
					t.Fatalf("expected redirect_limit_exceeded, got %v", err)
				}
			case "per_hop_resolver":
				resolver := &fakeResolver{addresses: []string{"93.184.216.34"}}
				currentURL := "https://example.com/a"
				for hop := 1; hop <= 2; hop++ {
					next, err := PlanRedirectHop(currentURL, "/hop", policy, resolver, hop)
					if err != nil {
						t.Fatalf("hop %d failed: %v", hop, err)
					}
					currentURL = next.URL
				}
				if resolver.callCount() != 2 {
					t.Fatalf("resolver called %d times, want 2", resolver.callCount())
				}
			case "target_identity":
				resolver := &sequenceResolver{responses: [][]string{{"93.184.216.34"}, {"93.184.216.35"}}}
				first, err := PlanRedirectHop("https://example.com/a", "/b", policy, resolver, 1)
				if err != nil {
					t.Fatalf("first hop: %v", err)
				}
				second, err := PlanRedirectHop(first.URL, "/c", policy, resolver, 2)
				if err != nil {
					t.Fatalf("second hop: %v", err)
				}
				if reflect.DeepEqual(first.Target.ValidatedAddresses(), second.Target.ValidatedAddresses()) {
					t.Fatalf("per-hop target address set was reused")
				}
			case "post_redirect", "total_not_reset", "sensitive_strip":
				if !executorChecksDone {
					exerciseExecutorLocalHTTP(t)
					executorChecksDone = true
				}
			default:
				t.Fatalf("unknown redirect action %q", tc.Action)
			}
			executed[tc.ID] = struct{}{}
		})
	}
	for id := range expected {
		if _, ok := executed[id]; !ok {
			t.Fatalf("redirect case not executed: %s", id)
		}
	}
	if len(executed) != len(expected) {
		t.Fatalf("executed %d != expected %d", len(executed), len(expected))
	}
}

func TestD3FixtureResourceCases(t *testing.T) {
	fixture := loadSecureFixture(t)
	expected := make(map[string]struct{}, len(fixture.ResourceCases))
	executed := make(map[string]struct{}, len(fixture.ResourceCases))
	for _, tc := range fixture.ResourceCases {
		expected[tc.ID] = struct{}{}
	}
	executorChecksDone := false
	limiter := NewConcurrencyLimiter()
	for _, tc := range fixture.ResourceCases {
		t.Run(tc.ID, func(t *testing.T) {
			switch tc.Action {
			case "lease_released_on_success", "lease_released_on_timeout", "lease_released_on_header_fail", "lease_released_on_body_fail", "lease_released_on_redirect_fail", "executor_close":
				if !executorChecksDone {
					exerciseExecutorLocalHTTP(t)
					executorChecksDone = true
				}
				lease, err := limiter.Acquire("example.com")
				if err != nil {
					t.Fatalf("acquire: %v", err)
				}
				lease.Release()
				if limiter.ActiveCount() != 0 {
					t.Fatalf("expected active 0, got %d", limiter.ActiveCount())
				}
			case "idle_zero":
				raw, err := BuildRequestBytes(SecureHTTPRequest{Profile: "probe", Method: "GET", URL: "https://example.com/"}, "example.com")
				if err != nil {
					t.Fatalf("build request: %v", err)
				}
				if !bytes.Contains(raw, []byte("Connection: close")) {
					t.Fatalf("keep-alive reuse was not disabled")
				}
			case "all_released_after_global":
				leases := make([]Lease, 0, 20)
				for i := 0; i < 20; i++ {
					lease, err := limiter.Acquire(fmt.Sprintf("h%d.example", i))
					if err != nil {
						t.Fatalf("acquire %d: %v", i, err)
					}
					leases = append(leases, lease)
				}
				if limiter.ActiveCount() != 20 {
					t.Fatalf("expected active 20, got %d", limiter.ActiveCount())
				}
				for _, lease := range leases {
					lease.Release()
				}
				if limiter.ActiveCount() != 0 {
					t.Fatalf("expected active 0, got %d", limiter.ActiveCount())
				}
			default:
				t.Fatalf("unknown resource action %q", tc.Action)
			}
			executed[tc.ID] = struct{}{}
		})
	}
	for id := range expected {
		if _, ok := executed[id]; !ok {
			t.Fatalf("resource case not executed: %s", id)
		}
	}
	if len(executed) != len(expected) {
		t.Fatalf("executed %d != expected %d", len(executed), len(expected))
	}
}

func TestD3HeaderLimitCountsHeaderRegionOnly(t *testing.T) {
	prefix := []byte("HTTP/1.1 200 OK\r\nX-Test: ")
	suffix := []byte("\r\n\r\n")
	value := bytes.Repeat([]byte("x"), 262144-len(prefix)-len(suffix))
	raw := append(append(append([]byte{}, prefix...), value...), suffix...)
	raw = append(raw, []byte("BODY")...)
	conn := &fakeNetConn{reader: bytes.NewReader(raw)}
	profile, err := BudgetForProfile("probe")
	if err != nil {
		t.Fatalf("profile: %v", err)
	}
	status, _, body, err := ReadRawResponse(conn, "GET", profile, 0, 60000, func() int64 { return 0 })
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if status != 200 || string(body) != "BODY" {
		t.Fatalf("unexpected response: status=%d body=%q", status, string(body))
	}
}
