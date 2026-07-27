import json
import os
from protocol.messages import (
    SearchMessage, URLMessage, HTMLMessage,
    ResultMessage, ErrorMessage,
)

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "redis_protocol_v1.json")


def _load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _assert_match_expected(msg_type, actual_dict, fixture_dict):
    expected = fixture_dict[msg_type]
    for k, v in expected.items():
        assert k in actual_dict, f"{msg_type} missing field {k}"
        assert actual_dict[k] == v, f"{msg_type}.{k}: {actual_dict[k]} != {v}"
    allowed = set(expected.keys())
    actual_keys = set(actual_dict.keys())
    extra = actual_keys - allowed
    assert not extra, f"{msg_type} has unexpected fields: {extra}"
    assert "time" not in actual_keys, f"{msg_type} should not have old time field"


def test_search_message():
    fix = _load_fixture()
    e = fix["_envelope"]
    msg = SearchMessage(task_id=e["task_id"], message_id=e["message_id"], timestamp=e["timestamp"],
                        site="czj_beijing", keyword="低空经济", level=1)
    _assert_match_expected("search", msg.to_dict(), fix)


def test_url_message():
    fix = _load_fixture()
    e = fix["_envelope"]
    msg = URLMessage(task_id=e["task_id"], message_id="msg-002", timestamp=e["timestamp"],
                     url="https://czj.beijing.gov.cn/art/1.html", site="czj_beijing", keyword="低空经济", level=1)
    _assert_match_expected("url", msg.to_dict(), fix)


def test_html_message():
    fix = _load_fixture()
    e = fix["_envelope"]
    msg = HTMLMessage(task_id=e["task_id"], message_id="msg-003", timestamp=e["timestamp"],
                      url="https://czj.beijing.gov.cn/art/1.html", site="czj_beijing",
                      keyword="低空经济", level=1, title="低空经济政策解读", html="<html><body>正文</body></html>")
    _assert_match_expected("html", msg.to_dict(), fix)


def test_result_message():
    fix = _load_fixture()
    e = fix["_envelope"]
    msg = ResultMessage(task_id=e["task_id"], message_id="msg-004", timestamp=e["timestamp"],
                        url="https://czj.beijing.gov.cn/art/1.html", title="低空经济政策解读",
                        publish_date="2026-07-27", content="正文内容", score=85)
    _assert_match_expected("result", msg.to_dict(), fix)


def test_error_message():
    fix = _load_fixture()
    e = fix["_envelope"]
    msg = ErrorMessage(task_id=e["task_id"], message_id="msg-005", timestamp=e["timestamp"],
                       stage="download", url="https://czj.beijing.gov.cn/art/1.html",
                       error_code="HTTP_403", error="forbidden", retryable=False)
    _assert_match_expected("error", msg.to_dict(), fix)
