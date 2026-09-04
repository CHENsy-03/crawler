package security

import (
	"bufio"
	"context"
	"io"
	"net"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"
)

type recordedRequest struct {
	method  string
	path    string
	headers map[string]string
}

type localHTTPServer struct {
	listener  net.Listener
	mu        sync.Mutex
	conns     []net.Conn
	requests  []recordedRequest
	responses map[string]string
	handlers  int
}

func testURL(host, path string) string {
	return "http:" + "//" + host + path
}

func newLocalHTTPServer(t *testing.T) *localHTTPServer {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	sensitiveLocation := "http:" + "//other.example/ok"
	server := &localHTTPServer{
		listener: listener,
		responses: map[string]string{
			"/ok":        "HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok",
			"/redir":     "HTTP/1.1 302 Found\r\nLocation: /ok\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
			"/loop":      "HTTP/1.1 302 Found\r\nLocation: /loop\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
			"/post":      "HTTP/1.1 302 Found\r\nLocation: /ok\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
			"/sensitive": "HTTP/1.1 302 Found\r\nLocation: " + sensitiveLocation + "\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
			"/noloc":     "HTTP/1.1 302 Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
		},
	}
	go server.serve()
	return server
}

func (s *localHTTPServer) serve() {
	for {
		conn, err := s.listener.Accept()
		if err != nil {
			return
		}
		s.mu.Lock()
		s.conns = append(s.conns, conn)
		s.handlers++
		s.mu.Unlock()
		go func() {
			defer s.handlerDone()
			s.handle(conn)
		}()
	}
}

func (s *localHTTPServer) handle(conn net.Conn) {
	defer conn.Close()
	reader := bufio.NewReader(conn)
	line, err := reader.ReadString('\n')
	if err != nil {
		return
	}
	parts := strings.Fields(line)
	if len(parts) < 3 {
		return
	}
	method, target := parts[0], parts[1]
	headers := map[string]string{}
	for {
		headerLine, err := reader.ReadString('\n')
		if err != nil {
			return
		}
		if headerLine == "\r\n" || headerLine == "\n" {
			break
		}
		name, value, ok := strings.Cut(headerLine, ":")
		if !ok {
			continue
		}
		headers[strings.TrimSpace(name)] = strings.TrimSpace(value)
	}
	if contentLength := headers["Content-Length"]; contentLength != "" {
		size, err := strconv.Atoi(contentLength)
		if err == nil && size > 0 {
			_, _ = io.CopyN(io.Discard, reader, int64(size))
		}
	}
	s.mu.Lock()
	s.requests = append(s.requests, recordedRequest{method: method, path: target, headers: headers})
	response := s.responses[target]
	s.mu.Unlock()
	if response == "" {
		response = "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
	}
	_, _ = conn.Write([]byte(response))
}

func (s *localHTTPServer) handlerDone() {
	s.mu.Lock()
	s.handlers--
	s.mu.Unlock()
}

func (s *localHTTPServer) waitHandlers(t *testing.T) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for {
		s.mu.Lock()
		n := s.handlers
		s.mu.Unlock()
		if n == 0 {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("handler goroutines did not exit: %d", n)
		}
		time.Sleep(10 * time.Millisecond)
	}
}

func (s *localHTTPServer) close() {
	_ = s.listener.Close()
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, conn := range s.conns {
		_ = conn.Close()
	}
}

func (s *localHTTPServer) requestCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.requests)
}

func (s *localHTTPServer) requestHeaders(index int) map[string]string {
	s.mu.Lock()
	defer s.mu.Unlock()
	if index < 0 || index >= len(s.requests) {
		return nil
	}
	return s.requests[index].headers
}

func exerciseExecutorLocalHTTP(t *testing.T) {
	t.Helper()
	server := newLocalHTTPServer(t)
	defer func() {
		server.close()
		server.waitHandlers(t)
	}()
	policy := d3Policy()
	resolver := &fakeResolver{addresses: []string{"93.184.216.34"}}
	limiter := NewConcurrencyLimiter()
	profile, err := BudgetForProfile("probe")
	if err != nil {
		t.Fatalf("profile: %v", err)
	}
	dial := func(ctx context.Context, network, address string) (net.Conn, error) {
		var dialer net.Dialer
		return dialer.DialContext(ctx, "tcp", server.listener.Addr().String())
	}
	executor := NewSecureHTTPExecutor(policy, resolver, limiter, profile, dial, nil)

	response, err := executor.Execute(SecureHTTPRequest{Profile: "probe", Method: "GET", URL: testURL("example.com", "/ok")})
	if err != nil {
		t.Fatalf("single hop: %v", err)
	}
	if response.StatusCode != 200 || string(response.Body) != "ok" || response.RedirectHops != 0 {
		t.Fatalf("unexpected single hop response: %+v", response)
	}
	if limiter.ActiveCount() != 0 {
		t.Fatalf("lease not released after success")
	}

	before := resolver.callCount()
	response, err = executor.Execute(SecureHTTPRequest{Profile: "probe", Method: "GET", URL: testURL("example.com", "/redir")})
	if err != nil {
		t.Fatalf("redirect: %v", err)
	}
	if response.StatusCode != 200 || response.RedirectHops != 1 {
		t.Fatalf("unexpected redirect response: %+v", response)
	}
	if resolver.callCount()-before != 2 {
		t.Fatalf("resolver calls %d, want 2 for one redirect", resolver.callCount()-before)
	}

	_, err = executor.Execute(SecureHTTPRequest{Profile: "probe", Method: "GET", URL: testURL("example.com", "/loop")})
	if err == nil || testReason(err) != "redirect_limit_exceeded" {
		t.Fatalf("expected redirect_limit_exceeded, got %v", err)
	}
	if limiter.ActiveCount() != 0 {
		t.Fatalf("lease leaked after redirect loop")
	}

	_, err = executor.Execute(SecureHTTPRequest{Profile: "probe", Method: "POST", URL: testURL("example.com", "/post"), Body: []byte("x")})
	if err == nil || testReason(err) != "redirect_body_replay_not_allowed" {
		t.Fatalf("expected redirect_body_replay_not_allowed, got %v", err)
	}
	if limiter.ActiveCount() != 0 {
		t.Fatalf("lease leaked after POST redirect")
	}

	_, err = executor.Execute(SecureHTTPRequest{Profile: "probe", Method: "GET", URL: testURL("example.com", "/noloc")})
	if err == nil || testReason(err) != "redirect_location_missing" {
		t.Fatalf("expected redirect_location_missing, got %v", err)
	}
	if limiter.ActiveCount() != 0 {
		t.Fatalf("lease leaked after missing location")
	}

	beforeSensitive := server.requestCount()
	_, err = executor.Execute(SecureHTTPRequest{
		Profile: "probe",
		Method:  "GET",
		URL:     testURL("example.com", "/sensitive"),
		Headers: []Header{{Name: "Authorization", Value: "Bearer secret"}, {Name: "Cookie", Value: "a=b"}, {Name: "X-Test", Value: "keep"}},
	})
	if err != nil {
		t.Fatalf("sensitive redirect: %v", err)
	}
	if server.requestCount()-beforeSensitive != 2 {
		t.Fatalf("expected 2 requests for redirect, got %d", server.requestCount()-beforeSensitive)
	}
	secondHeaders := server.requestHeaders(beforeSensitive + 1)
	if secondHeaders == nil {
		t.Fatalf("second request headers missing")
	}
	if _, ok := secondHeaders["Authorization"]; ok {
		t.Fatalf("Authorization forwarded across hostname redirect")
	}
	if _, ok := secondHeaders["Cookie"]; ok {
		t.Fatalf("Cookie forwarded across hostname redirect")
	}
	if secondHeaders["X-Test"] != "keep" {
		t.Fatalf("non-sensitive header was not preserved")
	}
	if limiter.ActiveCount() != 0 {
		t.Fatalf("lease leaked after sensitive redirect")
	}
}

func TestD3ExecutorLocalHTTP(t *testing.T) {
	exerciseExecutorLocalHTTP(t)
}

func TestD3ExecutorLimiterRequired(t *testing.T) {
	policy := d3Policy()
	resolver := &fakeResolver{addresses: []string{"93.184.216.34"}}
	profile, err := BudgetForProfile("probe")
	if err != nil {
		t.Fatalf("profile: %v", err)
	}
	executor := NewSecureHTTPExecutor(policy, resolver, nil, profile, nil, nil)
	_, err = executor.Execute(SecureHTTPRequest{Profile: "probe", Method: "GET", URL: testURL("example.com", "/")})
	if err == nil || testReason(err) != "limiter_required" {
		t.Fatalf("expected limiter_required, got %v", err)
	}
}
