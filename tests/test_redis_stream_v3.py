import json
from pathlib import Path

import pytest

from protocol.messages import ProtocolError
from protocol.stream_messages import (
    decode_capacity_state,
    decode_v3_message,
    encode_capacity_state,
    encode_v3_message,
)

ROOT = Path(__file__).resolve().parents[1]
STREAM_CASES = ROOT / "tests" / "fixtures" / "redis_stream_v3_cases.json"
CAPACITY_CASES = ROOT / "tests" / "fixtures" / "capacity_state_v1_cases.json"


def _stream_cases():
    return json.loads(STREAM_CASES.read_text(encoding="utf-8"))


def _capacity_cases():
    return json.loads(CAPACITY_CASES.read_text(encoding="utf-8"))


def test_v3_valid_cases_round_trip():
    cases = _stream_cases()
    for case in cases["cases"]:
        if not case["valid"]:
            continue
        raw = case.get("raw") or json.dumps(case["data"], ensure_ascii=False)
        message = decode_v3_message(raw, stream=case["stream"])
        encoded = encode_v3_message(message)
        decoded = decode_v3_message(encoded, stream=case["stream"])
        assert decoded.type == case["data"]["type"]
        if "raw" not in case:
            assert json.loads(encoded)["payload"] == case["data"]["payload"]


def test_v3_invalid_cases_hit_expected_rejection():
    cases = _stream_cases()
    rejected = 0
    rejected_names = set()
    for case in cases["cases"]:
        if case["valid"]:
            continue
        with pytest.raises(ProtocolError) as exc_info:
            decode_v3_message(
                case.get("raw") or json.dumps(case["data"], ensure_ascii=False),
                stream=case["stream"],
            )
        assert exc_info.value.code == case["expect"]["code"]
        assert case["expect"]["reason_marker"] in str(exc_info.value)
        rejected += 1
        rejected_names.add(case["name"])
    assert rejected >= 10
    required = {
        "invalid-artifact-ref-space",
        "invalid-artifact-ref-backslash",
        "invalid-artifact-ref-parent-relative",
        "invalid-artifact-ref-parent-inner",
        "invalid-artifact-ref-absolute",
        "invalid-artifact-ref-drive",
        "invalid-artifact-ref-drive-relative",
        "invalid-artifact-ref-drive-relative-upper",
        "invalid-artifact-ref-drive-relative-lower",
        "invalid-number-fraction",
        "invalid-number-bool",
        "invalid-number-nonfinite-json",
        "invalid-number-evidence-weight-overflow",
        "invalid-number-level-max-plus-one",
        "invalid-number-level-rounding-fraction",
    }
    assert required <= rejected_names


def test_v3_contract_matrix_is_complete():
    cases = _stream_cases()
    assert len(cases["streams"]) == 5
    assert {item["type"] for item in cases["streams"]} == {
        "search_requested", "url", "html", "result", "error",
    }
    assert {item["work_class"] for item in cases["streams"]} == {
        "ROOT", "CONTINUATION", "TERMINAL",
    }


def test_capacity_valid_cases_round_trip():
    cases = _capacity_cases()
    valid_names = set()
    for case in cases["cases"]:
        if not case["valid"]:
            continue
        raw = case.get("raw") or json.dumps(case["data"], ensure_ascii=False)
        state = decode_capacity_state(raw)
        encoded = encode_capacity_state(state)
        decoded = decode_capacity_state(encoded)
        assert decoded.event_type == case["data"]["event_type"]
        assert decoded.state == case["data"]["state"]
        valid_names.add(case["name"])
    required = {
        "valid-capacity-normal",
        "valid-capacity-warning",
        "valid-capacity-blocked",
        "valid-stream-drain-only",
            "valid-capacity-state-version-max",
            "valid-capacity-emergency-1e0",
            "valid-capacity-emergency-max",
    }
    assert required <= valid_names


def test_capacity_invalid_cases_hit_expected_rejection():
    cases = _capacity_cases()
    rejected = 0
    rejected_names = set()
    for case in cases["cases"]:
        if case["valid"]:
            continue
        with pytest.raises(ProtocolError) as exc_info:
            decode_capacity_state(case.get("raw") or json.dumps(case["data"], ensure_ascii=False))
        assert exc_info.value.code == case["expect"]["code"]
        assert case["expect"]["reason_marker"] in str(exc_info.value)
        rejected += 1
        rejected_names.add(case["name"])
    required = {
        "invalid-event-state-mismatch",
        "invalid-zero-emergency-reserve",
        "invalid-missing-state-version",
        "invalid-unknown-schema-version",
        "invalid-capacity-state-version-fraction",
        "invalid-capacity-emergency-nonfinite-json",
        "invalid-capacity-state-version-max-plus-one",
        "invalid-capacity-emergency-max-plus-one",
    }
    assert required <= rejected_names
