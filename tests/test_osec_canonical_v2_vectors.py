"""Canonical V2 vector fixture structural contract tests."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re

import pytest

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "outbound_security_canonical_v2_vectors.json")
A02_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "outbound_security_aggregate_vectors.json")
FIXTURE_SHA = "E7B1E9B80A8BDCCA527E5EC6435610AB5B111D4EB37B1AC2F9468BCBCDEE9EDF"
A02_SHA = "3dd12b56d4f04af48ffd7d5f1d27246524aa9b4d0aab063646c30f915a6407cc"

TOP_KEYS = [
    "format_version",
    "profile",
    "amendment",
    "canonical_json_version",
    "canonical_case_version",
    "evidence_limits_version",
    "provenance",
    "inherits_v1_valid_vectors",
    "valid_vectors",
    "resource_recipes",
    "direct_wrapper_vectors",
]

V1_VALID_NAMES = {
    "canonical_case_id_64", "canonical_case_minimal", "canonical_cjk", "canonical_control_short",
    "canonical_control_u00xx", "canonical_crlf_equivalent", "canonical_depth_128", "canonical_html_specials",
    "canonical_integer_zero", "canonical_internal_bom", "canonical_key_sort_ascii_cjk_nonbmp",
    "canonical_large_integer", "canonical_literal_backslash_u", "canonical_negative_zero",
    "canonical_nested_key_sort", "canonical_null_empty_distinction", "canonical_quote_backslash",
    "canonical_slash", "canonical_surrogate_pair", "canonical_type_int_bool_string", "canonical_u007f_c1",
    "canonical_u2028", "canonical_u2029", "canonical_unicode_object_key", "canonical_whitespace_equivalent",
}

VALID_NAMES = {
    "number_1_0", "number_443_0", "number_1_00", "number_1e5", "number_1E_plus_5",
    "number_negative_zero_fraction", "number_zero_fraction", "number_0_10", "number_1e_minus_5",
    "number_negative_1_25e_plus_3", "canonical_case_p004_shape", "canonical_case_ver003_shape",
}
RECIPE_NAMES = {"number_digits_4096_valid", "number_digits_4097_reject"}
WRAPPER_NAMES = {
    "direct_wrapper_integer_lexeme", "direct_wrapper_leading_plus", "direct_wrapper_leading_zero",
    "direct_wrapper_truncated_exponent", "direct_wrapper_nan", "direct_wrapper_infinity",
    "direct_wrapper_whitespace", "direct_wrapper_non_ascii_digit",
}

VALID_EXPECTED = {
    "number_1_0": ("canonical_json", b"1.0", b"1.0", None),
    "number_443_0": ("canonical_json", b"443.0", b"443.0", None),
    "number_1_00": ("canonical_json", b"1.00", b"1.00", None),
    "number_1e5": ("canonical_json", b"1e5", b"1e5", None),
    "number_1E_plus_5": ("canonical_json", b"1E+5", b"1E+5", None),
    "number_negative_zero_fraction": ("canonical_json", b"-0.0", b"-0.0", None),
    "number_zero_fraction": ("canonical_json", b"0.0", b"0.0", None),
    "number_0_10": ("canonical_json", b"0.10", b"0.10", None),
    "number_1e_minus_5": ("canonical_json", b"1e-5", b"1e-5", None),
    "number_negative_1_25e_plus_3": ("canonical_json", b"-1.25e+3", b"-1.25e+3", None),
    "canonical_case_p004_shape": (
        "canonical_case",
        b'{"ports":{"https":[443.0]},"id":"p-004"}',
        b'{"id":"p-004","ports":{"https":[443.0]}}',
        "b3c3de96070b6b1e777448472e515f8846d84db69b3d824b6d81a649d9778b71",
    ),
    "canonical_case_ver003_shape": (
        "canonical_case",
        b'{"value":1.0,"id":"ver-003"}',
        b'{"id":"ver-003","value":1.0}',
        "e5de3e28f87e3de599befb0eab0a64249b00322eabde9c5d66cd9eb4c1171890",
    ),
}

RECIPE_EXPECTED = {
    "number_digits_4096_valid": (4096, "1a333e81edc3d2d2b16b1617f30d3958e34d081c50c7712a9fb2912276d08cbb", "valid", "canonical", None),
    "number_digits_4097_reject": (4097, "c92a1c339eafdca9beace977107a9f396a12f1f29972654b7277d8c3e0106ede", "reject", "evidence_limits", "evidence_limit_number_digits"),
}

WRAPPER_EXPECTED = {
    "direct_wrapper_integer_lexeme": b"1",
    "direct_wrapper_leading_plus": b"+1.0",
    "direct_wrapper_leading_zero": b"01.0",
    "direct_wrapper_truncated_exponent": b"1e",
    "direct_wrapper_nan": b"NaN",
    "direct_wrapper_infinity": b"Infinity",
    "direct_wrapper_whitespace": b" 1.0",
    "direct_wrapper_non_ascii_digit": "\uff11.0".encode("utf-8"),
}

NONINTEGER_RE = re.compile(rb"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")


def _load_strict_json(path):
    raw = open(path, "rb").read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise AssertionError("BOM")
    if b"\r" in raw.replace(b"\r\n", b""):
        raise AssertionError("lone CR")
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
    return raw, obj


def _generate_recipe(recipe):
    if recipe["generator"] != "non_integer_digit_count":
        raise AssertionError("unknown generator")
    if recipe["output_kind"] != "json_number":
        raise AssertionError("unknown output kind")
    return b"1" * (recipe["count"] - 1) + b".0"


def _invalid_wrapper(raw):
    return not NONINTEGER_RE.match(raw) or (b"." not in raw and b"e" not in raw and b"E" not in raw)


def _reject_duplicate_json(text):
    def no_dup(pairs):
        seen = set()
        for key, _value in pairs:
            if key in seen:
                raise ValueError("duplicate key " + key)
            seen.add(key)
        return dict(pairs)

    json.JSONDecoder(object_pairs_hook=no_dup).raw_decode(text)


def _validate_v2_fixture(fixture):
    if list(fixture.keys()) != TOP_KEYS:
        raise AssertionError("top fields")
    if fixture["format_version"] != "1.0":
        raise AssertionError("format_version")
    if fixture["profile"] != "OSEC-EVIDENCE-PROFILE-V2":
        raise AssertionError("profile")
    if fixture["amendment"] != "OSEC-EVIDENCE-PROFILE-V2-AMENDMENT-1":
        raise AssertionError("amendment")
    if fixture["canonical_json_version"] != "OSEC-CANONICAL-JSON-V2":
        raise AssertionError("canonical_json_version")
    if fixture["canonical_case_version"] != "OSEC-CANONICAL-CASE-V2":
        raise AssertionError("canonical_case_version")
    if fixture["evidence_limits_version"] != "OSEC-EVIDENCE-LIMITS-V2":
        raise AssertionError("evidence_limits_version")
    if fixture["provenance"] != {"method": "independently_constructed"}:
        raise AssertionError("provenance")

    inherit = fixture["inherits_v1_valid_vectors"]
    if set(inherit.keys()) != {"fixture_path", "normalized_lf_sha256", "valid_vector_count", "required_valid_names"}:
        raise AssertionError("inherit fields")
    if inherit["fixture_path"] != "tests/fixtures/outbound_security_aggregate_vectors.json":
        raise AssertionError("inherit path")
    a02_raw = open(os.path.join(os.path.dirname(FIXTURE_PATH), "outbound_security_aggregate_vectors.json"), "rb").read()
    a02_norm = a02_raw.replace(b"\r\n", b"\n")
    if hashlib.sha256(a02_norm).hexdigest() != A02_SHA:
        raise AssertionError("A0.2 sha")
    a02_obj = json.loads(a02_norm.decode("utf-8"))
    a02_names = [v["name"] for v in a02_obj["valid_vectors"]]
    if inherit["valid_vector_count"] != 25 or len(a02_names) != 25:
        raise AssertionError("inherit count")
    if set(inherit["required_valid_names"]) != V1_VALID_NAMES or set(a02_names) != V1_VALID_NAMES:
        raise AssertionError("inherit names")
    if inherit["required_valid_names"] != sorted(inherit["required_valid_names"]):
        raise AssertionError("inherit order")

    valid = fixture["valid_vectors"]
    recipes = fixture["resource_recipes"]
    wrappers = fixture["direct_wrapper_vectors"]
    if len(valid) != 12 or len(recipes) != 2 or len(wrappers) != 8:
        raise AssertionError("counts")
    if {v["name"] for v in valid} != VALID_NAMES:
        raise AssertionError("valid inventory")
    if {r["name"] for r in recipes} != RECIPE_NAMES:
        raise AssertionError("recipe inventory")
    if {w["name"] for w in wrappers} != WRAPPER_NAMES:
        raise AssertionError("wrapper inventory")
    all_names = [v["name"] for v in valid] + [r["name"] for r in recipes] + [w["name"] for w in wrappers]
    if len(all_names) != len(set(all_names)):
        raise AssertionError("duplicate names")
    if set(all_names) & V1_VALID_NAMES:
        raise AssertionError("v1 name conflict")

    for vector in valid:
        name = vector["name"]
        if set(vector.keys()) != {"name", "target", "input_json_utf8_hex", "expected_canonical_utf8_hex", "expected_case_sha256"}:
            raise AssertionError("valid fields " + name)
        expected = VALID_EXPECTED[name]
        if vector["target"] != expected[0]:
            raise AssertionError("valid target " + name)
        if bytes.fromhex(vector["input_json_utf8_hex"]) != expected[1]:
            raise AssertionError("valid input " + name)
        if bytes.fromhex(vector["expected_canonical_utf8_hex"]) != expected[2]:
            raise AssertionError("valid expected " + name)
        if vector["expected_case_sha256"] != expected[3]:
            raise AssertionError("valid digest " + name)

    for recipe in recipes:
        name = recipe["name"]
        if set(recipe.keys()) != {"name", "generator", "count", "output_kind", "expected_input_sha256", "expected_outcome", "expected_stage", "expected_error"}:
            raise AssertionError("recipe fields " + name)
        count, sha, outcome, stage, error = RECIPE_EXPECTED[name]
        if recipe["count"] != count:
            raise AssertionError("recipe count " + name)
        if recipe["expected_input_sha256"] != sha:
            raise AssertionError("recipe sha field " + name)
        data = _generate_recipe(recipe)
        if len(data) != count + 1:
            raise AssertionError("recipe length " + name)
        if data.count(b".") != 1 or data[0] != ord("1") or not data.rstrip(b".0").isalnum():
            raise AssertionError("recipe grammar " + name)
        digits = count
        if hashlib.sha256(data).hexdigest() != sha:
            raise AssertionError("recipe sha " + name)
        if recipe["expected_outcome"] != outcome or recipe["expected_stage"] != stage or recipe["expected_error"] != error:
            raise AssertionError("recipe outcome " + name)

    for wrapper in wrappers:
        name = wrapper["name"]
        if set(wrapper.keys()) != {"name", "raw_lexeme_utf8_hex", "expected_error"}:
            raise AssertionError("wrapper fields " + name)
        raw = bytes.fromhex(wrapper["raw_lexeme_utf8_hex"])
        if raw != WRAPPER_EXPECTED[name]:
            raise AssertionError("wrapper raw " + name)
        if not _invalid_wrapper(raw):
            raise AssertionError("wrapper should be invalid " + name)
        if wrapper["expected_error"] != "canonical_invalid_number_lexeme":
            raise AssertionError("wrapper error " + name)


def test_v2_vector_fixture_positive():
    raw, fixture = _load_strict_json(FIXTURE_PATH)
    if hashlib.sha256(raw).hexdigest().upper() != FIXTURE_SHA:
        raise AssertionError("fixture sha")
    _validate_v2_fixture(fixture)


def test_v2_vector_fixture_rejects_invalid_metadata():
    _raw, fixture = _load_strict_json(FIXTURE_PATH)

    def run_bad(mutate):
        copy_fixture = copy.deepcopy(fixture)
        mutate(copy_fixture)
        with pytest.raises((AssertionError, ValueError)):
            _validate_v2_fixture(copy_fixture)

    run_bad(lambda f: f.__setitem__("unknown_top", True))
    run_bad(lambda f: f.__setitem__("profile", "OSEC-EVIDENCE-PROFILE-V3"))
    run_bad(lambda f: f.__setitem__("amendment", "OSEC-EVIDENCE-PROFILE-V2-AMENDMENT-2"))
    run_bad(lambda f: f["provenance"].__setitem__("method", "unknown"))
    run_bad(lambda f: f["inherits_v1_valid_vectors"].__setitem__("valid_vector_count", 24))
    run_bad(lambda f: f["inherits_v1_valid_vectors"]["required_valid_names"].pop())
    run_bad(lambda f: f["inherits_v1_valid_vectors"]["required_valid_names"].append("unknown"))
    run_bad(lambda f: f["inherits_v1_valid_vectors"]["required_valid_names"].sort(reverse=True))
    run_bad(lambda f: f["valid_vectors"].pop())
    run_bad(lambda f: f["valid_vectors"].append(copy.deepcopy(f["valid_vectors"][0])))
    run_bad(lambda f: f["valid_vectors"][0].__setitem__("target", "unknown"))
    run_bad(lambda f: f["valid_vectors"][0].__setitem__("unknown_field", True))
    run_bad(lambda f: f["valid_vectors"][0].__setitem__("input_json_utf8_hex", "ZZ"))
    run_bad(lambda f: f["valid_vectors"][10].__setitem__("expected_case_sha256", "0" + f["valid_vectors"][10]["expected_case_sha256"][1:]))
    run_bad(lambda f: f["valid_vectors"][0].__setitem__("expected_case_sha256", "0" * 64))
    run_bad(lambda f: f["valid_vectors"][10].__setitem__("expected_case_sha256", None))
    run_bad(lambda f: f["resource_recipes"].pop())
    run_bad(lambda f: f["resource_recipes"][0].__setitem__("generator", "unknown"))
    run_bad(lambda f: f["resource_recipes"][0].__setitem__("output_kind", "unknown"))
    run_bad(lambda f: f["resource_recipes"][0].__setitem__("expected_outcome", "unknown"))
    run_bad(lambda f: f["resource_recipes"][0].__setitem__("expected_stage", "unknown"))
    run_bad(lambda f: f["resource_recipes"][0].__setitem__("expected_error", "unknown"))
    run_bad(lambda f: f["resource_recipes"][0].__setitem__("count", 4095))
    run_bad(lambda f: f["resource_recipes"][0].__setitem__("expected_input_sha256", "0" + f["resource_recipes"][0]["expected_input_sha256"][1:]))
    run_bad(lambda f: f["direct_wrapper_vectors"].pop())
    run_bad(lambda f: f["direct_wrapper_vectors"][0].__setitem__("expected_error", "unknown"))
    run_bad(lambda f: f["direct_wrapper_vectors"][0].__setitem__("raw_lexeme_utf8_hex", "322e30"))

    with pytest.raises(AssertionError):
        _validate_v2_fixture({"unknown": True})
    with pytest.raises(ValueError):
        _reject_duplicate_json('{"a":1,"a":2}')
    assert _invalid_wrapper(b"1")
