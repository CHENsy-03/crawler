"""Manifest V2 generation, validation, and envelope serialization."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from crawler.security.osec_evidence import (
    CaseDigest,
    aggregate_v1,
    category_aggregate_v1,
)
from crawler.security.osec_evidence_v2 import (
    CanonicalCaseResult,
    canonical_case_v2,
    canonical_json_v2,
    strict_decode_v2,
)

MANIFEST_VERSION = "OSEC-CASE-MANIFEST-V2"
PROFILE = "OSEC-EVIDENCE-PROFILE-V2"
STRICT_DECODE_VERSION = "OSEC-STRICT-JSON-DECODE-V1"
EVIDENCE_LIMITS_VERSION = "OSEC-EVIDENCE-LIMITS-V2"
CANONICAL_JSON_VERSION = "OSEC-CANONICAL-JSON-V2"
CANONICAL_CASE_VERSION = "OSEC-CANONICAL-CASE-V2"
AGGREGATE_ALGORITHM = "OSEC-CASE-AGGREGATE-V1"
CATEGORY_AGGREGATE_ALGORITHM = "OSEC-CASE-CATEGORY-AGGREGATE-V1"
DIGEST_ALGORITHM = "SHA-256"
DATASET = "outbound_security_config"
MANIFEST_HASH_MAGIC = b"OSEC-CASE-MANIFEST-HASH-V2\x00"

DATASET_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
COHORT_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

MANIFEST_FIELDS = (
    "manifest_version",
    "profile",
    "strict_decode_version",
    "evidence_limits_version",
    "canonical_json_version",
    "canonical_case_version",
    "aggregate_algorithm",
    "category_aggregate_algorithm",
    "digest_algorithm",
    "dataset",
    "case_count",
    "cohorts",
    "category_names",
    "whole_set_aggregate_v1",
    "category_aggregates",
    "case_digests",
)
COHORT_FIELDS = ("name", "case_count", "case_ids", "aggregate_v1")
CASE_DIGEST_FIELDS = ("id", "category", "sha256")
ENVELOPE_FIELDS = ("manifest_v2", "manifest_hash_v2")


@dataclass(frozen=True)
class CohortV2:
    name: str
    case_count: int
    case_ids: list[str]
    aggregate_v1: str


@dataclass(frozen=True)
class CaseDigestV2:
    id: str
    category: str
    sha256: str


def _strict_load_object(raw: bytes) -> dict[str, Any]:
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key: " + key)
            result[key] = value
        return result

    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("BOM")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)


def _case_id(case: Any) -> str:
    if not isinstance(case, dict) or not isinstance(case.get("id"), str):
        raise ValueError("case id must be a string")
    return case["id"]


def _check_exact_fields(obj: Any, allowed: tuple[str, ...], where: str) -> None:
    if not isinstance(obj, dict):
        raise ValueError(where + ": expected object")
    unknown = sorted(set(obj) - set(allowed))
    missing = sorted(set(allowed) - set(obj))
    if unknown:
        raise ValueError(where + ": unknown field " + ",".join(unknown))
    if missing:
        raise ValueError(where + ": missing field " + ",".join(missing))


def _check_name_order(names: list[str], where: str) -> None:
    if names != sorted(names, key=lambda name: name.encode("utf-8")):
        raise ValueError(where + ": not UTF-8 byte ascending")


def _digest_records(cases: list[Any]) -> dict[str, CanonicalCaseResult]:
    seen = set()
    result = {}
    for case in cases:
        case_id = _case_id(case)
        if case_id in seen:
            raise ValueError("duplicate case id " + case_id)
        seen.add(case_id)
        result[case_id] = canonical_case_v2(case)
    return result


def build_manifest_v2(fixture_obj: Any, legacy_obj: Any) -> dict[str, Any]:
    if not isinstance(fixture_obj, dict) or not isinstance(legacy_obj, dict):
        raise ValueError("fixture or legacy must be objects")
    categories = fixture_obj.get("categories")
    if not isinstance(categories, dict) or not categories:
        raise ValueError("fixture categories must be a non-empty object")

    parent_to_ids: dict[str, list[str]] = {}
    parent_to_cases: dict[str, list[Any]] = {}
    all_cases: list[Any] = []
    id_to_parent: dict[str, str] = {}
    for parent_name, parent_cases in categories.items():
        if not isinstance(parent_name, str):
            raise ValueError("category name must be a string")
        if not isinstance(parent_cases, list):
            raise ValueError("category " + parent_name + ": cases must be a list")
        parent_to_ids[parent_name] = []
        parent_to_cases[parent_name] = list(parent_cases)
        for case in parent_cases:
            case_id = _case_id(case)
            if case_id in id_to_parent:
                raise ValueError("case id appears in multiple categories: " + case_id)
            id_to_parent[case_id] = parent_name
            parent_to_ids[parent_name].append(case_id)
            all_cases.append(case)

    all_ids = sorted(id_to_parent)
    if len(all_ids) != 125:
        raise ValueError("case count must be 125")

    digest_results = _digest_records(all_cases)
    candidate_digests = {case_id: digest_results[case_id].sha256 for case_id in all_ids}

    for parent_name, parent_cases in parent_to_cases.items():
        for case in parent_cases:
            case_id = _case_id(case)
            if case.get("category") != parent_name:
                raise ValueError("case category mismatch: " + case_id)

    legacy_cohorts = {cohort["name"]: cohort for cohort in legacy_obj.get("cohorts", [])}
    if set(legacy_cohorts) != {"all125", "base104", "amendment21"}:
        raise ValueError("legacy cohort names mismatch")
    A = set(all_ids)
    B = set(legacy_cohorts["base104"]["case_ids"])
    C = set(legacy_cohorts["amendment21"]["case_ids"])
    if len(B) != 104 or len(C) != 21 or B & C or (B | C) != A:
        raise ValueError("legacy cohort relation mismatch")

    cohorts = []
    for name in ("all125", "amendment21", "base104"):
        cohort = legacy_cohorts[name]
        case_ids = sorted(cohort["case_ids"])
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("cohort duplicate id " + name)
        aggregate = aggregate_v1([CaseDigest(cid, bytes.fromhex(candidate_digests[cid])) for cid in case_ids])
        if aggregate != cohort["aggregate_v1"]:
            raise ValueError("cohort aggregate mismatch " + name)
        cohorts.append(
            {
                "name": name,
                "case_count": len(case_ids),
                "case_ids": case_ids,
                "aggregate_v1": aggregate,
            }
        )

    category_names = sorted(categories)
    category_aggregates = {}
    for category_name in category_names:
        records = [CaseDigest(cid, bytes.fromhex(candidate_digests[cid])) for cid in parent_to_ids[category_name]]
        category_aggregates[category_name] = category_aggregate_v1(category_name, records)

    whole = aggregate_v1([CaseDigest(cid, bytes.fromhex(candidate_digests[cid])) for cid in all_ids])

    case_digests = [
        {
            "id": case_id,
            "category": id_to_parent[case_id],
            "sha256": candidate_digests[case_id],
        }
        for case_id in all_ids
    ]

    return {
        "manifest_version": MANIFEST_VERSION,
        "profile": PROFILE,
        "strict_decode_version": STRICT_DECODE_VERSION,
        "evidence_limits_version": EVIDENCE_LIMITS_VERSION,
        "canonical_json_version": CANONICAL_JSON_VERSION,
        "canonical_case_version": CANONICAL_CASE_VERSION,
        "aggregate_algorithm": AGGREGATE_ALGORITHM,
        "category_aggregate_algorithm": CATEGORY_AGGREGATE_ALGORITHM,
        "digest_algorithm": DIGEST_ALGORITHM,
        "dataset": DATASET,
        "case_count": len(all_ids),
        "cohorts": cohorts,
        "category_names": category_names,
        "whole_set_aggregate_v1": whole,
        "category_aggregates": category_aggregates,
        "case_digests": case_digests,
    }


def validate_manifest_v2(manifest: Any, fixture_obj: Any, legacy_obj: Any) -> None:
    categories = fixture_obj.get("categories")
    if not isinstance(categories, dict) or not categories:
        raise ValueError("fixture categories must be a non-empty object")
    _check_exact_fields(manifest, MANIFEST_FIELDS, "manifest_v2")
    for field, expected in (
        ("manifest_version", MANIFEST_VERSION),
        ("profile", PROFILE),
        ("strict_decode_version", STRICT_DECODE_VERSION),
        ("evidence_limits_version", EVIDENCE_LIMITS_VERSION),
        ("canonical_json_version", CANONICAL_JSON_VERSION),
        ("canonical_case_version", CANONICAL_CASE_VERSION),
        ("aggregate_algorithm", AGGREGATE_ALGORITHM),
        ("category_aggregate_algorithm", CATEGORY_AGGREGATE_ALGORITHM),
        ("digest_algorithm", DIGEST_ALGORITHM),
    ):
        if manifest[field] != expected:
            raise ValueError(field + " mismatch")

    dataset = manifest["dataset"]
    if not isinstance(dataset, str) or not DATASET_RE.match(dataset):
        raise ValueError("invalid dataset")
    if not isinstance(manifest["case_count"], int) or manifest["case_count"] != 125:
        raise ValueError("case_count mismatch")

    generated = build_manifest_v2(fixture_obj, legacy_obj)
    if manifest != generated:
        raise ValueError("manifest differs from regenerated manifest")

    cohorts = manifest["cohorts"]
    if not isinstance(cohorts, list) or len(cohorts) != 3:
        raise ValueError("cohort count mismatch")
    _check_name_order([cohort["name"] for cohort in cohorts], "cohorts")
    for cohort in cohorts:
        _check_exact_fields(cohort, COHORT_FIELDS, "cohort")
        name = cohort["name"]
        if name not in {"all125", "base104", "amendment21"} or not COHORT_NAME_RE.match(name):
            raise ValueError("invalid cohort name")
        case_ids = cohort["case_ids"]
        if not isinstance(case_ids, list) or not all(isinstance(cid, str) for cid in case_ids):
            raise ValueError("cohort case_ids must be strings")
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("cohort duplicate id " + name)
        if cohort["case_count"] != len(case_ids):
            raise ValueError("cohort case_count mismatch " + name)
        _check_name_order(case_ids, "cohort case_ids " + name)
        if not isinstance(cohort["aggregate_v1"], str) or not SHA256_HEX_RE.match(cohort["aggregate_v1"]):
            raise ValueError("cohort aggregate invalid " + name)

    category_names = manifest["category_names"]
    if not isinstance(category_names, list) or len(category_names) != len(categories):
        raise ValueError("category_names count mismatch")
    if set(category_names) != set(categories):
        raise ValueError("category_names set mismatch")
    _check_name_order(category_names, "category_names")
    if any(not isinstance(name, str) for name in category_names):
        raise ValueError("category_names must be strings")

    category_aggregates = manifest["category_aggregates"]
    if not isinstance(category_aggregates, dict) or set(category_aggregates) != set(category_names):
        raise ValueError("category_aggregates keys mismatch")
    for name in category_names:
        value = category_aggregates[name]
        if not isinstance(value, str) or not SHA256_HEX_RE.match(value):
            raise ValueError("category aggregate invalid " + name)

    case_digests = manifest["case_digests"]
    if not isinstance(case_digests, list) or len(case_digests) != 125:
        raise ValueError("case_digests count mismatch")
    ids = []
    for item in case_digests:
        _check_exact_fields(item, CASE_DIGEST_FIELDS, "case_digest")
        case_id = item["id"]
        if not isinstance(case_id, str):
            raise ValueError("case digest id must be a string")
        if not isinstance(item["category"], str):
            raise ValueError("case digest category must be a string")
        if not isinstance(item["sha256"], str) or not SHA256_HEX_RE.match(item["sha256"]):
            raise ValueError("case digest sha256 invalid " + case_id)
        ids.append(case_id)
    if len(set(ids)) != 125:
        raise ValueError("case digest duplicate id")
    _check_name_order(ids, "case_digests")


def manifest_hash_v2(manifest: Any) -> str:
    canonical = canonical_json_v2(manifest)
    return hashlib.sha256(MANIFEST_HASH_MAGIC + canonical).hexdigest()


def build_envelope_v2(manifest: Any) -> dict[str, Any]:
    return {"manifest_v2": manifest, "manifest_hash_v2": manifest_hash_v2(manifest)}


def envelope_to_bytes(envelope: Any) -> bytes:
    if not isinstance(envelope, dict) or set(envelope) != set(ENVELOPE_FIELDS):
        raise ValueError("envelope fields mismatch")
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def decode_envelope_v2(raw: bytes, fixture_obj: Any, legacy_obj: Any) -> dict[str, Any]:
    envelope = _strict_load_object(raw)
    _check_exact_fields(envelope, ENVELOPE_FIELDS, "envelope")
    manifest = envelope["manifest_v2"]
    validate_manifest_v2(manifest, fixture_obj, legacy_obj)
    expected = manifest_hash_v2(manifest)
    if envelope["manifest_hash_v2"] != expected:
        raise ValueError("manifest_hash_v2 mismatch")
    return {"manifest_v2": manifest, "manifest_hash_v2": envelope["manifest_hash_v2"]}


def load_fixture_and_legacy(fixture_raw: bytes, legacy_raw: bytes):
    fixture_obj = strict_decode_v2(fixture_raw)
    legacy_obj = strict_decode_v2(legacy_raw)
    return fixture_obj, legacy_obj