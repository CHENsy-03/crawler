"""Offline tests for deterministic SearchHit construction."""

from dataclasses import replace

from crawler.search.execution_models import SearchResultItem
from crawler.search.search_hit_builder import build_search_hit, compute_hit_id
from crawler.search.search_plan import (
    ADAPTER_HTML,
    KEYWORD_LOCATION_QUERY,
    PLAN_STATUS_READY,
    PROTOCOL_VERSION_V2,
    REQUEST_FORMAT_NONE,
    RESPONSE_FORMAT_HTML,
    SEARCH_STRATEGY_HTML_FORM,
    SearchPagination,
    SearchPlan,
    SearchRequestShape,
    SearchScope,
    compute_plan_id,
)

TASK_ID = "task-019b-2"
URL = "https://example.gov.cn/news/1.html"


def _plan():
    base = SearchPlan(
        plan_id="",
        endpoint="https://example.gov.cn/search",
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_READY,
        strategy=SEARCH_STRATEGY_HTML_FORM,
        adapter=ADAPTER_HTML,
        http_method="GET",
        request_format=REQUEST_FORMAT_NONE,
        response_format=RESPONSE_FORMAT_HTML,
        request_shape=SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",)),
        pagination=SearchPagination(),
        scope=SearchScope(domain="example.gov.cn"),
    )
    return replace(base, plan_id=compute_plan_id(base))


def _item(snippet="snippet", body="body", published_at="", source=""):
    return SearchResultItem(
        title="Title",
        url=URL,
        snippet=snippet,
        body=body,
        published_at=published_at,
        source=source,
    )


def test_compute_hit_id_is_deterministic_and_query_sensitive():
    first = compute_hit_id(
        protocol_version=PROTOCOL_VERSION_V2,
        task_id=TASK_ID,
        plan_id=_plan().plan_id,
        original_query="k1",
        query_term="k1",
        url=URL,
    )
    second = compute_hit_id(
        protocol_version=PROTOCOL_VERSION_V2,
        task_id=TASK_ID,
        plan_id=_plan().plan_id,
        original_query="k1",
        query_term="k1",
        url=URL,
    )
    other = compute_hit_id(
        protocol_version=PROTOCOL_VERSION_V2,
        task_id=TASK_ID,
        plan_id=_plan().plan_id,
        original_query="k2",
        query_term="k2",
        url=URL,
    )
    assert first == second
    assert first != other
    assert len(first) == 64
    assert first == first.lower()


def test_build_search_hit_maps_required_fields():
    plan = _plan()
    hit = build_search_hit(
        task_id=TASK_ID,
        plan=plan,
        original_query="k1",
        query_term="k1",
        item=_item(published_at="2026-08-13", source="custom.gov.cn"),
        discovered_at="2026-08-13T00:00:00Z",
    )
    assert hit.hit_id == compute_hit_id(
        protocol_version=PROTOCOL_VERSION_V2,
        task_id=TASK_ID,
        plan_id=plan.plan_id,
        original_query="k1",
        query_term="k1",
        url=URL,
    )
    assert hit.plan_id == plan.plan_id
    assert hit.url == URL
    assert hit.title == "Title"
    assert hit.snippet == "snippet"
    assert hit.published_at == "2026-08-13"
    assert hit.source == "custom.gov.cn"
    assert hit.score == 0
    assert hit.matched_keywords == []


def test_source_falls_back_to_scope_domain():
    plan = _plan()
    hit = build_search_hit(
        task_id=TASK_ID,
        plan=plan,
        original_query="k1",
        query_term="k1",
        item=_item(),
        discovered_at="now",
    )
    assert hit.source == "example.gov.cn"


def test_snippet_falls_back_to_body():
    plan = _plan()
    hit = build_search_hit(
        task_id=TASK_ID,
        plan=plan,
        original_query="k1",
        query_term="k1",
        item=_item(snippet="", body="body text"),
        discovered_at="now",
    )
    assert hit.snippet == "body text"
