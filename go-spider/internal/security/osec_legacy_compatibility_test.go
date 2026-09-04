package security

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"testing"
)

const (
	legacyFixtureSHA  = "8D8B12F5F030DEA6FACE5E2B25795F667657873BD4DD89A178659E0DAABDCB45"
	legacyRecordSHA   = "37A6EA15C1E7E7D80089AE0872992E2B405125EDD68C272739C2C09EF5001E81"
	legacyALL125      = "75336a374cd9ee82a8c811f380fd9ce6893364d65eaf0fbed76424307b2baa5b"
	legacyBASE104     = "bc38711ddf559eb5319eac9b080eeec611e3742d9cf0bbdb09072317cfc975b8"
	legacyAMENDMENT21 = "dfda4174b62f27b4132cf157e96b89be2982f9268724dc12f47ebc97c7df8850"
	p004Digest        = "4ed0c899258ba53fe64eaf92b2b243281f9dbd0cfe8fae4b5c6ba76bcc38fd50"
	ver003Digest      = "5ff23879522951099e3d6d44f8f74884905f23e29ebb64b17ed63efea5066806"
)

type compatCase struct {
	ID   string                 `json:"id"`
	Body map[string]interface{} `json:"-"`
}

type compatFixture struct {
	Algorithm          string                              `json:"algorithm"`
	SchemaVersion      string                              `json:"schema_version"`
	BaselineCaseIDs    []string                            `json:"baseline_case_ids"`
	ExpectedAll125V1   string                              `json:"expected_all125_v1"`
	ExpectedBase104V1  string                              `json:"expected_base104_v1"`
	ExpectedNew21V1    string                              `json:"expected_new21_v1"`
	FrozenReasons      []string                            `json:"frozen_reasons"`
	SiteMigrationDraft []interface{}                       `json:"site_migration_draft"`
	Categories         map[string][]map[string]interface{} `json:"categories"`
}

type legacyDigest struct {
	ID     string `json:"id"`
	SHA256 string `json:"sha256"`
}

type legacyCohort struct {
	Name        string   `json:"name"`
	CaseCount   int      `json:"case_count"`
	CaseIDs     []string `json:"case_ids"`
	AggregateV1 string   `json:"aggregate_v1"`
}

type legacyRecord struct {
	CaseCount         int                    `json:"case_count"`
	CaseDigests       []legacyDigest         `json:"case_digests"`
	Cohorts           []legacyCohort         `json:"cohorts"`
	Profile           string                 `json:"profile"`
	RecordVersion     string                 `json:"record_version"`
	Provenance        map[string]interface{} `json:"provenance"`
	ValidationActions []string               `json:"validation_actions"`
}

type compatCandidate struct {
	ID     string
	Digest string
}

type compatPeer struct {
	Digests    map[string]string
	Aggregates map[string]string
}

func compatFixturesPath(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Join(filepath.Dir(file), "..", "..", "..", "tests", "fixtures")
}

func sha256Hex(data []byte) string {
	sum := sha256.Sum256(data)
	return strings.ToUpper(hex.EncodeToString(sum[:]))
}

func compatNormalize(data []byte) ([]byte, error) {
	if bytes.HasPrefix(data, []byte{0xef, 0xbb, 0xbf}) {
		return nil, errors.New("BOM")
	}
	if bytes.IndexByte(bytes.ReplaceAll(data, []byte("\r\n"), nil), '\r') >= 0 {
		return nil, errors.New("lone CR")
	}
	return bytes.ReplaceAll(data, []byte("\r\n"), []byte("\n")), nil
}

func valueToInterface(value Value) interface{} {
	switch value.Kind {
	case NullKind:
		return nil
	case BoolKind:
		return value.Bool
	case IntegerKind:
		if value.Integer == nil {
			return "0"
		}
		return value.Integer.String()
	case StringKind:
		return value.String
	case ArrayKind:
		out := make([]interface{}, 0, len(value.Array))
		for _, item := range value.Array {
			out = append(out, valueToInterface(item))
		}
		return out
	case ObjectKind:
		out := make(map[string]interface{}, len(value.Object))
		for _, member := range value.Object {
			out[member.Key] = valueToInterface(member.Value)
		}
		return out
	case NonIntegerKind:
		return value.NonInteger
	default:
		return nil
	}
}

func decodeTyped[T any](t *testing.T, raw []byte, out *T) {
	t.Helper()
	if _, err := StrictDecodeV2(raw, DefaultEvidenceLimitsV2()); err != nil {
		t.Fatalf("StrictDecodeV2: %v", err)
	}
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	if err := dec.Decode(out); err != nil {
		t.Fatalf("typed decode: %v", err)
	}
}

func decodeLegacy(t *testing.T, raw []byte, out *legacyRecord) {
	t.Helper()
	if _, err := StrictDecodeV2(raw, DefaultEvidenceLimitsV2()); err != nil {
		t.Fatalf("StrictDecodeV2 legacy: %v", err)
	}
	if err := json.Unmarshal(raw, out); err != nil {
		t.Fatalf("legacy decode: %v", err)
	}
}

func loadCompatInputs(t *testing.T) (compatFixture, legacyRecord) {
	t.Helper()
	root := compatFixturesPath(t)
	fixtureRaw, err := os.ReadFile(filepath.Join(root, "outbound_security_config_contract.json"))
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	legacyRaw, err := os.ReadFile(filepath.Join(root, "outbound_security_config_legacy_digests.json"))
	if err != nil {
		t.Fatalf("read legacy: %v", err)
	}
	fixtureNorm, err := compatNormalize(fixtureRaw)
	if err != nil {
		t.Fatalf("fixture normalize: %v", err)
	}
	legacyNorm, err := compatNormalize(legacyRaw)
	if err != nil {
		t.Fatalf("legacy normalize: %v", err)
	}
	if sha256Hex(fixtureNorm) != legacyFixtureSHA {
		t.Fatalf("fixture SHA mismatch")
	}
	if sha256Hex(legacyNorm) != legacyRecordSHA {
		t.Fatalf("legacy SHA mismatch")
	}
	if dup, err := v2rtFindDuplicate(json.NewDecoder(bytes.NewReader(fixtureRaw))); err != nil || dup != "" {
		t.Fatalf("fixture duplicate key %q %v", dup, err)
	}
	if dup, err := v2rtFindDuplicate(json.NewDecoder(bytes.NewReader(legacyRaw))); err != nil || dup != "" {
		t.Fatalf("legacy duplicate key %q %v", dup, err)
	}
	var fixture compatFixture
	decodeTyped(t, fixtureRaw, &fixture)
	var legacy legacyRecord
	decodeLegacy(t, legacyRaw, &legacy)
	if legacy.CaseCount != 125 || len(legacy.CaseDigests) != 125 {
		t.Fatalf("legacy case count mismatch")
	}
	return fixture, legacy
}

func compatCases(fixture compatFixture) []Value {
	names := make([]string, 0, len(fixture.Categories))
	for name := range fixture.Categories {
		names = append(names, name)
	}
	sort.Strings(names)
	values := make([]Value, 0, 125)
	for _, name := range names {
		for _, caseObj := range fixture.Categories[name] {
			raw, err := json.Marshal(caseObj)
			if err != nil {
				panic(err)
			}
			value, err := StrictDecodeV2(raw, DefaultEvidenceLimitsV2())
			if err != nil {
				panic(err)
			}
			values = append(values, value)
		}
	}
	return values
}

func executeCompatCases(t *testing.T, fixture compatFixture, skip map[string]bool) []compatCandidate {
	t.Helper()
	values := compatCases(fixture)
	if len(values) != 125 {
		t.Fatalf("case count %d", len(values))
	}
	if _, err := ValidateCaseDataset(values, DefaultEvidenceLimits()); err != nil {
		t.Fatalf("ValidateCaseDataset: %v", err)
	}
	seen := make(map[string]bool, len(values))
	out := make([]compatCandidate, 0, len(values))
	for _, value := range values {
		obj := value.Object
		var idValue *Value
		for i := range obj {
			if obj[i].Key == "id" {
				idValue = &obj[i].Value
				break
			}
		}
		if idValue == nil || idValue.Kind != StringKind {
			t.Fatalf("case missing string id")
		}
		id := idValue.String
		if seen[id] {
			t.Fatalf("duplicate case id %s", id)
		}
		seen[id] = true
		if skip != nil && skip[id] {
			continue
		}
		result, err := CanonicalCaseV2(value)
		if err != nil {
			t.Fatalf("CanonicalCaseV2 %s: %v", id, err)
		}
		out = append(out, compatCandidate{ID: id, Digest: result.SHA256})
	}
	return out
}

func sortedIDs(candidates []compatCandidate) []string {
	ids := make([]string, 0, len(candidates))
	for _, c := range candidates {
		ids = append(ids, c.ID)
	}
	sort.Strings(ids)
	return ids
}

func candidateMap(candidates []compatCandidate) map[string]string {
	out := make(map[string]string, len(candidates))
	for _, c := range candidates {
		out[c.ID] = c.Digest
	}
	return out
}

func compatAggregate(candidates []compatCandidate, ids []string) (string, error) {
	byID := candidateMap(candidates)
	digests := make([]CaseDigest, 0, len(ids))
	for _, id := range ids {
		raw, err := hex.DecodeString(byID[id])
		if err != nil {
			return "", err
		}
		digests = append(digests, CaseDigest{ID: id, Digest: raw})
	}
	return AggregateV1(digests, "OSEC-CASE-AGGREGATE-V1")
}

func validateCompat(candidates []compatCandidate, fixture compatFixture, legacy legacyRecord, peer *compatPeer) error {
	byID := candidateMap(candidates)
	executed := sortedIDs(candidates)
	expected := make([]string, 0, len(legacy.CaseDigests))
	for _, item := range legacy.CaseDigests {
		expected = append(expected, item.ID)
	}
	sort.Strings(expected)
	if len(candidates) != 125 || len(expected) != 125 {
		return fmt.Errorf("case counts expected=%d executed=%d", len(expected), len(candidates))
	}
	expectedSet := make(map[string]bool, len(expected))
	for _, id := range expected {
		expectedSet[id] = true
	}
	missing := []string{}
	extra := []string{}
	for _, id := range expected {
		if _, ok := byID[id]; !ok {
			missing = append(missing, id)
		}
	}
	seen := map[string]bool{}
	for _, id := range executed {
		if seen[id] {
			return fmt.Errorf("duplicate candidate id %s", id)
		}
		seen[id] = true
		if !expectedSet[id] {
			extra = append(extra, id)
		}
	}
	if len(missing) > 0 || len(extra) > 0 {
		return fmt.Errorf("set mismatch missing=%v extra=%v", missing, extra)
	}
	legacyByID := make(map[string]string, len(legacy.CaseDigests))
	for _, item := range legacy.CaseDigests {
		legacyByID[item.ID] = item.SHA256
	}
	for _, id := range executed {
		if byID[id] != legacyByID[id] {
			return fmt.Errorf("digest mismatch %s", id)
		}
	}
	if peer != nil {
		for id, digest := range byID {
			if peer.Digests[id] != digest {
				return fmt.Errorf("peer digest mismatch %s", id)
			}
		}
	}
	cohortByID := make(map[string]*legacyCohort, len(legacy.Cohorts))
	for i := range legacy.Cohorts {
		c := &legacy.Cohorts[i]
		cohortByID[c.Name] = c
	}
	if len(cohortByID) != 3 {
		return fmt.Errorf("cohort names mismatch")
	}
	all := cohortByID["all125"]
	base := cohortByID["base104"]
	amendment := cohortByID["amendment21"]
	if all == nil || base == nil || amendment == nil {
		return fmt.Errorf("cohort names mismatch")
	}
	if !equalStrings(all.CaseIDs, executed) {
		return fmt.Errorf("cohort mismatch all125")
	}
	if !equalStrings(base.CaseIDs, sortedCopy(fixture.BaselineCaseIDs)) {
		return fmt.Errorf("cohort mismatch base104")
	}
	baseSet := make(map[string]bool, len(fixture.BaselineCaseIDs))
	for _, id := range fixture.BaselineCaseIDs {
		baseSet[id] = true
	}
	amendmentSet := []string{}
	for _, id := range executed {
		if !baseSet[id] {
			amendmentSet = append(amendmentSet, id)
		}
	}
	sort.Strings(amendmentSet)
	if !equalStrings(amendment.CaseIDs, amendmentSet) {
		return fmt.Errorf("cohort mismatch amendment21")
	}
	for _, id := range amendmentSet {
		if baseSet[id] {
			return fmt.Errorf("cohort overlap")
		}
	}
	if len(baseSet)+len(amendmentSet) != len(executed) {
		return fmt.Errorf("cohort union mismatch")
	}
	expectedAggregates := map[string]string{
		"all125":      fixture.ExpectedAll125V1,
		"base104":     fixture.ExpectedBase104V1,
		"amendment21": fixture.ExpectedNew21V1,
	}
	frozen := map[string]string{
		"all125":      legacyALL125,
		"base104":     legacyBASE104,
		"amendment21": legacyAMENDMENT21,
	}
	candidateAggregates := map[string]string{}
	for name, cohort := range cohortByID {
		value, err := compatAggregate(candidates, cohort.CaseIDs)
		if err != nil {
			return err
		}
		candidateAggregates[name] = value
		if value != cohort.AggregateV1 {
			return fmt.Errorf("aggregate mismatch %s:legacy", name)
		}
		if value != expectedAggregates[name] {
			return fmt.Errorf("aggregate mismatch %s:fixture", name)
		}
		if value != frozen[name] {
			return fmt.Errorf("aggregate mismatch %s:frozen", name)
		}
	}
	if peer != nil {
		for name, value := range candidateAggregates {
			if peer.Aggregates[name] != value {
				return fmt.Errorf("aggregate mismatch %s:peer", name)
			}
		}
	}
	if len(legacy.ValidationActions) > 0 {
		known := map[string]bool{"structure": true, "aggregate_recompute": true, "frozen_aggregates": true}
		if len(legacy.ValidationActions) != 3 {
			return fmt.Errorf("unknown validation action")
		}
		for _, action := range legacy.ValidationActions {
			if !known[action] {
				return fmt.Errorf("unknown validation action %s", action)
			}
		}
	}
	return nil
}

func equalStrings(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func sortedCopy(in []string) []string {
	out := append([]string(nil), in...)
	sort.Strings(out)
	return out
}

func flipHex(in string) string {
	if len(in) == 0 {
		return in
	}
	first := in[0]
	if first == '0' {
		return "1" + in[1:]
	}
	return "0" + in[1:]
}

func cloneFixture(fixture compatFixture) compatFixture {
	out := fixture
	out.BaselineCaseIDs = append([]string(nil), fixture.BaselineCaseIDs...)
	out.Categories = make(map[string][]map[string]interface{}, len(fixture.Categories))
	for name, cases := range fixture.Categories {
		copied := make([]map[string]interface{}, len(cases))
		for i, c := range cases {
			item := make(map[string]interface{}, len(c))
			for k, v := range c {
				item[k] = v
			}
			copied[i] = item
		}
		out.Categories[name] = copied
	}
	return out
}

func cloneLegacy(legacy legacyRecord) legacyRecord {
	out := legacy
	out.CaseDigests = append([]legacyDigest(nil), legacy.CaseDigests...)
	out.Cohorts = make([]legacyCohort, len(legacy.Cohorts))
	for i, c := range legacy.Cohorts {
		c.CaseIDs = append([]string(nil), c.CaseIDs...)
		out.Cohorts[i] = c
	}
	out.ValidationActions = append([]string(nil), legacy.ValidationActions...)
	return out
}

func cloneCandidates(candidates []compatCandidate) []compatCandidate {
	return append([]compatCandidate(nil), candidates...)
}

func clonePeer(peer compatPeer) compatPeer {
	out := compatPeer{Digests: make(map[string]string, len(peer.Digests)), Aggregates: make(map[string]string, len(peer.Aggregates))}
	for k, v := range peer.Digests {
		out.Digests[k] = v
	}
	for k, v := range peer.Aggregates {
		out.Aggregates[k] = v
	}
	return out
}

func buildPeer(candidates []compatCandidate, legacy legacyRecord) compatPeer {
	peer := compatPeer{Digests: candidateMap(candidates), Aggregates: map[string]string{}}
	for _, cohort := range legacy.Cohorts {
		value, _ := compatAggregate(candidates, cohort.CaseIDs)
		peer.Aggregates[cohort.Name] = value
	}
	return peer
}

func TestOSECCanonicalV2MatchesLegacy125Cases(t *testing.T) {
	fixture, legacy := loadCompatInputs(t)
	candidates := executeCompatCases(t, fixture, nil)
	if err := validateCompat(candidates, fixture, legacy, nil); err != nil {
		t.Fatalf("MATCH failed: %v", err)
	}
	byID := candidateMap(candidates)
	if byID["p-004"] != p004Digest {
		t.Fatalf("p-004 digest mismatch")
	}
	if byID["ver-003"] != ver003Digest {
		t.Fatalf("ver-003 digest mismatch")
	}
	if len(byID) != 125 {
		t.Fatalf("candidate count %d", len(byID))
	}
}

func TestOSECCanonicalV2CompatibilityGateRejectsMutations(t *testing.T) {
	fixture, legacy := loadCompatInputs(t)
	candidates := executeCompatCases(t, fixture, nil)
	peer := buildPeer(candidates, legacy)

	run := func(name string, candidates []compatCandidate, fixture compatFixture, legacy legacyRecord, peer *compatPeer) {
		t.Helper()
		if err := validateCompat(candidates, fixture, legacy, peer); err == nil {
			t.Fatalf("gate %s: expected rejection", name)
		}
	}

	t.Run("missing_case", func(t *testing.T) {
		run("missing_case", cloneCandidates(candidates)[:124], fixture, legacy, &peer)
	})
	t.Run("extra_case", func(t *testing.T) {
		run("extra_case", append(cloneCandidates(candidates), compatCandidate{ID: "unknown-extra", Digest: strings.Repeat("0", 64)}), fixture, legacy, &peer)
	})
	t.Run("duplicate_case", func(t *testing.T) {
		run("duplicate_case", append(cloneCandidates(candidates), candidates[0]), fixture, legacy, &peer)
	})
	t.Run("dispatcher_omits_case", func(t *testing.T) {
		run("dispatcher_omits_case", executeCompatCases(t, fixture, map[string]bool{candidates[0].ID: true}), fixture, legacy, &peer)
	})
	t.Run("candidate_digest_flip", func(t *testing.T) {
		mutated := cloneCandidates(candidates)
		mutated[0].Digest = flipHex(mutated[0].Digest)
		run("candidate_digest_flip", mutated, fixture, legacy, &peer)
	})
	t.Run("legacy_digest_flip", func(t *testing.T) {
		legacyMut := cloneLegacy(legacy)
		legacyMut.CaseDigests[0].SHA256 = flipHex(legacyMut.CaseDigests[0].SHA256)
		run("legacy_digest_flip", candidates, fixture, legacyMut, &peer)
	})
	t.Run("p004_numeric_normalization", func(t *testing.T) {
		fixtureMut := cloneFixture(fixture)
		ports := fixtureMut.Categories["port"]
		for _, c := range ports {
			if c["id"] == "p-004" {
				c["ports"] = map[string]interface{}{"https": []interface{}{json.Number("443")}}
			}
		}
		mutated := executeCompatCases(t, fixtureMut, nil)
		run("p004_numeric_normalization", mutated, fixtureMut, legacy, &peer)
	})
	t.Run("ver003_numeric_normalization", func(t *testing.T) {
		fixtureMut := cloneFixture(fixture)
		for _, c := range fixtureMut.Categories["version"] {
			if c["id"] == "ver-003" {
				c["value"] = json.Number("1")
			}
		}
		mutated := executeCompatCases(t, fixtureMut, nil)
		run("ver003_numeric_normalization", mutated, fixtureMut, legacy, &peer)
	})
	t.Run("ordinary_case_mutation", func(t *testing.T) {
		fixtureMut := cloneFixture(fixture)
		names := make([]string, 0, len(fixtureMut.Categories))
		for name := range fixtureMut.Categories {
			names = append(names, name)
		}
		sort.Strings(names)
		cases := fixtureMut.Categories[names[0]]
		first := cases[0]
		desc, _ := first["description"].(string)
		first["description"] = desc + " MUTATED"
		mutated := executeCompatCases(t, fixtureMut, nil)
		run("ordinary_case_mutation", mutated, fixtureMut, legacy, &peer)
	})
	t.Run("base104_missing_id", func(t *testing.T) {
		fixtureMut := cloneFixture(fixture)
		fixtureMut.BaselineCaseIDs = fixtureMut.BaselineCaseIDs[:len(fixtureMut.BaselineCaseIDs)-1]
		run("base104_missing_id", candidates, fixtureMut, legacy, &peer)
	})
	t.Run("base104_add_amendment_id", func(t *testing.T) {
		amendmentID := ""
		for _, c := range candidates {
			found := false
			for _, id := range fixture.BaselineCaseIDs {
				if id == c.ID {
					found = true
					break
				}
			}
			if !found {
				amendmentID = c.ID
				break
			}
		}
		fixtureMut := cloneFixture(fixture)
		fixtureMut.BaselineCaseIDs = append(fixtureMut.BaselineCaseIDs, amendmentID)
		run("base104_add_amendment_id", candidates, fixtureMut, legacy, &peer)
	})
	t.Run("amendment21_missing_id", func(t *testing.T) {
		legacyMut := cloneLegacy(legacy)
		for i := range legacyMut.Cohorts {
			if legacyMut.Cohorts[i].Name == "amendment21" {
				legacyMut.Cohorts[i].CaseIDs = legacyMut.Cohorts[i].CaseIDs[:len(legacyMut.Cohorts[i].CaseIDs)-1]
			}
		}
		run("amendment21_missing_id", candidates, fixture, legacyMut, &peer)
	})
	t.Run("amendment21_extra_id", func(t *testing.T) {
		legacyMut := cloneLegacy(legacy)
		for i := range legacyMut.Cohorts {
			if legacyMut.Cohorts[i].Name == "amendment21" {
				legacyMut.Cohorts[i].CaseIDs = append(legacyMut.Cohorts[i].CaseIDs, fixture.BaselineCaseIDs[0])
			}
		}
		run("amendment21_extra_id", candidates, fixture, legacyMut, &peer)
	})
	t.Run("cohort_overlap", func(t *testing.T) {
		legacyMut := cloneLegacy(legacy)
		for i := range legacyMut.Cohorts {
			if legacyMut.Cohorts[i].Name == "amendment21" {
				legacyMut.Cohorts[i].CaseIDs = append(legacyMut.Cohorts[i].CaseIDs, fixture.BaselineCaseIDs[0])
			}
		}
		run("cohort_overlap", candidates, fixture, legacyMut, &peer)
	})
	t.Run("cohort_union_mismatch", func(t *testing.T) {
		legacyMut := cloneLegacy(legacy)
		for i := range legacyMut.Cohorts {
			if legacyMut.Cohorts[i].Name == "all125" {
				legacyMut.Cohorts[i].CaseIDs = legacyMut.Cohorts[i].CaseIDs[:len(legacyMut.Cohorts[i].CaseIDs)-1]
			}
		}
		run("cohort_union_mismatch", candidates, fixture, legacyMut, &peer)
	})
	t.Run("cohort_order_mismatch", func(t *testing.T) {
		legacyMut := cloneLegacy(legacy)
		for i := range legacyMut.Cohorts {
			if legacyMut.Cohorts[i].Name == "all125" {
				reversed := append([]string(nil), legacyMut.Cohorts[i].CaseIDs...)
				for l, r := 0, len(reversed)-1; l < r; l, r = l+1, r-1 {
					reversed[l], reversed[r] = reversed[r], reversed[l]
				}
				legacyMut.Cohorts[i].CaseIDs = reversed
			}
		}
		run("cohort_order_mismatch", candidates, fixture, legacyMut, &peer)
	})
	t.Run("cohort_name_mismatch", func(t *testing.T) {
		legacyMut := cloneLegacy(legacy)
		for i := range legacyMut.Cohorts {
			if legacyMut.Cohorts[i].Name == "amendment21" {
				legacyMut.Cohorts[i].Name = "amendment22"
			}
		}
		run("cohort_name_mismatch", candidates, fixture, legacyMut, &peer)
	})
	for _, cohortName := range []string{"all125", "base104", "amendment21"} {
		cohortName := cohortName
		t.Run("aggregate_digest_flip_"+cohortName, func(t *testing.T) {
			legacyMut := cloneLegacy(legacy)
			for i := range legacyMut.Cohorts {
				if legacyMut.Cohorts[i].Name == cohortName {
					legacyMut.Cohorts[i].AggregateV1 = flipHex(legacyMut.Cohorts[i].AggregateV1)
				}
			}
			run("aggregate_digest_flip_"+cohortName, candidates, fixture, legacyMut, &peer)
		})
	}
	t.Run("aggregate_omits_record", func(t *testing.T) {
		peerMut := clonePeer(peer)
		peerMut.Aggregates["all125"] = strings.Repeat("0", 64)
		run("aggregate_omits_record", candidates, fixture, legacy, &peerMut)
	})
	t.Run("unknown_validation_action", func(t *testing.T) {
		legacyMut := cloneLegacy(legacy)
		legacyMut.ValidationActions = []string{"structure", "aggregate_recompute", "unknown_action"}
		run("unknown_validation_action", candidates, fixture, legacyMut, &peer)
	})
	t.Run("expected_executed_set_mismatch", func(t *testing.T) {
		legacyMut := cloneLegacy(legacy)
		legacyMut.CaseDigests = legacyMut.CaseDigests[:len(legacyMut.CaseDigests)-1]
		run("expected_executed_set_mismatch", candidates, fixture, legacyMut, &peer)
	})
	t.Run("peer_candidate_digest_mismatch", func(t *testing.T) {
		peerMut := clonePeer(peer)
		peerMut.Digests[candidates[0].ID] = flipHex(candidates[0].Digest)
		run("peer_candidate_digest_mismatch", candidates, fixture, legacy, &peerMut)
	})
	t.Run("peer_candidate_aggregate_mismatch", func(t *testing.T) {
		peerMut := clonePeer(peer)
		peerMut.Aggregates["base104"] = flipHex(peerMut.Aggregates["base104"])
		run("peer_candidate_aggregate_mismatch", candidates, fixture, legacy, &peerMut)
	})
}

func TestOSECV1MismatchHistoryIsPreserved(t *testing.T) {
	fixture, legacy := loadCompatInputs(t)
	legacyByID := make(map[string]string, len(legacy.CaseDigests))
	for _, item := range legacy.CaseDigests {
		legacyByID[item.ID] = item.SHA256
	}
	for _, caseID := range []string{"p-004", "ver-003"} {
		var caseObj map[string]interface{}
		found := false
		for _, cases := range fixture.Categories {
			for _, c := range cases {
				if c["id"] == caseID {
					caseObj = c
					found = true
				}
			}
		}
		if !found {
			t.Fatalf("missing case %s", caseID)
		}
		raw, err := json.Marshal(caseObj)
		if err != nil {
			t.Fatalf("marshal %s: %v", caseID, err)
		}
		value, err := StrictDecode(raw, DefaultEvidenceLimits())
		if err != nil {
			t.Fatalf("strict decode %s: %v", caseID, err)
		}
		if _, err := CanonicalCase(value); err == nil {
			t.Fatalf("V1 canonical_case accepted %s", caseID)
		} else {
			var ev *EvidenceError
			if !errors.As(err, &ev) || ev.Code != "canonical_non_integer_number" {
				t.Fatalf("V1 error code %v", err)
			}
		}
		v2Value, err := StrictDecodeV2(raw, DefaultEvidenceLimitsV2())
		if err != nil {
			t.Fatalf("strict decode v2 %s: %v", caseID, err)
		}
		result, err := CanonicalCaseV2(v2Value)
		if err != nil {
			t.Fatalf("CanonicalCaseV2 %s: %v", caseID, err)
		}
		if result.SHA256 != legacyByID[caseID] {
			t.Fatalf("V2 digest mismatch %s", caseID)
		}
	}
}
