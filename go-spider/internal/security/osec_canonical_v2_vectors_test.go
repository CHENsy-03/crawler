package security_test

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
	"unicode/utf8"
)

const (
	v2FixtureSHA = "E7B1E9B80A8BDCCA527E5EC6435610AB5B111D4EB37B1AC2F9468BCBCDEE9EDF"
	v2A02SHA     = "3dd12b56d4f04af48ffd7d5f1d27246524aa9b4d0aab063646c30f915a6407cc"
)

type v2Provenance struct {
	Method string `json:"method"`
}

type v2Inherit struct {
	FixturePath        string   `json:"fixture_path"`
	NormalizedLFSHA256 string   `json:"normalized_lf_sha256"`
	ValidVectorCount   int      `json:"valid_vector_count"`
	RequiredValidNames []string `json:"required_valid_names"`
}

type v2Valid struct {
	Name                     string  `json:"name"`
	Target                   string  `json:"target"`
	InputJSONUTF8Hex         string  `json:"input_json_utf8_hex"`
	ExpectedCanonicalUTF8Hex string  `json:"expected_canonical_utf8_hex"`
	ExpectedCaseSHA256       *string `json:"expected_case_sha256"`
}

type v2Recipe struct {
	Name                string  `json:"name"`
	Generator           string  `json:"generator"`
	Count               int     `json:"count"`
	OutputKind          string  `json:"output_kind"`
	ExpectedInputSHA256 string  `json:"expected_input_sha256"`
	ExpectedOutcome     string  `json:"expected_outcome"`
	ExpectedStage       string  `json:"expected_stage"`
	ExpectedError       *string `json:"expected_error"`
}

type v2Wrapper struct {
	Name             string `json:"name"`
	RawLexemeUTF8Hex string `json:"raw_lexeme_utf8_hex"`
	ExpectedError    string `json:"expected_error"`
}

type v2Fixture struct {
	FormatVersion         string       `json:"format_version"`
	Profile               string       `json:"profile"`
	Amendment             string       `json:"amendment"`
	CanonicalJSONVersion  string       `json:"canonical_json_version"`
	CanonicalCaseVersion  string       `json:"canonical_case_version"`
	EvidenceLimitsVersion string       `json:"evidence_limits_version"`
	Provenance            v2Provenance `json:"provenance"`
	Inherits              v2Inherit    `json:"inherits_v1_valid_vectors"`
	ValidVectors          []v2Valid    `json:"valid_vectors"`
	ResourceRecipes       []v2Recipe   `json:"resource_recipes"`
	DirectWrapperVectors  []v2Wrapper  `json:"direct_wrapper_vectors"`
}

func v2FixturePath(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "tests", "fixtures", "outbound_security_canonical_v2_vectors.json")
}

func strPtr(value string) *string {
	return &value
}

func v2A02Path(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "tests", "fixtures", "outbound_security_aggregate_vectors.json")
}

func findDuplicateV2Key(dec *json.Decoder) (string, error) {
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
			if dup, err := findDuplicateV2Key(dec); err != nil || dup != "" {
				return dup, err
			}
		}
		if _, err := dec.Token(); err != nil {
			return "", err
		}
	case '[':
		for dec.More() {
			if dup, err := findDuplicateV2Key(dec); err != nil || dup != "" {
				return dup, err
			}
		}
		if _, err := dec.Token(); err != nil {
			return "", err
		}
	}
	return "", nil
}

func loadV2Fixture(t *testing.T) v2Fixture {
	t.Helper()
	data, err := os.ReadFile(v2FixturePath(t))
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	sum := sha256.Sum256(data)
	if !strings.EqualFold(hex.EncodeToString(sum[:]), v2FixtureSHA) {
		t.Fatalf("fixture sha mismatch")
	}
	if bytes.Contains(data, []byte{0xEF, 0xBB, 0xBF}) || !utf8.Valid(data) || bytes.Contains(data, []byte("\r")) {
		t.Fatalf("fixture format")
	}
	if dup, err := findDuplicateV2Key(json.NewDecoder(bytes.NewReader(data))); err != nil || dup != "" {
		t.Fatalf("duplicate key %q %v", dup, err)
	}
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	var fixture v2Fixture
	if err := dec.Decode(&fixture); err != nil {
		t.Fatalf("decode fixture: %v", err)
	}
	if _, err := dec.Token(); err != io.EOF {
		t.Fatalf("trailing JSON")
	}
	return fixture
}

func v2ValidNames() map[string]bool {
	return map[string]bool{
		"number_1_0": true, "number_443_0": true, "number_1_00": true, "number_1e5": true,
		"number_1E_plus_5": true, "number_negative_zero_fraction": true, "number_zero_fraction": true,
		"number_0_10": true, "number_1e_minus_5": true, "number_negative_1_25e_plus_3": true,
		"canonical_case_p004_shape": true, "canonical_case_ver003_shape": true,
	}
}

func v2RecipeNames() map[string]bool {
	return map[string]bool{"number_digits_4096_valid": true, "number_digits_4097_reject": true}
}

func v2WrapperNames() map[string]bool {
	return map[string]bool{
		"direct_wrapper_integer_lexeme": true, "direct_wrapper_leading_plus": true,
		"direct_wrapper_leading_zero": true, "direct_wrapper_truncated_exponent": true,
		"direct_wrapper_nan": true, "direct_wrapper_infinity": true,
		"direct_wrapper_whitespace": true, "direct_wrapper_non_ascii_digit": true,
	}
}

type v2ValidExpected struct {
	Target   string
	Input    string
	Expected string
	Digest   *string
}

var v2ValidExpectedMap = map[string]v2ValidExpected{
	"number_1_0":                    {"canonical_json", "312e30", "312e30", nil},
	"number_443_0":                  {"canonical_json", "3434332e30", "3434332e30", nil},
	"number_1_00":                   {"canonical_json", "312e3030", "312e3030", nil},
	"number_1e5":                    {"canonical_json", "316535", "316535", nil},
	"number_1E_plus_5":              {"canonical_json", "31452b35", "31452b35", nil},
	"number_negative_zero_fraction": {"canonical_json", "2d302e30", "2d302e30", nil},
	"number_zero_fraction":          {"canonical_json", "302e30", "302e30", nil},
	"number_0_10":                   {"canonical_json", "302e3130", "302e3130", nil},
	"number_1e_minus_5":             {"canonical_json", "31652d35", "31652d35", nil},
	"number_negative_1_25e_plus_3":  {"canonical_json", "2d312e3235652b33", "2d312e3235652b33", nil},
	"canonical_case_p004_shape": {
		"canonical_case",
		"7b22706f727473223a7b226874747073223a5b3434332e305d7d2c226964223a22702d303034227d",
		"7b226964223a22702d303034222c22706f727473223a7b226874747073223a5b3434332e305d7d7d",
		strPtr("b3c3de96070b6b1e777448472e515f8846d84db69b3d824b6d81a649d9778b71"),
	},
	"canonical_case_ver003_shape": {
		"canonical_case",
		"7b2276616c7565223a312e302c226964223a227665722d303033227d",
		"7b226964223a227665722d303033222c2276616c7565223a312e307d",
		strPtr("e5de3e28f87e3de599befb0eab0a64249b00322eabde9c5d66cd9eb4c1171890"),
	},
}

type v2RecipeExpected struct {
	Count   int
	SHA     string
	Outcome string
	Stage   string
	Error   *string
}

var v2RecipeExpectedMap = map[string]v2RecipeExpected{
	"number_digits_4096_valid":  {4096, "1a333e81edc3d2d2b16b1617f30d3958e34d081c50c7712a9fb2912276d08cbb", "valid", "canonical", nil},
	"number_digits_4097_reject": {4097, "c92a1c339eafdca9beace977107a9f396a12f1f29972654b7277d8c3e0106ede", "reject", "evidence_limits", strPtr("evidence_limit_number_digits")},
}

var v2WrapperExpectedMap = map[string]string{
	"direct_wrapper_integer_lexeme":     "31",
	"direct_wrapper_leading_plus":       "2b312e30",
	"direct_wrapper_leading_zero":       "30312e30",
	"direct_wrapper_truncated_exponent": "3165",
	"direct_wrapper_nan":                "4e614e",
	"direct_wrapper_infinity":           "496e66696e697479",
	"direct_wrapper_whitespace":         "20312e30",
	"direct_wrapper_non_ascii_digit":    "efbc912e30",
}

var v2NonIntegerPattern = regexp.MustCompile(`^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$`)

func v2InvalidWrapper(raw []byte) bool {
	s := string(raw)
	return !v2NonIntegerPattern.MatchString(s) || (!strings.Contains(s, ".") && !strings.Contains(s, "e") && !strings.Contains(s, "E"))
}

func generateV2Recipe(r v2Recipe) ([]byte, error) {
	if r.Generator != "non_integer_digit_count" || r.OutputKind != "json_number" || r.Count < 2 {
		return nil, errors.New("recipe metadata")
	}
	return append(bytes.Repeat([]byte("1"), r.Count-1), []byte(".0")...), nil
}

func validateV2Fixture(f *v2Fixture) error {
	if f.FormatVersion != "1.0" || f.Profile != "OSEC-EVIDENCE-PROFILE-V2" ||
		f.Amendment != "OSEC-EVIDENCE-PROFILE-V2-AMENDMENT-1" ||
		f.CanonicalJSONVersion != "OSEC-CANONICAL-JSON-V2" ||
		f.CanonicalCaseVersion != "OSEC-CANONICAL-CASE-V2" ||
		f.EvidenceLimitsVersion != "OSEC-EVIDENCE-LIMITS-V2" ||
		f.Provenance.Method != "independently_constructed" {
		return errors.New("top metadata")
	}
	inherit := f.Inherits
	if inherit.FixturePath != "tests/fixtures/outbound_security_aggregate_vectors.json" || inherit.ValidVectorCount != 25 {
		return errors.New("inherit metadata")
	}
	a02Raw, err := os.ReadFile(v2A02Path(&testing.T{}))
	if err != nil {
		return err
	}
	a02Norm := bytes.ReplaceAll(a02Raw, []byte("\r\n"), []byte("\n"))
	a02Sum := sha256.Sum256(a02Norm)
	if hex.EncodeToString(a02Sum[:]) != v2A02SHA {
		return errors.New("a02 sha")
	}
	var a02 struct {
		ValidVectors []struct {
			Name string `json:"name"`
		} `json:"valid_vectors"`
	}
	if err := json.Unmarshal(a02Norm, &a02); err != nil || len(a02.ValidVectors) != 25 {
		return errors.New("a02 parse")
	}
	a02Names := map[string]bool{}
	for _, v := range a02.ValidVectors {
		a02Names[v.Name] = true
	}
	if len(inherit.RequiredValidNames) != 25 {
		return errors.New("inherit names count")
	}
	if !sortedUniqueStrings(inherit.RequiredValidNames) {
		return errors.New("inherit names order")
	}
	for _, name := range inherit.RequiredValidNames {
		if !a02Names[name] {
			return errors.New("inherit missing " + name)
		}
	}
	if len(f.ValidVectors) != 12 || len(f.ResourceRecipes) != 2 || len(f.DirectWrapperVectors) != 8 {
		return errors.New("counts")
	}
	if !matchNames(validNamesFromFixture(f), v2ValidNames()) ||
		!matchNames(recipeNamesFromFixture(f), v2RecipeNames()) ||
		!matchNames(wrapperNamesFromFixture(f), v2WrapperNames()) {
		return errors.New("inventory")
	}
	if !globalNamesUnique(f, a02Names) {
		return errors.New("duplicate names")
	}
	for _, v := range f.ValidVectors {
		expected, ok := v2ValidExpectedMap[v.Name]
		if !ok || v.Target != expected.Target || v.InputJSONUTF8Hex != expected.Input || v.ExpectedCanonicalUTF8Hex != expected.Expected {
			return errors.New("valid mapping " + v.Name)
		}
		if v.Target == "canonical_case" {
			canonical, err := hex.DecodeString(v.ExpectedCanonicalUTF8Hex)
			if err != nil {
				return err
			}
			sum := sha256.Sum256(canonical)
			actual := hex.EncodeToString(sum[:])
			if expected.Digest == nil || v.ExpectedCaseSHA256 == nil || *v.ExpectedCaseSHA256 != actual || *expected.Digest != actual {
				return errors.New("valid digest " + v.Name)
			}
		} else if v.ExpectedCaseSHA256 != nil || expected.Digest != nil {
			return errors.New("valid unexpected digest " + v.Name)
		}
	}
	for _, r := range f.ResourceRecipes {
		expected, ok := v2RecipeExpectedMap[r.Name]
		if !ok || r.Count != expected.Count || r.ExpectedInputSHA256 != expected.SHA ||
			r.ExpectedOutcome != expected.Outcome || r.ExpectedStage != expected.Stage ||
			!sameError(r.ExpectedError, expected.Error) {
			return errors.New("recipe mapping " + r.Name)
		}
		data, err := generateV2Recipe(r)
		if err != nil {
			return err
		}
		if len(data) != r.Count+1 || data[0] != '1' || bytes.Count(data, []byte(".")) != 1 {
			return errors.New("recipe grammar " + r.Name)
		}
		sum := sha256.Sum256(data)
		if hex.EncodeToString(sum[:]) != r.ExpectedInputSHA256 {
			return errors.New("recipe sha " + r.Name)
		}
		if r.ExpectedOutcome == "" || r.ExpectedStage == "" {
			return errors.New("recipe outcome " + r.Name)
		}
	}
	for _, w := range f.DirectWrapperVectors {
		expectedRaw, ok := v2WrapperExpectedMap[w.Name]
		raw, err := hex.DecodeString(w.RawLexemeUTF8Hex)
		if !ok || err != nil || w.RawLexemeUTF8Hex != expectedRaw || !v2InvalidWrapper(raw) || w.ExpectedError != "canonical_invalid_number_lexeme" {
			return errors.New("wrapper " + w.Name)
		}
	}
	return nil
}

func validNamesFromFixture(f *v2Fixture) map[string]bool {
	out := map[string]bool{}
	for _, v := range f.ValidVectors {
		out[v.Name] = true
	}
	return out
}

func recipeNamesFromFixture(f *v2Fixture) map[string]bool {
	out := map[string]bool{}
	for _, r := range f.ResourceRecipes {
		out[r.Name] = true
	}
	return out
}

func wrapperNamesFromFixture(f *v2Fixture) map[string]bool {
	out := map[string]bool{}
	for _, w := range f.DirectWrapperVectors {
		out[w.Name] = true
	}
	return out
}

func matchNames(actual, expected map[string]bool) bool {
	if len(actual) != len(expected) {
		return false
	}
	for name := range expected {
		if !actual[name] {
			return false
		}
	}
	return true
}

func sameError(a, b *string) bool {
	if a == nil || b == nil {
		return a == b
	}
	return *a == *b
}

func globalNamesUnique(f *v2Fixture, v1Names map[string]bool) bool {
	seen := map[string]bool{}
	for _, v := range f.ValidVectors {
		if v1Names[v.Name] {
			return false
		}
		if seen[v.Name] {
			return false
		}
		seen[v.Name] = true
	}
	for _, r := range f.ResourceRecipes {
		if v1Names[r.Name] {
			return false
		}
		if seen[r.Name] {
			return false
		}
		seen[r.Name] = true
	}
	for _, w := range f.DirectWrapperVectors {
		if v1Names[w.Name] {
			return false
		}
		if seen[w.Name] {
			return false
		}
		seen[w.Name] = true
	}
	return true
}

func sortedUniqueStrings(values []string) bool {
	for i := 1; i < len(values); i++ {
		if values[i] <= values[i-1] {
			return false
		}
	}
	return true
}

func TestCanonicalV2VectorFixture(t *testing.T) {
	fixture := loadV2Fixture(t)
	if err := validateV2Fixture(&fixture); err != nil {
		t.Fatalf("validate fixture: %v", err)
	}
}

func TestCanonicalV2VectorFixtureRejectsInvalidMetadata(t *testing.T) {
	runBad := func(name string, mutate func(*v2Fixture)) {
		f := loadV2Fixture(t)
		mutate(&f)
		if err := validateV2Fixture(&f); err == nil {
			t.Fatalf("mutation accepted: %s", name)
		}
	}
	runBad("top field", func(f *v2Fixture) { f.Profile = "OSEC-EVIDENCE-PROFILE-V3" })
	runBad("amendment", func(f *v2Fixture) { f.Amendment = "OSEC-EVIDENCE-PROFILE-V2-AMENDMENT-2" })
	runBad("inherit count", func(f *v2Fixture) { f.Inherits.ValidVectorCount = 24 })
	runBad("inherit names", func(f *v2Fixture) { f.Inherits.RequiredValidNames = f.Inherits.RequiredValidNames[1:] })
	runBad("valid missing", func(f *v2Fixture) { f.ValidVectors = f.ValidVectors[1:] })
	runBad("valid target", func(f *v2Fixture) { f.ValidVectors[0].Target = "unknown" })
	runBad("recipe generator", func(f *v2Fixture) { f.ResourceRecipes[0].Generator = "unknown" })
	runBad("recipe sha", func(f *v2Fixture) {
		value := f.ResourceRecipes[0].ExpectedInputSHA256
		f.ResourceRecipes[0].ExpectedInputSHA256 = "0" + value[1:]
		if value[0] == '0' {
			f.ResourceRecipes[0].ExpectedInputSHA256 = "1" + value[1:]
		}
	})
	runBad("recipe count", func(f *v2Fixture) { f.ResourceRecipes[0].Count = 4095 })
	runBad("wrapper error", func(f *v2Fixture) { f.DirectWrapperVectors[0].ExpectedError = "unknown" })
	runBad("wrapper raw", func(f *v2Fixture) { f.DirectWrapperVectors[0].RawLexemeUTF8Hex = "322e30" })

	data, err := os.ReadFile(v2FixturePath(t))
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	raw := string(data)
	cases := []struct {
		label       string
		marker      string
		replacement string
	}{
		{"top", `"format_version"`, `"unknown_top":true,"format_version"`},
		{"valid", `"name": "number_1_0"`, `"name": "number_1_0","unknown_valid_field":true`},
		{"recipe", `"name": "number_digits_4096_valid"`, `"name": "number_digits_4096_valid","unknown_recipe_field":true`},
		{"wrapper", `"name": "direct_wrapper_integer_lexeme"`, `"name": "direct_wrapper_integer_lexeme","unknown_wrapper_field":true`},
	}
	for _, tc := range cases {
		if strings.Count(raw, tc.marker) != 1 {
			t.Fatalf("marker %s count", tc.label)
		}
		injected := strings.Replace(raw, tc.marker, tc.replacement, 1)
		if !json.Valid([]byte(injected)) {
			t.Fatalf("invalid injected json %s", tc.label)
		}
		dec := json.NewDecoder(strings.NewReader(injected))
		dec.DisallowUnknownFields()
		var fixture v2Fixture
		if err := dec.Decode(&fixture); err == nil {
			t.Fatalf("unknown %s field accepted", tc.label)
		}
	}
}
