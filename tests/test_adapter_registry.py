"""Offline tests for the explicit AdapterRegistry."""

import pytest

from crawler.search.adapter_registry import AdapterRegistry
from crawler.search.execution_models import SearchPlanExecutionResult


class FakeAdapter:
    def __init__(self, name):
        self.adapter_name = name

    def execute(self, plan, query_term, *, fetcher, policy):
        return SearchPlanExecutionResult(plan.plan_id, "ok", (), "text/html")


def test_register_and_resolve_by_adapter_name():
    registry = AdapterRegistry()
    adapter = FakeAdapter("html")
    registry.register(adapter)
    assert registry.get("html") is adapter


def test_duplicate_registration_rejected():
    registry = AdapterRegistry()
    registry.register(FakeAdapter("html"))
    with pytest.raises(ValueError):
        registry.register(FakeAdapter("html"))


def test_unknown_name_rejected_on_register():
    registry = AdapterRegistry()
    with pytest.raises(ValueError):
        registry.register(FakeAdapter("custom"))


def test_missing_adapter_is_not_resolved():
    registry = AdapterRegistry()
    result = registry.resolve_plan(_plan("html"))
    assert not result.found
    assert result.adapter is None
    assert result.error == "adapter not registered"


def test_no_fallback_from_unknown_adapter():
    registry = AdapterRegistry()
    registry.register(FakeAdapter("html"))
    result = registry.resolve_plan(_plan("trs"))
    assert not result.found
    assert result.adapter is None


def _plan(adapter):
    from crawler.search.search_plan import (
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
    from dataclasses import replace

    base = SearchPlan(
        plan_id="",
        endpoint="https://example.gov.cn/search",
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_READY,
        strategy=SEARCH_STRATEGY_HTML_FORM,
        adapter=adapter,
        http_method="GET",
        request_format=REQUEST_FORMAT_NONE,
        response_format=RESPONSE_FORMAT_HTML,
        request_shape=SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",)),
        pagination=SearchPagination(),
        scope=SearchScope(domain="example.gov.cn"),
    )
    return replace(base, plan_id=compute_plan_id(base))
