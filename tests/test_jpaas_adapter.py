"""Offline tests for the formal JPAAS search adapter."""

import json
import os
from dataclasses import replace
from unittest.mock import patch

from crawler.search.adapter_registry import AdapterRegistry
from crawler.search.jpaas_adapter import JPAASSearchAdapter
from crawler.search.plan_executor import execute_search_plan
from crawler.search.search_plan import (
    ADAPTER_JPAAS,
    KEYWORD_LOCATION_QUERY,
    PLAN_STATUS_READY,
    PROTOCOL_VERSION_V2,
    REQUEST_FORMAT_NONE,
    RESPONSE_FORMAT_JSON,
    SEARCH_STRATEGY_JSON_API,
    SearchPagination,
    SearchPlan,
    SearchRequestShape,
    SearchScope,
    SearchSelectors,
    compute_plan_id,
)
from crawler.site.search_probe import (
    ProbeOutcome,
    SearchProbePolicy,
    SearchProbeRejection,
    SearchProbeResponse,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "jpaas_adapter_response.json")
POLICY = SearchProbePolicy()
DOMAIN = "example.gov.cn"
ENDPOINT = "https://example.gov.cn/api-gateway/jpaas-jsearch-web-server/interface/search/app/info"


def _plan(pagination=None):
    base = SearchPlan(
        plan_id="",
        endpoint=ENDPOINT,
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_READY,
        strategy=SEARCH_STRATEGY_JSON_API,
        adapter=ADAPTER_JPAAS,
        http_method="GET",
        request_format=REQUEST_FORMAT_NONE,
        response_format=RESPONSE_FORMAT_JSON,
        request_shape=SearchRequestShape(
            KEYWORD_LOCATION_QUERY,
            ("q",),
            fixed_query_params=(("webId", "3217"),),
        ),
        pagination=pagination or SearchPagination(
            enabled=True,
            location="query",
            value_path=("p",),
            start=1,
            step=1,
            page_size_path=("pg",),
            page_size=10,
            max_pages=1,
        ),
        selectors=SearchSelectors("", "", "", "", ""),
        scope=SearchScope(domain=DOMAIN, allowed_path_prefixes=["/"]),
    )
    return replace(base, plan_id=compute_plan_id(base))


def _response(body, content_type="application/json", url=ENDPOINT):
    return ProbeOutcome(SearchProbeResponse(200, content_type, body.encode("utf-8"), url, 0), None)


def _fixture_body():
    with open(FIXTURE, "r", encoding="utf-8") as f:
        return f.read()


class FakeFetcher:
    def __init__(self, outcomes=None, error=None, rejection=None):
        self.outcomes = list(outcomes or [])
        self.error = error
        self.rejection = rejection
        self.calls = []

    def fetch(self, request, *, policy):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        if self.rejection is not None:
            return ProbeOutcome(None, self.rejection)
        if not self.outcomes:
            return _response('{"code":"200","data":{"appSearchResultBeanList":[]}}')
        return self.outcomes.pop(0)


def test_valid_jpaas_plan_executes():
    result = JPAASSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response(_fixture_body())]), policy=POLICY)
    assert result.success
    assert len(result.items) == 2


def test_invalid_combinations_return_plan_invalid():
    adapter = JPAASSearchAdapter()
    plan = _plan()
    for kwargs in [
        {"adapter": "html"},
        {"strategy": "html_form"},
        {"http_method": "POST"},
        {"request_format": "form_urlencoded"},
        {"response_format": "html"},
    ]:
        bad = replace(plan, plan_id="", **kwargs)
        bad = replace(bad, plan_id=compute_plan_id(bad))
        result = adapter.execute(bad, ("k",), fetcher=FakeFetcher(), policy=POLICY)
        assert result.failure_code == "plan_invalid", kwargs


def test_jpaas_get_request_construction():
    pagination = SearchPagination(enabled=True, location="query", value_path=("p",), start=1, step=1, page_size_path=("pg",), page_size=10, max_pages=2)
    fetcher = FakeFetcher([_response(_fixture_body()), _response('{"code":"200","data":{"appSearchResultBeanList":[]}}')])
    JPAASSearchAdapter().execute(_plan(pagination), ("k",), fetcher=fetcher, policy=POLICY)
    request = fetcher.calls[0]
    assert "q=k" in request.url
    assert "webId=3217" in request.url
    assert "p=1" in request.url
    assert "pg=10" in request.url
    assert "p=2" in fetcher.calls[1].url
    assert request.body is None
    assert "Content-Type" not in dict(request.headers)


def test_content_type_accepts_plus_json_and_charset():
    for ctype in ["application/json", "application/ld+json", "application/json; charset=utf-8"]:
        result = JPAASSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response(_fixture_body(), content_type=ctype)]), policy=POLICY)
        assert result.success, ctype


def test_wrong_content_type_is_response_rejected():
    result = JPAASSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response("{}", content_type="text/html")]), policy=POLICY)
    assert result.failure_code == "response_rejected"


def test_invalid_json_is_response_rejected():
    result = JPAASSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response("{not-json")]), policy=POLICY)
    assert result.failure_code == "response_rejected"


def test_duplicate_json_key_is_response_rejected():
    body = '{"code":"200","code":"200","data":{"appSearchResultBeanList":[]}}'
    result = JPAASSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.failure_code == "response_rejected"


def test_non_success_code_is_response_rejected():
    body = '{"code":"500","data":{"appSearchResultBeanList":[]}}'
    result = JPAASSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.failure_code == "response_rejected"


def test_missing_result_container_is_selector_mismatch():
    result = JPAASSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response('{"code":"200","data":{}}')]), policy=POLICY)
    assert result.failure_code == "selector_mismatch"


def test_first_page_empty_is_no_results():
    result = JPAASSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response('{"code":"200","data":{"appSearchResultBeanList":[]}}')]), policy=POLICY)
    assert result.status == "ok"
    assert result.failure_code == "no_results"
    assert result.items == ()


def test_nested_and_direct_document_mapping():
    result = JPAASSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response(_fixture_body())]), policy=POLICY)
    assert result.items[0].title == "标题一"
    assert result.items[0].url == "https://example.gov.cn/a.html"
    assert result.items[0].snippet == "正文一"
    assert result.items[1].title == "标题二"
    assert result.items[1].url == "https://example.gov.cn/b.html"


def test_dangerous_result_url_is_response_rejected():
    body = '{"code":"200","data":{"appSearchResultBeanList":[{"title":"Bad","url":"javascript:alert(1)"}]}}'
    result = JPAASSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.failure_code == "response_rejected"
    assert result.items == ()


def test_cross_scope_result_url_is_response_rejected():
    body = '{"code":"200","data":{"appSearchResultBeanList":[{"title":"Bad","url":"https://other.example/a"}]}}'
    result = JPAASSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.failure_code == "response_rejected"


def test_multipage_aggregates_and_dedupes():
    pagination = SearchPagination(enabled=True, location="query", value_path=("p",), start=1, step=1, page_size_path=("pg",), page_size=10, max_pages=3)
    page2 = json.dumps({"code":"200","data":{"appSearchResultBeanList":[{"title":"三","url":"/c"}]}}, ensure_ascii=False)
    duplicate = _fixture_body()
    fetcher = FakeFetcher([_response(_fixture_body()), _response(page2), _response(duplicate)])
    result = JPAASSearchAdapter().execute(_plan(pagination), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 3
    assert len(result.items) == 3


def test_duplicate_page_stops():
    pagination = SearchPagination(enabled=True, location="query", value_path=("p",), start=1, step=1, page_size_path=("pg",), page_size=10, max_pages=3)
    page1 = _fixture_body()
    fetcher = FakeFetcher([_response(page1), _response(page1)])
    result = JPAASSearchAdapter().execute(_plan(pagination), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 2
    assert len(result.items) == 2


def test_later_page_failure_is_fail_closed():
    pagination = SearchPagination(enabled=True, location="query", value_path=("p",), start=1, step=1, page_size_path=("pg",), page_size=10, max_pages=2)
    fetcher = FakeFetcher([_response(_fixture_body())], error=RuntimeError("boom"))
    result = JPAASSearchAdapter().execute(_plan(pagination), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.status == "failed"
    assert result.failure_code == "transport_failure"
    assert result.items == ()


def test_executor_delegates_to_jpaas_adapter():
    plan = _plan()
    fetcher = FakeFetcher([_response(_fixture_body())])
    result = execute_search_plan(plan, ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success


def test_registry_resolves_jpaas_adapter():
    registry = AdapterRegistry()
    registry.register(JPAASSearchAdapter())
    resolved = registry.resolve_plan(_plan())
    assert resolved.found
    assert resolved.adapter is not None


def test_no_network_dns_or_redis_access():
    def fail(*_args, **_kwargs):
        raise AssertionError("external access attempted")

    fetcher = FakeFetcher([_response(_fixture_body())])
    with patch("socket.getaddrinfo", side_effect=fail), patch("urllib.request.urlopen", side_effect=fail):
        result = JPAASSearchAdapter().execute(_plan(), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 1
