package security

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type ea1Valid struct {
	Name                     string  `json:"name"`
	Target                   string  `json:"target"`
	InputJSONUTF8Hex         string  `json:"input_json_utf8_hex"`
	ExpectedCanonicalUTF8Hex string  `json:"expected_canonical_utf8_hex"`
	ExpectedCaseSHA256       *string `json:"expected_case_sha256"`
}

type ea1Reject struct {
	Name             string  `json:"name"`
	Target           string  `json:"target"`
	InputJSONUTF8Hex *string `json:"input_json_utf8_hex"`
	Recipe           *string `json:"recipe"`
	ExpectedStage    string  `json:"expected_stage"`
	ExpectedError    string  `json:"expected_error"`
}

type ea1Recipe struct {
	Name                string `json:"name"`
	Generator           string `json:"generator"`
	PrefixHex           string `json:"prefix_hex"`
	UnitHex             string `json:"unit_hex"`
	SeparatorHex        string `json:"separator_hex"`
	SuffixHex           string `json:"suffix_hex"`
	Count               int    `json:"count"`
	OutputKind          string `json:"output_kind"`
	ExpectedInputSHA256 string `json:"expected_input_sha256"`
	ExpectedStage       string `json:"expected_stage"`
	ExpectedError       string `json:"expected_error"`
}

type ea1Fixture struct {
	ValidVectors    []ea1Valid  `json:"valid_vectors"`
	RejectVectors   []ea1Reject `json:"reject_vectors"`
	ResourceRecipes []ea1Recipe `json:"resource_recipes"`
}

func ea1FixturePath(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "tests", "fixtures", "outbound_security_aggregate_vectors.json")
}

func loadEA1Fixture(t *testing.T) ea1Fixture {
	t.Helper()
	data, err := os.ReadFile(ea1FixturePath(t))
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	var fixture ea1Fixture
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode fixture: %v", err)
	}
	return fixture
}

func decodeHexBytes(t *testing.T, value string) []byte {
	t.Helper()
	decoded, err := hex.DecodeString(value)
	if err != nil {
		t.Fatalf("hex %q: %v", value, err)
	}
	return decoded
}

func generateEA1Recipe(t *testing.T, recipe ea1Recipe) []byte {
	t.Helper()
	prefix := decodeHexBytes(t, recipe.PrefixHex)
	unit := decodeHexBytes(t, recipe.UnitHex)
	var separator []byte
	if recipe.SeparatorHex != "" {
		separator = decodeHexBytes(t, recipe.SeparatorHex)
	}
	suffix := decodeHexBytes(t, recipe.SuffixHex)
	var out []byte
	switch recipe.Generator {
	case "repeat_unit":
		out = append(out, prefix...)
		out = append(out, unit...)
		for i := 1; i < recipe.Count; i++ {
			out = append(out, separator...)
			out = append(out, unit...)
		}
		out = append(out, suffix...)
	case "nested_container":
		for i := 0; i < recipe.Count; i++ {
			out = append(out, prefix...)
		}
		out = append(out, unit...)
		for i := 0; i < recipe.Count; i++ {
			out = append(out, suffix...)
		}
	case "object_members":
		out = append(out, prefix...)
		for i := 0; i < recipe.Count; i++ {
			if i > 0 {
				out = append(out, separator...)
			}
			out = append(out, []byte(fmt.Sprintf(`"k%d":0`, i))...)
		}
		out = append(out, suffix...)
	case "file_size_pad":
		out = append(out, prefix...)
		for i := 0; i < recipe.Count; i++ {
			out = append(out, unit...)
		}
		out = append(out, suffix...)
	case "case_dataset":
		out = append(out, prefix...)
		for i := 0; i < recipe.Count; i++ {
			if i > 0 {
				out = append(out, separator...)
			}
			out = append(out, []byte(fmt.Sprintf(`{"id":"c%d"}`, i))...)
		}
		out = append(out, suffix...)
	default:
		t.Fatalf("unknown generator %q", recipe.Generator)
	}
	return out
}

func TestEA1A02ValidVectors(t *testing.T) {
	fixture := loadEA1Fixture(t)
	executed := map[string]bool{}
	limits := DefaultEvidenceLimits()
	for _, vector := range fixture.ValidVectors {
		raw := decodeHexBytes(t, vector.InputJSONUTF8Hex)
		expected := decodeHexBytes(t, vector.ExpectedCanonicalUTF8Hex)
		value, err := StrictDecode(raw, limits)
		if err != nil {
			t.Fatalf("valid %s strict: %v", vector.Name, err)
		}
		var canonical []byte
		if vector.Target == "canonical_case" {
			result, err := CanonicalCase(value)
			if err != nil {
				t.Fatalf("valid %s case: %v", vector.Name, err)
			}
			if !bytes.Equal(result.Canonical, expected) {
				t.Fatalf("valid %s canonical mismatch", vector.Name)
			}
			if vector.ExpectedCaseSHA256 == nil || result.SHA256 != *vector.ExpectedCaseSHA256 {
				t.Fatalf("valid %s digest mismatch", vector.Name)
			}
			canonical = result.Canonical
		} else {
			canonical, err = CanonicalJSON(value)
			if err != nil {
				t.Fatalf("valid %s canonical: %v", vector.Name, err)
			}
			if !bytes.Equal(canonical, expected) {
				t.Fatalf("valid %s canonical mismatch", vector.Name)
			}
		}
		_ = canonical
		executed[vector.Name] = true
	}
	if len(executed) != 25 {
		t.Fatalf("executed valid %d", len(executed))
	}
}

func TestEA1A02RejectVectors(t *testing.T) {
	fixture := loadEA1Fixture(t)
	executed := map[string]bool{}
	limits := DefaultEvidenceLimits()
	for _, vector := range fixture.RejectVectors {
		if vector.Recipe != nil {
			executed[vector.Name] = true
			continue
		}
		raw := decodeHexBytes(t, *vector.InputJSONUTF8Hex)
		var err error
		if vector.Target == "canonical" {
			var value Value
			value, err = StrictDecode(raw, limits)
			if err == nil {
				if vector.ExpectedError == "canonical_root_not_object" || vector.ExpectedError == "canonical_missing_id" || vector.ExpectedError == "canonical_invalid_id" {
					_, err = CanonicalCase(value)
				} else {
					_, err = CanonicalJSON(value)
				}
			}
		} else {
			_, err = StrictDecode(raw, limits)
		}
		var evidenceErr *EvidenceError
		if !errors.As(err, &evidenceErr) || evidenceErr.Code != vector.ExpectedError {
			t.Fatalf("reject %s code %v != %s", vector.Name, err, vector.ExpectedError)
		}
		executed[vector.Name] = true
	}
	if len(executed) != 35 {
		t.Fatalf("executed reject %d", len(executed))
	}
}

func TestEA1A02ResourceRecipes(t *testing.T) {
	fixture := loadEA1Fixture(t)
	executed := map[string]bool{}
	limits := DefaultEvidenceLimits()
	for _, recipe := range fixture.ResourceRecipes {
		data := generateEA1Recipe(t, recipe)
		sum := sha256.Sum256(data)
		if hex.EncodeToString(sum[:]) != recipe.ExpectedInputSHA256 {
			t.Fatalf("recipe %s sha mismatch", recipe.Name)
		}
		var err error
		if recipe.Name == "recipe_case_count_10001" {
			_, err = ValidateCaseDataset(make([]Value, 10001), limits)
		} else {
			_, err = StrictDecode(data, limits)
		}
		var evidenceErr *EvidenceError
		if !errors.As(err, &evidenceErr) || evidenceErr.Code != recipe.ExpectedError {
			t.Fatalf("recipe %s code %v", recipe.Name, err)
		}
		executed[recipe.Name] = true
	}
	if len(executed) != 7 {
		t.Fatalf("executed recipes %d", len(executed))
	}
}

func TestEA1AggregateHardcodedExpected(t *testing.T) {
	digests := []CaseDigest{
		{ID: "a", Digest: bytes.Repeat([]byte{0x00}, 32)},
		{ID: "b", Digest: bytes.Repeat([]byte{0x01}, 32)},
	}
	aggregate, err := AggregateV1(digests, "OSEC-CASE-AGGREGATE-V1")
	if err != nil || aggregate != "491d7d8881628da0ed213673a79fb250f285bfbf6573f414254119c1c5ba70e2" {
		t.Fatalf("aggregate %s %v", aggregate, err)
	}
	category, err := CategoryAggregateV1("test", digests)
	if err != nil || category != "91832a3c5e90e6b6136d02ba293bbd31e90aace1a55f4f40f08957975afa0d17" {
		t.Fatalf("category %s %v", category, err)
	}
}

func TestEA1LocalNegatives(t *testing.T) {
	limits := DefaultEvidenceLimits()
	if _, err := CanonicalJSON(Value{Kind: ValueKind(99)}); err == nil {
		t.Fatal("invalid kind accepted")
	}
	if _, err := CanonicalJSON(Value{Kind: IntegerKind, Integer: nil}); err == nil {
		t.Fatal("nil integer accepted")
	}
	if _, err := CanonicalJSON(Value{Kind: StringKind, String: string([]byte{0xff})}); err == nil {
		t.Fatal("invalid utf8 string accepted")
	}
	if _, err := CanonicalJSON(Value{Kind: ObjectKind, Object: []ObjectMember{{Key: string([]byte{0xff}), Value: Value{Kind: NullKind}}}}); err == nil {
		t.Fatal("invalid utf8 key accepted")
	}
	if _, err := CanonicalJSON(Value{Kind: NonIntegerKind, NonInteger: "1.0"}); err == nil {
		t.Fatal("noninteger accepted")
	}
	trueBytes, err := CanonicalJSON(Value{Kind: BoolKind, Bool: true})
	if err != nil || string(trueBytes) != "true" {
		t.Fatalf("bool encoding")
	}
	one := new(big.Int).SetInt64(1)
	intBytes, err := CanonicalJSON(Value{Kind: IntegerKind, Integer: one})
	if err != nil || string(intBytes) != "1" {
		t.Fatalf("int encoding")
	}
	if _, err := StrictDecode([]byte(`{"a":1,"\u0061":2}`), limits); err == nil {
		t.Fatal("duplicate accepted")
	}
	if _, err := StrictDecode([]byte(`{"a":1} x`), limits); err == nil {
		t.Fatal("trailing accepted")
	}
	if _, err := StrictDecode([]byte("01"), limits); err == nil {
		t.Fatal("leading zero accepted")
	}

	digest := CaseDigest{ID: "a", Digest: bytes.Repeat([]byte{0}, 32)}
	if _, err := AggregateV1(nil, "OSEC-CASE-AGGREGATE-V1"); err == nil {
		t.Fatal("empty aggregate accepted")
	}
	if _, err := AggregateV1([]CaseDigest{digest, {ID: "a", Digest: bytes.Repeat([]byte{1}, 32)}}, "OSEC-CASE-AGGREGATE-V1"); err == nil {
		t.Fatal("duplicate id accepted")
	}
	if _, err := AggregateV1([]CaseDigest{{ID: "a", Digest: bytes.Repeat([]byte{0}, 31)}}, "OSEC-CASE-AGGREGATE-V1"); err == nil {
		t.Fatal("bad digest length accepted")
	}
	if _, err := AggregateV1([]CaseDigest{digest}, "UNKNOWN"); err == nil {
		t.Fatal("unknown algorithm accepted")
	}
	if _, err := checkedU32(1<<32, "aggregate_count_overflow"); err == nil {
		t.Fatal("count overflow accepted")
	}
	if _, err := checkedU32(1<<32, "aggregate_length_overflow"); err == nil {
		t.Fatal("length overflow accepted")
	}
	if _, err := CategoryAggregateV1("Bad Name", []CaseDigest{digest}); err == nil {
		t.Fatal("invalid category accepted")
	}

	sentinel := "SECRET_SENTINEL"
	_, err = StrictDecode([]byte(`{"x":`+sentinel+`}`), limits)
	var evidenceErr *EvidenceError
	if !errors.As(err, &evidenceErr) || strings.Contains(evidenceErr.Error(), sentinel) {
		t.Fatalf("error leaks input: %v", err)
	}
}

func TestEA1ProductionIsolation(t *testing.T) {
	paths := []string{
		filepath.Join("..", "client", "resty.go"),
		filepath.Join("..", "worker", "pool.go"),
		filepath.Join("..", "queue", "redis.go"),
	}
	for _, path := range paths {
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatalf("read %s: %v", path, err)
		}
		if strings.Contains(string(data), "osec_evidence") {
			t.Fatalf("%s references osec_evidence", path)
		}
	}
	source, err := os.ReadFile("osec_evidence.go")
	if err != nil {
		t.Fatalf("read candidate: %v", err)
	}
	for _, forbidden := range []string{`"net/http"`, "net.Dial", "os/exec", "http.Client"} {
		if strings.Contains(string(source), forbidden) {
			t.Fatalf("candidate contains %s", forbidden)
		}
	}
}
