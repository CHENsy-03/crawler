package security

import (
	"bytes"
	"fmt"
	"io"
	"net"
	"strconv"
	"strings"
	"time"
)

// SecureHTTPError is a stable secure transport failure.
type SecureHTTPError struct {
	ReasonCode string
}

func (e *SecureHTTPError) Error() string { return e.ReasonCode }

func secureHTTPFail(reason string) error { return &SecureHTTPError{ReasonCode: reason} }

// SecureHTTPRequest is an immutable request model.
type SecureHTTPRequest struct {
	Profile string
	Method  string
	URL     string
	Headers []Header
	Body    []byte
}

// Header is a single HTTP header pair.
type Header struct {
	Name  string
	Value string
}

// SecureHTTPResponse is the bounded response result.
type SecureHTTPResponse struct {
	StatusCode   int
	FinalURL     string
	Headers      []Header
	Body         []byte
	RedirectHops int
}

func invalidHeaderValue(value string) bool {
	return strings.ContainsAny(value, "\r\n\x00")
}

func isHTTPToken(value string) bool {
	if value == "" {
		return false
	}
	for _, r := range value {
		if r > 127 {
			return false
		}
		switch {
		case r >= '0' && r <= '9':
		case r >= 'A' && r <= 'Z':
		case r >= 'a' && r <= 'z':
		case strings.ContainsRune("!#$%&'*+-.^_`|~", r):
		default:
			return false
		}
	}
	return true
}

func trimOWS(value []byte) []byte {
	return bytes.Trim(value, " \t")
}

// ValidateSecureRequest validates method, body, and headers.
func ValidateSecureRequest(req SecureHTTPRequest) error {
	switch req.Method {
	case "GET", "HEAD", "POST":
	default:
		return secureHTTPFail("method_not_allowed")
	}
	if req.Method == "GET" || req.Method == "HEAD" {
		if len(req.Body) != 0 {
			return secureHTTPFail("method_body_not_allowed")
		}
	}
	if err := CheckRequestBodySize(len(req.Body)); err != nil {
		return err
	}
	for _, header := range req.Headers {
		if invalidHeaderValue(header.Name) || invalidHeaderValue(header.Value) {
			return secureHTTPFail("invalid_header")
		}
		if !isHTTPToken(header.Name) {
			return secureHTTPFail("invalid_header")
		}
		switch strings.ToLower(header.Name) {
		case "host", "transfer-encoding", "proxy-authorization", "connection", "content-length":
			return secureHTTPFail("forbidden_header")
		}
	}
	return nil
}

// BuildRequestBytes builds the raw HTTP/1.1 request.
func BuildRequestBytes(req SecureHTTPRequest, host string) ([]byte, error) {
	if err := ValidateSecureRequest(req); err != nil {
		return nil, err
	}
	idx := strings.Index(req.URL, "://")
	rest := req.URL
	if idx >= 0 {
		rest = req.URL[idx+3:]
	}
	slash := strings.IndexByte(rest, '/')
	path := "/"
	if slash >= 0 {
		path = rest[slash:]
	}
	if path == "" {
		path = "/"
	}
	var buf bytes.Buffer
	fmt.Fprintf(&buf, "%s %s HTTP/1.1\r\n", req.Method, path)
	fmt.Fprintf(&buf, "Host: %s\r\n", host)
	sentEncoding := false
	for _, header := range req.Headers {
		if strings.EqualFold(header.Name, "Accept-Encoding") {
			sentEncoding = true
		}
		fmt.Fprintf(&buf, "%s: %s\r\n", header.Name, header.Value)
	}
	if !sentEncoding {
		buf.WriteString("Accept-Encoding: identity\r\n")
	}
	if req.Method == "POST" {
		fmt.Fprintf(&buf, "Content-Length: %d\r\n", len(req.Body))
	}
	buf.WriteString("Connection: close\r\n\r\n")
	buf.Write(req.Body)
	return buf.Bytes(), nil
}

func parseResponseHead(head []byte) (int, []Header, error) {
	lines := bytes.Split(head, []byte("\r\n"))
	firstLine := lines[0]
	for _, b := range firstLine {
		if b < 0x20 && b != 0x09 && b != 0x20 {
			return 0, nil, secureHTTPFail("invalid_http_response")
		}
		if b == 0x7f {
			return 0, nil, secureHTTPFail("invalid_http_response")
		}
	}
	statusParts := bytes.SplitN(firstLine, []byte(" "), 3)
	if len(statusParts) < 2 {
		return 0, nil, secureHTTPFail("invalid_http_response")
	}
	version := string(statusParts[0])
	if version != "HTTP/1.0" && version != "HTTP/1.1" {
		return 0, nil, secureHTTPFail("invalid_http_response")
	}
	statusText := statusParts[1]
	if len(statusText) != 3 {
		return 0, nil, secureHTTPFail("invalid_http_response")
	}
	for _, b := range statusText {
		if b < '0' || b > '9' {
			return 0, nil, secureHTTPFail("invalid_http_response")
		}
	}
	status, err := strconv.Atoi(string(statusText))
	if err != nil {
		return 0, nil, secureHTTPFail("invalid_http_response")
	}
	headers := make([]Header, 0, len(lines)-1)
	for _, line := range lines[1:] {
		if len(line) == 0 {
			return 0, nil, secureHTTPFail("invalid_http_response")
		}
		if line[0] == ' ' || line[0] == '\t' {
			return 0, nil, secureHTTPFail("invalid_http_response")
		}
		if bytes.ContainsAny(line, "\r\n\x00") {
			return 0, nil, secureHTTPFail("invalid_http_response")
		}
		name, value, ok := bytes.Cut(line, []byte(":"))
		if !ok || len(name) == 0 {
			return 0, nil, secureHTTPFail("invalid_http_response")
		}
		if !isHTTPToken(string(name)) {
			return 0, nil, secureHTTPFail("invalid_http_response")
		}
		valueText := string(trimOWS(value))
		if strings.ContainsAny(valueText, "\r\n\x00") {
			return 0, nil, secureHTTPFail("invalid_http_response")
		}
		headers = append(headers, Header{Name: string(name), Value: valueText})
	}
	return status, headers, nil
}

func readResponseHeads(conn net.Conn, timeoutMS int) (int, []Header, []byte, error) {
	_ = conn.SetReadDeadline(time.Now().Add(time.Duration(timeoutMS) * time.Millisecond))
	pending := make([]byte, 0, 4096)
	tmp := make([]byte, 4096)
	used := 0
	for {
		if idx := bytes.Index(pending, []byte("\r\n\r\n")); idx >= 0 {
			headEnd := idx + 4
			total := used + headEnd
			if total > NewTransportBudget().ResponseHeadersBytes() {
				return 0, nil, nil, secureHTTPFail("response_headers_too_large")
			}
			status, headers, err := parseResponseHead(pending[:idx])
			if err != nil {
				return 0, nil, nil, err
			}
			pending = pending[headEnd:]
			used = total
			if status == 101 {
				return 0, nil, nil, secureHTTPFail("protocol_upgrade_not_allowed")
			}
			if status >= 100 && status <= 199 {
				continue
			}
			if status < 200 || status > 599 {
				return 0, nil, nil, secureHTTPFail("invalid_http_response")
			}
			return status, headers, pending, nil
		}
		if used+len(pending) >= NewTransportBudget().ResponseHeadersBytes() {
			return 0, nil, nil, secureHTTPFail("response_headers_too_large")
		}
		n, err := conn.Read(tmp)
		if n > 0 {
			pending = append(pending, tmp[:n]...)
		}
		if err != nil {
			if ne, ok := err.(net.Error); ok && ne.Timeout() {
				return 0, nil, nil, secureHTTPFail("response_header_timeout")
			}
			return 0, nil, nil, secureHTTPFail("connection_failed")
		}
		if n == 0 {
			return 0, nil, nil, secureHTTPFail("connection_failed")
		}
	}
}

type timedConnReader struct {
	conn    net.Conn
	startMS int64
	totalMS int64
	clock   func() int64
}

func (r *timedConnReader) Read(maxBytes int, timeoutMS int) ([]byte, error) {
	now := r.clock()
	if now-r.startMS >= r.totalMS {
		return nil, &BoundedIOError{ReasonCode: "total_timeout_exceeded"}
	}
	remaining := r.totalMS - (now - r.startMS)
	deadline := int64(timeoutMS)
	if remaining < deadline {
		deadline = remaining
	}
	if deadline <= 0 {
		return nil, &BoundedIOError{ReasonCode: "total_timeout_exceeded"}
	}
	_ = r.conn.SetReadDeadline(time.Now().Add(time.Duration(deadline) * time.Millisecond))
	buf := make([]byte, maxBytes)
	n, err := r.conn.Read(buf)
	if n > 0 {
		return buf[:n], nil
	}
	if err != nil {
		if ne, ok := err.(net.Error); ok && ne.Timeout() {
			if r.clock()-r.startMS >= r.totalMS {
				return nil, &BoundedIOError{ReasonCode: "total_timeout_exceeded"}
			}
			return nil, &BoundedIOError{ReasonCode: "read_idle_timeout"}
		}
		if err == io.EOF {
			return []byte{}, nil
		}
		return nil, err
	}
	return []byte{}, nil
}

type pendingConnReader struct {
	timedConnReader
	pending []byte
}

func (r *pendingConnReader) Read(maxBytes int, timeoutMS int) ([]byte, error) {
	if len(r.pending) > 0 {
		if maxBytes > len(r.pending) {
			maxBytes = len(r.pending)
		}
		out := r.pending[:maxBytes]
		r.pending = r.pending[maxBytes:]
		return out, nil
	}
	return r.timedConnReader.Read(maxBytes, timeoutMS)
}

type lengthLimitedReader struct {
	reader    pendingConnReader
	remaining int
}

func (r *lengthLimitedReader) Read(maxBytes int, timeoutMS int) ([]byte, error) {
	if r.remaining <= 0 {
		return []byte{}, nil
	}
	if maxBytes > r.remaining {
		maxBytes = r.remaining
	}
	data, err := r.reader.Read(maxBytes, timeoutMS)
	r.remaining -= len(data)
	return data, err
}

const maxChunkLineBytes = 8192

func isHexDigit(b byte) bool {
	return (b >= '0' && b <= '9') || (b >= 'a' && b <= 'f') || (b >= 'A' && b <= 'F')
}

func readChunkedBody(conn net.Conn, profile BudgetProfile, startMS, totalMS int64, clock func() int64, initial []byte) ([]byte, error) {
	limit := profile.ResponseBodyBytes()
	pending := append([]byte(nil), initial...)
	result := make([]byte, 0, 1024)

	readSome := func(size int) error {
		for len(pending) < size {
			now := clock()
			if now-startMS >= totalMS {
				return &BoundedIOError{ReasonCode: "total_timeout_exceeded"}
			}
			remaining := totalMS - (now - startMS)
			timeoutMS := int64(1000)
			if remaining < timeoutMS {
				timeoutMS = remaining
			}
			if timeoutMS <= 0 {
				return &BoundedIOError{ReasonCode: "total_timeout_exceeded"}
			}
			_ = conn.SetReadDeadline(time.Now().Add(time.Duration(timeoutMS) * time.Millisecond))
			tmp := make([]byte, size-len(pending))
			n, err := conn.Read(tmp)
			if n > 0 {
				pending = append(pending, tmp[:n]...)
				continue
			}
			if err != nil {
				if ne, ok := err.(net.Error); ok && ne.Timeout() {
					if clock()-startMS >= totalMS {
						return &BoundedIOError{ReasonCode: "total_timeout_exceeded"}
					}
					return &BoundedIOError{ReasonCode: "read_idle_timeout"}
				}
				return secureHTTPFail("connection_failed")
			}
			return secureHTTPFail("connection_failed")
		}
		return nil
	}

	readLine := func() ([]byte, error) {
		for {
			if idx := bytes.Index(pending, []byte("\r\n")); idx >= 0 {
				line := pending[:idx]
				pending = pending[idx+2:]
				return line, nil
			}
			if len(pending) >= maxChunkLineBytes {
				return nil, secureHTTPFail("invalid_chunked_encoding")
			}
			now := clock()
			if now-startMS >= totalMS {
				return nil, &BoundedIOError{ReasonCode: "total_timeout_exceeded"}
			}
			remaining := totalMS - (now - startMS)
			timeoutMS := int64(1000)
			if remaining < timeoutMS {
				timeoutMS = remaining
			}
			if timeoutMS <= 0 {
				return nil, &BoundedIOError{ReasonCode: "total_timeout_exceeded"}
			}
			_ = conn.SetReadDeadline(time.Now().Add(time.Duration(timeoutMS) * time.Millisecond))
			tmp := make([]byte, 4096)
			n, err := conn.Read(tmp)
			if n > 0 {
				pending = append(pending, tmp[:n]...)
				continue
			}
			if err != nil {
				if ne, ok := err.(net.Error); ok && ne.Timeout() {
					if clock()-startMS >= totalMS {
						return nil, &BoundedIOError{ReasonCode: "total_timeout_exceeded"}
					}
					return nil, &BoundedIOError{ReasonCode: "read_idle_timeout"}
				}
				return nil, secureHTTPFail("connection_failed")
			}
			return nil, secureHTTPFail("connection_failed")
		}
	}

	for {
		line, err := readLine()
		if err != nil {
			return nil, err
		}
		if bytes.Contains(line, []byte(";")) {
			return nil, secureHTTPFail("chunk_extension_not_allowed")
		}
		if len(line) == 0 {
			return nil, secureHTTPFail("invalid_chunked_encoding")
		}
		for _, b := range line {
			if !isHexDigit(b) {
				return nil, secureHTTPFail("invalid_chunked_encoding")
			}
		}
		sizeValue, err := strconv.ParseInt(string(line), 16, 64)
		if err != nil {
			return nil, secureHTTPFail("invalid_chunked_encoding")
		}
		if sizeValue == 0 {
			trailerLine, err := readLine()
			if err != nil {
				return nil, err
			}
			if len(trailerLine) != 0 {
				return nil, secureHTTPFail("invalid_chunked_trailer")
			}
			break
		}
		if sizeValue > int64(limit-len(result)) {
			return nil, secureHTTPFail("response_body_too_large")
		}
		if err := readSome(int(sizeValue)); err != nil {
			return nil, err
		}
		result = append(result, pending[:sizeValue]...)
		pending = pending[sizeValue:]
		if err := readSome(2); err != nil {
			return nil, err
		}
		if !bytes.Equal(pending[:2], []byte("\r\n")) {
			return nil, secureHTTPFail("invalid_chunked_encoding")
		}
		pending = pending[2:]
	}
	return result, nil
}

func validateFramingHeaders(headerMap map[string][]string) error {
	teValues := headerMap["transfer-encoding"]
	clValues := headerMap["content-length"]
	if len(teValues) == 0 {
		return nil
	}
	if len(clValues) > 0 {
		return secureHTTPFail("invalid_transfer_encoding")
	}
	codings := make([]string, 0, 4)
	for _, value := range teValues {
		for _, part := range strings.Split(value, ",") {
			codings = append(codings, strings.ToLower(strings.Trim(part, " \t")))
		}
	}
	if len(codings) != 1 || codings[0] != "chunked" {
		return secureHTTPFail("invalid_transfer_encoding")
	}
	return nil
}

// ReadRawResponse reads a raw HTTP/1.1 response without keep-alive reuse.
func ReadRawResponse(conn net.Conn, method string, profile BudgetProfile, startMS, totalMS int64, clock func() int64) (int, []Header, []byte, error) {
	if totalMS <= 0 {
		return 0, nil, nil, &BoundedIOError{ReasonCode: "total_timeout_exceeded"}
	}
	budget := NewTransportBudget()
	headerTimeout := budget.ResponseHeaderTimeoutMS()
	if int64(headerTimeout) > totalMS {
		headerTimeout = int(totalMS)
	}
	status, headers, rest, err := readResponseHeads(conn, headerTimeout)
	if err != nil {
		return 0, nil, nil, err
	}
	headerMap := map[string][]string{}
	for _, header := range headers {
		key := strings.ToLower(header.Name)
		headerMap[key] = append(headerMap[key], header.Value)
	}
	if method == "HEAD" || status == 204 || status == 304 {
		if err := validateFramingHeaders(headerMap); err != nil {
			return 0, nil, nil, err
		}
		return status, headers, []byte{}, nil
	}
	if err := validateFramingHeaders(headerMap); err != nil {
		return 0, nil, nil, err
	}
	if enc := headerMap["content-encoding"]; len(enc) > 0 && strings.ToLower(enc[0]) != "identity" {
		return 0, nil, nil, secureHTTPFail("unsupported_content_encoding")
	}
	if len(headerMap["transfer-encoding"]) > 0 {
		body, err := readChunkedBody(conn, profile, startMS, totalMS, clock, rest)
		if err != nil {
			return 0, nil, nil, err
		}
		return status, headers, body, nil
	}
	clValues := headerMap["content-length"]
	if len(clValues) > 0 {
		anyValues := make([]any, 0, len(clValues))
		for _, value := range clValues {
			anyValues = append(anyValues, value)
		}
		declared, err := ValidateContentLengths(anyValues, profile)
		if err != nil {
			return 0, nil, nil, err
		}
		reader := &lengthLimitedReader{reader: pendingConnReader{timedConnReader: timedConnReader{conn: conn, startMS: startMS, totalMS: totalMS, clock: clock}, pending: rest}, remaining: declared}
		result, err := ReadBoundedWithClock(profile, reader, clock)
		if err != nil {
			return 0, nil, nil, err
		}
		if result.TotalRead < declared {
			return 0, nil, nil, secureHTTPFail("connection_failed")
		}
		return status, headers, result.Data, nil
	}
	reader := &pendingConnReader{timedConnReader: timedConnReader{conn: conn, startMS: startMS, totalMS: totalMS, clock: clock}, pending: rest}
	result, err := ReadBoundedWithClock(profile, reader, clock)
	if err != nil {
		return 0, nil, nil, err
	}
	return status, headers, result.Data, nil
}
