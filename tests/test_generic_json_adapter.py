"""Offline tests for the formal Generic JSON search adapter."""

import json
from dataclasses import replace
from unittest.mock import patch

from crawler.search.adapter_registry import AdapterRegistry
from crawler.search.generic_json_adapter import GenericJSONSearchAdapter
from crawler.search.plan_executor import execute_search_plan
from crawler.search.search_plan import (
    ADAPTER_GENERIC_JSON,
    KEYWORD_LOCATION_JSON,
    KEYWORD_LOCATION_QUERY,
    PLAN_STATUS_READY,
    PROTOCOL_VERSION_V2,
    REQUEST_FORMAT_JSON,
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

POLICY = SearchProbePolicy()
DOMAIN = "api.example.gov.cn"
GET_ENDPOINT = "https://api.example.gov.cn/search"
POST_ENDPOINT = "https://api.example.gov.cn/search"


def _get_plan():
    base = SearchPlan(
        plan_id="",
        endpoint=GET_ENDPOINT,
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_READY,
        strategy=SEARCH_STRATEGY_JSON_API,
        adapter=ADAPTER_GENERIC_JSON,
        http_method="GET",
        request_format=REQUEST_FORMAT_NONE,
        response_format=RESPONSE_FORMAT_JSON,
        request_shape=SearchRequestShape(
            KEYWORD_LOCATION_QUERY,
            ("q",),
            fixed_query_params=(("api", "1"),),
        ),
        pagination=SearchPagination(
            enabled=True,
            location="query",
            value_path=("page",),
            start=1,
            step=1,
            page_size_path=("size",),
            page_size=10,
            max_pages=1,
        ),
        selectors=SearchSelectors("/data/items", "/title", "/url", "/snippet", "/body"),
        scope=SearchScope(domain=DOMAIN, allowed_path_prefixes=["/"]),
    )
    return replace(base, plan_id=compute_plan_id(base))


def _post_plan():
    base = SearchPlan(
        plan_id="",
        endpoint=POST_ENDPOINT,
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_READY,
        strategy=SEARCH_STRATEGY_JSON_API,
        adapter=ADAPTER_GENERIC_JSON,
        http_method="POST",
        request_format=REQUEST_FORMAT_JSON,
        response_format=RESPONSE_FORMAT_JSON,
        request_shape=SearchRequestShape(
            KEYWORD_LOCATION_JSON,
            ("query", "kw"),
        ),
        pagination=SearchPagination(
            enabled=True,
            location="json",
            value_path=("page",),
            start=1,
            step=1,
            page_size_path=("size",),
            page_size=10,
            max_pages=1,
        ),
        selectors=SearchSelectors("/data/items", "/title", "/url", "", ""),
        scope=SearchScope(domain=DOMAIN, allowed_path_prefixes=["/"]),
    )
    return replace(base, plan_id=compute_plan_id(base))


def _response(body, content_type="application/json", url=GET_ENDPOINT):
    return ProbeOutcome(SearchProbeResponse(200, content_type, body.encode("utf-8"), url, 0), None)


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
            return _response('{"data":{"items":[]}}')
        return self.outcomes.pop(0)


def _ok_body():
    return json.dumps({
        "data": {
            "items": [
                {"title": "A", "url": "/a.html", "snippet": "s1", "body": "b1"},
                {"title": "B", "url": "https://api.example.gov.cn/b.html"},
            ]
        }
    }, ensure_ascii=False)


def test_valid_get_plan_executes():
    result = GenericJSONSearchAdapter().execute(_get_plan(), "k", fetcher=FakeFetcher([_response(_ok_body())]), policy=POLICY)
    assert result.success
    assert len(result.items) == 2


def test_valid_post_plan_executes():
    result = GenericJSONSearchAdapter().execute(_post_plan(), "k", fetcher=FakeFetcher([_response(_ok_body(), url=POST_ENDPOINT)]), policy=POLICY)
    assert result.success


def test_invalid_combinations_return_plan_invalid():
    adapter = GenericJSONSearchAdapter()
    plan = _get_plan()
    for kwargs in [
        {"adapter": "html"},
        {"strategy": "html_form"},
        {"request_format": "json"},
        {"response_format": "html"},
    ]:
        bad = replace(plan, plan_id="", **kwargs)
        bad = replace(bad, plan_id=compute_plan_id(bad))
        result = adapter.execute(bad, "k", fetcher=FakeFetcher(), policy=POLICY)
        assert result.failure_code == "plan_invalid", kwargs


def test_get_request_construction():
    fetcher = FakeFetcher([_response(_ok_body())])
    GenericJSONSearchAdapter().execute(_get_plan(), "k", fetcher=fetcher, policy=POLICY)
    request = fetcher.calls[0]
    assert "q=k" in request.url
    assert "api=1" in request.url
    assert "page=1" in request.url
    assert "size=10" in request.url
    assert request.body is None


def test_post_request_construction():
    fetcher = FakeFetcher([_response(_ok_body(), url=POST_ENDPOINT)])
    GenericJSONSearchAdapter().execute(_post_plan(), "k", fetcher=fetcher, policy=POLICY)
    request = fetcher.calls[0]
    body = json.loads(request.body.decode("utf-8"))
    assert body == {"query": {"kw": "k"}, "page": 1, "size": 10}
    assert dict(request.headers)["Content-Type"] == "application/json"


def test_pointer_escape_parsing():
    body = json.dumps({"rows": [{"title": "A/B", "url": "/a?x=1~2", "text~x": "ok"}]}, ensure_ascii=False)
    plan = replace(
        _get_plan(),
        selectors=SearchSelectors("/rows", "/title", "/url", "/text~0x", ""),
        plan_id="",
    )
    plan = replace(plan, plan_id=compute_plan_id(plan))
    result = GenericJSONSearchAdapter().execute(plan, "k", fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.success
    assert result.items[0].title == "A/B"


def test_top_level_array_parsing():
    body = json.dumps([{"title": "A", "url": "/a"}], ensure_ascii=False)
    plan = replace(_get_plan(), selectors=SearchSelectors("", "/title", "/url", "", ""), plan_id="")
    plan = replace(plan, plan_id=compute_plan_id(plan))
    result = GenericJSONSearchAdapter().execute(plan, "k", fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.success
    assert result.items[0].url == "https://api.example.gov.cn/a"


def test_missing_result_pointer_is_selector_mismatch():
    result = GenericJSONSearchAdapter().execute(_get_plan(), "k", fetcher=FakeFetcher([_response('{"data":{}}')]), policy=POLICY)
    assert result.failure_code == "selector_mismatch"


def test_wrong_container_type_is_selector_mismatch():
    result = GenericJSONSearchAdapter().execute(_get_plan(), "k", fetcher=FakeFetcher([_response('{"data":{"items":{}}}')]), policy=POLICY)
    assert result.failure_code == "selector_mismatch"


def test_missing_title_or_url_is_selector_mismatch():
    body = '{"data":{"items":[{"title":"A"}]}}'
    result = GenericJSONSearchAdapter().execute(_get_plan(), "k", fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.failure_code == "selector_mismatch"


def test_first_page_empty_is_no_results():
    result = GenericJSONSearchAdapter().execute(_get_plan(), "k", fetcher=FakeFetcher([_response('{"data":{"items":[]}}')]), policy=POLICY)
    assert result.status == "ok"
    assert result.failure_code == "no_results"
    assert result.items == ()


def test_invalid_json_is_response_rejected():
    result = GenericJSONSearchAdapter().execute(_get_plan(), "k", fetcher=FakeFetcher([_response("{bad")]), policy=POLICY)
    assert result.failure_code == "response_rejected"


def test_duplicate_json_key_is_response_rejected():
    body = '{"data":{"items":[]},"data":{"items":[]}}'
    result = GenericJSONSearchAdapter().execute(_get_plan(), "k", fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.failure_code == "response_rejected"


def test_dangerous_result_url_is_response_rejected():
    body = '{"data":{"items":[{"title":"A","url":"javascript:alert(1)"}]}}'
    result = GenericJSONSearchAdapter().execute(_get_plan(), "k", fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.failure_code == "response_rejected"
    assert result.items == ()


def test_cross_scope_result_url_is_response_rejected():
    body = '{"data":{"items":[{"title":"A","url":"https://other.example/a"}]}}'
    result = GenericJSONSearchAdapter().execute(_get_plan(), "k", fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.failure_code == "response_rejected"


def test_multipage_aggregates_and_dedupes():
    pagination = replace(_get_plan().pagination, max_pages=3)
    plan = replace(_get_plan(), pagination=pagination, plan_id="")
    plan = replace(plan, plan_id=compute_plan_id(plan))
    page2 = json.dumps({"data": {"items": [{"title": "C", "url": "/c.html"}]}}, ensure_ascii=False)
    duplicate = _ok_body()
    fetcher = FakeFetcher([_response(_ok_body()), _response(page2), _response(duplicate)])
    result = GenericJSONSearchAdapter().execute(plan, "k", fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 3
    assert len(result.items) == 3


def test_duplicate_page_stops():
    pagination = replace(_get_plan().pagination, max_pages=3)
    plan = replace(_get_plan(), pagination=pagination, plan_id="")
    plan = replace(plan, plan_id=compute_plan_id(plan))
    fetcher = FakeFetcher([_response(_ok_body()), _response(_ok_body())])
    result = GenericJSONSearchAdapter().execute(plan, "k", fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 2
    assert len(result.items) == 2


def test_later_page_failure_is_fail_closed():
    pagination = replace(_get_plan().pagination, max_pages=2)
    plan = replace(_get_plan(), pagination=pagination, plan_id="")
    plan = replace(plan, plan_id=compute_plan_id(plan))
    fetcher = FakeFetcher([_response(_ok_body())], error=RuntimeError("boom"))
    result = GenericJSONSearchAdapter().execute(plan, "k", fetcher=fetcher, policy=POLICY)
    assert result.status == "failed"
    assert result.failure_code == "transport_failure"
    assert result.items == ()


def test_executor_delegates_to_generic_json_adapter():
    plan = _get_plan()
    fetcher = FakeFetcher([_response(_ok_body())])
    result = execute_search_plan(plan, "k", fetcher=fetcher, policy=POLICY)
    assert result.success


def test_registry_resolves_generic_json_adapter():
    registry = AdapterRegistry()
    registry.register(GenericJSONSearchAdapter())
    resolved = registry.resolve_plan(_get_plan())
    assert resolved.found
    assert resolved.adapter is not None


def test_no_network_dns_or_redis_access():
    def fail(*_args, **_kwargs):
        raise AssertionError("external access attempted")

    fetcher = FakeFetcher([_response(_ok_body())])
    with patch("socket.getaddrinfo", side_effect=fail), patch("urllib.request.urlopen", side_effect=fail):
        result = GenericJSONSearchAdapter().execute(_get_plan(), "k", fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 1


def test_path_prefix_boundary_is_enforced():
    plan = replace(_get_plan(), scope=SearchScope(domain=DOMAIN, allowed_path_prefixes=["/news"]), plan_id="")
    plan = replace(plan, plan_id=compute_plan_id(plan))
    body = "{\"data\":{\"items\":[{\"title\":\"A\",\"url\":\"/news-old/a\"}]}}"
    result = GenericJSONSearchAdapter().execute(plan, "k", fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.failure_code == "response_rejected"
    assert result.items == ()


def test_disabled_pagination_executes_single_page():
    plan = replace(_get_plan(), pagination=SearchPagination(), plan_id="")
    plan = replace(plan, plan_id=compute_plan_id(plan))
    fetcher = FakeFetcher([_response(_ok_body())])
    result = GenericJSONSearchAdapter().execute(plan, "k", fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 1
    assert "page=" not in fetcher.calls[0].url
    assert "size=" not in fetcher.calls[0].url
