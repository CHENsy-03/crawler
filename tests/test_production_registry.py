"""Offline tests for the production adapter registry composition."""

from unittest.mock import patch

from crawler.search.adapter_composition import build_default_adapter_registry
from crawler.search.adapter_registry import AdapterRegistry
from crawler.search.execution_models import SearchPlanExecutionResult
from crawler.search.plan_executor import RegistryPlanExecutor, execute_plan_with_registry
from crawler.search.search_plan import (
    ADAPTER_GENERIC_JSON,
    ADAPTER_HTML,
    ADAPTER_JPAAS,
    ADAPTER_TRS,
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
from crawler.site.search_probe import SearchProbePolicy
from dataclasses import replace

POLICY = SearchProbePolicy()


def _plan(adapter=ADAPTER_HTML):
    base = SearchPlan(
        plan_id="",
        endpoint="https://example.gov.cn/search",
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_READY,
        strategy=SEARCH_STRATEGY_HTML_FORM if adapter == ADAPTER_HTML else "json_api",
        adapter=adapter,
        http_method="GET",
        request_format=REQUEST_FORMAT_NONE,
        response_format=RESPONSE_FORMAT_HTML,
        request_shape=SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",)),
        pagination=SearchPagination(),
        scope=SearchScope(domain="example.gov.cn"),
    )
    return replace(base, plan_id=compute_plan_id(base))


class FakeAdapter:
    def __init__(self, name):
        self.adapter_name = name
        self.calls = []

    def execute(self, plan, keywords, *, fetcher, policy):
        self.calls.append(plan)
        return SearchPlanExecutionResult(plan.plan_id, "ok", (), "text/html")


def test_default_registry_contains_only_four_adapters():
    registry = build_default_adapter_registry()
    assert set(registry._adapters) == {ADAPTER_HTML, ADAPTER_TRS, ADAPTER_JPAAS, ADAPTER_GENERIC_JSON}


def test_default_registry_is_fresh_per_call():
    first = build_default_adapter_registry()
    second = build_default_adapter_registry()
    assert first is not second
    assert first.get(ADAPTER_HTML) is not second.get(ADAPTER_HTML)


def test_registry_construction_makes_no_network():
    def fail(*_args, **_kwargs):
        raise AssertionError("network access attempted")

    with patch("socket.getaddrinfo", side_effect=fail), patch("urllib.request.urlopen", side_effect=fail):
        registry = build_default_adapter_registry()
    assert registry.get(ADAPTER_HTML) is not None


def test_registry_plan_executor_uses_injected_registry():
    registry = AdapterRegistry()
    adapter = FakeAdapter(ADAPTER_HTML)
    registry.register(adapter)
    executor = RegistryPlanExecutor(registry)
    result = executor(_plan(), ("k",), fetcher=None, policy=POLICY)
    assert result.success
    assert len(adapter.calls) == 1


def test_registry_executor_has_no_fallback_for_missing_adapter():
    registry = AdapterRegistry()
    result = execute_plan_with_registry(_plan(), ("k",), registry=registry, fetcher=None, policy=POLICY)
    assert result.failure_code == "plan_invalid"


def test_strategy_and_source_do_not_affect_dispatch():
    registry = AdapterRegistry()
    adapter = FakeAdapter(ADAPTER_HTML)
    registry.register(adapter)
    plan = _plan(ADAPTER_HTML)
    plan = replace(plan, discovery=replace(plan.discovery, source="trs_signature"), plan_id="")
    plan = replace(plan, plan_id=compute_plan_id(plan))
    result = execute_plan_with_registry(plan, ("k",), registry=registry, fetcher=None, policy=POLICY)
    assert result.success
    assert adapter.calls
