"""Offline tests for the formal HTML search adapter."""

import os
from dataclasses import replace
from unittest.mock import patch

from crawler.search.adapter import SearchAdapter
from crawler.search.html_adapter import HTMLSearchAdapter
from crawler.search.search_plan import (
    ADAPTER_HTML,
    KEYWORD_LOCATION_FORM,
    KEYWORD_LOCATION_QUERY,
    PLAN_STATUS_READY,
    PROTOCOL_VERSION_V2,
    REQUEST_FORMAT_FORM_URLENCODED,
    REQUEST_FORMAT_NONE,
    RESPONSE_FORMAT_HTML,
    SEARCH_STRATEGY_HTML_FORM,
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

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "html_adapter_results.html")
POLICY = SearchProbePolicy()
DOMAIN = "example.gov.cn"
ENDPOINT = "https://example.gov.cn/search"


def _plan(method="GET", pagination=SearchPagination(), shape=None):
    base = SearchPlan(
        plan_id="",
        endpoint=ENDPOINT,
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_READY,
        strategy=SEARCH_STRATEGY_HTML_FORM,
        adapter=ADAPTER_HTML,
        http_method=method,
        request_format=REQUEST_FORMAT_NONE if method == "GET" else REQUEST_FORMAT_FORM_URLENCODED,
        response_format=RESPONSE_FORMAT_HTML,
        request_shape=shape or SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",)),
        pagination=pagination,
        selectors=SearchSelectors(".result-item", "h3 a", "h3 a", ".summary", ""),
        scope=SearchScope(domain=DOMAIN, allowed_path_prefixes=["/"]),
    )
    return replace(base, plan_id=compute_plan_id(base))


def _html_response(body, url=ENDPOINT, content_type="text/html"):
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
            return _html_response("")
        outcome = self.outcomes.pop(0)
        return outcome


def test_adapter_implements_protocol():
    assert isinstance(HTMLSearchAdapter(), SearchAdapter)
    assert HTMLSearchAdapter().adapter_name == "html"


def test_valid_html_get_and_post_plans_execute():
    adapter = HTMLSearchAdapter()
    get_fetcher = FakeFetcher([_html_response(_fixture_body())])
    result = adapter.execute(_plan(), ("k",), fetcher=get_fetcher, policy=POLICY)
    assert result.success
    post_plan = _plan(method="POST", shape=SearchRequestShape(KEYWORD_LOCATION_FORM, ("q",), form_fields=(("site", "x"),)))
    post_fetcher = FakeFetcher([_html_response(_fixture_body())])
    result = adapter.execute(post_plan, ("k",), fetcher=post_fetcher, policy=POLICY)
    assert result.success


def test_invalid_adapter_combinations_return_plan_invalid():
    adapter = HTMLSearchAdapter()
    plan = _plan()
    bad = replace(plan, strategy="json_api", plan_id="")
    bad = replace(bad, plan_id=compute_plan_id(bad))
    result = adapter.execute(bad, ("k",), fetcher=FakeFetcher(), policy=POLICY)
    assert result.failure_code == "plan_invalid"
    bad = replace(plan, request_format="json", plan_id="")
    bad = replace(bad, plan_id=compute_plan_id(bad))
    result = adapter.execute(bad, ("k",), fetcher=FakeFetcher(), policy=POLICY)
    assert result.failure_code == "plan_invalid"


def test_missing_selectors_returns_plan_not_executable():
    plan = replace(_plan(), selectors=SearchSelectors("", "", "", "", ""), plan_id="")
    plan = replace(plan, plan_id=compute_plan_id(plan))
    result = HTMLSearchAdapter().execute(plan, ("k",), fetcher=FakeFetcher(), policy=POLICY)
    assert result.failure_code == "plan_not_executable"


def test_get_request_construction():
    pagination = SearchPagination(enabled=True, location="query", value_path=("page",), start=1, step=1, page_size_path=("size",), page_size=10, max_pages=1)
    plan = _plan(pagination=pagination)
    fetcher = FakeFetcher([_html_response(_fixture_body())])
    HTMLSearchAdapter().execute(plan, ("低空经济",), fetcher=fetcher, policy=POLICY)
    request = fetcher.calls[0]
    assert "q=%E4%BD%8E%E7%A9%BA%E7%BB%8F%E6%B5%8E" in request.url
    assert "page=1" in request.url
    assert "size=10" in request.url
    assert request.body is None
    assert "Content-Type" not in dict(request.headers)
    assert "text/html" in dict(request.headers)["Accept"]


def test_post_form_request_construction():
    shape = SearchRequestShape(KEYWORD_LOCATION_FORM, ("q",), form_fields=(("site", "abc"),))
    pagination = SearchPagination(enabled=True, location="form", value_path=("page",), start=1, step=1, max_pages=1)
    plan = _plan(method="POST", shape=shape, pagination=pagination)
    fetcher = FakeFetcher([_html_response(_fixture_body())])
    HTMLSearchAdapter().execute(plan, ("k",), fetcher=fetcher, policy=POLICY)
    request = fetcher.calls[0]
    body = request.body.decode("utf-8")
    assert "q=k" in body
    assert "site=abc" in body
    assert "page=1" in body
    assert dict(request.headers)["Content-Type"] == "application/x-www-form-urlencoded"
    assert "{keyword}" not in body


def test_html_parse_and_dedupe():
    fetcher = FakeFetcher([_html_response(_fixture_body())])
    result = HTMLSearchAdapter().execute(_plan(), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    urls = [item.url for item in result.items]
    assert urls == [
        "https://example.gov.cn/a.html",
        "https://example.gov.cn/b.html",
        "https://example.gov.cn/c.html",
    ]
    assert result.items[0].title == "Alpha & Co"
    assert result.items[1].title == "Beta 中文"
    assert result.items[0].snippet == "First summary"


def test_invalid_css_is_selector_mismatch():
    plan = replace(_plan(), selectors=SearchSelectors("@@@", "h3 a", "h3 a", "", ""), plan_id="")
    plan = replace(plan, plan_id=compute_plan_id(plan))
    result = HTMLSearchAdapter().execute(plan, ("k",), fetcher=FakeFetcher([_html_response(_fixture_body())]), policy=POLICY)
    assert result.failure_code == "selector_mismatch"


def test_missing_title_or_url_is_selector_mismatch():
    body = '<div class="result-item"><h3>No Link</h3></div>'
    result = HTMLSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_html_response(body)]), policy=POLICY)
    assert result.failure_code == "selector_mismatch"


def test_wrong_content_type_is_response_rejected():
    result = HTMLSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_html_response("plain", content_type="text/plain")]), policy=POLICY)
    assert result.failure_code == "response_rejected"


def test_dangerous_result_url_is_response_rejected():
    body = '<div class="result-item"><h3><a href="javascript:alert(1)">Bad</a></h3></div>'
    result = HTMLSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_html_response(body)]), policy=POLICY)
    assert result.failure_code == "response_rejected"
    assert result.items == ()


def test_cross_scope_result_url_is_response_rejected():
    body = '<div class="result-item"><h3><a href="https://other.example/a">Bad</a></h3></div>'
    result = HTMLSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_html_response(body)]), policy=POLICY)
    assert result.failure_code == "response_rejected"


def test_first_page_zero_results_is_no_results():
    result = HTMLSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_html_response("<html></html>")]), policy=POLICY)
    assert result.status == "ok"
    assert result.failure_code == "no_results"
    assert result.items == ()


def test_multipage_stops_at_max_pages():
    pagination = SearchPagination(enabled=True, location="query", value_path=("page",), start=1, step=1, max_pages=2)
    fetcher = FakeFetcher([_html_response(_fixture_body()), _html_response('<div class="result-item"><h3><a href="/d.html">D</a></h3></div>')])
    result = HTMLSearchAdapter().execute(_plan(pagination=pagination), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 2
    assert "page=2" in fetcher.calls[1].url
    assert result.items[-1].url == "https://example.gov.cn/d.html"


def test_multipage_stops_on_empty_page():
    pagination = SearchPagination(enabled=True, location="query", value_path=("page",), start=1, step=1, max_pages=3)
    fetcher = FakeFetcher([_html_response(_fixture_body()), _html_response("<html></html>")])
    result = HTMLSearchAdapter().execute(_plan(pagination=pagination), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 2
    assert result.items[0].url == "https://example.gov.cn/a.html"


def test_multipage_stops_on_duplicate_page():
    pagination = SearchPagination(enabled=True, location="query", value_path=("page",), start=1, step=1, max_pages=3)
    fetcher = FakeFetcher([_html_response(_fixture_body()), _html_response(_fixture_body())])
    result = HTMLSearchAdapter().execute(_plan(pagination=pagination), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 2
    assert len(result.items) == 3


def test_offset_pagination_value():
    pagination = SearchPagination(enabled=True, location="query", value_path=("offset",), start=0, step=10, max_pages=2)
    fetcher = FakeFetcher([_html_response(_fixture_body()), _html_response('<div class="result-item"><h3><a href="/d.html">D</a></h3></div>')])
    HTMLSearchAdapter().execute(_plan(pagination=pagination), ("k",), fetcher=fetcher, policy=POLICY)
    assert "offset=0" in fetcher.calls[0].url
    assert "offset=10" in fetcher.calls[1].url


def test_later_page_failure_is_fail_closed():
    pagination = SearchPagination(enabled=True, location="query", value_path=("page",), start=1, step=1, max_pages=2)
    fetcher = FakeFetcher([_html_response(_fixture_body())], error=RuntimeError("boom"))
    result = HTMLSearchAdapter().execute(_plan(pagination=pagination), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.status == "failed"
    assert result.failure_code == "transport_failure"
    assert result.items == ()


def test_later_page_rejection_is_fail_closed():
    pagination = SearchPagination(enabled=True, location="query", value_path=("page",), start=1, step=1, max_pages=2)
    fetcher = FakeFetcher([_html_response(_fixture_body())], rejection=SearchProbeRejection("response_too_large", "too large"))
    result = HTMLSearchAdapter().execute(_plan(pagination=pagination), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.failure_code == "transport_failure"
    assert result.items == ()


def test_no_network_dns_or_redis_access():
    def fail(*_args, **_kwargs):
        raise AssertionError("external access attempted")

    fetcher = FakeFetcher([_html_response(_fixture_body())])
    with patch("socket.getaddrinfo", side_effect=fail), patch("urllib.request.urlopen", side_effect=fail):
        result = HTMLSearchAdapter().execute(_plan(), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 1


def test_path_prefix_boundary_is_enforced():
    plan = replace(_plan(), scope=SearchScope(domain=DOMAIN, allowed_path_prefixes=["/news"]), plan_id="")
    plan = replace(plan, plan_id=compute_plan_id(plan))
    body = "<div class=\"result-item\"><h3><a href=\"/news-old/a.html\">A</a></h3></div>"
    result = HTMLSearchAdapter().execute(plan, ("k",), fetcher=FakeFetcher([_html_response(body)]), policy=POLICY)
    assert result.failure_code == "response_rejected"
    assert result.items == ()
