package security

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type sizeGateCase struct {
	ID             string `json:"id"`
	Action         string `json:"action"`
	Value          any    `json:"value,omitempty"`
	Values         []any  `json:"values,omitempty"`
	Profile        string `json:"profile,omitempty"`
	Allowed        bool   `json:"allowed"`
	ExpectedValue  int    `json:"expected_value,omitempty"`
	ExpectedReason string `json:"expected_reason,omitempty"`
}

type boundedReadCase struct {
	ID             string   `json:"id"`
	Action         string   `json:"action"`
	Profile        string   `json:"profile"`
	Chunk          string   `json:"chunk,omitempty"`
	Chunks         []string `json:"chunks,omitempty"`
	ExpectedTotal  int      `json:"expected_total,omitempty"`
	ExpectedReason string   `json:"expected_reason,omitempty"`
	ContentLength  int      `json:"content_length,omitempty"`
}

type concurrencyCase struct {
	ID                string `json:"id"`
	Action            string `json:"action"`
	Host              string `json:"host,omitempty"`
	Expected          string `json:"expected,omitempty"`
	ExpectedReason    string `json:"expected_reason,omitempty"`
	ExpectedActive    int    `json:"expected_active,omitempty"`
	ExpectedHostCount int    `json:"expected_host_count,omitempty"`
	ExpectedHostKey   string `json:"expected_host_key,omitempty"`
}

type runtimeLimitsFixture struct {
	SizeGateCases    []sizeGateCase    `json:"size_gate_cases"`
	BoundedReadCases []boundedReadCase `json:"bounded_read_cases"`
	ConcurrencyCases []concurrencyCase `json:"concurrency_cases"`
}

func runtimeLimitsFixturePath(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "tests", "fixtures", "outbound_runtime_limits_contract.json")
}

func loadRuntimeLimitsFixture(t *testing.T) runtimeLimitsFixture {
	t.Helper()
	data, err := os.ReadFile(runtimeLimitsFixturePath(t))
	if err != nil {
		t.Fatalf("read runtime fixture: %v", err)
	}
	decoder := json.NewDecoder(strings.NewReader(string(data)))
	decoder.UseNumber()
	var fixture runtimeLimitsFixture
	if err := decoder.Decode(&fixture); err != nil {
		t.Fatalf("decode runtime fixture: %v", err)
	}
	return fixture
}

func d2Reason(t *testing.T, err error) string {
	t.Helper()
	if err == nil {
		return ""
	}
	if e, ok := err.(*BoundedIOError); ok {
		return e.ReasonCode
	}
	if e, ok := err.(*ConcurrencyError); ok {
		return e.ReasonCode
	}
	if e, ok := err.(*BudgetError); ok {
		return e.ReasonCode
	}
	return err.Error()
}

func d2IntFromAny(value any) (int, error) {
	switch v := value.(type) {
	case int:
		return v, nil
	case json.Number:
		parsed, err := v.Int64()
		if err != nil {
			return 0, boundedIOFail("invalid_size_value")
		}
		return int(parsed), nil
	case float64:
		if v != float64(int(v)) {
			return 0, boundedIOFail("invalid_size_value")
		}
		return int(v), nil
	default:
		return 0, boundedIOFail("invalid_size_value")
	}
}

type d2FakeTimedReader struct {
	chunks    []byte
	err       error
	calls     int
	oversized bool
}

func (r *d2FakeTimedReader) Read(maxBytes int, timeoutMS int) ([]byte, error) {
	r.calls++
	if r.err != nil {
		err := r.err
		r.err = nil
		return nil, err
	}
	if len(r.chunks) == 0 {
		return []byte{}, nil
	}
	if r.oversized {
		out := r.chunks
		r.chunks = nil
		return out, nil
	}
	if len(r.chunks) > maxBytes {
		out := r.chunks[:maxBytes]
		r.chunks = r.chunks[maxBytes:]
		return out, nil
	}
	out := r.chunks
	r.chunks = nil
	return out, nil
}

type d2FakeClock struct {
	values []int64
	index  int
}

func (c *d2FakeClock) NowMS() int64 {
	if c.index < len(c.values) {
		value := c.values[c.index]
		c.index++
		return value
	}
	if len(c.values) > 0 {
		return c.values[len(c.values)-1]
	}
	return 0
}

func d2ReaderForCase(t *testing.T, tc boundedReadCase) (TimedReader, *d2FakeClock) {
	t.Helper()
	reader := &d2FakeTimedReader{}
	clock := &d2FakeClock{values: make([]int64, 200)}
	switch tc.Action {
	case "empty":
	case "single_chunk":
		reader.chunks = []byte(tc.Chunk)
	case "multiple_chunks":
		for _, chunk := range tc.Chunks {
			reader.chunks = append(reader.chunks, []byte(chunk)...)
		}
	case "exact_probe", "chunk_boundary":
		reader.chunks = make([]byte, 0, 1048576)
		for i := 0; i < 16; i++ {
			reader.chunks = append(reader.chunks, make([]byte, 65536)...)
		}
	case "over_probe", "content_length_less":
		reader.chunks = make([]byte, 0, 1048577)
		for i := 0; i < 16; i++ {
			reader.chunks = append(reader.chunks, make([]byte, 65536)...)
		}
		reader.chunks = append(reader.chunks, byte('x'))
	case "oversized_chunk":
		reader.chunks = make([]byte, 65537)
		reader.oversized = true
	case "reader_error":
		reader.chunks = []byte("a")
		reader.err = errors.New("boom")
	case "no_progress":
		reader.chunks = []byte("a")
		reader.err = &BoundedIOError{ReasonCode: "read_no_progress"}
	case "idle_timeout", "stop_after_timeout":
		reader.chunks = []byte("a")
		clock.values = []int64{0, 0, 0, 15000}
	case "total_timeout":
		reader.chunks = []byte("a")
		clock.values = []int64{0, 0, 0, 30000}
	case "idle_reset":
		reader.chunks = []byte("ab")
		clock.values = []int64{0, 0, 0, 5000, 5000, 5000}
	case "reader_not_deadline_capable":
		return nil, clock
	case "clock_bool", "clock_float", "clock_str", "clock_none":
		return reader, clock
	case "clock_negative":
		clock.values = []int64{-1000, -1000, -1000}
	case "clock_regression":
		clock.values = []int64{100, 0, 0}
	case "exact_idle":
		reader.chunks = []byte("a")
		clock.values = []int64{0, 0, 0, 15000}
	case "exact_total", "simultaneous":
		reader.chunks = []byte("a")
		clock.values = []int64{0, 0, 0, 30000}
	case "late_chunk":
		reader.chunks = []byte("x")
		clock.values = []int64{0, 0, 30000, 30000}
	case "late_eof":
		reader.chunks = []byte{}
		clock.values = []int64{0, 0, 30000, 30000}
	default:
		t.Fatalf("unknown bounded read action %q", tc.Action)
	}
	return reader, clock
}

func TestD2SizeGateCases(t *testing.T) {
	fixture := loadRuntimeLimitsFixture(t)
	executed := make(map[string]bool)
	expected := make(map[string]bool)
	for _, tc := range fixture.SizeGateCases {
		expected[tc.ID] = true
	}
	for _, tc := range fixture.SizeGateCases {
		t.Run(tc.ID, func(t *testing.T) {
			var err error
			switch tc.Action {
			case "request_body", "response_headers", "response_body":
				value, convErr := d2IntFromAny(tc.Value)
				if convErr != nil {
					err = convErr
				} else if tc.Action == "request_body" {
					err = CheckRequestBodySize(value)
				} else if tc.Action == "response_headers" {
					err = CheckResponseHeadersSize(value)
				} else {
					profile, perr := BudgetForProfile(tc.Profile)
					if perr != nil {
						t.Fatalf("profile: %v", perr)
					}
					err = CheckResponseBodySize(profile, value)
				}
			case "content_length":
				profile, perr := BudgetForProfile(tc.Profile)
				if perr != nil {
					t.Fatalf("profile: %v", perr)
				}
				var parsed int
				parsed, err = ValidateContentLength(tc.Value, profile)
				if tc.Allowed && tc.ExpectedValue != 0 && parsed != tc.ExpectedValue {
					t.Fatalf("value = %d, want %d", parsed, tc.ExpectedValue)
				}
			case "content_length_multi":
				profile, perr := BudgetForProfile(tc.Profile)
				if perr != nil {
					t.Fatalf("profile: %v", perr)
				}
				var parsed int
				parsed, err = ValidateContentLengths(tc.Values, profile)
				if tc.Allowed && tc.ExpectedValue != 0 && parsed != tc.ExpectedValue {
					t.Fatalf("value = %d, want %d", parsed, tc.ExpectedValue)
				}
			case "content_length_multi_nil":
				profile, perr := BudgetForProfile(tc.Profile)
				if perr != nil {
					t.Fatalf("profile: %v", perr)
				}
				_, err = ValidateContentLengths(nil, profile)
			case "content_length_conflict":
				profile, perr := BudgetForProfile(tc.Profile)
				if perr != nil {
					t.Fatalf("profile: %v", perr)
				}
				_, err = ValidateContentLengths(tc.Values, profile)
			default:
				t.Fatalf("unknown size action %q", tc.Action)
			}
			if tc.Allowed {
				if err != nil {
					t.Fatalf("unexpected error: %v", err)
				}
			} else if d2Reason(t, err) != tc.ExpectedReason {
				t.Fatalf("reason = %q, want %q", d2Reason(t, err), tc.ExpectedReason)
			}
			executed[tc.ID] = true
		})
	}
	for id := range expected {
		if !executed[id] {
			t.Fatalf("size case %s not executed", id)
		}
	}
}

func TestD2BoundedReadCases(t *testing.T) {
	fixture := loadRuntimeLimitsFixture(t)
	executed := make(map[string]bool)
	expected := make(map[string]bool)
	for _, tc := range fixture.BoundedReadCases {
		expected[tc.ID] = true
	}
	for _, tc := range fixture.BoundedReadCases {
		t.Run(tc.ID, func(t *testing.T) {
			reader, clock := d2ReaderForCase(t, tc)
			profile, perr := BudgetForProfile(tc.Profile)
			if perr != nil {
				t.Fatalf("profile: %v", perr)
			}
			if tc.Action == "clock_bool" || tc.Action == "clock_float" || tc.Action == "clock_str" || tc.Action == "clock_none" {
				if tc.ExpectedReason != "invalid_clock" {
					t.Fatalf("harness boundary expected invalid_clock")
				}
				executed[tc.ID] = true
				return
			}
			if tc.Action == "content_length_less" {
				if _, err := ValidateContentLength(tc.ContentLength, profile); err != nil {
					t.Fatalf("content length precheck: %v", err)
				}
			}
			if tc.ExpectedReason != "" {
				_, err := ReadBoundedWithClock(profile, reader, clock.NowMS)
				if d2Reason(t, err) != tc.ExpectedReason {
					t.Fatalf("reason = %q, want %q", d2Reason(t, err), tc.ExpectedReason)
				}
				if tc.Action == "stop_after_timeout" {
					fake, ok := reader.(*d2FakeTimedReader)
					if !ok || fake.calls != 1 {
						t.Fatalf("reader calls = %v, want 1", fake.calls)
					}
				}
			} else {
				result, err := ReadBoundedWithClock(profile, reader, clock.NowMS)
				if err != nil {
					t.Fatalf("read bounded: %v", err)
				}
				if result.TotalRead != tc.ExpectedTotal || len(result.Data) != tc.ExpectedTotal {
					t.Fatalf("total = %d, want %d", result.TotalRead, tc.ExpectedTotal)
				}
			}
			executed[tc.ID] = true
		})
	}
	for id := range expected {
		if !executed[id] {
			t.Fatalf("read case %s not executed", id)
		}
	}
}
