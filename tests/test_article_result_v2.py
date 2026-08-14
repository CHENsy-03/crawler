"""Offline Python contract tests for ArticleResult v2 messages."""

import json
import os

import pytest

from protocol.messages import (
    HTMLMessageV2,
    ProtocolError,
    URLMessageV2,
    decode_v2_article_message,
)

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "article_result_v2_contract.json")


def _load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _article_payload():
    return dict(_load_fixture()["article_result_v2"])


def test_fixture_exists():
    assert os.path.isfile(FIXTURE_PATH)


def test_url_v2_matches_fixture():
    fixture = _load_fixture()
    message = decode_v2_article_message(json.dumps(fixture["url_v2"]))
    assert isinstance(message, URLMessageV2)
    assert message.to_dict() == fixture["url_v2"]


def test_html_v2_matches_fixture():
    fixture = _load_fixture()
    message = decode_v2_article_message(json.dumps(fixture["html_v2"]))
    assert isinstance(message, HTMLMessageV2)
    assert message.to_dict() == fixture["html_v2"]


def test_article_result_v2_matches_fixture():
    fixture = _load_fixture()
    message = decode_v2_article_message(json.dumps(fixture["article_result_v2"]))
    assert message.to_dict() == fixture["article_result_v2"]


def test_three_message_types_roundtrip():
    fixture = _load_fixture()
    for key in ("url_v2", "html_v2", "article_result_v2"):
        payload = json.dumps(fixture[key])
        decoded = decode_v2_article_message(payload)
        assert decode_v2_article_message(json.dumps(decoded.to_dict())).to_dict() == decoded.to_dict()


def test_empty_matched_evidence_serializes_as_array():
    fixture = _load_fixture()
    message = decode_v2_article_message(json.dumps(fixture["article_result_v2_empty_evidence"]))
    assert message.to_dict()["matched_evidence"] == []
    assert json.dumps(message.to_dict(), ensure_ascii=False) == json.dumps(fixture["article_result_v2_empty_evidence"], ensure_ascii=False)


def test_extract_failed_allows_empty_content_and_hash():
    fixture = _load_fixture()
    message = decode_v2_article_message(json.dumps(fixture["article_result_v2_extract_failed"]))
    assert message.status == "extract_failed"
    assert message.content == ""
    assert message.content_hash == ""
    assert message.to_dict() == fixture["article_result_v2_extract_failed"]


def test_explicit_null_rejected():
    payload = _article_payload()
    payload["score"] = None
    with pytest.raises(ProtocolError):
        decode_v2_article_message(json.dumps(payload))


def test_unknown_field_rejected():
    payload = _article_payload()
    payload["unexpected"] = True
    with pytest.raises(ProtocolError):
        decode_v2_article_message(json.dumps(payload))


def test_invalid_status_rejected():
    payload = _article_payload()
    payload["status"] = "not_a_status"
    with pytest.raises(ProtocolError):
        decode_v2_article_message(json.dumps(payload))


def test_invalid_extraction_method_rejected():
    payload = _article_payload()
    payload["extraction_method"] = "not_a_method"
    with pytest.raises(ProtocolError):
        decode_v2_article_message(json.dumps(payload))


def test_negative_score_rejected():
    payload = _article_payload()
    payload["score"] = -1
    with pytest.raises(ProtocolError):
        decode_v2_article_message(json.dumps(payload))


def test_boolean_score_rejected():
    payload = _article_payload()
    payload["score"] = True
    with pytest.raises(ProtocolError):
        decode_v2_article_message(json.dumps(payload))


def test_invalid_content_hash_rejected():
    payload = _article_payload()
    payload["content_hash"] = "0" * 64
    with pytest.raises(ProtocolError):
        decode_v2_article_message(json.dumps(payload))


def test_missing_content_hash_rejected_when_content_present():
    payload = _article_payload()
    payload["content_hash"] = ""
    with pytest.raises(ProtocolError):
        decode_v2_article_message(json.dumps(payload))


def test_invalid_requested_url_rejected():
    payload = _article_payload()
    payload["requested_url"] = "javascript:alert(1)"
    with pytest.raises(ProtocolError):
        decode_v2_article_message(json.dumps(payload))


def test_invalid_evidence_rejected():
    payload = _article_payload()
    payload["matched_evidence"] = [
        {"term": "低空经济", "origin": "original", "field": "title", "weight": -1}
    ]
    with pytest.raises(ProtocolError):
        decode_v2_article_message(json.dumps(payload))


def test_unknown_evidence_field_rejected():
    payload = _article_payload()
    payload["matched_evidence"] = [
        {"term": "低空经济", "origin": "original", "field": "title", "weight": 1, "extra": True}
    ]
    with pytest.raises(ProtocolError):
        decode_v2_article_message(json.dumps(payload))


def test_wrong_protocol_version_rejected():
    payload = _article_payload()
    payload["protocol_version"] = "1.0"
    with pytest.raises(ProtocolError):
        decode_v2_article_message(json.dumps(payload))


def test_unknown_type_rejected():
    payload = _article_payload()
    payload["type"] = "unknown"
    with pytest.raises(ProtocolError):
        decode_v2_article_message(json.dumps(payload))
