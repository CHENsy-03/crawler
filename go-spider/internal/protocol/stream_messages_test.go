package protocol

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

type v3Fixture struct {
	Streams []struct {
		Stream    string `json:"stream"`
		Type      string `json:"type"`
		WorkClass string `json:"work_class"`
	} `json:"streams"`
	Cases []struct {
		Name   string          `json:"name"`
		Stream string          `json:"stream"`
		Valid  bool            `json:"valid"`
		Data   json.RawMessage `json:"data"`
		Raw    string          `json:"raw,omitempty"`
		Expect struct {
			Code         string `json:"code"`
			ReasonMarker string `json:"reason_marker"`
		} `json:"expect"`
	} `json:"cases"`
}

func loadV3Fixture(t *testing.T) v3Fixture {
	t.Helper()
	path := filepath.Join("..", "..", "..", "tests", "fixtures", "redis_stream_v3_cases.json")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read v3 fixture: %v", err)
	}
	var fixture v3Fixture
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode v3 fixture: %v", err)
	}
	return fixture
}

func TestV3ValidCasesRoundTrip(t *testing.T) {
	fixture := loadV3Fixture(t)
	validNames := map[string]bool{}
	for _, tc := range fixture.Cases {
		if !tc.Valid {
			continue
		}
		input := []byte(tc.Raw)
		if tc.Raw == "" {
			input = tc.Data
		}
		message, err := DecodeV3Message(input, tc.Stream)
		if err != nil {
			t.Fatalf("valid case %s rejected: %v", tc.Name, err)
		}
		encoded, err := EncodeV3Message(message)
		if err != nil {
			t.Fatalf("encode valid case %s: %v", tc.Name, err)
		}
		if _, err := DecodeV3Message(encoded, tc.Stream); err != nil {
			t.Fatalf("round trip valid case %s: %v", tc.Name, err)
		}
		validNames[tc.Name] = true
	}
	required := map[string]bool{
		"valid-search-requested":                true,
		"valid-url":                             true,
		"valid-html-artifact-ref":               true,
		"valid-result":                          true,
		"valid-error":                           true,
		"valid-artifact-object-key-a-dot-dot-b": true,
		"valid-number-level-max":                true,
		"valid-number-max-pages-1e0":            true,
		"valid-number-max-pages-1p0":            true,
	}
	for name := range required {
		if !validNames[name] {
			t.Fatalf("required valid case %s was not executed", name)
		}
	}
}

func TestV3InvalidCasesHitExpectedRejection(t *testing.T) {
	fixture := loadV3Fixture(t)
	rejected := 0
	rejectedNames := map[string]bool{}
	for _, tc := range fixture.Cases {
		if tc.Valid {
			continue
		}
		input := []byte(tc.Raw)
		if tc.Raw == "" {
			input = tc.Data
		}
		_, err := DecodeV3Message(input, tc.Stream)
		if err == nil {
			t.Fatalf("invalid case %s was accepted", tc.Name)
		}
		var codeErr *StreamCodeError
		if !errors.As(err, &codeErr) {
			t.Fatalf("invalid case %s error has no code: %v", tc.Name, err)
		}
		if codeErr.Code != tc.Expect.Code {
			t.Fatalf("invalid case %s code=%s want %s", tc.Name, codeErr.Code, tc.Expect.Code)
		}
		if codeErr.Code != "INVALID_JSON" && !contains(codeErr.Msg, tc.Expect.ReasonMarker) {
			t.Fatalf("invalid case %s message=%q want marker %q", tc.Name, codeErr.Msg, tc.Expect.ReasonMarker)
		}
		rejected++
		rejectedNames[tc.Name] = true
	}
	required := map[string]bool{
		"invalid-artifact-ref-space":                true,
		"invalid-artifact-ref-backslash":            true,
		"invalid-artifact-ref-parent-relative":      true,
		"invalid-artifact-ref-parent-inner":         true,
		"invalid-artifact-ref-absolute":             true,
		"invalid-artifact-ref-drive":                true,
		"invalid-artifact-ref-drive-relative":       true,
		"invalid-artifact-ref-drive-relative-upper": true,
		"invalid-artifact-ref-drive-relative-lower": true,
		"invalid-number-fraction":                   true,
		"invalid-number-bool":                       true,
		"invalid-number-nonfinite-json":             true,
		"invalid-number-evidence-weight-overflow":   true,
		"invalid-number-level-max-plus-one":         true,
		"invalid-number-level-rounding-fraction":    true,
	}
	for name := range required {
		if !rejectedNames[name] {
			t.Fatalf("required invalid case %s was not executed", name)
		}
	}
}

func contains(value, marker string) bool {
	for i := 0; i+len(marker) <= len(value); i++ {
		if value[i:i+len(marker)] == marker {
			return true
		}
	}
	return false
}

type capacityFixture struct {
	Cases []struct {
		Name   string          `json:"name"`
		Valid  bool            `json:"valid"`
		Data   json.RawMessage `json:"data"`
		Raw    string          `json:"raw,omitempty"`
		Expect struct {
			Code         string `json:"code"`
			ReasonMarker string `json:"reason_marker"`
		} `json:"expect"`
	} `json:"cases"`
}

func loadCapacityFixture(t *testing.T) capacityFixture {
	t.Helper()
	path := filepath.Join("..", "..", "..", "tests", "fixtures", "capacity_state_v1_cases.json")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read capacity fixture: %v", err)
	}
	var fixture capacityFixture
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode capacity fixture: %v", err)
	}
	return fixture
}

func TestCapacityValidCasesRoundTrip(t *testing.T) {
	fixture := loadCapacityFixture(t)
	validNames := map[string]bool{}
	for _, tc := range fixture.Cases {
		if !tc.Valid {
			continue
		}
		input := []byte(tc.Raw)
		if tc.Raw == "" {
			input = tc.Data
		}
		state, err := DecodeCapacityState(input)
		if err != nil {
			t.Fatalf("valid capacity case %s rejected: %v", tc.Name, err)
		}
		encoded, err := EncodeCapacityState(state)
		if err != nil {
			t.Fatalf("encode capacity case %s: %v", tc.Name, err)
		}
		if _, err := DecodeCapacityState(encoded); err != nil {
			t.Fatalf("round trip capacity case %s: %v", tc.Name, err)
		}
		validNames[tc.Name] = true
	}
	for _, name := range []string{
		"valid-capacity-normal", "valid-capacity-warning", "valid-capacity-blocked",
		"valid-stream-drain-only", "valid-capacity-state-version-max",
		"valid-capacity-emergency-1e0", "valid-capacity-emergency-max",
	} {
		if !validNames[name] {
			t.Fatalf("required valid capacity case %s not executed", name)
		}
	}
}

func TestCapacityInvalidCasesHitExpectedRejection(t *testing.T) {
	fixture := loadCapacityFixture(t)
	rejected := 0
	rejectedNames := map[string]bool{}
	for _, tc := range fixture.Cases {
		if tc.Valid {
			continue
		}
		input := []byte(tc.Raw)
		if tc.Raw == "" {
			input = tc.Data
		}
		_, err := DecodeCapacityState(input)
		if err == nil {
			t.Fatalf("invalid capacity case %s was accepted", tc.Name)
		}
		var codeErr *StreamCodeError
		if !errors.As(err, &codeErr) {
			t.Fatalf("invalid capacity case %s error has no code: %v", tc.Name, err)
		}
		if codeErr.Code != tc.Expect.Code {
			t.Fatalf("invalid capacity case %s code=%s want %s", tc.Name, codeErr.Code, tc.Expect.Code)
		}
		if codeErr.Code != "INVALID_JSON" && !contains(codeErr.Msg, tc.Expect.ReasonMarker) {
			t.Fatalf("invalid capacity case %s message=%q want marker %q", tc.Name, codeErr.Msg, tc.Expect.ReasonMarker)
		}
		rejected++
		rejectedNames[tc.Name] = true
	}
	for _, name := range []string{
		"invalid-event-state-mismatch", "invalid-zero-emergency-reserve",
		"invalid-missing-state-version", "invalid-unknown-schema-version",
		"invalid-capacity-state-version-fraction", "invalid-capacity-emergency-nonfinite-json",
		"invalid-capacity-state-version-max-plus-one", "invalid-capacity-emergency-max-plus-one",
	} {
		if !rejectedNames[name] {
			t.Fatalf("required invalid capacity case %s not executed", name)
		}
	}
}
