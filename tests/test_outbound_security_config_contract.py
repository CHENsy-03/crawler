"""TASK-022E-B contract fixture integrity tests.

This module validates the shared outbound security configuration fixture only.
It must not import production configuration loaders, read production config,
perform DNS, or open sockets.
"""

import json
import os
import re

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
}
KNOWN_ACTIONS = {"accept", "reject", "marker", "reference", "cross_validation", "logging"}
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
