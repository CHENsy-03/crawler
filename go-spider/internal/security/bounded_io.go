package security

import (
	"encoding/json"
	"math/big"
	"strings"
	"time"
)

// BoundedIOError is a stable runtime limit failure.
type BoundedIOError struct {
	ReasonCode string
}

func (e *BoundedIOError) Error() string { return e.ReasonCode }

func boundedIOFail(reason string) error { return &BoundedIOError{ReasonCode: reason} }

// TimedReader is the deadline-aware reader contract. Each call receives the
// maximum bytes and the timeout for that read; empty bytes mean EOF.
type TimedReader interface {
	Read(maxBytes int, timeoutMS int) ([]byte, error)
}

const MaxReadChunkBytes = 65536

func checkSizeValue(value int) error {
	if value < 0 {
		return boundedIOFail("negative_size")
	}
	return nil
}

// CheckRequestBodySize rejects request bodies above the sealed budget.
func CheckRequestBodySize(value int) error {
	if err := checkSizeValue(value); err != nil {
		return err
	}
	if value > NewTransportBudget().RequestBodyBytes() {
		return boundedIOFail("request_body_too_large")
	}
	return nil
}

// CheckResponseHeadersSize rejects response headers above the sealed budget.
func CheckResponseHeadersSize(value int) error {
	if err := checkSizeValue(value); err != nil {
		return err
	}
	if value > NewTransportBudget().ResponseHeadersBytes() {
		return boundedIOFail("response_headers_too_large")
	}
	return nil
}

// CheckResponseBodySize rejects a decoded body above the profile budget.
func CheckResponseBodySize(profile BudgetProfile, value int) error {
	if err := checkSizeValue(value); err != nil {
		return err
	}
	if value > profile.ResponseBodyBytes() {
		return boundedIOFail("response_body_too_large")
	}
	return nil
}

func parseContentLengthToken(token string) (*big.Int, error) {
	stripped := strings.Trim(token, " \t")
	if stripped == "" {
		return nil, boundedIOFail("invalid_content_length")
	}
	for _, r := range stripped {
		if r < '0' || r > '9' {
			return nil, boundedIOFail("invalid_content_length")
		}
	}
	value := new(big.Int)
	if _, ok := value.SetString(stripped, 10); !ok {
		return nil, boundedIOFail("invalid_content_length")
	}
	return value, nil
}

func contentLengthValues(value any) ([]*big.Int, error) {
	switch v := value.(type) {
	case nil:
		return nil, nil
	case bool:
		return nil, boundedIOFail("invalid_content_length")
	case int:
		if v < 0 {
			return nil, boundedIOFail("invalid_content_length")
		}
		return []*big.Int{big.NewInt(int64(v))}, nil
	case string:
		parts := strings.Split(v, ",")
		out := make([]*big.Int, 0, len(parts))
		for _, part := range parts {
			parsed, err := parseContentLengthToken(part)
			if err != nil {
				return nil, err
			}
			out = append(out, parsed)
		}
		return out, nil
	case json.Number:
		parts := strings.Split(v.String(), ",")
		out := make([]*big.Int, 0, len(parts))
		for _, part := range parts {
			parsed, err := parseContentLengthToken(part)
			if err != nil {
				return nil, err
			}
			out = append(out, parsed)
		}
		return out, nil
	default:
		return nil, boundedIOFail("invalid_content_length")
	}
}

func contentLengthCompare(values []*big.Int) (*big.Int, error) {
	if len(values) == 0 {
		return nil, boundedIOFail("invalid_content_length")
	}
	first := values[0]
	for _, value := range values[1:] {
		if first.Cmp(value) != 0 {
			return nil, boundedIOFail("invalid_content_length")
		}
	}
	return first, nil
}

func contentLengthWithinProfile(value *big.Int, profile BudgetProfile) (int, error) {
	limit := big.NewInt(int64(profile.ResponseBodyBytes()))
	if value.Cmp(limit) > 0 {
		return 0, boundedIOFail("response_body_too_large")
	}
	return int(value.Int64()), nil
}

// ValidateContentLength validates one Content-Length field value.
func ValidateContentLength(value any, profile BudgetProfile) (int, error) {
	if value == nil {
		return 0, nil
	}
	values, err := contentLengthValues(value)
	if err != nil {
		return 0, err
	}
	first, err := contentLengthCompare(values)
	if err != nil {
		return 0, err
	}
	return contentLengthWithinProfile(first, profile)
}

// ValidateContentLengths validates repeated Content-Length field values.
func ValidateContentLengths(values []any, profile BudgetProfile) (int, error) {
	if len(values) == 0 {
		return 0, boundedIOFail("invalid_content_length")
	}
	flattened := make([]*big.Int, 0)
	for _, raw := range values {
		parsed, err := contentLengthValues(raw)
		if err != nil {
			return 0, err
		}
		flattened = append(flattened, parsed...)
	}
	if len(flattened) == 0 {
		return 0, boundedIOFail("invalid_content_length")
	}
	first, err := contentLengthCompare(flattened)
	if err != nil {
		return 0, err
	}
	return contentLengthWithinProfile(first, profile)
}

// BoundedReadResult is returned only after the whole body is within budget.
type BoundedReadResult struct {
	Data      []byte
	TotalRead int
}

// ReadBounded reads a bounded body using a real monotonic clock.
func ReadBounded(profile BudgetProfile, reader TimedReader) (BoundedReadResult, error) {
	start := time.Now()
	return readBoundedWithClock(profile, NewTransportBudget().ReadIdleTimeoutMS(), reader, func() int64 {
		return time.Since(start).Milliseconds()
	})
}

// ReadBoundedWithClock is the injectable-clock variant used by tests.
func ReadBoundedWithClock(profile BudgetProfile, reader TimedReader, clock func() int64) (BoundedReadResult, error) {
	return readBoundedWithClock(profile, NewTransportBudget().ReadIdleTimeoutMS(), reader, clock)
}

func sampleClock(clock func() int64, previous *int64) (int64, error) {
	value := clock()
	if value < 0 || (previous != nil && value < *previous) {
		return 0, boundedIOFail("invalid_clock")
	}
	if previous != nil {
		*previous = value
	}
	return value, nil
}

func classifyTimeout(start, lastActivity, totalTimeoutMS, readIdleMS, now int64) error {
	if now-start >= totalTimeoutMS {
		return boundedIOFail("total_timeout_exceeded")
	}
	if now-lastActivity >= int64(readIdleMS) {
		return boundedIOFail("read_idle_timeout")
	}
	return nil
}

func readBoundedWithClock(profile BudgetProfile, readIdleMS int, reader TimedReader, clock func() int64) (BoundedReadResult, error) {
	if reader == nil {
		return BoundedReadResult{}, boundedIOFail("reader_not_deadline_capable")
	}
	start, err := sampleClock(clock, nil)
	if err != nil {
		return BoundedReadResult{}, err
	}
	lastClock := start
	lastActivity := start
	data := make([]byte, 0, 1024)
	total := 0
	for {
		now, err := sampleClock(clock, &lastClock)
		if err != nil {
			return BoundedReadResult{}, err
		}
		if err := classifyTimeout(start, lastActivity, int64(profile.TotalTimeoutMS()), int64(readIdleMS), now); err != nil {
			return BoundedReadResult{}, err
		}
		totalRemaining := int64(profile.TotalTimeoutMS()) - (now - start)
		timeoutMS := int64(readIdleMS)
		if totalRemaining < timeoutMS {
			timeoutMS = totalRemaining
		}
		allowed := int64(profile.ResponseBodyBytes()) - int64(total) + 1
		if allowed > MaxReadChunkBytes {
			allowed = MaxReadChunkBytes
		}
		if allowed <= 0 {
			allowed = 1
		}
		chunk, readErr := reader.Read(int(allowed), int(timeoutMS))
		now2, clockErr := sampleClock(clock, &lastClock)
		if clockErr != nil {
			return BoundedReadResult{}, clockErr
		}
		if readErr != nil {
			if err := classifyTimeout(start, lastActivity, int64(profile.TotalTimeoutMS()), int64(readIdleMS), now2); err != nil {
				return BoundedReadResult{}, err
			}
			if e, ok := readErr.(*BoundedIOError); ok {
				return BoundedReadResult{}, e
			}
			return BoundedReadResult{}, boundedIOFail("read_failed")
		}
		if err := classifyTimeout(start, lastActivity, int64(profile.TotalTimeoutMS()), int64(readIdleMS), now2); err != nil {
			return BoundedReadResult{}, err
		}
		if len(chunk) > int(allowed) {
			return BoundedReadResult{}, boundedIOFail("response_body_too_large")
		}
		if len(chunk) == 0 {
			return BoundedReadResult{Data: data, TotalRead: total}, nil
		}
		total += len(chunk)
		if total > profile.ResponseBodyBytes() {
			return BoundedReadResult{}, boundedIOFail("response_body_too_large")
		}
		data = append(data, chunk...)
		lastActivity = now2
	}
}
