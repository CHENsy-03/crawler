"""E/A1 candidate runtime conformance and local negative tests."""

from __future__ import annotations

import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from crawler.security.osec_evidence import (
    AGGREGATE_V1_MAGIC,
    CATEGORY_AGGREGATE_V1_MAGIC,
    DEFAULT_LIMITS,
    FROZEN_ERROR_CODES,
    CaseDigest,
    EvidenceLimits,
    OSECError,
    _checked_u32,
    aggregate_v1,
    canonical_case,
    canonical_json,
    category_aggregate_v1,
    strict_decode,
    validate_case_dataset,
)

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "outbound_security_aggregate_vectors.json")
VALID_NAMES = {
    "canonical_case_minimal", "canonical_html_specials", "canonical_u2028", "canonical_u2029",
    "canonical_literal_backslash_u", "canonical_cjk", "canonical_quote_backslash", "canonical_control_short",
    "canonical_control_u00xx", "canonical_slash", "canonical_u007f_c1", "canonical_unicode_object_key",
    "canonical_nested_key_sort", "canonical_null_empty_distinction", "canonical_type_int_bool_string",
    "canonical_integer_zero", "canonical_negative_zero", "canonical_large_integer", "canonical_surrogate_pair",
    "canonical_internal_bom", "canonical_whitespace_equivalent", "canonical_crlf_equivalent",
    "canonical_key_sort_ascii_cjk_nonbmp", "canonical_depth_128", "canonical_case_id_64",
}
REJECT_NAMES = {
    "strict_bom", "strict_invalid_utf8", "strict_empty_input", "strict_whitespace_only", "strict_malformed_json",
    "strict_trailing_data", "strict_duplicate_literal_key", "strict_duplicate_decoded_key", "strict_lone_high_surrogate",
    "strict_lone_low_surrogate", "strict_high_high_surrogate", "strict_high_nonlow_surrogate", "strict_low_high_surrogate",
    "strict_nan", "strict_infinity", "strict_negative_infinity", "strict_leading_zero", "strict_truncated_exponent",
    "limit_file_size_16mib_plus_1", "limit_depth_129", "limit_integer_4097_digits", "limit_array_10001",
    "limit_object_1001_members", "limit_string_1mib_plus_1", "limit_case_count_10001",
    "canonical_noninteger_1_0", "canonical_noninteger_1e5", "canonical_noninteger_negative_zero",
    "canonical_root_non_object", "canonical_missing_id", "canonical_empty_id", "canonical_uppercase_id",
    "canonical_underscore_id", "canonical_id_65", "canonical_nonstring_id",
}
RECIPE_NAMES = {
    "recipe_integer_4097_digits", "recipe_array_10001", "recipe_string_1mib_plus_1", "recipe_file_size_16mib_plus_1",
    "recipe_depth_129", "recipe_object_1001_members", "recipe_case_count_10001",
}
TARGETS = {"canonical_json", "canonical_case", "strict_decode", "evidence_limits", "canonical"}
STAGES = {"strict_decode", "evidence_limits", "canonical"}
GENERATORS = {"repeat_unit", "nested_container", "object_members", "file_size_pad", "case_dataset"}
OUTPUT_KINDS = {"raw_bytes", "typed_dataset"}
AGGREGATE_EXPECTED = "491d7d8881628da0ed213673a79fb250f285bfbf6573f414254119c1c5ba70e2"
CATEGORY_AGGREGATE_EXPECTED = "91832a3c5e90e6b6136d02ba293bbd31e90aace1a55f4f40f08957975afa0d17"


def _load_fixture():
    raw = open(FIXTURE_PATH, "rb").read()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")

    def no_dup(pairs):
        seen = set()
        for key, _value in pairs:
            if key in seen:
                raise ValueError("duplicate key " + key)
            seen.add(key)
        return dict(pairs)

    obj, end = json.JSONDecoder(object_pairs_hook=no_dup).raw_decode(text)
    assert text[end:].strip() == ""
    return obj


def _generate_recipe(recipe):
    prefix = bytes.fromhex(recipe["prefix_hex"])
    unit = bytes.fromhex(recipe["unit_hex"])
    separator = bytes.fromhex(recipe["separator_hex"]) if recipe["separator_hex"] else b""
    suffix = bytes.fromhex(recipe["suffix_hex"])
    count = recipe["count"]
    generator = recipe["generator"]
    if generator not in GENERATORS:
        raise AssertionError("unknown generator " + generator)
    if recipe["output_kind"] not in OUTPUT_KINDS:
        raise AssertionError("unknown output kind")
    if generator == "repeat_unit":
        return prefix + unit + b"".join(separator + unit for _ in range(count - 1)) + suffix
    if generator == "nested_container":
        return prefix * count + unit + suffix * count
    if generator == "object_members":
        return prefix + b",".join(b'"k%d":0' % i for i in range(count)) + suffix
    if generator == "file_size_pad":
        return prefix + unit * count + suffix
    if generator == "case_dataset":
        return prefix + b",".join(b'{"id":"c%d"}' % i for i in range(count)) + suffix
    raise AssertionError("unreachable generator")


def _canonical_errors():
    return {
        "canonical_root_not_object",
        "canonical_missing_id",
        "canonical_invalid_id",
    }


def test_a02_valid_vectors():
    fixture = _load_fixture()
    executed = set()
    for vector in fixture["valid_vectors"]:
        name = vector["name"]
        assert vector["target"] in {"canonical_json", "canonical_case"}
        raw = bytes.fromhex(vector["input_json_utf8_hex"])
        expected = bytes.fromhex(vector["expected_canonical_utf8_hex"])
        value = strict_decode(raw)
        if vector["target"] == "canonical_case":
            result = canonical_case(value)
            assert result.canonical == expected
            assert result.sha256 == vector["expected_case_sha256"]
        else:
            assert canonical_json(value) == expected
            assert vector["expected_case_sha256"] is None
        executed.add(name)
    assert executed == VALID_NAMES


def test_a02_reject_vectors():
    fixture = _load_fixture()
    executed = set()
    for vector in fixture["reject_vectors"]:
        name = vector["name"]
        assert vector["target"] == vector["expected_stage"]
        if vector["recipe"] is None:
            raw = bytes.fromhex(vector["input_json_utf8_hex"])
            with pytest.raises(OSECError) as excinfo:
                if vector["target"] == "canonical":
                    value = strict_decode(raw)
                    if vector["expected_error"] in _canonical_errors():
                        canonical_case(value)
                    else:
                        canonical_json(value)
                else:
                    strict_decode(raw)
            assert excinfo.value.code == vector["expected_error"]
        executed.add(name)
    assert executed == REJECT_NAMES


def test_a02_resource_recipes():
    fixture = _load_fixture()
    executed = set()
    for recipe in fixture["resource_recipes"]:
        data = _generate_recipe(recipe)
        assert hashlib.sha256(data).hexdigest() == recipe["expected_input_sha256"]
        if recipe["name"] == "recipe_case_count_10001":
            cases = json.loads(data)
            with pytest.raises(OSECError) as excinfo:
                validate_case_dataset(cases)
            assert excinfo.value.code == "evidence_limit_case_count"
        else:
            with pytest.raises(OSECError) as excinfo:
                strict_decode(data)
            assert excinfo.value.code == recipe["expected_error"]
        executed.add(recipe["name"])
    assert executed == RECIPE_NAMES


def test_unknown_vector_metadata_fail_closed():
    fixture = _load_fixture()
    for vector in fixture["valid_vectors"]:
        assert vector["target"] in TARGETS
    for vector in fixture["reject_vectors"]:
        assert vector["target"] in STAGES
        assert vector["expected_stage"] in STAGES
    for recipe in fixture["resource_recipes"]:
        assert recipe["generator"] in GENERATORS
        assert recipe["output_kind"] in OUTPUT_KINDS
    with pytest.raises(AssertionError):
        _generate_recipe({"generator": "unknown_generator", "output_kind": "raw_bytes", "prefix_hex": "5b", "unit_hex": "30", "separator_hex": "", "suffix_hex": "5d", "count": 1})
    with pytest.raises(AssertionError):
        _generate_recipe({"generator": "nested_container", "output_kind": "unknown_kind", "prefix_hex": "5b", "unit_hex": "30", "separator_hex": "", "suffix_hex": "5d", "count": 1})


def test_aggregate_hardcoded_expected():
    digests = [CaseDigest("a", b"\x00" * 32), CaseDigest("b", b"\x01" * 32)]
    assert aggregate_v1(digests) == AGGREGATE_EXPECTED
    assert category_aggregate_v1("test", digests) == CATEGORY_AGGREGATE_EXPECTED


def test_local_negative_python_values():
    with pytest.raises(OSECError) as exc:
        canonical_json(1.5)
    assert exc.value.code == "canonical_invalid_value_type"
    with pytest.raises(OSECError):
        canonical_json(Decimal("1.5"))
    with pytest.raises(OSECError):
        canonical_json(b"bytes")
    with pytest.raises(OSECError):
        canonical_json({1: "x"})
    with pytest.raises(OSECError):
        canonical_json(object())
    cycle = []
    cycle.append(cycle)
    with pytest.raises(OSECError):
        canonical_json(cycle)
    dcycle = {}
    dcycle["self"] = dcycle
    with pytest.raises(OSECError):
        canonical_json(dcycle)
    shared = [1]
    assert canonical_json([shared, shared]) == b"[[1],[1]]"
    with pytest.raises(OSECError) as exc:
        canonical_json("\ud800")
    assert exc.value.code == "canonical_invalid_unicode"
    with pytest.raises(OSECError):
        canonical_json({"\ud800": 1})
    assert canonical_json(True) == b"true"


def test_local_negative_aggregate():
    digest = CaseDigest("a", b"\x00" * 32)
    with pytest.raises(OSECError) as exc:
        aggregate_v1([])
    assert exc.value.code == "aggregate_empty_set"
    with pytest.raises(OSECError):
        aggregate_v1([digest, CaseDigest("a", b"\x01" * 32)])
    with pytest.raises(OSECError):
        aggregate_v1([CaseDigest("a", b"\x00" * 31)])
    with pytest.raises(OSECError):
        aggregate_v1([digest], algorithm="UNKNOWN")
    with pytest.raises(OSECError) as exc:
        _checked_u32(2**32, "aggregate_count_overflow")
    assert exc.value.code == "aggregate_count_overflow"
    with pytest.raises(OSECError) as exc:
        _checked_u32(2**32, "aggregate_length_overflow")
    assert exc.value.code == "aggregate_length_overflow"
    with pytest.raises(OSECError) as exc:
        category_aggregate_v1("Bad Name", [digest])
    assert exc.value.code == "manifest_invalid_category"


def test_error_message_does_not_leak_input():
    sentinel = b"SECRET_SENTINEL"
    try:
        strict_decode(b'{"bad": ' + sentinel)
    except OSECError as exc:
        assert sentinel.decode() not in str(exc)
    else:
        raise AssertionError("expected error")


def test_production_isolation():
    init = Path("crawler/security/__init__.py").read_text(encoding="utf-8")
    assert "osec_evidence" not in init
    root = Path("crawler")
    for path in root.rglob("*.py"):
        if "security" in path.parts:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        assert "osec_evidence" not in source, path
