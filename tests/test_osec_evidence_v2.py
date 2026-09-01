"""Canonical V2 candidate runtime conformance tests."""

from __future__ import annotations

import hashlib
import json
import os

import pytest

from crawler.security.osec_evidence import (
    NonIntegerNumber,
    OSECError,
    canonical_case,
    canonical_json,
)
from crawler.security.osec_evidence_v2 import (
    DEFAULT_LIMITS_V2,
    EvidenceLimitsV2,
    canonical_case_v2,
    canonical_json_v2,
    strict_decode_v2,
)

V2_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "outbound_security_canonical_v2_vectors.json")
A02_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "outbound_security_aggregate_vectors.json")

V2_VALID = {
    "number_1_0", "number_443_0", "number_1_00", "number_1e5", "number_1E_plus_5",
    "number_negative_zero_fraction", "number_zero_fraction", "number_0_10", "number_1e_minus_5",
    "number_negative_1_25e_plus_3", "canonical_case_p004_shape", "canonical_case_ver003_shape",
}
V2_RECIPES = {"number_digits_4096_valid", "number_digits_4097_reject"}
V2_WRAPPERS = {
    "direct_wrapper_integer_lexeme", "direct_wrapper_leading_plus", "direct_wrapper_leading_zero",
    "direct_wrapper_truncated_exponent", "direct_wrapper_nan", "direct_wrapper_infinity",
    "direct_wrapper_whitespace", "direct_wrapper_non_ascii_digit",
}


def _load_strict(path):
    raw = open(path, "rb").read()
    text = raw.decode("utf-8")

    def no_dup(pairs):
        seen = set()
        for key, _value in pairs:
            if key in seen:
                raise ValueError("duplicate key " + key)
            seen.add(key)
        return dict(pairs)

    obj, end = json.JSONDecoder(object_pairs_hook=no_dup).raw_decode(text)
    if text[end:].strip():
        raise AssertionError("trailing data")
    return obj


def _generate_recipe(recipe):
    return b"1" * (recipe["count"] - 1) + b".0"


def _run_valid(vector):
    raw = bytes.fromhex(vector["input_json_utf8_hex"])
    expected = bytes.fromhex(vector["expected_canonical_utf8_hex"])
    value = strict_decode_v2(raw)
    if vector["target"] == "canonical_case":
        result = canonical_case_v2(value)
        assert result.canonical == expected
        assert result.sha256 == vector["expected_case_sha256"]
    else:
        assert canonical_json_v2(value) == expected
        assert vector["expected_case_sha256"] is None


def test_v2_runtime_v2_valid_vectors():
    fixture = _load_strict(V2_FIXTURE)
    executed = set()
    for vector in fixture["valid_vectors"]:
        _run_valid(vector)
        executed.add(vector["name"])
    assert executed == V2_VALID


def test_v2_runtime_inherited_v1_valid_vectors():
    fixture = _load_strict(A02_FIXTURE)
    executed = set()
    for vector in fixture["valid_vectors"]:
        _run_valid(vector)
        executed.add(vector["name"])
    assert len(executed) == 25


def test_v2_runtime_recipes():
    fixture = _load_strict(V2_FIXTURE)
    for recipe in fixture["resource_recipes"]:
        data = _generate_recipe(recipe)
        if recipe["name"] == "number_digits_4096_valid":
            value = strict_decode_v2(data)
            assert canonical_json_v2(value) == data
        else:
            with pytest.raises(OSECError) as excinfo:
                strict_decode_v2(data)
            assert excinfo.value.code == "evidence_limit_number_digits"


def test_v2_runtime_direct_wrappers():
    fixture = _load_strict(V2_FIXTURE)
    for wrapper in fixture["direct_wrapper_vectors"]:
        raw = bytes.fromhex(wrapper["raw_lexeme_utf8_hex"]).decode("utf-8")
        with pytest.raises(OSECError) as excinfo:
            canonical_json_v2(NonIntegerNumber(raw))
        assert excinfo.value.code == "canonical_invalid_number_lexeme"


def test_v2_local_negatives():
    with pytest.raises(OSECError) as exc:
        canonical_json_v2(1.5)
    assert exc.value.code == "canonical_invalid_value_type"
    with pytest.raises(OSECError):
        canonical_json_v2(float("nan"))
    with pytest.raises(OSECError):
        canonical_json_v2(b"bytes")
    with pytest.raises(OSECError):
        canonical_json_v2(object())
    with pytest.raises(OSECError):
        canonical_json_v2({1: "x"})
    cycle = []
    cycle.append(cycle)
    with pytest.raises(OSECError):
        canonical_json_v2(cycle)
    dcycle = {}
    dcycle["self"] = dcycle
    with pytest.raises(OSECError):
        canonical_json_v2(dcycle)
    shared = [1]
    assert canonical_json_v2([shared, shared]) == b"[[1],[1]]"
    with pytest.raises(OSECError):
        canonical_json_v2("\ud800")
    with pytest.raises(OSECError):
        canonical_json_v2({"\ud800": 1})
    with pytest.raises(OSECError):
        canonical_json_v2(NonIntegerNumber("1"))
    with pytest.raises(OSECError):
        canonical_json_v2(NonIntegerNumber(" 1.0"))
    with pytest.raises(OSECError):
        canonical_json_v2(NonIntegerNumber("\uff11.0"))
    with pytest.raises(OSECError):
        canonical_json_v2(NonIntegerNumber("1" * 4096 + ".0"))
    assert canonical_json_v2(NonIntegerNumber("1" * 4095 + ".0")) == ("1" * 4095 + ".0").encode("ascii")
    assert canonical_json_v2(True) == b"true"
    assert canonical_json_v2(1) == b"1"
    with pytest.raises(OSECError):
        canonical_json(NonIntegerNumber("1.0"))
    with pytest.raises(OSECError):
        canonical_case(NonIntegerNumber("1.0"))

    # Limits V2 boundaries.
    limits = EvidenceLimitsV2(nesting_depth=1)
    with pytest.raises(OSECError) as exc:
        strict_decode_v2(b"[[0]]", limits)
    assert exc.value.code == "evidence_limit_nesting_depth"
    limits = EvidenceLimitsV2(array_length=1)
    with pytest.raises(OSECError):
        strict_decode_v2(b"[0,0]", limits)
    limits = EvidenceLimitsV2(object_members=1)
    with pytest.raises(OSECError):
        strict_decode_v2(b'{"a":1,"b":2}', limits)
    limits = EvidenceLimitsV2(string_length=1)
    with pytest.raises(OSECError):
        strict_decode_v2(b'"ab"', limits)

    # Error message isolation.
    try:
        strict_decode_v2(b'{"x": SECRET_SENTINEL')
    except OSECError as exc:
        assert "SECRET_SENTINEL" not in str(exc)
    else:
        raise AssertionError("expected error")


def test_v2_counterfactuals():
    assert canonical_json_v2(strict_decode_v2(b"1.0")) == b"1.0"
    assert canonical_json_v2(strict_decode_v2(b"1.00")) == b"1.00"
    assert canonical_json_v2(strict_decode_v2(b"1E+5")) == b"1E+5"
    assert canonical_json_v2(strict_decode_v2(b"-0.0")) == b"-0.0"
    with pytest.raises(OSECError) as exc:
        strict_decode_v2(b"1" * 4096 + b".0")
    assert exc.value.code == "evidence_limit_number_digits"
    with pytest.raises(OSECError) as exc:
        strict_decode_v2(b'{"a":1,"\\u0061":2}')
    assert exc.value.code == "strict_decode_duplicate_key"
    with pytest.raises(OSECError) as exc:
        strict_decode_v2(b'{"a":1,')
    assert exc.value.code == "strict_decode_invalid_json"
    with pytest.raises(OSECError):
        canonical_json_v2(NonIntegerNumber(" 1.0"))
    with pytest.raises(OSECError):
        canonical_json_v2(NonIntegerNumber("\uff11.0"))
    with pytest.raises(OSECError):
        canonical_json_v2(1.5)
    # Bridge limits must not skip structural checks.
    with pytest.raises(OSECError) as exc:
        strict_decode_v2(b"[[[[0]]]]", EvidenceLimitsV2(nesting_depth=1))
    assert exc.value.code == "evidence_limit_nesting_depth"
    with pytest.raises(OSECError):
        strict_decode_v2(b"[0,0,0]", EvidenceLimitsV2(array_length=1))
    # No ID special-casing.
    assert canonical_case_v2(strict_decode_v2(b'{"id":"z-001","v":1}')).sha256
