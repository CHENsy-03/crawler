import json
import os

import pytest

from protocol.messages import (
    PROTOCOL_VERSION,
    PROTOCOL_VERSION_V2,
    ProtocolError,
    SearchRequestedMessage,
    decode_search_request,
    normalize_keywords,
    validate_target_url,
)

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "redis_protocol_v2.json")
V1_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "redis_protocol_v1.json")


def _load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_fixture_path_is_repo_relative_not_cwd():
    assert os.path.isfile(FIXTURE_PATH)
    assert os.path.basename(FIXTURE_PATH) == "redis_protocol_v2.json"


def test_v2_fixture_matches_search_requested():
    fix = _load_fixture()
    envelope = fix["_envelope"]
    msg = SearchRequestedMessage(
        task_id=envelope["task_id"],
        message_id=envelope["message_id"],
        timestamp=envelope["timestamp"],
        protocol_version=PROTOCOL_VERSION_V2,
        target_url="https://example.gov.cn/search",
        keywords=[" 低空经济 ", "无人机", "低空经济", "   "],
        level=1,
        max_pages=5,
    )
    actual = msg.to_dict()
    expected = fix["search_requested"]
    for key, value in expected.items():
        assert actual[key] == value, f"search_requested.{key}: {actual[key]} != {value}"


def test_v2_decode_normalizes_keywords():
    fix = _load_fixture()
    decoded = decode_search_request(json.dumps(fix["search_requested"]))
    assert isinstance(decoded, SearchRequestedMessage)
    assert decoded.keywords == ["低空经济", "无人机"]
    assert decoded.target_url == "https://example.gov.cn/search"


def test_v2_roundtrip():
    fix = _load_fixture()
    expected = fix["search_requested_normalized"]
    decoded = decode_search_request(json.dumps(expected))
    restored = SearchRequestedMessage(**json.loads(json.dumps(decoded.to_dict())))
    assert restored.to_dict() == expected


def test_v2_minimal_applies_defaults():
    decoded = decode_search_request(json.dumps(_load_fixture()["search_requested_minimal"]))
    assert decoded.level == 0
    assert decoded.max_pages == 1


def test_v1_fixture_still_decodes():
    with open(V1_FIXTURE_PATH, "r", encoding="utf-8") as f:
        v1 = json.load(f)
    decoded = decode_search_request(json.dumps(v1["search"]))
    assert decoded.protocol_version == PROTOCOL_VERSION
    assert decoded.site == "czj_beijing"


def test_missing_protocol_version_rejected():
    with pytest.raises(ProtocolError) as exc:
        decode_search_request(json.dumps({"type": "search_requested", "target_url": "https://x.test"}))
    assert exc.value.code == "MISSING_PROTOCOL_VERSION"


def test_unknown_protocol_version_rejected():
    with pytest.raises(ProtocolError) as exc:
        decode_search_request(json.dumps({
            "protocol_version": "9.9",
            "task_id": "t",
            "message_id": "m",
            "timestamp": "now",
            "type": "search_requested",
            "target_url": "https://x.test",
            "keywords": ["k"],
        }))
    assert exc.value.code == "UNKNOWN_PROTOCOL_VERSION"


def test_v2_requires_search_requested_type():
    with pytest.raises(ProtocolError):
        decode_search_request(json.dumps({
            "protocol_version": PROTOCOL_VERSION_V2,
            "type": "search",
            "target_url": "https://x.test",
            "keywords": ["k"],
        }))


def test_v1_missing_required_fields():
    for payload in [
        {"protocol_version": "1.0", "type": "search", "keyword": "k", "level": 1, "max_pages": 1},
        {"protocol_version": "1.0", "type": "search", "site": "s", "level": 1, "max_pages": 1},
    ]:
        with pytest.raises(ProtocolError) as exc:
            decode_search_request(json.dumps(payload))
        assert exc.value.code == "INVALID_MESSAGE"


def test_v1_rejects_v2_fields():
    for payload in [
        {"protocol_version": "1.0", "task_id": "t", "message_id": "m", "timestamp": "now", "type": "search", "site": "s", "keyword": "k", "level": 1, "max_pages": 1, "target_url": "https://x"},
        {"protocol_version": "1.0", "task_id": "t", "message_id": "m", "timestamp": "now", "type": "search", "site": "s", "keyword": "k", "level": 1, "max_pages": 1, "keywords": ["k"]},
    ]:
        with pytest.raises(ProtocolError) as exc:
            decode_search_request(json.dumps(payload))
        assert exc.value.code == "UNKNOWN_FIELD"


def test_v2_rejects_v1_fields():
    for field, value in [("site", "s"), ("profile", "p"), ("keyword", "k")]:
        payload = {
            "protocol_version": "2.0",
            "task_id": "t",
            "message_id": "m",
            "timestamp": "now",
            "type": "search_requested",
            "target_url": "https://x",
            "keywords": ["k"],
            field: value,
        }
        with pytest.raises(ProtocolError) as exc:
            decode_search_request(json.dumps(payload))
        assert exc.value.code == "UNKNOWN_FIELD"


def test_unknown_field_rejected():
    payload = {
        "protocol_version": "2.0",
        "task_id": "t",
        "message_id": "m",
        "timestamp": "now",
        "type": "search_requested",
        "target_url": "https://x",
        "keywords": ["k"],
        "bogus": 1,
    }
    with pytest.raises(ProtocolError) as exc:
        decode_search_request(json.dumps(payload))
    assert exc.value.code == "UNKNOWN_FIELD"


def test_null_optional_rejected():
    for field in ["level", "max_pages"]:
        payload = {
            "protocol_version": "2.0",
            "type": "search_requested",
            "target_url": "https://x",
            "keywords": ["k"],
            field: None,
        }
        with pytest.raises(ProtocolError) as exc:
            decode_search_request(json.dumps(payload))
        assert exc.value.code == "INVALID_MESSAGE"


@pytest.mark.parametrize("raw", [
    "https://example.gov.cn:443/search",
    "http://example.gov.cn:65535/search?q=1",
])
def test_valid_target_url(raw):
    validate_target_url(raw)


@pytest.mark.parametrize("raw", [
    "",
    "   ",
    " https://example.gov.cn/search",
    "https://example.gov.cn/search ",
    "ftp://example.gov.cn/search",
    "/relative/path",
    "example.gov.cn/search",
    "https:///missing-host",
    "https://user@:80",
    "https://example.gov.cn:abc",
    "https://example.gov.cn:99999",
    "https://example.gov.cn:",
])
def test_invalid_target_url(raw):
    with pytest.raises(ProtocolError) as exc:
        validate_target_url(raw)
    assert exc.value.code == "INVALID_TARGET_URL"


def test_empty_keywords_rejected():
    with pytest.raises(ProtocolError) as exc:
        normalize_keywords([])
    assert exc.value.code == "EMPTY_KEYWORDS"


def test_blank_keywords_rejected():
    with pytest.raises(ProtocolError) as exc:
        normalize_keywords(["", "   "])
    assert exc.value.code == "EMPTY_KEYWORDS"


def test_null_keywords_rejected():
    with pytest.raises(ProtocolError) as exc:
        normalize_keywords(None)
    assert exc.value.code == "INVALID_KEYWORD"


def test_keyword_normalization_rule():
    assert normalize_keywords([" 低空经济 ", "无人机", "低空经济", "   "]) == ["低空经济", "无人机"]

def test_protocol_integer_type_rejected():
    base = {
        "protocol_version": "2.0",
        "task_id": "t-1",
        "message_id": "m-1",
        "timestamp": "2026-07-31T00:00:00Z",
        "type": "search_requested",
        "target_url": "https://x.test",
        "keywords": ["k"],
    }
    for field, value in [("level", "1"), ("max_pages", 1.0), ("level", True)]:
        with pytest.raises(ProtocolError) as exc:
            decode_search_request(json.dumps({**base, field: value}))
        assert exc.value.code == "INVALID_INTEGER"


def test_v2_keywords_string_rejected():
    payload = {
        "protocol_version": "2.0",
        "task_id": "t",
        "message_id": "m",
        "timestamp": "now",
        "type": "search_requested",
        "target_url": "https://x.test",
        "keywords": "k",
    }
    with pytest.raises(ProtocolError) as exc:
        decode_search_request(json.dumps(payload))
    assert exc.value.code == "INVALID_KEYWORD"


def test_v2_keywords_object_rejected():
    payload = {
        "protocol_version": "2.0",
        "task_id": "t",
        "message_id": "m",
        "timestamp": "now",
        "type": "search_requested",
        "target_url": "https://x.test",
        "keywords": {"k": 1},
    }
    with pytest.raises(ProtocolError) as exc:
        decode_search_request(json.dumps(payload))
    assert exc.value.code == "INVALID_KEYWORD"


def test_normalize_keywords_tuple_rejected():
    with pytest.raises(ProtocolError) as exc:
        normalize_keywords(("k",))
    assert exc.value.code == "INVALID_KEYWORD"


def test_v1_site_and_keyword_must_be_non_blank_strings():
    base = {
        "protocol_version": "1.0",
        "task_id": "t",
        "message_id": "m",
        "timestamp": "now",
        "type": "search",
        "level": 1,
        "max_pages": 1,
    }
    cases = [
        {"site": None},
        {"site": ""},
        {"site": "   "},
        {"site": 1},
        {"site": []},
        {"keyword": None},
        {"keyword": ""},
        {"keyword": "   "},
        {"keyword": 1},
        {"keyword": []},
    ]
    for case in cases:
        with pytest.raises(ProtocolError) as exc:
            decode_search_request(json.dumps({**base, **case}))
        assert exc.value.code == "INVALID_MESSAGE", case


def test_malformed_ipv6_target_url_rejected():
    for raw in ["https://[::1", "https://[invalid]"]:
        with pytest.raises(ProtocolError) as exc:
            validate_target_url(raw)
        assert exc.value.code == "INVALID_TARGET_URL"

def test_v1_invalid_fixture_cases_rejected():
    for case in _load_fixture()["invalid_v1_cases"]:
        with pytest.raises(ProtocolError) as exc:
            decode_search_request(json.dumps(case))
        assert exc.value.code == "INVALID_MESSAGE", case

def test_v2_null_keyword_elements_rejected():
    for case in _load_fixture()["invalid_keywords_cases"]:
        with pytest.raises(ProtocolError) as exc:
            decode_search_request(json.dumps(case))
        assert exc.value.code == "INVALID_KEYWORD", case


def test_v2_string_null_keyword_accepted():
    decoded = decode_search_request(json.dumps(_load_fixture()["valid_keywords_null_string"]))
    assert decoded.keywords == ["null"]
