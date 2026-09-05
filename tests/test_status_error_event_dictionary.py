import copy
import json
import re
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft7Validator

from protocol import status_error_event as see


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "status_error_event_dictionary_v1.json"
SCHEMA_PATH = ROOT / "protocol" / "status_error_event_dictionary.schema.json"


def _load():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8")), json.loads(
        SCHEMA_PATH.read_text(encoding="utf-8")
    )


def _require_unique(entries, key, label):
    raw = [key(item) for item in entries]
    assert len(raw) == len(set(raw)), label


def _assert_schema_negative(fixture, validator, keyword=None, path=None):
    errors = list(validator.iter_errors(fixture))
    assert errors
    if keyword is not None:
        assert any(error.validator == keyword for error in errors), errors
    if path is not None:
        assert any(list(error.absolute_path) == path for error in errors), errors


def test_schema_self_validates_and_fixture_validates():
    fixture, schema = _load()
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema)
    validator.validate(fixture)


def test_schema_negative_cases():
    fixture, schema = _load()
    validator = Draft7Validator(schema)

    missing_root = copy.deepcopy(fixture)
    del missing_root["events"]
    _assert_schema_negative(missing_root, validator)

    missing_status_field = copy.deepcopy(fixture)
    del missing_status_field["statuses"][0]["canonical_symbol"]
    _assert_schema_negative(missing_status_field, validator)

    wrong_type = copy.deepcopy(fixture)
    wrong_type["statuses"][0]["domain"] = 3
    _assert_schema_negative(wrong_type, validator)

    empty_symbol = copy.deepcopy(fixture)
    empty_symbol["statuses"][0]["canonical_symbol"] = ""
    _assert_schema_negative(empty_symbol, validator)

    invalid_family = copy.deepcopy(fixture)
    invalid_family["events"][0]["family"] = "NOT_A_FAMILY"
    _assert_schema_negative(invalid_family, validator)

    invalid_retry = copy.deepcopy(fixture)
    invalid_retry["errors"][0]["retryability"] = "SOMETIMES"
    _assert_schema_negative(invalid_retry, validator)

    unknown_field = copy.deepcopy(fixture)
    unknown_field["events"][0]["unknown"] = True
    _assert_schema_negative(unknown_field, validator)

    remove_audit = copy.deepcopy(fixture)
    remove_audit["events"] = [
        event for event in remove_audit["events"] if event["family"] != "AUDIT_EVENT"
    ]
    _assert_schema_negative(remove_audit, validator)

    null_bypass = copy.deepcopy(fixture)
    null_bypass["errors"][0]["canonical_code"] = None
    _assert_schema_negative(null_bypass, validator)


def test_fixture_has_no_duplicates():
    fixture, _ = _load()
    _require_unique(
        fixture["statuses"],
        lambda item: (item["domain"], item["canonical_symbol"]),
        "status",
    )
    _require_unique(fixture["errors"], lambda item: item["canonical_code"], "error")
    _require_unique(
        fixture["events"],
        lambda item: (item["family"], item["version"], item["event_type"]),
        "event",
    )
    _require_unique(fixture["legacy_aliases"], lambda item: item["legacy"], "alias")
    _require_unique(
        fixture["compatibility_decisions"], lambda item: item["id"], "decision"
    )


def test_duplicate_negative_cases():
    fixture, _ = _load()

    dup_status = copy.deepcopy(fixture)
    status_extra = dict(dup_status["statuses"][0])
    status_extra["wire_value"] = "DIFFERENT_WIRE"
    assert status_extra != dup_status["statuses"][0]
    dup_status["statuses"].append(status_extra)
    with pytest.raises(AssertionError):
        _require_unique(
            dup_status["statuses"],
            lambda item: (item["domain"], item["canonical_symbol"]),
            "status",
        )

    dup_error = copy.deepcopy(fixture)
    error_extra = dict(dup_error["errors"][0])
    error_extra["retryability"] = "ALWAYS" if error_extra["retryability"] != "ALWAYS" else "NEVER"
    assert error_extra != dup_error["errors"][0]
    dup_error["errors"].append(error_extra)
    with pytest.raises(AssertionError):
        _require_unique(dup_error["errors"], lambda item: item["canonical_code"], "error")

    dup_event = copy.deepcopy(fixture)
    event_extra = dict(dup_event["events"][0])
    event_extra["producer"] = "different_producer"
    assert event_extra != dup_event["events"][0]
    dup_event["events"].append(event_extra)
    with pytest.raises(AssertionError):
        _require_unique(
            dup_event["events"],
            lambda item: (item["family"], item["version"], item["event_type"]),
            "event",
        )

    dup_alias = copy.deepcopy(fixture)
    alias_extra = dict(dup_alias["legacy_aliases"][0])
    alias_extra["target"] = "different_target"
    assert alias_extra != dup_alias["legacy_aliases"][0]
    dup_alias["legacy_aliases"].append(alias_extra)
    with pytest.raises(AssertionError):
        _require_unique(
            dup_alias["legacy_aliases"], lambda item: item["legacy"], "alias"
        )

    dup_decision = copy.deepcopy(fixture)
    decision_extra = dict(dup_decision["compatibility_decisions"][0])
    decision_extra["decision"] = "different decision"
    assert decision_extra != dup_decision["compatibility_decisions"][0]
    dup_decision["compatibility_decisions"].append(decision_extra)
    with pytest.raises(AssertionError):
        _require_unique(
            dup_decision["compatibility_decisions"], lambda item: item["id"], "decision"
        )


def test_status_metadata():
    fixture, _ = _load()
    allowed_type = {"USER_VISIBLE", "RUNTIME", "INTERNAL", "TERMINAL", "OPERATIONAL"}
    allowed_class = {"CANONICAL", "COMPATIBILITY_ALIAS", "HISTORICAL", "CONFLICT"}
    for item in fixture["statuses"]:
        assert item["domain"]
        assert re.fullmatch(r"[a-z][a-z0-9_]*", item["domain"])
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*", item["canonical_symbol"])
        assert item["wire_value"]
        assert item["type"] in allowed_type
        assert isinstance(item["terminal"], bool)
        assert item["normative_source"]
        assert item["semantics"]
        assert item["compatibility_class"] in allowed_class


def test_error_metadata_and_counts():
    fixture, _ = _load()
    counts = {}
    for item in fixture["errors"]:
        assert item["canonical_code"]
        assert re.fullmatch(r"[a-z][a-z0-9_]*", item["canonical_code"])
        assert item["namespace"]
        assert item["retryability"] in {"NEVER", "ALWAYS", "CONDITIONAL"}
        counts[item["retryability"]] = counts.get(item["retryability"], 0) + 1
        assert item["http_status"] is None or 100 <= item["http_status"] <= 599
        assert isinstance(item["client_exposable"], bool)
        assert item["normative_source"]
        assert item["meaning"]
        assert item["compatibility_class"] in {
            "CANONICAL",
            "COMPATIBILITY_ALIAS",
            "HISTORICAL",
            "CONFLICT",
        }
        if item["client_exposable"]:
            assert item["http_status"] is not None
    assert counts == {"NEVER": 46, "ALWAYS": 8, "CONDITIONAL": 9}
    assert len(fixture["errors"]) == 63


def test_scenario_error_metadata_and_boundaries():
    fixture, _ = _load()
    by_code = {item["canonical_code"]: item for item in fixture["errors"]}
    expected = {
        "validation_error": 400,
        "task_limit_exceeded": 422,
        "event_history_expired": 410,
        "over_limit": 429,
        "export_expired": 410,
    }
    for code, status in expected.items():
        item = by_code[code]
        assert item["client_exposable"] is True
        assert item["compatibility_class"] == "CANONICAL"
        assert item["http_status"] == status
    assert fixture["contract_version"] == "1.1"
    assert len(fixture["compatibility_decisions"]) == 6


def test_event_metadata_and_counts():
    fixture, _ = _load()
    counts = {}
    for item in fixture["events"]:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", item["event_type"])
        assert item["family"] in {
            "TASK_EVENT",
            "STREAM_MESSAGE",
            "AUDIT_EVENT",
            "CONTROL_EVENT",
            "OPERATIONAL_EVENT",
        }
        assert item["transport"]
        assert re.fullmatch(r"\d+(\.\d+)?", item["version"])
        assert item["producer"]
        assert item["consumer"]
        assert item["normative_source"]
        assert item["payload_contract_owner"]
        counts[item["family"]] = counts.get(item["family"], 0) + 1
    assert counts == {
        "TASK_EVENT": 7,
        "STREAM_MESSAGE": 6,
        "AUDIT_EVENT": 1,
        "CONTROL_EVENT": 4,
        "OPERATIONAL_EVENT": 4,
    }
    assert len(fixture["events"]) == 22
    audit = [item for item in fixture["events"] if item["family"] == "AUDIT_EVENT"]
    assert len(audit) == 1
    expected_audit = audit[0]
    assert expected_audit["event_type"] == "global_block_legal_request_activated"
    assert expected_audit["producer"] == "go_api"
    assert expected_audit["consumer"] == "go_api"
    assert expected_audit["transport"] == "in_process"
    assert expected_audit["persistence_target"] == "mysql_audit_log"
    assert expected_audit["normative_source"] == "V1.1 10.3"
    assert expected_audit["payload_contract_owner"] == "DEV-004"
    assert "global_block_legal_request_activated" not in {
        item["event_type"] for item in fixture["events"] if item["family"] != "AUDIT_EVENT"
    }


def test_audit_semantics_negative_cases():
    fixture, schema = _load()
    validator = Draft7Validator(schema)
    audit_index = next(
        index
        for index, item in enumerate(fixture["events"])
        if item["family"] == "AUDIT_EVENT"
    )

    old_transport = copy.deepcopy(fixture)
    old_transport["events"][audit_index]["transport"] = "audit_log"
    _assert_schema_negative(old_transport, validator)

    missing_persistence = copy.deepcopy(fixture)
    del missing_persistence["events"][audit_index]["persistence_target"]
    _assert_schema_negative(missing_persistence, validator)

    audit_service = copy.deepcopy(fixture)
    audit_service["events"][audit_index]["consumer"] = "audit_service"
    _assert_schema_negative(audit_service, validator)

    wrong_payload_owner = copy.deepcopy(fixture)
    wrong_payload_owner["events"][audit_index]["payload_contract_owner"] = "DEV-005"
    _assert_schema_negative(wrong_payload_owner, validator)

    wrong_source = copy.deepcopy(fixture)
    wrong_source["events"][audit_index]["normative_source"] = "V1.1 10.4"
    _assert_schema_negative(wrong_source, validator)

    no_audit = copy.deepcopy(fixture)
    no_audit["events"] = [
        item for item in no_audit["events"] if item["family"] != "AUDIT_EVENT"
    ]
    _assert_schema_negative(no_audit, validator)


def test_persistence_target_bidirectional_and_transport_case_negative_cases():
    fixture, schema = _load()
    validator = Draft7Validator(schema)

    audit_index = next(
        index
        for index, item in enumerate(fixture["events"])
        if item["family"] == "AUDIT_EVENT"
    )
    control_index = next(
        index
        for index, item in enumerate(fixture["events"])
        if item["family"] == "CONTROL_EVENT"
    )
    task_index = next(
        index
        for index, item in enumerate(fixture["events"])
        if item["family"] == "TASK_EVENT"
    )

    control_with_persistence = copy.deepcopy(fixture)
    control_with_persistence["events"][control_index]["persistence_target"] = "mysql_audit_log"
    _assert_schema_negative(
        control_with_persistence,
        validator,
        keyword="not",
        path=["events", control_index],
    )

    task_with_persistence = copy.deepcopy(fixture)
    task_with_persistence["events"][task_index]["persistence_target"] = "some_target"
    _assert_schema_negative(
        task_with_persistence,
        validator,
        keyword="not",
        path=["events", task_index],
    )

    non_audit_null = copy.deepcopy(fixture)
    non_audit_null["events"][task_index]["persistence_target"] = None
    _assert_schema_negative(
        non_audit_null,
        validator,
        keyword="not",
        path=["events", task_index],
    )

    audit_missing = copy.deepcopy(fixture)
    del audit_missing["events"][audit_index]["persistence_target"]
    _assert_schema_negative(
        audit_missing,
        validator,
        keyword="required",
        path=["events", audit_index],
    )

    audit_unknown = copy.deepcopy(fixture)
    audit_unknown["events"][audit_index]["persistence_target"] = "unknown_target"
    _assert_schema_negative(
        audit_unknown,
        validator,
        keyword="const",
        path=["events", audit_index, "persistence_target"],
    )

    audit_empty = copy.deepcopy(fixture)
    audit_empty["events"][audit_index]["persistence_target"] = ""
    _assert_schema_negative(
        audit_empty,
        validator,
        keyword="const",
        path=["events", audit_index, "persistence_target"],
    )

    lower_sse = copy.deepcopy(fixture)
    lower_sse["events"][task_index]["transport"] = "sse"
    _assert_schema_negative(
        lower_sse,
        validator,
        keyword="enum",
        path=["events", task_index, "transport"],
    )


def test_aliases_and_decisions_metadata():
    fixture, _ = _load()
    codes = {item["canonical_code"] for item in fixture["errors"]}
    for alias in fixture["legacy_aliases"]:
        assert alias["legacy"]
        assert alias["classification"] in {
            "CANONICAL",
            "COMPATIBILITY_ALIAS",
            "HISTORICAL",
            "CONFLICT",
        }
        if alias["classification"] != "CONFLICT":
            assert alias["target"] in codes
    for decision in fixture["compatibility_decisions"]:
        assert re.fullmatch(r"[A-Z0-9_]+", decision["id"])
        assert decision["source"]
        assert decision["current_value"]
        assert decision["target_value"]
        assert decision["decision"]
        assert decision["scope"]
        assert decision["work_package"]


def test_python_enums_match_fixture_without_fixture_generation():
    fixture, _ = _load()
    by_domain = {}
    for item in fixture["statuses"]:
        by_domain.setdefault(item["domain"], {})[item["canonical_symbol"]] = item["wire_value"]
    assert set(by_domain) == set(see.STATUS_ENUMS)
    for domain, expected in by_domain.items():
        actual = {member.name: member.value for member in see.STATUS_ENUMS[domain]}
        assert actual == expected, domain
    error_values = {member.value for member in see.ErrorCode}
    assert error_values == {item["canonical_code"] for item in fixture["errors"]}
    event_values = {member.value for member in see.EventType}
    assert event_values == {item["event_type"] for item in fixture["events"]}
    assert len(error_values) == 63
    assert len(event_values) == 22


def test_negative_values_and_semantic_boundaries():
    assert "PENDING" in {m.value for m in see.ExportJobStatus}
    assert "PENDING" in {m.value for m in see.OutboxEventStatus}
    assert "RUNNING" in {m.value for m in see.CrawlTaskStatus}
    assert "RUNNING" not in {m.value for m in see.ReviewDecisionStatus}
    assert "SUCCEEDED" not in {m.value for m in see.TaskArticleStatus}
    assert "heartbeat" not in {m.value for m in see.EventType}
    assert "UNKNOWN_VALUE" not in {m.value for m in see.ErrorCode}
    assert "global_block_legal_request_activated" in {
        m.value for m in see.EventType
    }
