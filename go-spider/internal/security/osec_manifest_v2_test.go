package security

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const (
	manifestContractSHA = "8D8B12F5F030DEA6FACE5E2B25795F667657873BD4DD89A178659E0DAABDCB45"
	manifestLegacySHA   = "37A6EA15C1E7E7D80089AE0872992E2B405125EDD68C272739C2C09EF5001E81"
	manifestALL125      = "75336a374cd9ee82a8c811f380fd9ce6893364d65eaf0fbed76424307b2baa5b"
	manifestBASE104     = "bc38711ddf559eb5319eac9b080eeec611e3742d9cf0bbdb09072317cfc975b8"
	manifestAMENDMENT21 = "dfda4174b62f27b4132cf157e96b89be2982f9268724dc12f47ebc97c7df8850"
	manifestFixtureHash = "01535055051b6e2d4ef7c25aa2ea6c84b26cd01917d35c9f4c3251c5f3828069"
)

func manifestSHA256(data []byte) string {
	sum := sha256.Sum256(data)
	return strings.ToUpper(hex.EncodeToString(sum[:]))
}

func loadManifestInputs(t *testing.T) (map[string]any, map[string]any, []byte) {
	t.Helper()
	root := filepath.Join("..", "..", "..", "tests", "fixtures")
	contractRaw, err := os.ReadFile(filepath.Join(root, "outbound_security_config_contract.json"))
	if err != nil {
		t.Fatalf("read contract: %v", err)
	}
	legacyRaw, err := os.ReadFile(filepath.Join(root, "outbound_security_config_legacy_digests.json"))
	if err != nil {
		t.Fatalf("read legacy: %v", err)
	}
	manifestRaw, err := os.ReadFile(filepath.Join(root, "outbound_security_config_manifest_v2.json"))
	if err != nil {
		t.Fatalf("read manifest: %v", err)
	}
	if manifestSHA256(bytes.ReplaceAll(contractRaw, []byte("\r\n"), []byte("\n"))) != manifestContractSHA {
		t.Fatalf("contract SHA mismatch")
	}
	if manifestSHA256(bytes.ReplaceAll(legacyRaw, []byte("\r\n"), []byte("\n"))) != manifestLegacySHA {
		t.Fatalf("legacy SHA mismatch")
	}
	if dup, err := v2rtFindDuplicate(json.NewDecoder(bytes.NewReader(contractRaw))); err != nil || dup != "" {
		t.Fatalf("contract duplicate %q %v", dup, err)
	}
	if dup, err := v2rtFindDuplicate(json.NewDecoder(bytes.NewReader(legacyRaw))); err != nil || dup != "" {
		t.Fatalf("legacy duplicate %q %v", dup, err)
	}
	contract := map[string]any{}
	legacy := map[string]any{}
	if err := decodeJSONNumber(contractRaw, &contract); err != nil {
		t.Fatalf("contract decode: %v", err)
	}
	if err := decodeJSONNumber(legacyRaw, &legacy); err != nil {
		t.Fatalf("legacy decode: %v", err)
	}
	return contract, legacy, manifestRaw
}

func decodeJSONNumber(raw []byte, out any) error {
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	return dec.Decode(out)
}

func TestOSECManifestV2GenerateAndValidate(t *testing.T) {
	contract, legacy, manifestRaw := loadManifestInputs(t)
	manifest, err := BuildManifestV2(contract, legacy)
	if err != nil {
		t.Fatalf("BuildManifestV2: %v", err)
	}
	if err := ValidateManifestV2(manifest, contract, legacy); err != nil {
		t.Fatalf("ValidateManifestV2: %v", err)
	}
	if manifest.CaseCount != 125 || len(manifest.CaseDigests) != 125 {
		t.Fatalf("case count mismatch")
	}
	if len(manifest.CategoryNames) != 12 || len(manifest.CategoryAggregates) != 12 {
		t.Fatalf("category count mismatch")
	}
	byName := map[string]CohortV2{}
	for _, c := range manifest.Cohorts {
		byName[c.Name] = c
	}
	if byName["all125"].AggregateV1 != manifestALL125 || byName["base104"].AggregateV1 != manifestBASE104 || byName["amendment21"].AggregateV1 != manifestAMENDMENT21 {
		t.Fatalf("cohort aggregate mismatch")
	}
	if manifest.WholeSetAggregateV1 != manifestALL125 {
		t.Fatalf("whole set aggregate mismatch")
	}
	envelope, err := BuildEnvelopeV2(manifest)
	if err != nil {
		t.Fatalf("BuildEnvelopeV2: %v", err)
	}
	if envelope.ManifestHashV2 != manifestFixtureHash {
		t.Fatalf("manifest hash mismatch got=%s want=%s", envelope.ManifestHashV2, manifestFixtureHash)
	}
	gotBytes, err := EnvelopeToBytes(envelope)
	if err != nil {
		t.Fatalf("EnvelopeToBytes: %v", err)
	}
	if !bytes.Equal(gotBytes, manifestRaw) {
		t.Fatalf("envelope bytes differ from fixture")
	}
	if _, err := DecodeEnvelopeV2(manifestRaw, contract, legacy); err != nil {
		t.Fatalf("DecodeEnvelopeV2: %v", err)
	}
	if manifest.Cohorts[0].Name != "all125" || manifest.Cohorts[1].Name != "amendment21" || manifest.Cohorts[2].Name != "base104" {
		t.Fatalf("cohort order mismatch")
	}
	digests := map[string]string{}
	for _, d := range manifest.CaseDigests {
		digests[d.ID] = d.SHA256
	}
	if digests["p-004"] != "4ed0c899258ba53fe64eaf92b2b243281f9dbd0cfe8fae4b5c6ba76bcc38fd50" {
		t.Fatalf("p-004 digest mismatch")
	}
	if digests["ver-003"] != "5ff23879522951099e3d6d44f8f74884905f23e29ebb64b17ed63efea5066806" {
		t.Fatalf("ver-003 digest mismatch")
	}
}

func TestOSECManifestV2Negative(t *testing.T) {
	contract, legacy, manifestRaw := loadManifestInputs(t)
	manifest, err := BuildManifestV2(contract, legacy)
	if err != nil {
		t.Fatalf("BuildManifestV2: %v", err)
	}
	envelope, err := BuildEnvelopeV2(manifest)
	if err != nil {
		t.Fatalf("BuildEnvelopeV2: %v", err)
	}
	expect := func(name string, mutate func(m *ManifestV2, e *ManifestEnvelopeV2) error) {
		t.Helper()
		mm := manifest
		ee := envelope
		if err := mutate(&mm, &ee); err == nil {
			t.Fatalf("negative %s: expected error", name)
		}
	}
	expect("case_digest_missing", func(m *ManifestV2, e *ManifestEnvelopeV2) error {
		m.CaseDigests = m.CaseDigests[:124]
		return ValidateManifestV2(*m, contract, legacy)
	})
	expect("cohort_order", func(m *ManifestV2, e *ManifestEnvelopeV2) error {
		m.Cohorts[1], m.Cohorts[2] = m.Cohorts[2], m.Cohorts[1]
		return ValidateManifestV2(*m, contract, legacy)
	})
	expect("digest_flip", func(m *ManifestV2, e *ManifestEnvelopeV2) error {
		m.CaseDigests[0].SHA256 = flipHex(m.CaseDigests[0].SHA256)
		return ValidateManifestV2(*m, contract, legacy)
	})
	expect("unknown_field", func(m *ManifestV2, e *ManifestEnvelopeV2) error {
		raw, err := EnvelopeToBytes(*e)
		if err != nil {
			return err
		}
		raw = bytes.Replace(raw, []byte(`"manifest_hash_v2"`), []byte(`"extra":true,"manifest_hash_v2"`), 1)
		_, err = DecodeEnvelopeV2(raw, contract, legacy)
		return err
	})
	_ = manifestRaw
}
