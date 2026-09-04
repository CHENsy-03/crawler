"""Offline tests for v2 detail extraction, relevance and worker dispatch."""

import json
import re
from unittest.mock import patch

import pytest

from crawler.detail.article_result_builder import build_article_result_v2, build_summary
from crawler.detail.extraction_v2 import DetailExtractionResult, extract_detail_v2
from crawler.detail.relevance_v2 import RelevanceResult, score_detail
from protocol.messages import ArticleResultV2, HTMLMessageV2, decode_v2_article_message
from parser.html_parser import extract_content


def _long_html(prefix="正文", count=140):
    return "".join(f"<p>{prefix}{i:03d}{'正文' * 20}</p>" for i in range(count))


def _html_message(html, snippet=""):
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
        snippet=snippet,
        published_at="2026-08-12",
        source="example.gov.cn",
        level=0,
        html=html,
    )


def _score_config():
    return {"title_weight": 5, "body_weight": 1, "url_weight": 0, "threshold": 2}


def _score(msg, detail, summary, summary_from_snippet, title_is_detail):
    return score_detail(
        original_query=msg.original_query,
        query_term=msg.query_term,
        title=detail.title or msg.title,
        summary=summary,
        content=detail.content,
        url=detail.canonical_url or msg.final_url,
        score_config=_score_config(),
        summary_from_snippet=summary_from_snippet,
        title_is_detail=title_is_detail,
    )


class _FakeRedis:
    def __init__(self):
        self.calls = []
        self.raise_on_lpush = False

    def lpush(self, queue, value):
        if self.raise_on_lpush:
            raise RuntimeError("redis down")
        self.calls.append((queue, value))


# Extraction


def test_v2_generic_extraction_full_text():
    html = '<html><body><h1>详情标题</h1><div class="article-content">' + _long_html() + "</div></body></html>"
    result = extract_detail_v2(html, final_url="https://example.gov.cn/a.html")
    assert result.title == "详情标题"
    assert result.title_source == "h1"
    assert len(result.content) > 5000
    assert result.extraction_method == "fallback"


def test_v2_cms_rule_method():
    site_cfg = {"extract": {"mode": "trs"}}
    html = '<html><body><div class="TRS_Editor">' + _long_html() + "</div></body></html>"
    result = extract_detail_v2(html, site_cfg=site_cfg, final_url="https://example.gov.cn/a.html")
    assert result.extraction_method == "cms_rule"
    assert result.content


def test_v1_extract_content_still_3000():
    html = '<html><body><div class="article-content">' + _long_html() + "</div></body></html>"
    content = extract_content(html)
    assert len(content) <= 3000


def test_noise_tags_removed():
    html = '<html><body><nav>nav</nav><script>bad()</script><footer>foot</footer><div class="article-content">' + _long_html() + "</div></body></html>"
    result = extract_detail_v2(html, final_url="https://example.gov.cn/a.html")
    assert "nav" not in result.content
    assert "bad" not in result.content
    assert "foot" not in result.content


def test_title_h1_preferred():
    html = "<html><head><title>旧标题</title></head><body><h1>新标题</h1></body></html>"
    result = extract_detail_v2(html, final_url="https://example.gov.cn/a.html")
    assert result.title == "新标题"
    assert result.title_source == "h1"


def test_canonical_relative():
    html = '<html><head><link rel="canonical" href="/canonical"></head><body></body></html>'
    result = extract_detail_v2(html, final_url="https://example.gov.cn/a.html")
    assert result.canonical_url == "https://example.gov.cn/canonical"


def test_canonical_multi_token_rel():
    html = '<html><head><link rel="alternate canonical" href="/canonical"></head><body></body></html>'
    result = extract_detail_v2(html, final_url="https://example.gov.cn/a.html")
    assert result.canonical_url == "https://example.gov.cn/canonical"


def test_canonical_first_valid_after_invalid():
    html = '<html><head><link rel="canonical" href="javascript:void(0)"><link rel="canonical" href="/real"></head><body></body></html>'
    result = extract_detail_v2(html, final_url="https://example.gov.cn/a.html")
    assert result.canonical_url == "https://example.gov.cn/real"


def test_canonical_invalid_empty():
    html = '<html><head><link rel="canonical" href="javascript:void(0)"></head><body></body></html>'
    result = extract_detail_v2(html, final_url="https://example.gov.cn/a.html")
    assert result.canonical_url == ""


def test_empty_html_none_method():
    result = extract_detail_v2("<html></html>", final_url="https://example.gov.cn/a.html")
    assert result.content == ""
    assert result.extraction_method == "none"


def test_default_ai_not_called():
    with patch("crawler.detail.extraction_v2.parse_with_ai", side_effect=AssertionError("must not call AI")):
        result = extract_detail_v2("<html><body><p>低空经济正文</p></body></html>", global_config={"ai_enabled": False})
    assert result.content


def test_extract_unicode_whitespace_normalized():
    html = "<html><body><div class=\"article-content\"><p>低空&nbsp;经济\u3000政策</p></div></body></html>"
    result = extract_detail_v2(html, final_url="https://example.gov.cn/a.html")
    assert " " in result.content
    assert "\u3000" not in result.content


# Relevance


def test_relevance_accepted_content_detail():
    relevance = score_detail(
        original_query="低空经济", query_term="低空经济",
        title="标题", summary="", content="低空经济正文内容", url="https://example.gov.cn/a",
        score_config={"title_weight": 5, "body_weight": 5, "url_weight": 0, "threshold": 2}, summary_from_snippet=False, title_is_detail=False,
    )
    assert relevance.status == "accepted"
    assert relevance.original_score >= 2


def test_relevance_accepted_detail_title():
    relevance = score_detail(
        original_query="低空经济", query_term="低空经济",
        title="低空经济政策解读", summary="", content="正文", url="https://example.gov.cn/a",
        score_config=_score_config(), summary_from_snippet=False, title_is_detail=True,
    )
    assert relevance.status == "accepted"


def test_relevance_only_expanded_review_required():
    relevance = score_detail(
        original_query="甲", query_term="乙",
        title="乙", summary="", content="", url="https://example.gov.cn/乙",
        score_config=_score_config(), summary_from_snippet=False,
    )
    assert relevance.status == "review_required"
    assert relevance.score > 0
    assert relevance.original_score == 0
    assert all(e.origin == "expanded" for e in relevance.evidence)


def test_relevance_summary_from_content_not_scored():
    relevance = score_detail(
        original_query="低空经济", query_term="低空经济",
        title="标题", summary="低空经济摘要", content="低空经济正文",
        url="https://example.gov.cn/a", score_config=_score_config(),
        summary_from_snippet=False, title_is_detail=False,
    )
    fields = [e.field for e in relevance.evidence]
    assert "summary" not in fields
    assert "content" in fields


def test_relevance_summary_from_snippet_scored_but_not_accept():
    relevance = score_detail(
        original_query="低空经济", query_term="低空经济",
        title="标题", summary="低空经济摘要", content="正文无关键词",
        url="https://example.gov.cn/a", score_config={"title_weight": 5, "body_weight": 5, "url_weight": 0, "threshold": 2},
        summary_from_snippet=True, title_is_detail=False,
    )
    assert relevance.original_score >= 2
    assert relevance.status == "review_required"
    assert any(e.field == "summary" for e in relevance.evidence)


def test_relevance_message_title_fallback_not_accept():
    relevance = score_detail(
        original_query="低空经济", query_term="低空经济",
        title="低空经济消息标题", summary="", content="正文无关键词",
        url="https://example.gov.cn/a", score_config=_score_config(),
        summary_from_snippet=False, title_is_detail=False,
    )
    assert relevance.original_score >= 2
    assert relevance.status == "review_required"


def test_relevance_url_weight_zero_not_accept():
    relevance = score_detail(
        original_query="低空经济", query_term="低空经济",
        title="标题", summary="", content="正文无关键词", url="https://example.gov.cn/低空经济",
        score_config=_score_config(), summary_from_snippet=False,
    )
    assert relevance.status == "review_required"
    assert relevance.score == 0
    assert any(e.field == "url" for e in relevance.evidence)


def test_relevance_irrelevant():
    relevance = score_detail(
        original_query="低空经济", query_term="低空经济",
        title="标题", summary="", content="正文无关键词", url="https://example.gov.cn/a",
        score_config=_score_config(), summary_from_snippet=False,
    )
    assert relevance.status == "irrelevant"
    assert relevance.evidence == ()


def test_relevance_evidence_order_stable():
    relevance = score_detail(
        original_query="甲", query_term="乙",
        title="甲 乙", summary="乙", content="甲", url="https://example.gov.cn/乙",
        score_config={"title_weight": 5, "body_weight": 1, "url_weight": 1, "threshold": 2},
        summary_from_snippet=True,
    )
    assert [(e.term, e.origin, e.field) for e in relevance.evidence] == [
        ("甲", "original", "title"),
        ("甲", "original", "content"),
        ("乙", "expanded", "title"),
        ("乙", "expanded", "summary"),
        ("乙", "expanded", "url"),
    ]


def test_relevance_no_duplicate_evidence_same_field():
    relevance = score_detail(
        original_query="低空经济", query_term="低空经济",
        title="低空经济 低空经济", summary="", content="",
        url="https://example.gov.cn/a", score_config=_score_config(),
        summary_from_snippet=False, title_is_detail=True,
    )
    assert [e.field for e in relevance.evidence] == ["title"]


def test_relevance_canonical_url_used_for_scoring():
    relevance = score_detail(
        original_query="低空经济", query_term="低空经济",
        title="标题", summary="", content="", url="https://example.gov.cn/低空经济",
        score_config={"title_weight": 5, "body_weight": 1, "url_weight": 2, "threshold": 2},
        summary_from_snippet=False,
    )
    assert any(e.field == "url" and e.weight == 2 for e in relevance.evidence)
    assert relevance.status == "review_required"


# ArticleResult builder


def test_article_builder_accepted():
    html = '<html><body><h1>低空经济详情标题</h1><div class="article-content">' + _long_html(prefix="低空经济正文", count=30) + "</div></body></html>"
    detail = extract_detail_v2(html, final_url="https://example.gov.cn/a.html")
    msg = _html_message(html)
    summary, from_snippet = build_summary(msg.snippet, detail.content)
    relevance = _score(msg, detail, summary, from_snippet, True)
    result = build_article_result_v2(msg, detail, relevance, summary=summary, summary_from_snippet=from_snippet)
    assert result.status == "accepted"
    assert result.content_hash == __import__("hashlib").sha256(result.content.encode("utf-8")).hexdigest()
    assert result.requested_url == msg.requested_url
    assert result.final_url == msg.final_url
    assert result.canonical_url == detail.canonical_url
    assert result.source == "example.gov.cn"
    assert "html" not in result.to_dict()


def test_article_builder_extract_failed():
    msg = _html_message("<html></html>")
    detail = extract_detail_v2(msg.html, final_url=msg.final_url)
    summary, from_snippet = build_summary(msg.snippet, detail.content)
    relevance = _score(msg, detail, summary, from_snippet, False)
    result = build_article_result_v2(msg, detail, relevance, summary=summary, summary_from_snippet=from_snippet)
    assert result.status == "extract_failed"
    assert result.content == ""
    assert result.content_hash == ""
    assert result.extraction_method == "none"
    assert result.score == 0
    assert result.matched_evidence == ()


def test_article_builder_detail_date_priority():
    html = '<html><head><meta property="article:published_time" content="2026-08-01T10:00:00Z"></head><body><div class="article-content">' + _long_html() + "</div></body></html>"
    msg = _html_message(html, snippet="2026-08-12")
    detail = extract_detail_v2(html, final_url=msg.final_url)
    summary, from_snippet = build_summary(msg.snippet, detail.content)
    relevance = _score(msg, detail, summary, from_snippet, True)
    result = build_article_result_v2(msg, detail, relevance, summary=summary, summary_from_snippet=from_snippet)
    assert result.publish_date == "2026-08-01"


def test_article_builder_published_at_fallback_normalized():
    html = "<html><body><p>低空经济政策</p></body></html>"
    msg = _html_message(html)
    detail = extract_detail_v2(html, final_url=msg.final_url)
    summary, from_snippet = build_summary(msg.snippet, detail.content)
    relevance = _score(msg, detail, summary, from_snippet, False)
    result = build_article_result_v2(msg, detail, relevance, summary=summary, summary_from_snippet=from_snippet)
    assert result.publish_date == "2026-08-12"


def test_build_summary_snippet_preferred():
    summary, from_snippet = build_summary("<b>低空经济摘要</b>", "正文内容")
    assert summary == "低空经济摘要"
    assert from_snippet is True


def test_build_summary_content_fallback():
    summary, from_snippet = build_summary("", "正文内容" * 200)
    assert len(summary) == 500
    assert from_snippet is False


def test_builder_message_ids_unique():
    msg = _html_message('<html><body><h1>低空经济</h1><p>低空经济正文</p></body></html>')
    detail = extract_detail_v2(msg.html, final_url=msg.final_url)
    summary, from_snippet = build_summary(msg.snippet, detail.content)
    relevance = _score(msg, detail, summary, from_snippet, True)
    a = build_article_result_v2(msg, detail, relevance, summary=summary, summary_from_snippet=from_snippet)
    b = build_article_result_v2(msg, detail, relevance, summary=summary, summary_from_snippet=from_snippet)
    assert a.message_id != b.message_id
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", a.timestamp)
    assert a.timestamp.endswith("Z")


# Worker dispatch


def test_worker_v2_dispatch_publishes_article_result():
    from workers.parser_worker import _dispatch_html_message
    html = '<html><body><h1>低空经济详情标题</h1><div class="article-content">' + _long_html(prefix="低空经济正文", count=30) + "</div></body></html>"
    raw = _html_message(html).to_dict()
    r = _FakeRedis()
    result = _dispatch_html_message(raw, r)
    assert result is not None
    assert result["type"] == "article_result"
    assert result["hit_id"] == "h1"
    assert result["status"] == "accepted"
    assert r.calls and r.calls[0][0] == "crawler:result"
    payload = json.loads(r.calls[0][1])
    assert payload["type"] == "article_result"
    assert "html" not in payload
    decoded = decode_v2_article_message(json.dumps(payload))
    assert isinstance(decoded, ArticleResultV2)


def test_worker_v1_and_missing_version_use_legacy():
    from workers.parser_worker import _dispatch_html_message
    r = _FakeRedis()
    v1 = {
        "protocol_version": "1.0",
        "task_id": "t1",
        "message_id": "m1",
        "timestamp": "now",
        "type": "html",
        "url": "https://czj.beijing.gov.cn/art/1.html",
        "site": "czj_beijing",
        "keyword": "低空经济",
        "level": 1,
        "title": "标题",
        "html": "<html><body><p>" + ("正文" * 100) + "</p></body></html>",
    }
    assert _dispatch_html_message(v1, r) is not None
    assert r.calls[0][0] == "crawler:result"
    r.calls.clear()
    missing = {k: v for k, v in v1.items() if k != "protocol_version"}
    assert _dispatch_html_message(missing, r) is not None
    assert r.calls[0][0] == "crawler:result"


def test_worker_explicit_null_version_rejected():
    from workers.parser_worker import _dispatch_html_message
    r = _FakeRedis()
    raw = _html_message("<html></html>").to_dict()
    raw["protocol_version"] = None
    assert _dispatch_html_message(raw, r) is None
    assert r.calls == []


def test_worker_non_string_version_rejected():
    from workers.parser_worker import _dispatch_html_message
    r = _FakeRedis()
    raw = _html_message("<html></html>").to_dict()
    raw["protocol_version"] = 2.0
    assert _dispatch_html_message(raw, r) is None
    assert r.calls == []


def test_worker_non_object_rejected():
    from workers.parser_worker import _dispatch_html_message
    r = _FakeRedis()
    assert _dispatch_html_message([], r) is None
    assert r.calls == []


def test_worker_invalid_v2_does_not_publish():
    from workers.parser_worker import _dispatch_html_message
    r = _FakeRedis()
    raw = _html_message("<html></html>").to_dict()
    raw["hit_id"] = None
    assert _dispatch_html_message(raw, r) is None
    assert r.calls == []


def test_worker_unknown_version_does_not_publish():
    from workers.parser_worker import _dispatch_html_message
    r = _FakeRedis()
    raw = _html_message("<html></html>").to_dict()
    raw["protocol_version"] = "9.9"
    assert _dispatch_html_message(raw, r) is None
    assert r.calls == []


def test_worker_extract_failed_published():
    from workers.parser_worker import _dispatch_html_message
    r = _FakeRedis()
    raw = _html_message("<html></html>").to_dict()
    result = _dispatch_html_message(raw, r)
    assert result is not None
    assert result["status"] == "extract_failed"
    assert result["content"] == ""
    assert result["content_hash"] == ""
    payload = json.loads(r.calls[0][1])
    assert payload["status"] == "extract_failed"
    assert payload["matched_evidence"] == []


def test_worker_extraction_exception_still_publishes_failed():
    from workers.parser_worker import _dispatch_html_message
    with patch("crawler.detail.extraction_v2.get_global_content_selectors", side_effect=RuntimeError("boom")):
        r = _FakeRedis()
        raw = _html_message("<html><body><p>低空经济正文</p></body></html>").to_dict()
        result = _dispatch_html_message(raw, r)
    assert result is not None
    assert result["status"] == "extract_failed"
    assert r.calls and r.calls[0][0] == "crawler:result"


def test_worker_publish_failure_not_faked():
    from workers.parser_worker import _dispatch_html_message
    r = _FakeRedis()
    r.raise_on_lpush = True
    raw = _html_message("<html></html>").to_dict()
    assert _dispatch_html_message(raw, r) is None
    assert r.calls == []


def test_worker_v2_does_not_call_score_article():
    from workers.parser_worker import _dispatch_html_message, score_article
    import workers.parser_worker as parser_worker_module
    with patch.object(parser_worker_module, "score_article", side_effect=AssertionError("legacy scorer called")):
        r = _FakeRedis()
        raw = _html_message("<html><body><p>低空经济正文</p></body></html>").to_dict()
        result = _dispatch_html_message(raw, r)
    assert result is not None
    assert result["type"] == "article_result"


def test_b1_fixture_article_result_roundtrip():
    fixture_path = "tests/fixtures/article_result_v2_contract.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture = json.load(f)
    for key in ("article_result_v2", "article_result_v2_empty_evidence", "article_result_v2_extract_failed"):
        decoded = decode_v2_article_message(json.dumps(fixture[key], ensure_ascii=False))
        assert isinstance(decoded, ArticleResultV2)
        assert decoded.to_dict() == fixture[key]