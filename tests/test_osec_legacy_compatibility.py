"""A0.3b V2 125-case compatibility gate.

All 125 cases are executed uniformly through CanonicalCaseV2. V1 canonical_case
is used only to preserve the historical p-004/ver-003 mismatch assertion.
"""

from __future__ import annotations

import copy
import hashlib
import os

import pytest

from crawler.security.osec_evidence import (
    CaseDigest,
    OSECError,
    aggregate_v1,
    canonical_case,
    strict_decode,
    validate_case_dataset,
)
from crawler.security.osec_evidence_v2 import (
    canonical_case_v2,
    strict_decode_v2,
)

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "outbound_security_config_contract.json")
LEGACY_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "outbound_security_config_legacy_digests.json")
FIXTURE_SHA = "8D8B12F5F030DEA6FACE5E2B25795F667657873BD4DD89A178659E0DAABDCB45"
LEGACY_SHA = "37A6EA15C1E7E7D80089AE0872992E2B405125EDD68C272739C2C09EF5001E81"
CANDIDATE_COMMIT = "591f1e3e0d60d8946d617e9fc2b25e589ce4e0ca"
LEGACY_COMMIT = "a0bd91f03aef881713b4d78b3eef895c77ea005f"
FROZEN_AGGREGATES = {
    "all125": "75336a374cd9ee82a8c811f380fd9ce6893364d65eaf0fbed76424307b2baa5b",
    "base104": "bc38711ddf559eb5319eac9b080eeec611e3742d9cf0bbdb09072317cfc975b8",
    "amendment21": "dfda4174b62f27b4132cf157e96b89be2982f9268724dc12f47ebc97c7df8850",
}
KNOWN_ACTIONS = {"structure", "aggregate_recompute", "frozen_aggregates"}


def _read_normalized(path):
    raw = open(path, "rb").read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise AssertionError("BOM")
    if b"\r" in raw.replace(b"\r\n", b""):
        raise AssertionError("lone CR")
    normalized = raw.replace(b"\r\n", b"\n")
    return raw, normalized, hashlib.sha256(normalized).hexdigest().upper()


def _load_authoritative_inputs():
    fixture_raw, fixture_norm, fixture_sha = _read_normalized(FIXTURE_PATH)
    legacy_raw, legacy_norm, legacy_sha = _read_normalized(LEGACY_PATH)
    if fixture_sha != FIXTURE_SHA or legacy_sha != LEGACY_SHA:
        raise AssertionError("fixture or legacy SHA mismatch")
    fixture_obj = strict_decode_v2(fixture_raw)
    legacy_obj = strict_decode_v2(legacy_raw)
    return fixture_obj, legacy_obj


def _enumerate_cases(fixture_obj):
    return [case for cases in fixture_obj["categories"].values() for case in cases]


def _execute_candidate_cases(fixture_obj, skip_ids=None):
    all_cases = _enumerate_cases(fixture_obj)
    validate_case_dataset(all_cases)
    skip_ids = skip_ids or set()
    results = []
    seen = set()
    for case in all_cases:
        case_id = case["id"]
        if case_id in seen:
            raise AssertionError("duplicate candidate id " + case_id)
        seen.add(case_id)
        if case_id in skip_ids:
            continue
        result = canonical_case_v2(case)
        results.append((case_id, result.sha256))
    return results


def _flip_first_hex(value):
    return ("0" if value[0] != "0" else "1") + value[1:]


def _aggregate_for_cohort(candidate_digests, cohort_ids):
    items = [CaseDigest(case_id, bytes.fromhex(candidate_digests[case_id])) for case_id in cohort_ids]
    return aggregate_v1(items)


def _validate_compatibility(results, fixture_obj, legacy_obj, peer=None):
    actual_map = {}
    actual_ids = []
    duplicate = []
    for case_id, digest in results:
        if case_id in actual_map:
            duplicate.append(case_id)
        actual_map[case_id] = digest
        actual_ids.append(case_id)
    if duplicate:
        raise AssertionError("duplicate candidate ids " + ",".join(duplicate))

    legacy_digests = {item["id"]: item["sha256"] for item in legacy_obj["case_digests"]}
    expected_ids = set(legacy_digests)
    actual_set = set(actual_ids)
    missing = sorted(expected_ids - actual_set)
    extra = sorted(actual_set - expected_ids)
    mismatch = sorted(case_id for case_id in expected_ids & actual_set if actual_map[case_id] != legacy_digests[case_id])
    if len(actual_ids) != 125 or len(expected_ids) != 125:
        raise AssertionError("case counts expected=%d executed=%d" % (len(expected_ids), len(actual_ids)))
    if missing or extra or mismatch:
        raise AssertionError("digest mismatch missing=%s extra=%s mismatch=%s" % (missing, extra, mismatch))

    legacy_actions = set(legacy_obj.get("validation_actions", sorted(KNOWN_ACTIONS)))
    if legacy_actions != KNOWN_ACTIONS:
        raise AssertionError("unknown validation action")

    legacy_cohorts = {cohort["name"]: cohort for cohort in legacy_obj["cohorts"]}
    if set(legacy_cohorts) != {"all125", "base104", "amendment21"}:
        raise AssertionError("cohort names mismatch")
    cohort_mismatches = []
    all_ids_sorted = sorted(actual_ids)
    if list(legacy_cohorts["all125"]["case_ids"]) != all_ids_sorted:
        cohort_mismatches.append("all125")
    if list(legacy_cohorts["base104"]["case_ids"]) != sorted(fixture_obj["baseline_case_ids"]):
        cohort_mismatches.append("base104")
    base_set = set(fixture_obj["baseline_case_ids"])
    amendment_set = actual_set - base_set
    if list(legacy_cohorts["amendment21"]["case_ids"]) != sorted(amendment_set):
        cohort_mismatches.append("amendment21")
    if base_set & amendment_set:
        cohort_mismatches.append("overlap")
    if base_set | amendment_set != actual_set:
        cohort_mismatches.append("union")
    if cohort_mismatches:
        raise AssertionError("cohort mismatch " + ",".join(sorted(cohort_mismatches)))

    fixture_expected = {
        "all125": fixture_obj["expected_all125_v1"],
        "base104": fixture_obj["expected_base104_v1"],
        "amendment21": fixture_obj["expected_new21_v1"],
    }
    candidate_aggregates = {}
    aggregate_mismatches = []
    for name, cohort in legacy_cohorts.items():
        candidate_aggregates[name] = _aggregate_for_cohort(actual_map, cohort["case_ids"])
        if candidate_aggregates[name] != cohort["aggregate_v1"]:
            aggregate_mismatches.append(name + ":legacy")
        if candidate_aggregates[name] != fixture_expected[name]:
            aggregate_mismatches.append(name + ":fixture")
        if candidate_aggregates[name] != FROZEN_AGGREGATES[name]:
            aggregate_mismatches.append(name + ":frozen")
    if peer is not None:
        for name, cohort in legacy_cohorts.items():
            if candidate_aggregates[name] != peer["aggregates"][name]:
                aggregate_mismatches.append(name + ":peer")
        for case_id in sorted(actual_map):
            if actual_map[case_id] != peer["digests"][case_id]:
                raise AssertionError("peer digest mismatch " + case_id)
    if aggregate_mismatches:
        raise AssertionError("aggregate mismatch " + ",".join(sorted(aggregate_mismatches)))

    return {
        "expected_ids": sorted(expected_ids),
        "executed_ids": sorted(actual_ids),
        "missing_ids": missing,
        "extra_ids": extra,
        "duplicate_ids": duplicate,
        "digest_mismatches": mismatch,
        "cohort_mismatches": cohort_mismatches,
        "aggregate_mismatches": aggregate_mismatches,
        "candidate_digests": actual_map,
        "candidate_aggregates": candidate_aggregates,
        "result": "MATCH",
    }


def _build_peer(results):
    legacy_obj, fixture_obj = None, None
    # Peer is only used for consistency checks; values come from the base run.
    peer_fixture, peer_legacy = _load_authoritative_inputs()
    metrics = _validate_compatibility(results, peer_fixture, peer_legacy)
    return {"digests": dict(metrics["candidate_digests"]), "aggregates": dict(metrics["candidate_aggregates"])}


def test_osec_canonical_v2_matches_legacy_125_cases():
    fixture_obj, legacy_obj = _load_authoritative_inputs()
    results = _execute_candidate_cases(fixture_obj)
    metrics = _validate_compatibility(results, fixture_obj, legacy_obj)
    assert metrics["result"] == "MATCH"
    assert metrics["expected_ids"] == metrics["executed_ids"]
    assert len(metrics["executed_ids"]) == 125
    assert metrics["missing_ids"] == []
    assert metrics["extra_ids"] == []
    assert metrics["duplicate_ids"] == []
    assert metrics["digest_mismatches"] == []
    assert metrics["cohort_mismatches"] == []
    assert metrics["aggregate_mismatches"] == []
    assert metrics["candidate_aggregates"] == FROZEN_AGGREGATES
    assert metrics["candidate_digests"]["p-004"] == "4ed0c899258ba53fe64eaf92b2b243281f9dbd0cfe8fae4b5c6ba76bcc38fd50"
    assert metrics["candidate_digests"]["ver-003"] == "5ff23879522951099e3d6d44f8f74884905f23e29ebb64b17ed63efea5066806"


def test_osec_canonical_v2_compatibility_gate_rejects_mutations():
    fixture_obj, legacy_obj = _load_authoritative_inputs()
    base_results = _execute_candidate_cases(fixture_obj)
    base_peer = _build_peer(base_results)

    def expect_reject(name=None, mutate_results=None, mutate_fixture=None, mutate_legacy=None, mutate_peer=None, skip_ids=None):
        results = copy.deepcopy(base_results)
        fixture = copy.deepcopy(fixture_obj)
        legacy = copy.deepcopy(legacy_obj)
        peer = copy.deepcopy(base_peer)
        if mutate_results:
            mutate_results(results)
        if mutate_fixture:
            mutate_fixture(fixture)
        if mutate_legacy:
            mutate_legacy(legacy)
        if mutate_peer:
            mutate_peer(peer)
        if mutate_fixture or skip_ids is not None:
            results = _execute_candidate_cases(fixture, skip_ids=skip_ids)
        with pytest.raises((AssertionError, OSECError)):
            _validate_compatibility(results, fixture, legacy, peer=peer)

    expect_reject("missing_case", mutate_results=lambda r: r.pop())
    expect_reject("extra_case", mutate_results=lambda r: r.append(("unknown-extra", "0" * 64)))
    expect_reject("duplicate_case", mutate_results=lambda r: r.append(copy.deepcopy(r[0])))
    expect_reject("dispatcher_omits_case", skip_ids={base_results[0][0]});
    expect_reject("candidate_digest_flip", mutate_results=lambda r: r.__setitem__(0, (r[0][0], _flip_first_hex(r[0][1]))))
    expect_reject(
        "legacy_digest_flip",
        mutate_legacy=lambda l: l["case_digests"][0].__setitem__("sha256", _flip_first_hex(l["case_digests"][0]["sha256"])),
    )

    def find_case(fixture, case_id):
        for cases in fixture["categories"].values():
            for case in cases:
                if case["id"] == case_id:
                    return case
        raise AssertionError("missing " + case_id)

    def mutate_numeric(fixture, case_id, key, new_value):
        case = find_case(fixture, case_id)
        case[key] = new_value

    expect_reject("p004_numeric_normalization", mutate_fixture=lambda f: mutate_numeric(f, "p-004", "ports", {"https": [443]}))
    expect_reject("ver003_numeric_normalization", mutate_fixture=lambda f: mutate_numeric(f, "ver-003", "value", 1))
    def mutate_ordinary(f):
        case = find_case(f, "d-001")
        case["description"] = case.get("description", "") + " MUTATED"

    expect_reject("ordinary_case_mutation", mutate_fixture=mutate_ordinary);
    expect_reject("base104_missing_id", mutate_fixture=lambda f: f["baseline_case_ids"].pop())
    amendment_id = next(c["id"] for c in _enumerate_cases(fixture_obj) if c["id"] not in set(fixture_obj["baseline_case_ids"]))
    expect_reject("base104_add_amendment_id", mutate_fixture=lambda f: f["baseline_case_ids"].append(amendment_id))
    expect_reject("amendment21_missing_id", mutate_legacy=lambda l: l["cohorts"][2]["case_ids"].pop())
    base_first = fixture_obj["baseline_case_ids"][0]
    expect_reject("amendment21_extra_id", mutate_legacy=lambda l: l["cohorts"][2]["case_ids"].append(base_first))
    expect_reject("cohort_overlap", mutate_legacy=lambda l: l["cohorts"][2]["case_ids"].append(base_first))
    expect_reject("cohort_union_mismatch", mutate_legacy=lambda l: l["cohorts"][0]["case_ids"].pop())
    expect_reject("cohort_order_mismatch", mutate_legacy=lambda l: l["cohorts"][0].__setitem__("case_ids", list(reversed(l["cohorts"][0]["case_ids"]))))
    expect_reject("cohort_name_mismatch", mutate_legacy=lambda l: l["cohorts"][2].__setitem__("name", "amendment22"))
    for cohort_index in range(3):
        expect_reject(
            "aggregate_digest_flip_" + str(cohort_index),
            mutate_legacy=lambda l, idx=cohort_index: l["cohorts"][idx].__setitem__("aggregate_v1", _flip_first_hex(l["cohorts"][idx]["aggregate_v1"])),
        )
    expect_reject("aggregate_omits_record", mutate_peer=lambda p: p["aggregates"].__setitem__("all125", "0" * 64))
    expect_reject(
        "unknown_validation_action",
        mutate_legacy=lambda l: l.__setitem__("validation_actions", ["structure", "aggregate_recompute", "unknown_action"]),
    )
    expect_reject("expected_executed_set_mismatch", mutate_legacy=lambda l: l["case_digests"].pop())
    expect_reject("peer_candidate_digest_mismatch", mutate_peer=lambda p: p["digests"].__setitem__(base_results[0][0], _flip_first_hex(base_results[0][1])))
    expect_reject("peer_candidate_aggregate_mismatch", mutate_peer=lambda p: p["aggregates"].__setitem__("base104", _flip_first_hex(p["aggregates"]["base104"])))


def test_osec_v1_mismatch_history_is_preserved():
    fixture_raw, _normalized, _sha = _read_normalized(FIXTURE_PATH)
    v1_fixture = strict_decode(fixture_raw)
    _, legacy_obj = _load_authoritative_inputs()
    legacy_digests = {item["id"]: item["sha256"] for item in legacy_obj["case_digests"]}
    v1_cases = {case["id"]: case for cases in v1_fixture["categories"].values() for case in cases}
    for case_id in ("p-004", "ver-003"):
        v1_value = v1_cases[case_id]
        with pytest.raises(OSECError) as exc:
            canonical_case(v1_value)
        assert exc.value.code == "canonical_non_integer_number"
        v2_result = canonical_case_v2(v1_value)
        assert v2_result.sha256 == legacy_digests[case_id]