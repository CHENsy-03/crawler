package security

import (
	"net/netip"
	"strings"
	"sync"
	"unicode"
)

// ConcurrencyError is a stable limiter failure.
type ConcurrencyError struct {
	ReasonCode string
}

func (e *ConcurrencyError) Error() string { return e.ReasonCode }

func concurrencyFail(reason string) error { return &ConcurrencyError{ReasonCode: reason} }

type leaseToken struct {
	limiter  *ConcurrencyLimiter
	host     string
	released bool
}

// Lease releases exactly one acquired concurrency slot.
type Lease struct {
	token *leaseToken
}

// Release is idempotent and never makes counts negative.
func (l *Lease) Release() bool {
	if l == nil || l.token == nil {
		return false
	}
	return l.token.limiter.release(l.token)
}

// ConcurrencyLimiter is a process-wide fail-fast active connection limiter.
type ConcurrencyLimiter struct {
	mu           sync.Mutex
	active       int
	hosts        map[string]int
	globalLimit  int
	perHostLimit int
}

// NewConcurrencyLimiter reads limits from the sealed D1 TransportBudget.
func NewConcurrencyLimiter() *ConcurrencyLimiter {
	budget := NewTransportBudget()
	return &ConcurrencyLimiter{
		hosts:        make(map[string]int),
		globalLimit:  budget.GlobalActive(),
		perHostLimit: budget.PerHostActive(),
	}
}

func canonicalIPv4(host string) (string, bool) {
	parts := strings.Split(host, ".")
	if len(parts) != 4 {
		return "", false
	}
	out := make([]string, 0, 4)
	for _, part := range parts {
		if part == "" || len(part) > 3 {
			return "", false
		}
		if len(part) > 1 && part[0] == '0' {
			return "", false
		}
		value := 0
		for _, r := range part {
			if r < '0' || r > '9' {
				return "", false
			}
			value = value*10 + int(r-'0')
		}
		if value > 255 {
			return "", false
		}
		out = append(out, part)
	}
	return strings.Join(out, "."), true
}

func normalizeHostKey(host string) (string, error) {
	if host == "" {
		return "", concurrencyFail("invalid_host_key")
	}
	for _, r := range host {
		if r > unicode.MaxASCII || unicode.IsSpace(r) || unicode.IsControl(r) || unicode.Is(unicode.Cf, r) {
			return "", concurrencyFail("invalid_host_key")
		}
	}
	if strings.ContainsAny(host, "@/?#\\") {
		return "", concurrencyFail("invalid_host_key")
	}
	lower := strings.ToLower(host)
	if strings.Contains(lower, ":") {
		if strings.HasPrefix(lower, "[") || strings.Contains(lower, "%") {
			return "", concurrencyFail("invalid_host_key")
		}
		if addr, err := netip.ParseAddr(lower); err == nil {
			return addr.String(), nil
		}
		return "", concurrencyFail("invalid_host_key")
	}
	if strings.Contains(lower, ".") {
		parts := strings.Split(lower, ".")
		if len(parts) == 4 {
			allDigits := true
			for _, part := range parts {
				if part == "" {
					allDigits = false
					break
				}
				for _, r := range part {
					if r < '0' || r > '9' {
						allDigits = false
						break
					}
				}
				if !allDigits {
					break
				}
			}
			if allDigits {
				canonical, ok := canonicalIPv4(lower)
				if !ok {
					return "", concurrencyFail("invalid_host_key")
				}
				return canonical, nil
			}
		}
	}
	if strings.HasSuffix(lower, ".") {
		lower = strings.TrimSuffix(lower, ".")
		if lower == "" || strings.HasSuffix(lower, ".") {
			return "", concurrencyFail("invalid_host_key")
		}
	}
	labels := strings.Split(lower, ".")
	if len(lower) > 253 {
		return "", concurrencyFail("invalid_host_key")
	}
	for _, label := range labels {
		if label == "" || len(label) > 63 {
			return "", concurrencyFail("invalid_host_key")
		}
		if !((label[0] >= 'a' && label[0] <= 'z') || (label[0] >= '0' && label[0] <= '9')) {
			return "", concurrencyFail("invalid_host_key")
		}
		if !((label[len(label)-1] >= 'a' && label[len(label)-1] <= 'z') || (label[len(label)-1] >= '0' && label[len(label)-1] <= '9')) {
			return "", concurrencyFail("invalid_host_key")
		}
		for _, r := range label {
			if !((r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') || r == '-') {
				return "", concurrencyFail("invalid_host_key")
			}
		}
	}
	return lower, nil
}

// Acquire reserves one global and one per-host slot.
func (l *ConcurrencyLimiter) Acquire(host string) (Lease, error) {
	key, err := normalizeHostKey(host)
	if err != nil {
		return Lease{}, err
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.active >= l.globalLimit {
		return Lease{}, concurrencyFail("global_concurrency_exceeded")
	}
	if l.hosts[key] >= l.perHostLimit {
		return Lease{}, concurrencyFail("host_concurrency_exceeded")
	}
	l.active++
	l.hosts[key]++
	return Lease{token: &leaseToken{limiter: l, host: key}}, nil
}

func (l *ConcurrencyLimiter) release(token *leaseToken) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	if token == nil || token.limiter != l || token.released {
		return false
	}
	if l.active <= 0 || l.hosts[token.host] <= 0 {
		return false
	}
	token.released = true
	l.active--
	count := l.hosts[token.host] - 1
	if count <= 0 {
		delete(l.hosts, token.host)
	} else {
		l.hosts[token.host] = count
	}
	return true
}

// ActiveCount returns the current global active count.
func (l *ConcurrencyLimiter) ActiveCount() int {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.active
}

// HostCount returns the current active count for a normalized host key.
func (l *ConcurrencyLimiter) HostCount(host string) int {
	key, err := normalizeHostKey(host)
	if err != nil {
		return 0
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.hosts[key]
}
