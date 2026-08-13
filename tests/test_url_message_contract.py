"""Offline cross-language contract test for the formal Python URLMessage."""

import json
import os

from protocol.messages import URLMessage

from crawler.search.search_orchestrator import RedisURLMessagePublisher

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "url_message_contract.json")
EXPECTED_FIELDS = {
    "protocol_version",
    "task_id",
    "message_id",
    "timestamp",
    "type",
    "url",
    "site",
    "keyword",
    "level",
    "title",
}


def _load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _message():
    return URLMessage(
        protocol_version="2.0",
        task_id="task-compat-001",
        message_id="msg-compat-001",
        timestamp="2026-08-12T00:00:00Z",
        url="https://example.gov.cn/a.html",
        site="example.gov.cn",
        keyword="低空经济",
        level=1,
        title="示例标题",
    )


def test_formal_url_message_to_dict_is_top_level_and_matches_fixture():
    assert _load_fixture() == _message().to_dict()


def test_formal_url_message_json_serialization_keeps_contract():
    actual = _message().to_dict()
    assert set(actual) == EXPECTED_FIELDS
    parsed = json.loads(json.dumps(actual, ensure_ascii=False))
    assert parsed == actual
    assert "time" not in parsed
    assert "payload" not in parsed


def test_redis_publisher_publishes_exact_formal_url_message_json():
    class FakeRedis:
        def __init__(self):
            self.calls = []

        def lpush(self, name, value):
            self.calls.append((name, value))

    fake = FakeRedis()
    RedisURLMessagePublisher(fake).publish(_message())
    assert len(fake.calls) == 1
    name, payload = fake.calls[0]
    assert name == "crawler:url"
    assert json.loads(payload) == _message().to_dict()
