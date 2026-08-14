package security

import (
	"fmt"
	"net/netip"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"unicode"

	"golang.org/x/net/idna"
)

var schemePattern = regexp.MustCompile(`^([A-Za-z][A-Za-z0-9+.\-]*):`)

const (
	MaxURLUTF8Bytes   = 8192
	MaxHostnameOctets = 253
	MaxLabelOctets    = 63
)

type URLNormalizationError struct {
	ReasonCode string
}

func (e *URLNormalizationError) Error() string { return e.ReasonCode }

func fail(reason string) error { return &URLNormalizationError{ReasonCode: reason} }

func schemeFromRaw(raw string) (string, error) {
	match := schemePattern.FindStringSubmatch(raw)
	if match == nil {
		return "", nil
	}
	return strings.ToLower(match[1]), nil
}

func isUnicodeLabelSeparator(r rune) bool {
	return r == '.' || r == '\u3002' || r == '\uff0e' || r == '\uff61'
}

func looksLikeUnicodeNumericHost(value string) bool {
	if strings.HasSuffix(value, ".") {
		value = value[:len(value)-1]
	}
	if value == "" {
		return false
	}
	hasNonASCII := false
	for _, r := range value {
		if unicode.Is(unicode.Nd, r) {
			if r > 127 {
				hasNonASCII = true
			}
			continue
		}
		if isUnicodeLabelSeparator(r) {
			continue
		}
		return false
	}
	return hasNonASCII
}

func normalizeArabicIndicDigits(value string) string {
	var b strings.Builder
	for _, r := range value {
		switch {
		case r >= 0x0660 && r <= 0x0669:
			b.WriteRune('0' + (r - 0x0660))
		case r >= 0x06F0 && r <= 0x06F9:
			b.WriteRune('0' + (r - 0x06F0))
		default:
			b.WriteRune(r)
		}
	}
	return b.String()
}

func isHexByte(b byte) bool {
	return (b >= '0' && b <= '9') || (b >= 'a' && b <= 'f') || (b >= 'A' && b <= 'F')
}

func hexValue(b byte) int {
	switch {
	case b >= '0' && b <= '9':
		return int(b - '0')
	case b >= 'a' && b <= 'f':
		return int(b-'a') + 10
	default:
		return int(b-'A') + 10
	}
}

func upperHex(b byte) byte {
	if b >= 'a' && b <= 'f' {
		return b - 'a' + 'A'
	}
	return b
}

func isUnreserved(b byte) bool {
	return (b >= 'a' && b <= 'z') || (b >= 'A' && b <= 'Z') || (b >= '0' && b <= '9') || b == '-' || b == '.' || b == '_' || b == '~'
}

func rejectControlAndBackslash(raw string) error {
	for _, r := range raw {
		if r == '\\' {
			return fail("backslash_not_allowed")
		}
		if unicode.IsSpace(r) || unicode.IsControl(r) || unicode.Is(unicode.Cf, r) {
			return fail("control_character")
		}
	}
	return nil
}

func parseStrictIPv4(host string) (string, bool) {
	parts := strings.Split(host, ".")
	if len(parts) != 4 {
		return "", false
	}
	out := make([]string, 4)
	for i, part := range parts {
		if part == "" || len(part) > 3 {
			return "", false
		}
		if len(part) > 1 && part[0] == '0' {
			return "", false
		}
		n, err := strconv.Atoi(part)
		if err != nil || n < 0 || n > 255 {
			return "", false
		}
		out[i] = strconv.Itoa(n)
	}
	return strings.Join(out, "."), true
}

func looksNumericAmbiguous(host string) bool {
	digitsDots := true
	hasDot := false
	for _, r := range host {
		if r >= '0' && r <= '9' {
			continue
		}
		if r == '.' {
			hasDot = true
			continue
		}
		digitsDots = false
		break
	}
	if digitsDots {
		return true
	}
	if strings.HasPrefix(host, "0x") || strings.HasPrefix(host, "0X") {
		rest := host[2:]
		allHex := rest != ""
		for _, r := range rest {
			if !isHexByte(byte(r)) {
				allHex = false
				break
			}
		}
		if allHex {
			return true
		}
	}
	if strings.Contains(strings.ToLower(host), "x") {
		allMixed := true
		for _, r := range host {
			if isHexByte(byte(r)) || r == '.' || r == 'x' || r == 'X' {
				continue
			}
			allMixed = false
			break
		}
		if allMixed {
			return true
		}
	}
	_ = hasDot
	return false
}

func normalizeHost(rawAuthority, host string) (string, bool, error) {
	if host == "" {
		return "", false, fail("invalid_host")
	}
	if strings.Contains(host, "%") {
		return "", false, fail("invalid_host")
	}

	if strings.HasPrefix(rawAuthority, "[") {
		addr, err := netip.ParseAddr(host)
		if err != nil || !addr.Is6() {
			return "", false, fail("invalid_host")
		}
		return addr.String(), true, nil
	}

	if quad, ok := parseStrictIPv4(host); ok {
		return quad, true, nil
	}
	if looksLikeUnicodeNumericHost(host) {
		return "", false, fail("ambiguous_ip_literal")
	}
	if looksNumericAmbiguous(host) {
		return "", false, fail("ambiguous_ip_literal")
	}

	candidate := host
	if strings.HasSuffix(candidate, ".") {
		candidate = candidate[:len(candidate)-1]
	}
	if candidate == "" || strings.HasPrefix(candidate, ".") || strings.Contains(candidate, "..") {
		return "", false, fail("invalid_host")
	}
	if len(candidate) > MaxHostnameOctets {
		return "", false, fail("host_too_long")
	}
	labels := strings.Split(candidate, ".")
	for _, label := range labels {
		if label == "" {
			return "", false, fail("invalid_host")
		}
		if len(label) > MaxLabelOctets {
			return "", false, fail("label_too_long")
		}
	}

	candidate = normalizeArabicIndicDigits(candidate)
	asciiHost, err := idna.Lookup.ToASCII(candidate)
	if err != nil {
		return "", false, fail("invalid_idna")
	}
	asciiHost = strings.ToLower(asciiHost)
	if asciiHost == "" || len(asciiHost) > MaxHostnameOctets {
		return "", false, fail("host_too_long")
	}
	for _, label := range strings.Split(asciiHost, ".") {
		if label == "" {
			return "", false, fail("invalid_host")
		}
		if len(label) > MaxLabelOctets {
			return "", false, fail("label_too_long")
		}
		if strings.HasPrefix(label, "xn--") {
			decoded, err := idna.Lookup.ToUnicode(label)
			if err != nil || !containsNonASCII(decoded) {
				return "", false, fail("invalid_idna")
			}
		}
	}
	if _, ok := parseStrictIPv4(asciiHost); ok || looksNumericAmbiguous(asciiHost) {
		return "", false, fail("ambiguous_ip_literal")
	}
	return asciiHost, false, nil
}

func containsNonASCII(s string) bool {
	for _, r := range s {
		if r > 127 {
			return true
		}
	}
	return false
}

func canonicalPercent(value string) (string, error) {
	var b strings.Builder
	for i := 0; i < len(value); {
		c := value[i]
		if c == '%' {
			if i+2 >= len(value) || !isHexByte(value[i+1]) || !isHexByte(value[i+2]) {
				return "", fail("invalid_percent_encoding")
			}
			code := hexValue(value[i+1])<<4 | hexValue(value[i+2])
			if code < 0x20 || code == 0x7F {
				return "", fail("invalid_percent_encoding")
			}
			if isUnreserved(byte(code)) {
				b.WriteByte(byte(code))
			} else {
				b.WriteByte('%')
				b.WriteByte(upperHex(value[i+1]))
				b.WriteByte(upperHex(value[i+2]))
			}
			i += 3
			continue
		}
		if c < 0x80 {
			if c < 0x20 || c == 0x7F {
				return "", fail("invalid_percent_encoding")
			}
			b.WriteByte(c)
			i++
			continue
		}
		fmt.Fprintf(&b, "%%%02X", c)
		i++
	}
	return b.String(), nil
}

func removeLastSegment(output string) string {
	idx := strings.LastIndex(output, "/")
	if idx < 0 {
		return ""
	}
	return output[:idx]
}

func removeDotSegments(path string) string {
	remaining := path
	output := ""
	for remaining != "" {
		switch {
		case strings.HasPrefix(remaining, "../"):
			remaining = remaining[3:]
		case strings.HasPrefix(remaining, "./"):
			remaining = remaining[2:]
		case strings.HasPrefix(remaining, "/./"):
			remaining = "/" + remaining[3:]
		case remaining == "/.":
			remaining = "/"
		case strings.HasPrefix(remaining, "/../"):
			remaining = "/" + remaining[4:]
			output = removeLastSegment(output)
		case remaining == "/..":
			remaining = "/"
			output = removeLastSegment(output)
		case remaining == "." || remaining == "..":
			remaining = ""
		default:
			if strings.HasPrefix(remaining, "/") {
				next := strings.Index(remaining[1:], "/")
				if next < 0 {
					output += remaining
					remaining = ""
				} else {
					idx := next + 1
					output += remaining[:idx]
					remaining = remaining[idx:]
				}
			} else {
				next := strings.Index(remaining, "/")
				if next < 0 {
					output += remaining
					remaining = ""
				} else {
					output += remaining[:next]
					remaining = remaining[next:]
				}
			}
		}
	}
	return output
}

func splitRawPathQuery(raw string) (string, string) {
	idx := strings.Index(raw, "://")
	if idx < 0 {
		return "", ""
	}
	rest := raw[idx+3:]
	authEnd := strings.IndexAny(rest, "/?#")
	if authEnd < 0 {
		return "", ""
	}
	rest = rest[authEnd:]
	if i := strings.IndexByte(rest, '#'); i >= 0 {
		rest = rest[:i]
	}
	if i := strings.IndexByte(rest, '?'); i >= 0 {
		return rest[:i], rest[i+1:]
	}
	return rest, ""
}

func authorityFromRaw(raw string) string {
	idx := strings.Index(raw, "://")
	if idx < 0 {
		return ""
	}
	authority := raw[idx+3:]
	if end := strings.IndexAny(authority, "/?#"); end >= 0 {
		authority = authority[:end]
	}
	return authority
}

func pathQueryHasInvalidPercent(raw string) bool {
	path, query := splitRawPathQuery(raw)
	if _, err := canonicalPercent(path); err != nil {
		return true
	}
	if _, err := canonicalPercent(query); err != nil {
		return true
	}
	return false
}

func validateRawPort(raw string) error {
	idx := strings.Index(raw, "://")
	if idx < 0 {
		return nil
	}
	authority := raw[idx+3:]
	if end := strings.IndexAny(authority, "/?#"); end >= 0 {
		authority = authority[:end]
	}
	if strings.Contains(authority, "@") {
		return nil
	}
	if strings.HasPrefix(authority, "[") {
		closeBracket := strings.Index(authority, "]")
		if closeBracket < 0 {
			return fail("invalid_url")
		}
		suffix := authority[closeBracket+1:]
		if suffix == "" {
			return nil
		}
		if !strings.HasPrefix(suffix, ":") {
			return fail("invalid_port")
		}
		portStr := suffix[1:]
		if !validPortString(portStr) {
			return fail("invalid_port")
		}
		return nil
	}
	colon := strings.LastIndex(authority, ":")
	if colon < 0 {
		return nil
	}
	portStr := authority[colon+1:]
	if !validPortString(portStr) {
		return fail("invalid_port")
	}
	return nil
}

func validPortString(portStr string) bool {
	if portStr == "" {
		return false
	}
	for i := 0; i < len(portStr); i++ {
		if portStr[i] < '0' || portStr[i] > '9' {
			return false
		}
	}
	n, err := strconv.Atoi(portStr)
	return err == nil && n > 0 && n <= 65535
}

func NormalizeOutboundURL(raw string) (NormalizedURL, error) {
	if raw == "" {
		return NormalizedURL{}, fail("empty_url")
	}
	if len([]byte(raw)) > MaxURLUTF8Bytes {
		return NormalizedURL{}, fail("url_too_long")
	}
	if err := rejectControlAndBackslash(raw); err != nil {
		return NormalizedURL{}, err
	}
	scheme, schemeErr := schemeFromRaw(raw)
	if schemeErr != nil {
		return NormalizedURL{}, schemeErr
	}
	if scheme == "" {
		return NormalizedURL{}, fail("absolute_url_required")
	}
	if scheme != "http" && scheme != "https" {
		return NormalizedURL{}, fail("scheme_not_allowed")
	}
	if err := validateRawPort(raw); err != nil {
		return NormalizedURL{}, err
	}
	u, err := url.Parse(raw)
	if err != nil {
		if pathQueryHasInvalidPercent(raw) {
			return NormalizedURL{}, fail("invalid_percent_encoding")
		}
		if strings.Contains(authorityFromRaw(raw), "%") {
			return NormalizedURL{}, fail("invalid_host")
		}
		return NormalizedURL{}, fail("invalid_url")
	}
	scheme = strings.ToLower(u.Scheme)
	if !strings.Contains(raw, "://") {
		return NormalizedURL{}, fail("absolute_url_required")
	}
	if u.Host == "" {
		return NormalizedURL{}, fail("authority_required")
	}
	if u.User != nil || strings.Contains(u.Host, "@") {
		return NormalizedURL{}, fail("userinfo_not_allowed")
	}
	hostname := u.Hostname()
	if hostname == "" {
		return NormalizedURL{}, fail("invalid_host")
	}

	if strings.HasSuffix(u.Host, ":") {
		return NormalizedURL{}, fail("invalid_port")
	}
	rawPort := u.Port()
	var port int
	explicitPort := rawPort != ""
	if explicitPort {
		parsed, err := strconv.Atoi(rawPort)
		if err != nil || parsed <= 0 || parsed > 65535 {
			return NormalizedURL{}, fail("invalid_port")
		}
		port = parsed
	} else if scheme == "http" {
		port = 80
	} else {
		port = 443
	}

	host, isIPLiteral, err := normalizeHost(u.Host, hostname)
	if err != nil {
		return NormalizedURL{}, err
	}
	hostForAuthority := host
	if isIPLiteral && strings.Contains(host, ":") {
		hostForAuthority = "[" + host + "]"
	}
	authority := hostForAuthority
	defaultPort := 80
	if scheme == "https" {
		defaultPort = 443
	}
	if explicitPort && port != defaultPort {
		authority = fmt.Sprintf("%s:%d", hostForAuthority, port)
	}

	path, query := splitRawPathQuery(raw)
	canonicalPath, err := canonicalPercent(path)
	if err != nil {
		return NormalizedURL{}, err
	}
	canonicalQuery, err := canonicalPercent(query)
	if err != nil {
		return NormalizedURL{}, err
	}
	canonicalPath = removeDotSegments(canonicalPath)
	if canonicalPath == "" || canonicalPath == "." {
		canonicalPath = "/"
	}

	normalized := scheme + "://" + authority + canonicalPath
	if canonicalQuery != "" {
		normalized += "?" + canonicalQuery
	}
	if len([]byte(normalized)) > MaxURLUTF8Bytes {
		return NormalizedURL{}, fail("url_too_long")
	}

	return NormalizedURL{
		Scheme:        scheme,
		Host:          host,
		Port:          port,
		ExplicitPort:  explicitPort,
		Authority:     authority,
		NormalizedURL: normalized,
		IsIPLiteral:   isIPLiteral,
	}, nil
}
