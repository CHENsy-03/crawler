package security

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"math/big"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const v2RuntimeFixtureSHA = "E7B1E9B80A8BDCCA527E5EC6435610AB5B111D4EB37B1AC2F9468BCBCDEE9EDF"

type v2rtValid struct {
	Name                     string  `json:"name"`
	Target                   string  `json:"target"`
	InputJSONUTF8Hex         string  `json:"input_json_utf8_hex"`
	ExpectedCanonicalUTF8Hex string  `json:"expected_canonical_utf8_hex"`
	ExpectedCaseSHA256       *string `json:"expected_case_sha256"`
}

type v2rtRecipe struct {
	Name       string `json:"name"`
	Count      int    `json:"count"`
	OutputKind string `json:"output_kind"`
}

type v2rtWrapper struct {
	Name             string `json:"name"`
	RawLexemeUTF8Hex string `json:"raw_lexeme_utf8_hex"`
}

type v2rtFixture struct {
	ValidVectors         []v2rtValid   `json:"valid_vectors"`
	ResourceRecipes      []v2rtRecipe  `json:"resource_recipes"`
	DirectWrapperVectors []v2rtWrapper `json:"direct_wrapper_vectors"`
}

func v2rtPath(t *testing.T, name string) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "tests", "fixtures", name)
}

func v2rtFindDuplicate(dec *json.Decoder) (string, error) {
	tok, err := dec.Token()
	if err != nil {
		return "", err
	}
	delim, ok := tok.(json.Delim)
	if !ok {
		return "", nil
	}
	switch delim {
	case '{':
		seen := map[string]bool{}
		for dec.More() {
			keyTok, err := dec.Token()
			if err != nil {
				return "", err
			}
			key, ok := keyTok.(string)
			if !ok {
				return "", errors.New("key not string")
			}
			if seen[key] {
				return key, nil
			}
			seen[key] = true
			if dup, err := v2rtFindDuplicate(dec); err != nil || dup != "" {
				return dup, err
			}
		}
		if _, err := dec.Token(); err != nil {
			return "", err
		}
	case '[':
		for dec.More() {
			if dup, err := v2rtFindDuplicate(dec); err != nil || dup != "" {
				return dup, err
			}
		}
		if _, err := dec.Token(); err != nil {
			return "", err
		}
	}
	return "", nil
}

func loadV2RuntimeFixture(t *testing.T, path string) v2rtFixture {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	if dup, err := v2rtFindDuplicate(json.NewDecoder(bytes.NewReader(data))); err != nil || dup != "" {
		t.Fatalf("duplicate key %q %v", dup, err)
	}
	var fixture v2rtFixture
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode: %v", err)
	}
	return fixture
}

func runV2RTValid(t *testing.T, vector v2rtValid) {
	t.Helper()
	raw, err := hex.DecodeString(vector.InputJSONUTF8Hex)
	if err != nil {
		t.Fatalf("input hex %s: %v", vector.Name, err)
	}
	expected, err := hex.DecodeString(vector.ExpectedCanonicalUTF8Hex)
	if err != nil {
		t.Fatalf("expected hex %s: %v", vector.Name, err)
	}
	value, err := StrictDecodeV2(raw, DefaultEvidenceLimitsV2())
	if err != nil {
		t.Fatalf("decode %s: %v", vector.Name, err)
	}
	if vector.Target == "canonical_case" {
		result, err := CanonicalCaseV2(value)
		if err != nil {
			t.Fatalf("case %s: %v", vector.Name, err)
		}
		if !bytes.Equal(result.Canonical, expected) {
			t.Fatalf("canonical mismatch %s", vector.Name)
		}
		if vector.ExpectedCaseSHA256 == nil || result.SHA256 != *vector.ExpectedCaseSHA256 {
			t.Fatalf("digest mismatch %s", vector.Name)
		}
		return
	}
	canonical, err := CanonicalJSONV2(value)
	if err != nil {
		t.Fatalf("canonical %s: %v", vector.Name, err)
	}
	if !bytes.Equal(canonical, expected) {
		t.Fatalf("canonical mismatch %s", vector.Name)
	}
	if vector.ExpectedCaseSHA256 != nil {
		t.Fatalf("unexpected digest %s", vector.Name)
	}
}

func TestOSECEvidenceV2RuntimeVectors(t *testing.T) {
	fixture := loadV2RuntimeFixture(t, v2rtPath(t, "outbound_security_canonical_v2_vectors.json"))
	if len(fixture.ValidVectors) != 12 {
		t.Fatalf("valid count %d", len(fixture.ValidVectors))
	}
	for _, vector := range fixture.ValidVectors {
		runV2RTValid(t, vector)
	}

	a02 := loadV2RuntimeFixture(t, v2rtPath(t, "outbound_security_aggregate_vectors.json"))
	if len(a02.ValidVectors) != 25 {
		t.Fatalf("a02 valid count %d", len(a02.ValidVectors))
	}
	for _, vector := range a02.ValidVectors {
		runV2RTValid(t, vector)
	}
}

func TestOSECEvidenceV2RuntimeRecipesAndWrappers(t *testing.T) {
	fixture := loadV2RuntimeFixture(t, v2rtPath(t, "outbound_security_canonical_v2_vectors.json"))
	for _, recipe := range fixture.ResourceRecipes {
		data := append(bytes.Repeat([]byte("1"), recipe.Count-1), []byte(".0")...)
		if recipe.Name == "number_digits_4096_valid" {
			value, err := StrictDecodeV2(data, DefaultEvidenceLimitsV2())
			if err != nil {
				t.Fatalf("4096 decode: %v", err)
			}
			canonical, err := CanonicalJSONV2(value)
			if err != nil || !bytes.Equal(canonical, data) {
				t.Fatalf("4096 canonical %v", err)
			}
		} else {
			_, err := StrictDecodeV2(data, DefaultEvidenceLimitsV2())
			var evidenceErr *EvidenceError
			if !errors.As(err, &evidenceErr) || evidenceErr.Code != "evidence_limit_number_digits" {
				t.Fatalf("4097 error %v", err)
			}
		}
	}
	for _, wrapper := range fixture.DirectWrapperVectors {
		raw, err := hex.DecodeString(wrapper.RawLexemeUTF8Hex)
		if err != nil {
			t.Fatalf("wrapper hex %s: %v", wrapper.Name, err)
		}
		_, err = CanonicalJSONV2(Value{Kind: NonIntegerKind, NonInteger: string(raw)})
		var evidenceErr *EvidenceError
		if !errors.As(err, &evidenceErr) || evidenceErr.Code != "canonical_invalid_number_lexeme" {
			t.Fatalf("wrapper %s error %v", wrapper.Name, err)
		}
	}
}

func TestOSECEvidenceV2LocalNegatives(t *testing.T) {
	limits := DefaultEvidenceLimitsV2()
	if _, err := CanonicalJSONV2(Value{Kind: ValueKind(99)}); err == nil {
		t.Fatal("invalid kind accepted")
	}
	if _, err := CanonicalJSONV2(Value{Kind: IntegerKind, Integer: nil}); err == nil {
		t.Fatal("nil integer accepted")
	}
	if _, err := CanonicalJSONV2(Value{Kind: StringKind, String: string([]byte{0xff})}); err == nil {
		t.Fatal("invalid utf8 accepted")
	}
	if _, err := CanonicalJSONV2(Value{Kind: NonIntegerKind, NonInteger: "1"}); err == nil {
		t.Fatal("invalid wrapper accepted")
	}
	if _, err := CanonicalJSONV2(Value{Kind: NonIntegerKind, NonInteger: "1.0"}); err != nil {
		t.Fatal("valid wrapper rejected")
	}
	if _, err := CanonicalJSONV2(Value{Kind: NonIntegerKind, NonInteger: strings.Repeat("1", 4096) + ".0"}); err == nil {
		t.Fatal("4097 wrapper accepted")
	}
	one := new(big.Int).SetInt64(1)
	if _, err := CanonicalJSONV2(Value{Kind: IntegerKind, Integer: one}); err != nil {
		t.Fatal("integer canonical")
	}
	if _, err := CanonicalJSON(Value{Kind: NonIntegerKind, NonInteger: "1.0"}); err == nil {
		t.Fatal("v1 canonical accepted noninteger")
	}
	if _, err := StrictDecodeV2([]byte(`{"a":1,"\u0061":2}`), limits); err == nil {
		t.Fatal("duplicate accepted")
	}
	if _, err := StrictDecodeV2([]byte(`{"a":1,`), limits); err == nil {
		t.Fatal("malformed accepted")
	}
	if _, err := StrictDecodeV2([]byte(`{"a":"`+strings.Repeat("a", 2)+`"}`), EvidenceLimitsV2{StringLength: 1, FileSize: 1 << 30, NestingDepth: 1 << 20, NumberDigits: 1 << 20, ArrayLength: 1 << 20, ObjectMembers: 1 << 20, CaseCount: 1 << 20}); err == nil {
		t.Fatal("string limit accepted")
	}

	sentinel := "SECRET_SENTINEL"
	_, err := StrictDecodeV2([]byte(`{"x":`+sentinel+`}`), limits)
	var evidenceErr *EvidenceError
	if !errors.As(err, &evidenceErr) || strings.Contains(evidenceErr.Error(), sentinel) {
		t.Fatalf("error leak %v", err)
	}
}

func TestOSECEvidenceV2Counterfactuals(t *testing.T) {
	limits := DefaultEvidenceLimitsV2()
	check := func(name string, raw []byte, expected []byte) {
		t.Helper()
		value, err := StrictDecodeV2(raw, limits)
		if err != nil {
			t.Fatalf("%s decode: %v", name, err)
		}
		canonical, err := CanonicalJSONV2(value)
		if err != nil || !bytes.Equal(canonical, expected) {
			t.Fatalf("%s canonical mismatch", name)
		}
	}
	check("1.0", []byte("1.0"), []byte("1.0"))
	check("1.00", []byte("1.00"), []byte("1.00"))
	check("1E+5", []byte("1E+5"), []byte("1E+5"))
	check("-0.0", []byte("-0.0"), []byte("-0.0"))
	if _, err := StrictDecodeV2(append(bytes.Repeat([]byte("1"), 4096), []byte(".0")...), limits); err == nil {
		t.Fatal("4097 accepted")
	}
	if _, err := StrictDecodeV2([]byte(`{"a":1,"\u0061":2}`), limits); err == nil {
		t.Fatal("duplicate accepted")
	}
	if _, err := StrictDecodeV2([]byte(`{"a":1,`), limits); err == nil {
		t.Fatal("malformed accepted")
	}
	if _, err := CanonicalJSONV2(Value{Kind: NonIntegerKind, NonInteger: " 1.0"}); err == nil {
		t.Fatal("whitespace accepted")
	}
	if _, err := CanonicalJSONV2(Value{Kind: NonIntegerKind, NonInteger: "\uff11.0"}); err == nil {
		t.Fatal("fullwidth accepted")
	}
	if _, err := CanonicalJSONV2(Value{Kind: NonIntegerKind, NonInteger: "1.0"}); err != nil {
		t.Fatal("valid wrapper rejected")
	}
	if _, err := StrictDecodeV2([]byte("[[[[0]]]]"), EvidenceLimitsV2{NestingDepth: 1, FileSize: 1 << 30, NumberDigits: 1 << 20, ArrayLength: 1 << 20, ObjectMembers: 1 << 20, StringLength: 1 << 20, CaseCount: 1 << 20}); err == nil {
		t.Fatal("depth limit skipped")
	}
	if _, err := StrictDecodeV2([]byte("[0,0,0]"), EvidenceLimitsV2{ArrayLength: 1, FileSize: 1 << 30, NestingDepth: 1 << 20, NumberDigits: 1 << 20, ObjectMembers: 1 << 20, StringLength: 1 << 20, CaseCount: 1 << 20}); err == nil {
		t.Fatal("array limit skipped")
	}
	sum := sha256.Sum256([]byte(`{"id":"z-001","v":1}`))
	result, err := CanonicalCaseV2(Value{Kind: ObjectKind, Object: []ObjectMember{
		{Key: "id", Value: Value{Kind: StringKind, String: "z-001"}},
		{Key: "v", Value: Value{Kind: IntegerKind, Integer: big.NewInt(1)}},
	}})
	if err != nil || result.SHA256 != hex.EncodeToString(sum[:]) {
		t.Fatalf("case no special branch")
	}
}
