package security

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math/big"
	"reflect"
	"regexp"
	"sort"
)

const (
	manifestVersionV2       = "OSEC-CASE-MANIFEST-V2"
	manifestProfileV2       = "OSEC-EVIDENCE-PROFILE-V2"
	manifestStrictDecodeV2  = "OSEC-STRICT-JSON-DECODE-V1"
	manifestLimitsV2        = "OSEC-EVIDENCE-LIMITS-V2"
	manifestCanonicalJSONV2 = "OSEC-CANONICAL-JSON-V2"
	manifestCanonicalCaseV2 = "OSEC-CANONICAL-CASE-V2"
	manifestAggregateV1     = "OSEC-CASE-AGGREGATE-V1"
	manifestCategoryAggV1   = "OSEC-CASE-CATEGORY-AGGREGATE-V1"
	manifestDigestAlgorithm = "SHA-256"
	manifestDataset         = "outbound_security_config"
	manifestHashMagicV2     = "OSEC-CASE-MANIFEST-HASH-V2\x00"
	manifestCaseCount       = 125
)

var (
	manifestDatasetRE    = regexp.MustCompile(`^[a-z][a-z0-9_-]{0,63}$`)
	manifestCohortNameRE = regexp.MustCompile(`^[a-z][a-z0-9_-]{0,63}$`)
	manifestSHA256HexRE  = regexp.MustCompile(`^[0-9a-f]{64}$`)
)

// CohortV2 is one manifest cohort.
type CohortV2 struct {
	Name        string
	CaseCount   int
	CaseIDs     []string
	AggregateV1 string
}

// CaseDigestV2 is one manifest case digest entry.
type CaseDigestV2 struct {
	ID       string
	Category string
	SHA256   string
}

// ManifestV2 is the manifest_v2 payload.
type ManifestV2 struct {
	ManifestVersion            string
	Profile                    string
	StrictDecodeVersion        string
	EvidenceLimitsVersion      string
	CanonicalJSONVersion       string
	CanonicalCaseVersion       string
	AggregateAlgorithm         string
	CategoryAggregateAlgorithm string
	DigestAlgorithm            string
	Dataset                    string
	CaseCount                  int
	Cohorts                    []CohortV2
	CategoryNames              []string
	WholeSetAggregateV1        string
	CategoryAggregates         map[string]string
	CaseDigests                []CaseDigestV2
}

// ManifestEnvelopeV2 is the outer envelope.
type ManifestEnvelopeV2 struct {
	ManifestV2     ManifestV2
	ManifestHashV2 string
}

func manifestJSONValue(manifest ManifestV2) (Value, error) {
	obj := []ObjectMember{
		{Key: "manifest_version", Value: Value{Kind: StringKind, String: manifest.ManifestVersion}},
		{Key: "profile", Value: Value{Kind: StringKind, String: manifest.Profile}},
		{Key: "strict_decode_version", Value: Value{Kind: StringKind, String: manifest.StrictDecodeVersion}},
		{Key: "evidence_limits_version", Value: Value{Kind: StringKind, String: manifest.EvidenceLimitsVersion}},
		{Key: "canonical_json_version", Value: Value{Kind: StringKind, String: manifest.CanonicalJSONVersion}},
		{Key: "canonical_case_version", Value: Value{Kind: StringKind, String: manifest.CanonicalCaseVersion}},
		{Key: "aggregate_algorithm", Value: Value{Kind: StringKind, String: manifest.AggregateAlgorithm}},
		{Key: "category_aggregate_algorithm", Value: Value{Kind: StringKind, String: manifest.CategoryAggregateAlgorithm}},
		{Key: "digest_algorithm", Value: Value{Kind: StringKind, String: manifest.DigestAlgorithm}},
		{Key: "dataset", Value: Value{Kind: StringKind, String: manifest.Dataset}},
		{Key: "case_count", Value: Value{Kind: IntegerKind, Integer: bigIntFromInt(manifest.CaseCount)}},
	}
	cohorts := make([]Value, 0, len(manifest.Cohorts))
	for _, cohort := range manifest.Cohorts {
		ids := make([]Value, 0, len(cohort.CaseIDs))
		for _, id := range cohort.CaseIDs {
			ids = append(ids, Value{Kind: StringKind, String: id})
		}
		cohorts = append(cohorts, Value{Kind: ObjectKind, Object: []ObjectMember{
			{Key: "name", Value: Value{Kind: StringKind, String: cohort.Name}},
			{Key: "case_count", Value: Value{Kind: IntegerKind, Integer: bigIntFromInt(cohort.CaseCount)}},
			{Key: "case_ids", Value: Value{Kind: ArrayKind, Array: ids}},
			{Key: "aggregate_v1", Value: Value{Kind: StringKind, String: cohort.AggregateV1}},
		}})
	}
	obj = append(obj, ObjectMember{Key: "cohorts", Value: Value{Kind: ArrayKind, Array: cohorts}})

	names := make([]Value, 0, len(manifest.CategoryNames))
	for _, name := range manifest.CategoryNames {
		names = append(names, Value{Kind: StringKind, String: name})
	}
	obj = append(obj, ObjectMember{Key: "category_names", Value: Value{Kind: ArrayKind, Array: names}})
	obj = append(obj, ObjectMember{Key: "whole_set_aggregate_v1", Value: Value{Kind: StringKind, String: manifest.WholeSetAggregateV1}})

	aggMembers := make([]ObjectMember, 0, len(manifest.CategoryAggregates))
	for _, name := range manifest.CategoryNames {
		aggMembers = append(aggMembers, ObjectMember{Key: name, Value: Value{Kind: StringKind, String: manifest.CategoryAggregates[name]}})
	}
	obj = append(obj, ObjectMember{Key: "category_aggregates", Value: Value{Kind: ObjectKind, Object: aggMembers}})

	digests := make([]Value, 0, len(manifest.CaseDigests))
	for _, digest := range manifest.CaseDigests {
		digests = append(digests, Value{Kind: ObjectKind, Object: []ObjectMember{
			{Key: "id", Value: Value{Kind: StringKind, String: digest.ID}},
			{Key: "category", Value: Value{Kind: StringKind, String: digest.Category}},
			{Key: "sha256", Value: Value{Kind: StringKind, String: digest.SHA256}},
		}})
	}
	obj = append(obj, ObjectMember{Key: "case_digests", Value: Value{Kind: ArrayKind, Array: digests}})
	return Value{Kind: ObjectKind, Object: obj}, nil
}

func envelopeJSONValue(manifest ManifestV2, hash string) (Value, error) {
	manifestValue, err := manifestJSONValue(manifest)
	if err != nil {
		return Value{}, err
	}
	return Value{Kind: ObjectKind, Object: []ObjectMember{
		{Key: "manifest_v2", Value: manifestValue},
		{Key: "manifest_hash_v2", Value: Value{Kind: StringKind, String: hash}},
	}}, nil
}

// ManifestHashV2 computes the sealed manifest hash from manifest_v2.
func ManifestHashV2(manifest ManifestV2) (string, error) {
	value, err := manifestJSONValue(manifest)
	if err != nil {
		return "", err
	}
	canonical, err := CanonicalJSONV2(value)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(append([]byte(manifestHashMagicV2), canonical...))
	return hex.EncodeToString(sum[:]), nil
}

// BuildEnvelopeV2 builds the complete envelope.
func BuildEnvelopeV2(manifest ManifestV2) (ManifestEnvelopeV2, error) {
	hash, err := ManifestHashV2(manifest)
	if err != nil {
		return ManifestEnvelopeV2{}, err
	}
	return ManifestEnvelopeV2{ManifestV2: manifest, ManifestHashV2: hash}, nil
}

// EnvelopeToBytes serializes the envelope deterministically.
func EnvelopeToBytes(envelope ManifestEnvelopeV2) ([]byte, error) {
	value, err := envelopeJSONValue(envelope.ManifestV2, envelope.ManifestHashV2)
	if err != nil {
		return nil, err
	}
	return CanonicalJSONV2(value)
}

// DecodeEnvelopeV2 strictly decodes and validates an envelope.
func DecodeEnvelopeV2(raw []byte, fixtureObj, legacyObj any) (ManifestEnvelopeV2, error) {
	value, err := StrictDecodeV2(raw, DefaultEvidenceLimitsV2())
	if err != nil {
		return ManifestEnvelopeV2{}, err
	}
	if value.Kind != ObjectKind {
		return ManifestEnvelopeV2{}, fmt.Errorf("envelope must be object")
	}
	envelopeMap := objectToMap(value)
	if len(envelopeMap) != 2 {
		return ManifestEnvelopeV2{}, fmt.Errorf("envelope unknown field")
	}
	if _, ok := envelopeMap["manifest_v2"]; !ok {
		return ManifestEnvelopeV2{}, fmt.Errorf("envelope missing manifest_v2")
	}
	hashValue, ok := envelopeMap["manifest_hash_v2"]
	if !ok || hashValue.Kind != StringKind {
		return ManifestEnvelopeV2{}, fmt.Errorf("envelope missing manifest_hash_v2")
	}
	manifestValue, ok := envelopeMap["manifest_v2"]
	if !ok || manifestValue.Kind != ObjectKind {
		return ManifestEnvelopeV2{}, fmt.Errorf("envelope manifest_v2 must be object")
	}
	manifest, err := decodeManifestV2(manifestValue)
	if err != nil {
		return ManifestEnvelopeV2{}, err
	}
	if err := ValidateManifestV2(manifest, fixtureObj, legacyObj); err != nil {
		return ManifestEnvelopeV2{}, err
	}
	expected, err := ManifestHashV2(manifest)
	if err != nil {
		return ManifestEnvelopeV2{}, err
	}
	if hashValue.String != expected {
		return ManifestEnvelopeV2{}, fmt.Errorf("manifest_hash_v2 mismatch")
	}
	return ManifestEnvelopeV2{ManifestV2: manifest, ManifestHashV2: hashValue.String}, nil
}

// ValidateManifestV2 validates manifest_v2 against the fixture and legacy record.
func ValidateManifestV2(manifest ManifestV2, fixtureObj, legacyObj any) error {
	if manifest.ManifestVersion != manifestVersionV2 ||
		manifest.Profile != manifestProfileV2 ||
		manifest.StrictDecodeVersion != manifestStrictDecodeV2 ||
		manifest.EvidenceLimitsVersion != manifestLimitsV2 ||
		manifest.CanonicalJSONVersion != manifestCanonicalJSONV2 ||
		manifest.CanonicalCaseVersion != manifestCanonicalCaseV2 ||
		manifest.AggregateAlgorithm != manifestAggregateV1 ||
		manifest.CategoryAggregateAlgorithm != manifestCategoryAggV1 ||
		manifest.DigestAlgorithm != manifestDigestAlgorithm {
		return fmt.Errorf("manifest version field mismatch")
	}
	if !manifestDatasetRE.MatchString(manifest.Dataset) || manifest.Dataset != manifestDataset {
		return fmt.Errorf("manifest dataset mismatch")
	}
	if manifest.CaseCount != manifestCaseCount {
		return fmt.Errorf("manifest case_count mismatch")
	}
	fixture, ok := fixtureObj.(map[string]any)
	if !ok {
		return fmt.Errorf("fixture object required")
	}
	legacy, ok := legacyObj.(map[string]any)
	if !ok {
		return fmt.Errorf("legacy object required")
	}
	generated, err := BuildManifestV2(fixture, legacy)
	if err != nil {
		return err
	}
	if !reflect.DeepEqual(generated, manifest) {
		return fmt.Errorf("manifest differs from regenerated manifest")
	}
	if len(manifest.Cohorts) != 3 {
		return fmt.Errorf("cohort count mismatch")
	}
	if !sortedUTF8Strings(namesOfCohorts(manifest.Cohorts)) {
		return fmt.Errorf("cohort order mismatch")
	}
	for _, cohort := range manifest.Cohorts {
		if !manifestCohortNameRE.MatchString(cohort.Name) {
			return fmt.Errorf("invalid cohort name")
		}
		if len(cohort.CaseIDs) != len(uniqueStrings(cohort.CaseIDs)) {
			return fmt.Errorf("cohort duplicate id %s", cohort.Name)
		}
		if cohort.CaseCount != len(cohort.CaseIDs) {
			return fmt.Errorf("cohort case_count mismatch %s", cohort.Name)
		}
		if !sortedUTF8Strings(cohort.CaseIDs) {
			return fmt.Errorf("cohort case_ids order mismatch %s", cohort.Name)
		}
		if !manifestSHA256HexRE.MatchString(cohort.AggregateV1) {
			return fmt.Errorf("cohort aggregate invalid %s", cohort.Name)
		}
	}
	if len(manifest.CategoryNames) != len(manifest.CategoryAggregates) {
		return fmt.Errorf("category_names count mismatch")
	}
	if !sortedUTF8Strings(manifest.CategoryNames) {
		return fmt.Errorf("category_names order mismatch")
	}
	for _, name := range manifest.CategoryNames {
		if _, ok := manifest.CategoryAggregates[name]; !ok {
			return fmt.Errorf("category aggregate missing %s", name)
		}
	}
	if len(manifest.CaseDigests) != manifestCaseCount {
		return fmt.Errorf("case_digests count mismatch")
	}
	if !sortedUTF8Strings(idsOfCaseDigests(manifest.CaseDigests)) {
		return fmt.Errorf("case_digests order mismatch")
	}
	if len(uniqueStrings(idsOfCaseDigests(manifest.CaseDigests))) != manifestCaseCount {
		return fmt.Errorf("case_digests duplicate id")
	}
	return nil
}

func namesOfCohorts(cohorts []CohortV2) []string {
	out := make([]string, 0, len(cohorts))
	for _, c := range cohorts {
		out = append(out, c.Name)
	}
	return out
}

func idsOfCaseDigests(digests []CaseDigestV2) []string {
	out := make([]string, 0, len(digests))
	for _, d := range digests {
		out = append(out, d.ID)
	}
	return out
}

func uniqueStrings(in []string) []string {
	seen := map[string]bool{}
	out := make([]string, 0, len(in))
	for _, s := range in {
		if !seen[s] {
			seen[s] = true
			out = append(out, s)
		}
	}
	return out
}

func sortedUTF8Strings(in []string) bool {
	if len(in) == 0 {
		return true
	}
	copied := append([]string(nil), in...)
	sort.Slice(copied, func(i, j int) bool { return bytes.Compare([]byte(copied[i]), []byte(copied[j])) < 0 })
	return equalStringSlices(in, copied)
}

func equalStringSlices(a, b []string) bool {
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

func objectToMap(value Value) map[string]Value {
	out := map[string]Value{}
	for _, member := range value.Object {
		out[member.Key] = member.Value
	}
	return out
}

func decodeManifestV2(value Value) (ManifestV2, error) {
	if value.Kind != ObjectKind {
		return ManifestV2{}, fmt.Errorf("manifest_v2 must be object")
	}
	fields := map[string]bool{
		"manifest_version": true, "profile": true, "strict_decode_version": true,
		"evidence_limits_version": true, "canonical_json_version": true, "canonical_case_version": true,
		"aggregate_algorithm": true, "category_aggregate_algorithm": true, "digest_algorithm": true,
		"dataset": true, "case_count": true, "cohorts": true, "category_names": true,
		"whole_set_aggregate_v1": true, "category_aggregates": true, "case_digests": true,
	}
	m := objectToMap(value)
	if len(m) != len(fields) {
		return ManifestV2{}, fmt.Errorf("manifest_v2 unknown field")
	}
	for key := range fields {
		if _, ok := m[key]; !ok {
			return ManifestV2{}, fmt.Errorf("manifest_v2 missing field %s", key)
		}
	}
	strField := func(key string) (string, error) {
		v := m[key]
		if v.Kind != StringKind {
			return "", fmt.Errorf("manifest field %s must be string", key)
		}
		return v.String, nil
	}
	manifest := ManifestV2{}
	var err error
	if manifest.ManifestVersion, err = strField("manifest_version"); err != nil {
		return ManifestV2{}, err
	}
	if manifest.Profile, err = strField("profile"); err != nil {
		return ManifestV2{}, err
	}
	if manifest.StrictDecodeVersion, err = strField("strict_decode_version"); err != nil {
		return ManifestV2{}, err
	}
	if manifest.EvidenceLimitsVersion, err = strField("evidence_limits_version"); err != nil {
		return ManifestV2{}, err
	}
	if manifest.CanonicalJSONVersion, err = strField("canonical_json_version"); err != nil {
		return ManifestV2{}, err
	}
	if manifest.CanonicalCaseVersion, err = strField("canonical_case_version"); err != nil {
		return ManifestV2{}, err
	}
	if manifest.AggregateAlgorithm, err = strField("aggregate_algorithm"); err != nil {
		return ManifestV2{}, err
	}
	if manifest.CategoryAggregateAlgorithm, err = strField("category_aggregate_algorithm"); err != nil {
		return ManifestV2{}, err
	}
	if manifest.DigestAlgorithm, err = strField("digest_algorithm"); err != nil {
		return ManifestV2{}, err
	}
	if manifest.Dataset, err = strField("dataset"); err != nil {
		return ManifestV2{}, err
	}
	if m["case_count"].Kind != IntegerKind || m["case_count"].Integer == nil {
		return ManifestV2{}, fmt.Errorf("manifest case_count must be integer")
	}
	manifest.CaseCount = int(m["case_count"].Integer.Int64())
	if manifest.WholeSetAggregateV1, err = strField("whole_set_aggregate_v1"); err != nil {
		return ManifestV2{}, err
	}
	cohorts := m["cohorts"]
	if cohorts.Kind != ArrayKind {
		return ManifestV2{}, fmt.Errorf("manifest cohorts must be array")
	}
	manifest.Cohorts = make([]CohortV2, 0, len(cohorts.Array))
	cohortFields := map[string]bool{"name": true, "case_count": true, "case_ids": true, "aggregate_v1": true}
	for _, cohortValue := range cohorts.Array {
		if cohortValue.Kind != ObjectKind {
			return ManifestV2{}, fmt.Errorf("cohort must be object")
		}
		cm := objectToMap(cohortValue)
		if len(cm) != len(cohortFields) {
			return ManifestV2{}, fmt.Errorf("cohort unknown field")
		}
		for key := range cohortFields {
			if _, ok := cm[key]; !ok {
				return ManifestV2{}, fmt.Errorf("cohort missing field %s", key)
			}
		}
		nameValue, err := strFieldFromMap(cm, "name")
		if err != nil {
			return ManifestV2{}, err
		}
		aggValue, err := strFieldFromMap(cm, "aggregate_v1")
		if err != nil {
			return ManifestV2{}, err
		}
		if cm["case_count"].Kind != IntegerKind || cm["case_count"].Integer == nil {
			return ManifestV2{}, fmt.Errorf("cohort case_count must be integer")
		}
		idsValue := cm["case_ids"]
		if idsValue.Kind != ArrayKind {
			return ManifestV2{}, fmt.Errorf("cohort case_ids must be array")
		}
		ids := make([]string, 0, len(idsValue.Array))
		for _, id := range idsValue.Array {
			if id.Kind != StringKind {
				return ManifestV2{}, fmt.Errorf("cohort case_ids must be strings")
			}
			ids = append(ids, id.String)
		}
		manifest.Cohorts = append(manifest.Cohorts, CohortV2{Name: nameValue, CaseCount: int(cm["case_count"].Integer.Int64()), CaseIDs: ids, AggregateV1: aggValue})
	}
	namesValue := m["category_names"]
	if namesValue.Kind != ArrayKind {
		return ManifestV2{}, fmt.Errorf("manifest category_names must be array")
	}
	for _, name := range namesValue.Array {
		if name.Kind != StringKind {
			return ManifestV2{}, fmt.Errorf("manifest category_names must be strings")
		}
		manifest.CategoryNames = append(manifest.CategoryNames, name.String)
	}
	aggObj := m["category_aggregates"]
	if aggObj.Kind != ObjectKind {
		return ManifestV2{}, fmt.Errorf("manifest category_aggregates must be object")
	}
	manifest.CategoryAggregates = map[string]string{}
	for _, member := range aggObj.Object {
		if member.Value.Kind != StringKind {
			return ManifestV2{}, fmt.Errorf("category aggregate must be string")
		}
		manifest.CategoryAggregates[member.Key] = member.Value.String
	}
	digestsValue := m["case_digests"]
	if digestsValue.Kind != ArrayKind {
		return ManifestV2{}, fmt.Errorf("manifest case_digests must be array")
	}
	digestFields := map[string]bool{"id": true, "category": true, "sha256": true}
	for _, digestValue := range digestsValue.Array {
		if digestValue.Kind != ObjectKind {
			return ManifestV2{}, fmt.Errorf("case_digest must be object")
		}
		dm := objectToMap(digestValue)
		if len(dm) != len(digestFields) {
			return ManifestV2{}, fmt.Errorf("case_digest unknown field")
		}
		for key := range digestFields {
			if _, ok := dm[key]; !ok {
				return ManifestV2{}, fmt.Errorf("case_digest missing field %s", key)
			}
		}
		idValue, err := strFieldFromMap(dm, "id")
		if err != nil {
			return ManifestV2{}, err
		}
		categoryValue, err := strFieldFromMap(dm, "category")
		if err != nil {
			return ManifestV2{}, err
		}
		shaValue, err := strFieldFromMap(dm, "sha256")
		if err != nil {
			return ManifestV2{}, err
		}
		manifest.CaseDigests = append(manifest.CaseDigests, CaseDigestV2{ID: idValue, Category: categoryValue, SHA256: shaValue})
	}
	return manifest, nil
}

func strFieldFromMap(m map[string]Value, key string) (string, error) {
	v, ok := m[key]
	if !ok || v.Kind != StringKind {
		return "", fmt.Errorf("field %s must be string", key)
	}
	return v.String, nil
}

// BuildManifestV2 derives manifest_v2 from fixture and legacy objects.
func BuildManifestV2(fixtureObj, legacyObj map[string]any) (ManifestV2, error) {
	categoriesAny, ok := fixtureObj["categories"]
	if !ok {
		return ManifestV2{}, fmt.Errorf("fixture categories missing")
	}
	categories, ok := categoriesAny.(map[string]any)
	if !ok || len(categories) == 0 {
		return ManifestV2{}, fmt.Errorf("fixture categories must be object")
	}
	parentToIDs := map[string][]string{}
	idToParent := map[string]string{}
	allCases := []map[string]any{}
	var orderedCategories []string
	for parentName := range categories {
		orderedCategories = append(orderedCategories, parentName)
	}
	sort.Slice(orderedCategories, func(i, j int) bool {
		return bytes.Compare([]byte(orderedCategories[i]), []byte(orderedCategories[j])) < 0
	})
	for _, parentName := range orderedCategories {
		parentCasesAny, ok := categories[parentName]
		if !ok {
			return ManifestV2{}, fmt.Errorf("category missing %s", parentName)
		}
		parentCases, ok := parentCasesAny.([]any)
		if !ok {
			return ManifestV2{}, fmt.Errorf("category cases must be array %s", parentName)
		}
		ids := make([]string, 0, len(parentCases))
		for _, caseAny := range parentCases {
			caseObj, ok := caseAny.(map[string]any)
			if !ok {
				return ManifestV2{}, fmt.Errorf("case must be object")
			}
			idAny, ok := caseObj["id"]
			if !ok {
				return ManifestV2{}, fmt.Errorf("case missing id")
			}
			caseID, ok := idAny.(string)
			if !ok {
				return ManifestV2{}, fmt.Errorf("case id must be string")
			}
			if _, exists := idToParent[caseID]; exists {
				return ManifestV2{}, fmt.Errorf("case id in multiple categories %s", caseID)
			}
			idToParent[caseID] = parentName
			ids = append(ids, caseID)
			allCases = append(allCases, caseObj)
		}
		parentToIDs[parentName] = ids
	}
	if len(allCases) != manifestCaseCount {
		return ManifestV2{}, fmt.Errorf("case count mismatch")
	}
	allIDs := sortedStringKeys(idToParent)
	digests := map[string]string{}
	for _, caseObj := range allCases {
		raw, err := json.Marshal(caseObj)
		if err != nil {
			return ManifestV2{}, err
		}
		value, err := StrictDecodeV2(raw, DefaultEvidenceLimitsV2())
		if err != nil {
			return ManifestV2{}, err
		}
		result, err := CanonicalCaseV2(value)
		if err != nil {
			return ManifestV2{}, err
		}
		digests[caseObj["id"].(string)] = result.SHA256
	}
	// Parent category is authoritative; case.category must match.
	for parentName, ids := range parentToIDs {
		for _, caseID := range ids {
			categoryAny, ok := fixtureObj["categories"].(map[string]any)[parentName].([]any)
			if !ok {
				return ManifestV2{}, fmt.Errorf("category cases missing")
			}
			for _, caseAny := range categoryAny {
				caseObj := caseAny.(map[string]any)
				if caseObj["id"] == caseID {
					if caseObj["category"] != parentName {
						return ManifestV2{}, fmt.Errorf("case category mismatch %s", caseID)
					}
				}
			}
		}
	}
	legacyAny, ok := legacyObj["cohorts"]
	if !ok {
		return ManifestV2{}, fmt.Errorf("legacy cohorts missing")
	}
	legacyCohortsAny, ok := legacyAny.([]any)
	if !ok {
		return ManifestV2{}, fmt.Errorf("legacy cohorts must be array")
	}
	legacyCohorts := map[string]map[string]any{}
	for _, cohortAny := range legacyCohortsAny {
		cohort := cohortAny.(map[string]any)
		legacyCohorts[cohort["name"].(string)] = cohort
	}
	if len(legacyCohorts) != 3 {
		return ManifestV2{}, fmt.Errorf("legacy cohort names mismatch")
	}
	B := setOfStrings(legacyCohorts["base104"]["case_ids"].([]any))
	C := setOfStrings(legacyCohorts["amendment21"]["case_ids"].([]any))
	A := setOfStringsFromStrings(allIDs)
	if len(B) != 104 || len(C) != 21 || intersects(B, C) || !equalSet(B, C, A) {
		return ManifestV2{}, fmt.Errorf("legacy cohort relation mismatch")
	}
	cohorts := make([]CohortV2, 0, 3)
	for _, name := range []string{"all125", "amendment21", "base104"} {
		legacy := legacyCohorts[name]
		ids := sortedStringSlice(stringsOfAny(legacy["case_ids"].([]any)))
		if len(ids) != len(uniqueStrings(ids)) {
			return ManifestV2{}, fmt.Errorf("cohort duplicate id %s", name)
		}
		aggregate, err := aggregateV1ForIDs(digests, ids)
		if err != nil {
			return ManifestV2{}, err
		}
		if aggregate != legacy["aggregate_v1"] {
			return ManifestV2{}, fmt.Errorf("cohort aggregate mismatch %s", name)
		}
		cohorts = append(cohorts, CohortV2{Name: name, CaseCount: len(ids), CaseIDs: ids, AggregateV1: aggregate})
	}
	categoryNames := sortedCategoryKeys(parentToIDs)
	categoryAggregates := map[string]string{}
	for _, name := range categoryNames {
		records, err := digestRecords(digests, parentToIDs[name])
		if err != nil {
			return ManifestV2{}, err
		}
		aggregate, err := CategoryAggregateV1(name, records)
		if err != nil {
			return ManifestV2{}, err
		}
		categoryAggregates[name] = aggregate
	}
	wholeRecords, err := digestRecords(digests, allIDs)
	if err != nil {
		return ManifestV2{}, err
	}
	whole, err := AggregateV1(wholeRecords, "OSEC-CASE-AGGREGATE-V1")
	if err != nil {
		return ManifestV2{}, err
	}
	caseDigests := make([]CaseDigestV2, 0, len(allIDs))
	for _, caseID := range allIDs {
		caseDigests = append(caseDigests, CaseDigestV2{ID: caseID, Category: idToParent[caseID], SHA256: digests[caseID]})
	}
	return ManifestV2{
		ManifestVersion: manifestVersionV2, Profile: manifestProfileV2,
		StrictDecodeVersion: manifestStrictDecodeV2, EvidenceLimitsVersion: manifestLimitsV2,
		CanonicalJSONVersion: manifestCanonicalJSONV2, CanonicalCaseVersion: manifestCanonicalCaseV2,
		AggregateAlgorithm: manifestAggregateV1, CategoryAggregateAlgorithm: manifestCategoryAggV1,
		DigestAlgorithm: manifestDigestAlgorithm, Dataset: manifestDataset, CaseCount: len(allIDs),
		Cohorts: cohorts, CategoryNames: categoryNames, WholeSetAggregateV1: whole,
		CategoryAggregates: categoryAggregates, CaseDigests: caseDigests,
	}, nil
}

func aggregateV1ForIDs(digests map[string]string, ids []string) (string, error) {
	records, err := digestRecords(digests, ids)
	if err != nil {
		return "", err
	}
	return AggregateV1(records, "OSEC-CASE-AGGREGATE-V1")
}

func digestRecords(digests map[string]string, ids []string) ([]CaseDigest, error) {
	out := make([]CaseDigest, 0, len(ids))
	for _, id := range ids {
		raw, err := hex.DecodeString(digests[id])
		if err != nil {
			return nil, err
		}
		out = append(out, CaseDigest{ID: id, Digest: raw})
	}
	return out, nil
}

func sortedStringKeys(m map[string]string) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Slice(out, func(i, j int) bool { return bytes.Compare([]byte(out[i]), []byte(out[j])) < 0 })
	return out
}

func sortedCategoryKeys(m map[string][]string) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Slice(out, func(i, j int) bool { return bytes.Compare([]byte(out[i]), []byte(out[j])) < 0 })
	return out
}

func sortedStringSlice(in []string) []string {
	out := append([]string(nil), in...)
	sort.Slice(out, func(i, j int) bool { return bytes.Compare([]byte(out[i]), []byte(out[j])) < 0 })
	return out
}

func setOfStringsFromStrings(in []string) map[string]bool {
	out := map[string]bool{}
	for _, v := range in {
		out[v] = true
	}
	return out
}

func setOfStrings(in []any) map[string]bool {
	out := map[string]bool{}
	for _, v := range in {
		out[v.(string)] = true
	}
	return out
}

func stringsOfAny(in []any) []string {
	out := make([]string, 0, len(in))
	for _, v := range in {
		out = append(out, v.(string))
	}
	return out
}

func intersects(a, b map[string]bool) bool {
	for k := range a {
		if b[k] {
			return true
		}
	}
	return false
}

func equalSet(a, b, union map[string]bool) bool {
	return len(a)+len(b) == len(union) && !intersects(a, b)
}

func bigIntFromInt(value int) *big.Int {
	return big.NewInt(int64(value))
}
