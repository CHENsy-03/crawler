"""TASK-022E-B contract fixture integrity tests.

This module validates the shared outbound security configuration fixture only.
It must not import production configuration loaders, read production config,
perform DNS, or open sockets.
"""

import copy
import hashlib
import json
import os
import re
import struct

import pytest

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "outbound_security_config_contract.json")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "outbound_security.schema.json")
EXPECTED_CATEGORIES = {
    "valid_config",
    "top_level",
    "version",
    "policy_id",
    "hostname",
    "scheme",
    "port",
    "duplicate",
    "policy_reference",
    "site_cross_validation",
    "logging",
    "forbidden_field",
}
EXPECTED_REASONS = {
    "config_missing",
    "config_invalid_json",
    "config_invalid_top_level",
    "config_unsupported_version",
    "config_unknown_field",
    "config_missing_field",
    "config_invalid_type",
    "config_duplicate",
    "config_invalid_policy_id",
    "config_invalid_hostname",
    "config_forbidden_ip_literal",
    "config_invalid_scheme",
    "config_invalid_port",
    "config_invalid_policy_reference",
    "config_site_host_not_covered",
    "config_conflict",
    "config_unreadable",
    "config_limit_exceeded",
}
KNOWN_ACTIONS = {"accept", "reject", "marker", "reference", "cross_validation", "logging", "ordering"}
LOGGING_RULES = {
    "no_raw_config",
    "no_full_url",
    "no_credentials",
    "allow_reason_field_path",
    "allow_policy_id_no_policy",
    "allow_hostname_no_url",
}
ALLOWED_LOG_FIELDS = {"reason", "field_path", "policy_id", "hostname"}
HOSTNAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
POLICY_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
AGGREGATE_MAGIC = b"OSEC-CASE-AGGREGATE-V1\x00"
KNOWN_AGGREGATE_ALGORITHMS = {"OSEC-CASE-AGGREGATE-V1"}
EXPECTED_BASE104_V1 = "bc38711ddf559eb5319eac9b080eeec611e3742d9cf0bbdb09072317cfc975b8"
EXPECTED_NEW21_V1 = "dfda4174b62f27b4132cf157e96b89be2982f9268724dc12f47ebc97c7df8850"
EXPECTED_ALL125_V1 = "75336a374cd9ee82a8c811f380fd9ce6893364d65eaf0fbed76424307b2baa5b"
RAW_DUPLICATE_CASES = {
    "t-017": {
        "action": "reject",
        "scenario": "malformed_json_apparent_duplicate",
        "reason": "config_invalid_json",
        "validation_mode": "malformed_json",
    },
    "d-001": {
        "action": "marker",
        "scenario": None,
        "reason": "config_duplicate",
        "validation_mode": "raw_duplicate_json",
    },
    "d-008": {
        "action": "reject",
        "scenario": "duplicate_json_key_invalid_type",
        "reason": "config_duplicate",
        "validation_mode": "raw_duplicate_json",
    },
    "d-009": {
        "action": "reject",
        "scenario": "semantic_duplicate_invalid_type",
        "reason": "config_invalid_type",
        "validation_mode": "policy_id_type",
    },
    "d-010": {
        "action": "reject",
        "scenario": "duplicate_conflict",
        "reason": "config_duplicate",
        "validation_mode": "duplicate_port",
    },
}

SCENARIO_REGISTRY = {
    "t-017": ("reject", "malformed_json_apparent_duplicate", "config_invalid_json"),
    "t-018": ("reject", "unknown_field_missing_required", "config_unknown_field"),
    "h-019": ("reject", "ip_literal_invalid_hostname", "config_forbidden_ip_literal"),
    "d-008": ("reject", "duplicate_json_key_invalid_type", "config_duplicate"),
    "d-009": ("reject", "semantic_duplicate_invalid_type", "config_invalid_type"),
    "d-010": ("reject", "duplicate_conflict", "config_duplicate"),
    "pr-006": ("reference", "unknown_policy_reference_site_host_uncovered", "config_invalid_policy_reference"),
}

PAYLOAD_TEXT_REGISTRY = {
    "t-004": {"action": "reject", "scenario_present": False, "scenario": None, "reason": "config_invalid_top_level"},
    "t-005": {"action": "reject", "scenario_present": False, "scenario": None, "reason": "config_invalid_top_level"},
    "t-007": {"action": "reject", "scenario_present": False, "scenario": None, "reason": "config_invalid_json"},
    "t-013": {"action": "reject", "scenario_present": False, "scenario": None, "reason": "config_invalid_json"},
    "t-016": {"action": "reject", "scenario_present": False, "scenario": None, "reason": "config_invalid_json"},
    "t-017": {"action": "reject", "scenario_present": True, "scenario": "malformed_json_apparent_duplicate", "reason": "config_invalid_json"},
    "t-018": {"action": "reject", "scenario_present": True, "scenario": "unknown_field_missing_required", "reason": "config_unknown_field"},
    "d-001": {"action": "marker", "scenario_present": False, "scenario": None, "reason": "config_duplicate"},
    "d-008": {"action": "reject", "scenario_present": True, "scenario": "duplicate_json_key_invalid_type", "reason": "config_duplicate"},
    "pr-003": {"action": "reference", "scenario_present": False, "scenario": None, "reason": "config_conflict"},
}

SITE_DRAFT_KEYS = {
    "site_key",
    "hosts",
    "schemes",
    "ports",
    "suggested_policy_id",
    "multi_host",
    "http",
    "notes",
}


def _load_json_no_duplicates(path):
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key: " + key)
            result[key] = value
        return result

    with open(path, "r", encoding="utf-8") as f:
        data = f.read()
        assert not data.startswith("\ufeff")
        return json.loads(data, object_pairs_hook=reject_duplicates)


def _load_fixture():
    return _load_json_no_duplicates(FIXTURE_PATH)


def _case_canonical_bytes(case):
    return json.dumps(case, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _aggregate_v1(cases):
    records = sorted(
        ((case["id"].encode("utf-8"), hashlib.sha256(_case_canonical_bytes(case)).digest()) for case in cases),
        key=lambda record: record[0],
    )
    stream = AGGREGATE_MAGIC + struct.pack(">I", len(records))
    for case_id, digest in records:
        stream += struct.pack(">I", len(case_id)) + case_id + digest
    return hashlib.sha256(stream).hexdigest()


def _raw_json_pairs(payload):
    return json.loads(payload, object_pairs_hook=lambda pairs: pairs)


def _find_duplicate_raw_key(pairs):
    seen = set()
    for key, _value in pairs:
        if key in seen:
            return key
        seen.add(key)
    return None


def _raw_decode_pairs_prefix(payload):
    decoder = json.JSONDecoder(object_pairs_hook=lambda pairs: pairs)
    pairs, end = decoder.raw_decode(payload)
    return pairs, payload[end:]


def _classify_raw_payload(payload):
    try:
        pairs = json.loads(payload, object_pairs_hook=lambda pairs: pairs)
    except json.JSONDecodeError:
        return "config_invalid_json"
    if _find_duplicate_raw_key(pairs) is not None:
        return "config_duplicate"
    return None


def _validate_scenario_case(case):
    case_id = case.get("id")
    if case_id not in SCENARIO_REGISTRY:
        raise AssertionError("unknown scenario case " + repr(case_id))
    expected = SCENARIO_REGISTRY[case_id]
    actual = (case.get("action"), case.get("scenario"), case.get("reason"))
    if actual != expected:
        raise AssertionError(
            "scenario metadata mismatch for %s: %r != %r" % (case_id, actual, expected)
        )


def _validate_payload_text_case(case):
    case_id = case.get("id")
    if case_id not in PAYLOAD_TEXT_REGISTRY:
        raise AssertionError("unknown payload_text case " + repr(case_id))
    expected = PAYLOAD_TEXT_REGISTRY[case_id]
    actual = {
        "action": case.get("action"),
        "scenario_present": "scenario" in case,
        "scenario": case.get("scenario"),
        "reason": case.get("reason"),
    }
    if actual != expected:
        raise AssertionError(
            "payload metadata mismatch for %s: %r != %r" % (case_id, actual, expected)
        )


def _assert_metadata_registries(fixture):
    by_id = {}
    for cases in fixture["categories"].values():
        for case in cases:
            by_id[case["id"]] = case
    scenario_ids = {cid for cid, case in by_id.items() if "scenario" in case}
    if scenario_ids != set(SCENARIO_REGISTRY):
        raise AssertionError(
            "scenario registry mismatch: actual=%s expected=%s" % (sorted(scenario_ids), sorted(SCENARIO_REGISTRY))
        )
    for case_id in SCENARIO_REGISTRY:
        _validate_scenario_case(by_id[case_id])
    payload_ids = {cid for cid, case in by_id.items() if "payload_text" in case}
    if payload_ids != set(PAYLOAD_TEXT_REGISTRY):
        raise AssertionError(
            "payload registry mismatch: actual=%s expected=%s" % (sorted(payload_ids), sorted(PAYLOAD_TEXT_REGISTRY))
        )
    for case_id in PAYLOAD_TEXT_REGISTRY:
        _validate_payload_text_case(by_id[case_id])


def _assert_raw_duplicate_case(case):
    case_id = case["id"]
    if case_id not in RAW_DUPLICATE_CASES:
        raise AssertionError("unknown raw duplicate case " + case_id)
    meta = RAW_DUPLICATE_CASES[case_id]
    assert case["action"] == meta["action"], (case_id, case["action"], meta["action"])
    scenario_present = "scenario" in case
    assert scenario_present == (meta["scenario"] is not None), (case_id, scenario_present, meta["scenario"])
    if meta["scenario"] is not None:
        assert case.get("scenario") == meta["scenario"], (case_id, case.get("scenario"), meta["scenario"])
    assert case.get("reason") == meta["reason"], (case_id, case.get("reason"), meta["reason"])
    mode = meta["validation_mode"]
    if mode == "malformed_json":
        payload = case.get("payload_text")
        assert isinstance(payload, str) and payload, case_id
        assert payload.count('"config_version"') >= 2, case_id
        assert _classify_raw_payload(payload) == "config_invalid_json", case_id
    elif mode == "raw_duplicate_json":
        payload = case.get("payload_text")
        assert isinstance(payload, str) and payload, case_id
        assert _classify_raw_payload(payload) == "config_duplicate", case_id
    elif mode == "policy_id_type":
        values = case.get("policy_id_values")
        assert isinstance(values, list) and values, case_id
        invalid_type = any(
            not isinstance(item.get("policy_id"), str)
            for item in values
            if isinstance(item, dict)
        )
        assert invalid_type, case_id
    elif mode == "duplicate_port":
        ports = case.get("ports", {}).get("https")
        assert isinstance(ports, list) and len(ports) > len(set(ports)), case_id
    else:
        raise AssertionError("unknown validation mode " + mode)
    return case_id


def _assert_raw_duplicate_boundaries(fixture):
    by_id = {}
    for cases in fixture["categories"].values():
        for case in cases:
            by_id[case["id"]] = case
    _assert_metadata_registries(fixture)
    executed = set()
    for case_id in RAW_DUPLICATE_CASES:
        assert case_id in by_id, case_id
        executed.add(_assert_raw_duplicate_case(by_id[case_id]))
    assert executed == set(RAW_DUPLICATE_CASES)
    with pytest.raises(AssertionError):
        _assert_raw_duplicate_case({"id": "unknown-raw-action"})
    with pytest.raises(AssertionError):
        _validate_scenario_case({
            "id": "synthetic-unknown-scenario",
            "action": "reject",
            "scenario": "unknown_raw_scenario_for_contract_test",
            "reason": "config_unknown_field",
        })
    with pytest.raises(AssertionError):
        _validate_scenario_case({
            "id": "t-017",
            "action": "accept",
            "scenario": "malformed_json_apparent_duplicate",
            "reason": "config_invalid_json",
        })
    with pytest.raises(AssertionError):
        _validate_scenario_case({
            "id": "t-017",
            "action": "reject",
            "scenario": "unknown_raw_scenario_for_contract_test",
            "reason": "config_invalid_json",
        })
    with pytest.raises(AssertionError):
        _validate_scenario_case({
            "id": "t-017",
            "action": "reject",
            "scenario": "malformed_json_apparent_duplicate",
            "reason": "config_duplicate",
        })
    with pytest.raises(AssertionError):
        _validate_payload_text_case({
            "id": "synthetic-unknown-payload",
            "action": "reject",
            "reason": "config_invalid_json",
        })
    with pytest.raises(AssertionError):
        _validate_payload_text_case({
            "id": "d-001",
            "action": "reject",
            "reason": "config_duplicate",
        })
    with pytest.raises(AssertionError):
        _validate_payload_text_case({
            "id": "d-001",
            "action": "marker",
            "scenario": "unknown_raw_scenario_for_contract_test",
            "reason": "config_duplicate",
        })
    with pytest.raises(AssertionError):
        _validate_payload_text_case({
            "id": "d-001",
            "action": "marker",
            "reason": "config_invalid_json",
        })
    escaped_payload = '{"a":1,"\\u0061":2}'
    escaped_pairs = _raw_json_pairs(escaped_payload)
    assert _find_duplicate_raw_key(escaped_pairs) == "a"
    trailing = '{"a":1,"a":2} trailing'
    prefix_pairs, remainder = _raw_decode_pairs_prefix(trailing)
    assert _find_duplicate_raw_key(prefix_pairs) == "a"
    assert remainder.strip()
    assert _classify_raw_payload(trailing) == "config_invalid_json"




def test_contract_fixture_integrity():
    fixture = _load_fixture()
    assert set(fixture["frozen_reasons"]) == EXPECTED_REASONS
    assert set(fixture["categories"].keys()) == EXPECTED_CATEGORIES
    reason_counts = {}
    for category, cases in fixture["categories"].items():
        for case in cases:
            reason = case.get("reason")
            if reason is not None:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
    missing_reasons = EXPECTED_REASONS - set(reason_counts)
    assert not missing_reasons, missing_reasons
    assert len(fixture["categories"]["logging"]) == 6
    _assert_parameterized_cases(fixture)
    _assert_raw_duplicate_boundaries(fixture)
    hostnames = fixture["categories"]["hostname"]
    single_label = {case["hostname"]: case for case in hostnames if isinstance(case.get("hostname"), str) and "." not in case["hostname"] and case["hostname"] not in {"2001:db8::1"}}
    assert single_label.get("localhost", {}).get("reason") == "config_invalid_hostname"
    assert single_label.get("example", {}).get("reason") == "config_invalid_hostname"

    executed = set()
    expected = set()
    for category, cases in fixture["categories"].items():
        for case in cases:
            expected.add(case["id"])
    for category, cases in fixture["categories"].items():
        for case in cases:
            action = case["action"]
            assert action in KNOWN_ACTIONS, case["id"]
            assert case["category"] == category, case["id"]
            assert case["allowed"] in (True, False), case["id"]
            reason = case.get("reason")
            if reason is not None:
                assert reason in EXPECTED_REASONS, case["id"]
            if action == "accept":
                assert case["allowed"] is True, case["id"]
                assert reason is None, case["id"]
            elif action == "reject":
                assert case["allowed"] is False, case["id"]
                assert reason is not None, case["id"]
            elif action == "marker":
                assert case["allowed"] is False, case["id"]
                assert reason is not None, case["id"]
                assert "payload_text" in case, case["id"]
            elif action in ("reference", "cross_validation"):
                if case["allowed"]:
                    assert reason is None, case["id"]
                else:
                    assert reason is not None, case["id"]
            elif action == "logging":
                assert case["allowed"] is True, case["id"]
                _assert_logging_case(case)
            elif action == "ordering":
                assert case["allowed"] is True, case["id"]
                assert reason is None, case["id"]
                _assert_ordering_case(case)
            else:
                pytest.fail("unknown action " + case["id"])
            if "canonical" in case:
                assert isinstance(case["canonical"], (str, list)), case["id"]
            executed.add(case["id"])

    assert executed == expected
    draft = fixture["site_migration_draft"]
    assert len(draft) == 5
    for entry in draft:
        assert set(entry.keys()) == SITE_DRAFT_KEYS
        assert entry["site_key"]
        assert isinstance(entry["hosts"], list) and entry["hosts"]
        assert isinstance(entry["schemes"], list) and entry["schemes"]
        assert isinstance(entry["ports"], list) and entry["ports"]
        assert entry["suggested_policy_id"]
        assert isinstance(entry["multi_host"], bool)
        assert isinstance(entry["http"], bool)
    assert {entry["site_key"] for entry in draft} == {
        "czj_beijing",
        "czj_hangzhou",
        "sxcs_shaoxing",
        "sc_czt",
        "sd_czt",
    }


def test_aggregate_v1_contract():
    fixture = _load_fixture()
    assert fixture["algorithm"] in KNOWN_AGGREGATE_ALGORITHMS
    all_cases = [case for cases in fixture["categories"].values() for case in cases]
    all_ids = [case["id"] for case in all_cases]
    baseline_ids = fixture["baseline_case_ids"]
    assert len(all_ids) == 125
    assert len(set(all_ids)) == 125
    assert len(baseline_ids) == 104
    assert len(set(baseline_ids)) == 104
    assert set(baseline_ids) <= set(all_ids)
    new_ids = [cid for cid in all_ids if cid not in set(baseline_ids)]
    assert len(new_ids) == 21
    assert not (set(baseline_ids) & set(new_ids))
    assert set(baseline_ids) | set(new_ids) == set(all_ids)
    by_id = {case["id"]: case for case in all_cases}
    base_cases = [by_id[cid] for cid in baseline_ids]
    new_cases = [by_id[cid] for cid in new_ids]
    actual_base = _aggregate_v1(base_cases)
    actual_new = _aggregate_v1(new_cases)
    actual_all = _aggregate_v1(all_cases)
    assert actual_base == EXPECTED_BASE104_V1
    assert actual_new == EXPECTED_NEW21_V1
    assert actual_all == EXPECTED_ALL125_V1
    assert fixture["expected_base104_v1"] == EXPECTED_BASE104_V1
    assert fixture["expected_new21_v1"] == EXPECTED_NEW21_V1
    assert fixture["expected_all125_v1"] == EXPECTED_ALL125_V1
    assert actual_base == fixture["expected_base104_v1"]
    assert actual_new == fixture["expected_new21_v1"]
    assert actual_all == fixture["expected_all125_v1"]
    assert _aggregate_v1(list(reversed(all_cases))) == actual_all
    mutated = copy.deepcopy(all_cases)
    mutated[0]["description"] = mutated[0]["description"] + " MUTATED"
    assert _aggregate_v1(mutated) != actual_all
    mutated_base = copy.deepcopy(base_cases)
    mutated_base[0]["description"] = mutated_base[0]["description"] + " MUTATED"
    assert _aggregate_v1(mutated_base) != actual_base
    mutated_new = copy.deepcopy(new_cases)
    mutated_new[0]["description"] = mutated_new[0]["description"] + " MUTATED"
    assert _aggregate_v1(mutated_new) != actual_new


def test_contract_fixture_no_forbidden_config_fields():
    fixture = _load_fixture()
    forbidden = {
        "allowed_subdomain_roots",
        "redirect_allowed_domains",
        "redirect_allowed_subdomain_roots",
        "allow_http",
        "allow_controlled_subdomains",
        "proxy",
        "allow_private",
        "insecure_tls",
        "budget_override",
        "profile_override",
        "credentials",
        "url",
    }
    for case in fixture["categories"]["forbidden_field"]:
        assert case["field"] in forbidden
        assert case["reason"] == "config_unknown_field"

def test_contract_schema_hostname_pattern():
    schema = _load_json_no_duplicates(SCHEMA_PATH)
    pattern = schema["properties"]["policies"]["items"]["properties"]["allowed_domains"]["items"]["pattern"]
    assert re.fullmatch(pattern, "localhost") is None
    assert re.fullmatch(pattern, "example") is None
    assert re.fullmatch(pattern, "example-.com") is None
    assert re.fullmatch(pattern, "example.com") is not None
    assert re.fullmatch(pattern, "a-b.example") is not None

def _assert_logging_case(case):
    rule = case.get("logging_rule")
    assert rule in LOGGING_RULES, case["id"]
    raw_input = case.get("raw_input")
    assert isinstance(raw_input, str) and raw_input, case["id"]
    expected_log = case.get("expected_log")
    assert isinstance(expected_log, dict) and expected_log, case["id"]
    required = case.get("required_log_fields")
    assert isinstance(required, list) and required, case["id"]
    forbidden = case.get("forbidden_values")
    assert isinstance(forbidden, list), case["id"]
    for value in forbidden:
        assert isinstance(value, str) and value, case["id"]
        assert value in raw_input, (case["id"], value)
    serialized = json.dumps(expected_log, sort_keys=True, ensure_ascii=False)
    for value in forbidden:
        assert value not in serialized, (case["id"], value)
    assert set(expected_log) <= ALLOWED_LOG_FIELDS, case["id"]
    for field in required:
        assert field in expected_log, (case["id"], field)
    if "reason" in expected_log:
        assert expected_log["reason"] in EXPECTED_REASONS, case["id"]
    if "hostname" in expected_log:
        hostname = expected_log["hostname"]
        assert isinstance(hostname, str) and HOSTNAME_RE.fullmatch(hostname), case["id"]
        assert "://" not in hostname and "/" not in hostname and "?" not in hostname and "#" not in hostname, case["id"]
    if "policy_id" in expected_log:
        assert isinstance(expected_log["policy_id"], str) and POLICY_ID_RE.fullmatch(expected_log["policy_id"]), case["id"]


def test_contract_logging_rules():
    fixture = _load_fixture()
    executed = set()
    for case in fixture["categories"]["logging"]:
        _assert_logging_case(case)
        executed.add(case["logging_rule"])
    assert executed == LOGGING_RULES

def _assert_ordering_case(case):
    order_lists = [
        case.get("expected_field_order"),
        case.get("expected_site_order"),
        case.get("expected_policy_order"),
    ]
    assert any(isinstance(x, list) and x for x in order_lists), case["id"]
    for order in order_lists:
        if order is not None:
            assert isinstance(order, list) and order, case["id"]
            assert len(order) == len(set(order)), case["id"]


def _assert_parameterized_cases(fixture):
    by_id = {}
    for category, cases in fixture["categories"].items():
        for case in cases:
            by_id[case["id"]] = case
    assert by_id["t-011"]["source_size"] == 1048577
    assert by_id["t-012"]["depth"] == 33
    for cid in ("t-014", "t-015"):
        payload_hex = by_id[cid].get("payload_hex")
        assert isinstance(payload_hex, str) and payload_hex, cid
        bytes.fromhex(payload_hex)
    for cid in ("t-008", "t-009", "t-010"):
        assert by_id[cid]["source_state"] in {"unreadable", "directory", "non_regular_source"}


VECTOR_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "outbound_security_aggregate_vectors.json")
VECTOR_VALID_NAMES = {
    "canonical_case_minimal", "canonical_html_specials", "canonical_u2028", "canonical_u2029",
    "canonical_literal_backslash_u", "canonical_cjk", "canonical_quote_backslash", "canonical_control_short",
    "canonical_control_u00xx", "canonical_slash", "canonical_u007f_c1", "canonical_unicode_object_key",
    "canonical_nested_key_sort", "canonical_null_empty_distinction", "canonical_type_int_bool_string",
    "canonical_integer_zero", "canonical_negative_zero", "canonical_large_integer", "canonical_surrogate_pair",
    "canonical_internal_bom", "canonical_whitespace_equivalent", "canonical_crlf_equivalent",
    "canonical_key_sort_ascii_cjk_nonbmp", "canonical_depth_128", "canonical_case_id_64",
}
VECTOR_REJECT_NAMES = {
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
VECTOR_RECIPE_NAMES = {
    "recipe_integer_4097_digits", "recipe_array_10001", "recipe_string_1mib_plus_1", "recipe_file_size_16mib_plus_1",
    "recipe_depth_129", "recipe_object_1001_members", "recipe_case_count_10001",
}
VECTOR_TARGETS = {"canonical_json", "canonical_case", "strict_decode", "evidence_limits", "canonical"}
VECTOR_STAGES = {"strict_decode", "evidence_limits", "canonical"}
VECTOR_GENERATORS = {"repeat_unit", "nested_container", "object_members", "file_size_pad", "case_dataset"}
VECTOR_OUTPUT_KINDS = {"raw_bytes", "typed_dataset"}
VECTOR_ERRORS = {
    "strict_decode_invalid_json", "strict_decode_invalid_utf8", "strict_decode_bom", "strict_decode_duplicate_key",
    "strict_decode_lone_surrogate", "strict_decode_trailing_data", "evidence_limit_file_size",
    "evidence_limit_nesting_depth", "evidence_limit_integer_digits", "evidence_limit_array_length",
    "evidence_limit_object_members", "evidence_limit_string_length", "evidence_limit_case_count",
    "canonical_invalid_value_type", "canonical_non_integer_number", "canonical_invalid_unicode",
    "canonical_root_not_object", "canonical_missing_id", "canonical_invalid_id", "aggregate_empty_set",
    "aggregate_duplicate_id", "aggregate_invalid_digest_length", "aggregate_unknown_algorithm",
    "aggregate_count_overflow", "aggregate_length_overflow", "manifest_invalid_structure", "manifest_unknown_field",
    "manifest_count_mismatch", "manifest_case_digest_mismatch", "manifest_category_mismatch",
    "manifest_aggregate_mismatch", "manifest_invalid_dataset", "manifest_invalid_category",
    "manifest_duplicate_category", "manifest_invalid_cohort", "manifest_duplicate_cohort", "manifest_cohort_mismatch",
    "seal_record_invalid_structure", "seal_record_hash_mismatch", "seal_record_git_binding_failed",
}


def _load_vector_fixture():
    return _load_json_no_duplicates(VECTOR_FIXTURE_PATH)


def _validate_hex_utf8(value, label, allow_empty=False, require_utf8=True):
    assert isinstance(value, str), label
    if not allow_empty:
        assert value, label
    assert len(value) % 2 == 0, label
    assert value == value.lower(), label
    data = bytes.fromhex(value)
    if require_utf8:
        data.decode("utf-8")
    return data


def _validate_nested_zero_array(data, expected_depth):
    assert isinstance(data, bytes), "data must be bytes"
    assert isinstance(expected_depth, int) and expected_depth >= 1, "expected_depth must be positive"
    assert data == b"[" * expected_depth + b"0" + b"]" * expected_depth, "nested zero array structure"
    depth = 0
    max_depth = 0
    scalar_seen = False
    for index, byte_value in enumerate(data):
        if byte_value == ord("["):
            assert not scalar_seen, "open bracket after scalar"
            depth += 1
            max_depth = max(max_depth, depth)
        elif byte_value == ord("0"):
            assert not scalar_seen, "duplicate scalar"
            scalar_seen = True
            assert depth == expected_depth, "scalar at wrong depth"
        elif byte_value == ord("]"):
            assert scalar_seen, "close bracket before scalar"
            depth -= 1
            assert depth >= 0, "depth went negative"
        else:
            raise AssertionError("unexpected byte 0x%02x" % byte_value)
    assert scalar_seen, "missing scalar"
    assert depth == 0, "unclosed brackets"
    assert max_depth == expected_depth, "max depth mismatch"
    assert len(data) == 2 * expected_depth + 1, "length mismatch"


def _generate_vector_recipe_output(recipe):
    gen = recipe["generator"]
    prefix = bytes.fromhex(recipe["prefix_hex"])
    unit = bytes.fromhex(recipe["unit_hex"])
    separator = bytes.fromhex(recipe["separator_hex"]) if recipe["separator_hex"] else b""
    suffix = bytes.fromhex(recipe["suffix_hex"])
    count = recipe["count"]
    if gen == "repeat_unit":
        return prefix + unit + b"".join(separator + unit for _ in range(count - 1)) + suffix
    if gen == "nested_container":
        return prefix * count + unit + suffix * count
    if gen == "object_members":
        return prefix + b",".join(b'"k%d":0' % i for i in range(count)) + suffix
    if gen == "file_size_pad":
        return prefix + unit * count + suffix
    if gen == "case_dataset":
        return prefix + b",".join(b'{"id":"c%d"}' % i for i in range(count)) + suffix
    raise AssertionError("unknown generator " + gen)


def _assert_recipe_depth_129(recipe):
    data = _generate_vector_recipe_output(recipe)
    assert hashlib.sha256(data).hexdigest() == recipe["expected_input_sha256"], recipe["name"]
    _validate_nested_zero_array(data, 129)


def _validate_vector_fixture(fixture):
    assert set(fixture.keys()) == {"format_version", "profile", "provenance", "valid_vectors", "reject_vectors", "resource_recipes"}
    assert fixture["format_version"] == "1.0"
    assert fixture["profile"] == "OSEC-EVIDENCE-PROFILE-V2"
    assert fixture["provenance"] == {"method": "independently_constructed"}
    valid = fixture["valid_vectors"]
    reject = fixture["reject_vectors"]
    recipes = fixture["resource_recipes"]
    assert len(valid) == 25 and len(reject) == 35 and len(recipes) == 7
    all_names = [v["name"] for v in valid] + [r["name"] for r in reject] + [r["name"] for r in recipes]
    assert len(all_names) == len(set(all_names))
    assert {v["name"] for v in valid} == VECTOR_VALID_NAMES
    assert {r["name"] for r in reject} == VECTOR_REJECT_NAMES
    assert {r["name"] for r in recipes} == VECTOR_RECIPE_NAMES
    by_name = {}
    for v in valid + reject:
        by_name[v["name"]] = v
    for v in valid:
        assert set(v.keys()) == {"name", "target", "input_json_utf8_hex", "expected_canonical_utf8_hex", "expected_case_sha256"}
        assert v["target"] in {"canonical_json", "canonical_case"}
        _validate_hex_utf8(v["input_json_utf8_hex"], v["name"] + " input")
        exp = _validate_hex_utf8(v["expected_canonical_utf8_hex"], v["name"] + " expected")
        assert not exp.startswith(b"\xef\xbb\xbf")
        assert not exp.endswith(b"\n")
        if v["target"] == "canonical_case":
            assert isinstance(v["expected_case_sha256"], str)
            assert len(v["expected_case_sha256"]) == 64
            assert v["expected_case_sha256"] == v["expected_case_sha256"].lower()
            assert hashlib.sha256(exp).hexdigest() == v["expected_case_sha256"]
        else:
            assert v["expected_case_sha256"] is None
    assert by_name["canonical_integer_zero"]["expected_canonical_utf8_hex"] == by_name["canonical_negative_zero"]["expected_canonical_utf8_hex"]
    assert by_name["canonical_whitespace_equivalent"]["expected_canonical_utf8_hex"] == by_name["canonical_crlf_equivalent"]["expected_canonical_utf8_hex"]
    assert "5c7532303238" in by_name["canonical_literal_backslash_u"]["expected_canonical_utf8_hex"]
    depth128_input = bytes.fromhex(by_name["canonical_depth_128"]["input_json_utf8_hex"])
    depth128_expected = bytes.fromhex(by_name["canonical_depth_128"]["expected_canonical_utf8_hex"])
    _validate_nested_zero_array(depth128_input, 128)
    _validate_nested_zero_array(depth128_expected, 128)
    assert depth128_input == depth128_expected
    recipe_by_name = {r["name"]: r for r in recipes}
    for rj in reject:
        assert set(rj.keys()) == {"name", "target", "input_json_utf8_hex", "recipe", "expected_stage", "expected_error"}
        assert rj["target"] in {"strict_decode", "evidence_limits", "canonical"}
        assert rj["expected_stage"] == rj["target"]
        assert rj["expected_error"] in VECTOR_ERRORS
        if rj["recipe"] is None:
            assert isinstance(rj["input_json_utf8_hex"], str)
            _validate_hex_utf8(rj["input_json_utf8_hex"], rj["name"], allow_empty=True, require_utf8=False)
        else:
            assert rj["input_json_utf8_hex"] is None
            assert rj["recipe"] in recipe_by_name
    for r in recipes:
        assert set(r.keys()) == {"name", "generator", "prefix_hex", "unit_hex", "separator_hex", "suffix_hex", "count", "output_kind", "expected_input_sha256", "expected_stage", "expected_error"}
        assert r["generator"] in VECTOR_GENERATORS
        assert r["output_kind"] in VECTOR_OUTPUT_KINDS
        assert isinstance(r["count"], int) and r["count"] > 0
        assert len(r["expected_input_sha256"]) == 64
        assert r["expected_error"] in VECTOR_ERRORS
    for r in recipes:
        refs = [rj for rj in reject if rj["recipe"] == r["name"]]
        assert len(refs) == 1
        assert refs[0]["expected_stage"] == r["expected_stage"]
        assert refs[0]["expected_error"] == r["expected_error"]
    for rj in reject:
        if rj["recipe"] is not None:
            r = recipe_by_name[rj["recipe"]]
            assert rj["expected_stage"] == r["expected_stage"]
            assert rj["expected_error"] == r["expected_error"]


def test_aggregate_vectors_structure_and_inventory():
    fixture = _load_vector_fixture()
    _validate_vector_fixture(fixture)
    bad_top = dict(fixture)
    bad_top["unknown_top"] = True
    with pytest.raises(AssertionError):
        _validate_vector_fixture(bad_top)
    bad_valid = dict(fixture)
    bad_valid["valid_vectors"] = [dict(fixture["valid_vectors"][0])]
    bad_valid["valid_vectors"][0]["unknown_field"] = True
    with pytest.raises(AssertionError):
        _validate_vector_fixture(bad_valid)
    bad_recipe = dict(fixture)
    bad_recipe["resource_recipes"] = [dict(fixture["resource_recipes"][0])]
    bad_recipe["resource_recipes"][0]["generator"] = "unknown_generator"
    with pytest.raises(AssertionError):
        _validate_vector_fixture(bad_recipe)


def test_aggregate_vectors_resource_recipes():
    fixture = _load_vector_fixture()
    executed = set()
    for recipe in fixture["resource_recipes"]:
        data = _generate_vector_recipe_output(recipe)
        assert hashlib.sha256(data).hexdigest() == recipe["expected_input_sha256"], recipe["name"]
        if recipe["name"] == "recipe_file_size_16mib_plus_1":
            assert len(data) == 16777217
        elif recipe["name"] == "recipe_depth_129":
            _validate_nested_zero_array(data, 129)
        elif recipe["name"] == "recipe_integer_4097_digits":
            assert len(data) == 4097
        elif recipe["name"] == "recipe_array_10001":
            assert data.count(b",") == 10000
        elif recipe["name"] == "recipe_object_1001_members":
            keys = json.loads(data).keys()
            assert len(keys) == 1001
        elif recipe["name"] == "recipe_string_1mib_plus_1":
            assert len(data) == 1048585
        elif recipe["name"] == "recipe_case_count_10001":
            assert len(json.loads(data)) == 10001
        executed.add(recipe["name"])
    assert executed == VECTOR_RECIPE_NAMES


def test_aggregate_vectors_depth_structure_negatives():
    base = _load_vector_fixture()

    def mutate_valid(fx, data):
        for vector in fx["valid_vectors"]:
            if vector["name"] == "canonical_depth_128":
                vector["input_json_utf8_hex"] = data.hex()
                vector["expected_canonical_utf8_hex"] = data.hex()
                return
        raise AssertionError("canonical_depth_128 missing")

    def mutate_recipe(fx, **kwargs):
        for recipe in fx["resource_recipes"]:
            if recipe["name"] == "recipe_depth_129":
                recipe.update(kwargs)
                return
        raise AssertionError("recipe_depth_129 missing")

    def recipe_by_name(fx, name):
        for recipe in fx["resource_recipes"]:
            if recipe["name"] == name:
                return recipe
        raise AssertionError("recipe missing: " + name)

    valid_cases = [
        b"[" * 127 + b"0" + b"]" * 127,
        b"[" * 129 + b"0" + b"]" * 129,
        b"0" + b"[" * 128 + b"]" * 128,
        b"[" * 128 + b"]" * 128 + b"0",
        b"[" * 128 + b"0" + b"]" * 127,
        b"[" * 128 + b"0" + b"]" * 128 + b"x",
    ]
    for data in valid_cases:
        fx = copy.deepcopy(base)
        mutate_valid(fx, data)
        with pytest.raises(AssertionError):
            _validate_vector_fixture(fx)

    fx = copy.deepcopy(base)
    mutate_recipe(fx, count=128)
    with pytest.raises(AssertionError):
        _assert_recipe_depth_129(recipe_by_name(fx, "recipe_depth_129"))

    fx = copy.deepcopy(base)
    mutate_recipe(fx, count=130)
    with pytest.raises(AssertionError):
        _assert_recipe_depth_129(recipe_by_name(fx, "recipe_depth_129"))

    fx = copy.deepcopy(base)
    mutate_recipe(fx, count=130)
    with pytest.raises(AssertionError):
        _assert_recipe_depth_129(recipe_by_name(fx, "recipe_depth_129"))

    fx = copy.deepcopy(base)
    digest = recipe_by_name(fx, "recipe_depth_129")["expected_input_sha256"]
    mutate_recipe(fx, expected_input_sha256=("0" if digest[0] != "0" else "1") + digest[1:])
    with pytest.raises(AssertionError):
        _assert_recipe_depth_129(recipe_by_name(fx, "recipe_depth_129"))

    fx = copy.deepcopy(base)
    mutate_recipe(fx, unit_hex=b"[]".hex())
    with pytest.raises(AssertionError):
        _assert_recipe_depth_129(recipe_by_name(fx, "recipe_depth_129"))

    fx = copy.deepcopy(base)
    wrong_order = b"]" * 129 + b"0" + b"[" * 129
    mutate_recipe(
        fx,
        prefix_hex=b"]".hex(),
        suffix_hex=b"[".hex(),
        expected_input_sha256=hashlib.sha256(wrong_order).hexdigest(),
    )
    with pytest.raises(AssertionError):
        _assert_recipe_depth_129(recipe_by_name(fx, "recipe_depth_129"))


def test_aggregate_vectors_unknown_metadata_negatives():
    base = _load_vector_fixture()

    def run_bad(mutate):
        fx = copy.deepcopy(base)
        mutate(fx)
        with pytest.raises(AssertionError):
            _validate_vector_fixture(fx)

    def valid_by_name(fx, name):
        for vector in fx["valid_vectors"]:
            if vector["name"] == name:
                return vector
        raise AssertionError("valid vector missing: " + name)

    def reject_by_name(fx, name):
        for vector in fx["reject_vectors"]:
            if vector["name"] == name:
                return vector
        raise AssertionError("reject vector missing: " + name)

    def recipe_by_name(fx, name):
        for recipe in fx["resource_recipes"]:
            if recipe["name"] == name:
                return recipe
        raise AssertionError("recipe missing: " + name)

    run_bad(lambda fx: valid_by_name(fx, "canonical_case_minimal").__setitem__("target", "unknown_target"))
    run_bad(lambda fx: reject_by_name(fx, "strict_bom").__setitem__("target", "unknown_target"))
    run_bad(lambda fx: reject_by_name(fx, "strict_bom").__setitem__("expected_stage", "unknown_stage"))
    run_bad(lambda fx: reject_by_name(fx, "strict_bom").__setitem__("unknown_field", True))
    run_bad(lambda fx: recipe_by_name(fx, "recipe_depth_129").__setitem__("unknown_field", True))
    run_bad(lambda fx: recipe_by_name(fx, "recipe_depth_129").__setitem__("generator", "unknown_generator"))
    run_bad(lambda fx: recipe_by_name(fx, "recipe_depth_129").__setitem__("output_kind", "unknown_kind"))
    run_bad(lambda fx: recipe_by_name(fx, "recipe_depth_129").__setitem__("expected_stage", "unknown_stage"))
    run_bad(lambda fx: fx.__setitem__("unknown_top_level", True))
