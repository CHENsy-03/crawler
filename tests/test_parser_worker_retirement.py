"""Regression tests for retirement of parser/redis_worker.py."""

import importlib
import json
import os
from pathlib import Path

import pytest

from protocol.messages import HTMLMessageV2


ROOT = Path(__file__).resolve().parents[1]


class _FakeRedis:
    def __init__(self):
        self.calls = []

    def lpush(self, queue, value):
        self.calls.append((queue, value))


def _v2_html_message(html):
    return HTMLMessageV2(
        protocol_version="2.0",
        task_id="t1",
        message_id="m1",
        timestamp="2026-08-13T00:00:00Z",
        hit_id="h1",
        plan_id="p1",
        original_query="低空经济",
        query_term="低空经济",
        requested_url="https://example.gov.cn/a.html",
        final_url="https://example.gov.cn/a.html",
        content_type="text/html",
        title="消息标题",
        snippet="",
        published_at="2026-08-12",
        source="example.gov.cn",
        level=0,
        html=html,
    )


def test_old_worker_file_removed():
    assert not (ROOT / "parser" / "redis_worker.py").exists()


def test_old_worker_module_not_importable():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("parser.redis_worker")


def test_only_formal_consumer_scans_crawler_html_brpop():
    hits = []
    for directory in ("workers", "parser", "crawler"):
        for path in (ROOT / directory).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "brpop" in text and "crawler:html" in text:
                hits.append(path.relative_to(ROOT).as_posix())
    assert hits == ["workers/parser_worker.py"]


def test_formal_worker_does_not_use_old_local_store_imports():
    source = (ROOT / "workers" / "parser_worker.py").read_text(encoding="utf-8")
    assert "save_results" not in source
    assert "DedupDB" not in source
    assert "storage.json_store" not in source


def _legacy_message():
    return {
        "protocol_version": "1.0",
        "task_id": "t1",
        "message_id": "m1",
        "timestamp": "2026-08-13T00:00:00Z",
        "type": "html",
        "url": "https://czj.beijing.gov.cn/art/1.html",
        "site": "czj_beijing",
        "keyword": "低空经济",
        "level": 1,
        "title": "标题",
        "html": "<html><body><div class=\"article-content\"><p>" + ("正文" * 120) + "</p></div></body></html>",
    }


def test_legacy_missing_version_still_handled():
    from workers.parser_worker import _dispatch_html_message
    raw = _legacy_message()
    raw.pop("protocol_version")
    r = _FakeRedis()
    result = _dispatch_html_message(raw, r)
    assert result is not None
    assert r.calls and r.calls[0][0] == "crawler:result"
    payload = json.loads(r.calls[0][1])
    assert payload.get("protocol_version") == "1.0"
    assert payload.get("type") == "result"


def test_v1_still_handled():
    from workers.parser_worker import _dispatch_html_message
    r = _FakeRedis()
    result = _dispatch_html_message(_legacy_message(), r)
    assert result is not None
    assert r.calls and r.calls[0][0] == "crawler:result"
    payload = json.loads(r.calls[0][1])
    assert payload.get("protocol_version") == "1.0"
    assert payload.get("type") == "result"


def test_v2_still_uses_independent_path():
    from workers.parser_worker import _dispatch_html_message
    html = '<html><body><h1>低空经济详情标题</h1><div class="article-content">' + ("<p>低空经济正文内容</p>" * 80) + "</div></body></html>"
    raw = _v2_html_message(html).to_dict()
    r = _FakeRedis()
    result = _dispatch_html_message(raw, r)
    assert result is not None
    assert result["type"] == "article_result"
    assert r.calls and r.calls[0][0] == "crawler:result"
    payload = json.loads(r.calls[0][1])
    assert payload["type"] == "article_result"
    assert payload["status"] in {"accepted", "review_required"}