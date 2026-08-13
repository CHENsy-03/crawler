"""Offline tests for SearchPlanExecutor."""

import json
from dataclasses import replace

from crawler.search.plan_executor import execute_search_plan
from crawler.search.search_plan import (
    ADAPTER_GENERIC_JSON,
    ADAPTER_HTML,
    KEYWORD_LOCATION_FORM,
    KEYWORD_LOCATION_JSON,
    KEYWORD_LOCATION_QUERY,
    REQUEST_FORMAT_FORM_URLENCODED,
    REQUEST_FORMAT_JSON,
    REQUEST_FORMAT_NONE,
    RESPONSE_FORMAT_HTML,
    RESPONSE_FORMAT_JSON,
    SearchPagination,
    SearchRequestShape,

    PLAN_STATUS_READY,
    PROTOCOL_VERSION_V2,
    SEARCH_STRATEGY_HTML_FORM,
    SEARCH_STRATEGY_JSON_API,
    SearchPagination,
    SearchPlan,
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
TARGET = "https://example.gov.cn/"


def _plan(status=PLAN_STATUS_READY, strategy=SEARCH_STRATEGY_HTML_FORM, method="GET"):
    base = SearchPlan(
        plan_id="",
        endpoint="https://example.gov.cn/search",
        protocol_version=PROTOCOL_VERSION_V2,
        status=status,
        strategy=strategy,
        adapter=ADAPTER_HTML,
        http_method=method,
        request_format=REQUEST_FORMAT_NONE if method == "GET" else REQUEST_FORMAT_FORM_URLENCODED,
        response_format=RESPONSE_FORMAT_HTML,
        request_shape=SearchRequestShape(
            keyword_location=KEYWORD_LOCATION_QUERY if method == "GET" else KEYWORD_LOCATION_FORM,
            keyword_path=("q",),
        ),
        pagination=SearchPagination(),
        selectors=SearchSelectors("div.result-item", "a", "a", "", ""),
        scope=SearchScope(domain="example.gov.cn"),
        created_from="test",
    )
    return replace(base, plan_id=compute_plan_id(base))
def _json_plan(method="POST"):
    base = SearchPlan(
        plan_id="",
        endpoint="https://api.example.gov.cn/search",
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_READY,
        strategy=SEARCH_STRATEGY_JSON_API,
        adapter=ADAPTER_GENERIC_JSON,
        http_method=method,
        request_format=REQUEST_FORMAT_JSON if method == "POST" else REQUEST_FORMAT_NONE,
        response_format=RESPONSE_FORMAT_JSON,
        request_shape=SearchRequestShape(
            keyword_location=KEYWORD_LOCATION_JSON,
            keyword_path=("query", "kw"),
        ),
        pagination=SearchPagination(),
        selectors=SearchSelectors("/data/items", "/title", "/url", "", ""),
        scope=SearchScope(domain="api.example.gov.cn"),
        created_from="test",
    )
    return replace(base, plan_id=compute_plan_id(base))
class FakeFetcher:
    def __init__(self, outcome=None, error=None):
        self.outcome = outcome
        self.error = error
        self.calls = []

    def fetch(self, request, *, policy):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        if self.outcome is None:
            return ProbeOutcome(None, SearchProbeRejection("no_response", "no response"))
        return self.outcome


def _html_response(body=None, url="https://example.gov.cn/search", status=200):
    if body is None:
        body = (
            b'<div class="results">'
            b'<div class="result-item"><a href="/a.html">A</a></div>'
            b'<div class="result-item"><a href="/a.html">A</a></div>'
            b'<div class="result-item"><a href="/b.html">B</a></div>'
            b'</div>'
        )
    return ProbeOutcome(SearchProbeResponse(status, "text/html", body, url, 0), None)


def test_ready_plan_executes():
    plan = _plan()
    fetcher = FakeFetcher(_html_response())
    result = execute_search_plan(plan, ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    assert [item.url for item in result.items] == [
        "https://example.gov.cn/a.html",
        "https://example.gov.cn/b.html",
    ]


def test_draft_plan_makes_zero_requests():
    plan = _plan(status="draft")
    fetcher = FakeFetcher(_html_response())
    result = execute_search_plan(plan, ("k",), fetcher=fetcher, policy=POLICY)
    assert not result.success
    assert result.failure_code == "plan_not_executable"
    assert fetcher.calls == []


def test_unknown_status_makes_zero_requests():
    plan = _plan(status="blocked")
    fetcher = FakeFetcher(_html_response())
    result = execute_search_plan(plan, ("k",), fetcher=fetcher, policy=POLICY)
    assert result.failure_code == "plan_not_executable"
    assert fetcher.calls == []


def test_fingerprint_mismatch_rejected():
    plan = _plan()
    bad = replace(plan, plan_id="tampered")
    fetcher = FakeFetcher(_html_response())
    result = execute_search_plan(bad, ("k",), fetcher=fetcher, policy=POLICY)
    assert result.failure_code == "plan_invalid"
    assert fetcher.calls == []


def test_missing_selectors_rejected():
    plan = _plan()
    missing = replace(plan, selectors=SearchSelectors("", "", "", "", ""))
    fetcher = FakeFetcher(_html_response())
    result = execute_search_plan(missing, ("k",), fetcher=fetcher, policy=POLICY)
    assert result.failure_code == "plan_not_executable"
    assert fetcher.calls == []


def test_get_request_keyword_encoded_once():
    plan = _plan()
    fetcher = FakeFetcher(_html_response())
    execute_search_plan(plan, ("低空经济",), fetcher=fetcher, policy=POLICY)
    assert fetcher.calls[0].body is None
    assert "q=%E4%BD%8E%E7%A9%BA%E7%BB%8F%E6%B5%8E" in fetcher.calls[0].url


def test_post_form_body_uses_structured_request_shape():
    base = SearchPlan(
        plan_id="",
        endpoint="https://example.gov.cn/search",
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_READY,
        strategy=SEARCH_STRATEGY_HTML_FORM,
        adapter=ADAPTER_HTML,
        http_method="POST",
        request_format=REQUEST_FORMAT_FORM_URLENCODED,
        response_format=RESPONSE_FORMAT_HTML,
        request_shape=SearchRequestShape(
            keyword_location=KEYWORD_LOCATION_FORM,
            keyword_path=("q",),
            form_fields=(("siteCode", "abc"),),
        ),
        pagination=SearchPagination(),
        selectors=SearchSelectors("div.result-item", "a", "a", "", ""),
        scope=SearchScope(domain="example.gov.cn"),
    )
    plan = replace(base, plan_id=compute_plan_id(base))
    fetcher = FakeFetcher(_html_response())
    execute_search_plan(plan, ("低空经济",), fetcher=fetcher, policy=POLICY)
    body = fetcher.calls[0].body.decode("utf-8")
    assert "siteCode=abc" in body
    assert "q=" in body
    assert "低空经济" not in body
    assert "%E4%BD%8E%E7%A9%BA%E7%BB%8F%E6%B5%8E" in body


def test_json_plan_constructs_json_body():
    plan = _json_plan()
    fetcher = FakeFetcher(
        ProbeOutcome(
            SearchProbeResponse(
                200,
                "application/json",
                b'{"data":{"items":[{"title":"A","url":"https://api.example.gov.cn/a"},{"title":"B","url":"https://api.example.gov.cn/b"}]}}',
                "https://api.example.gov.cn/search",
                0,
            ),
            None,
        )
    )
    result = execute_search_plan(plan, ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    body = json.loads(fetcher.calls[0].body.decode("utf-8"))
    assert body["query"]["kw"] == "k"


def test_json_duplicate_keys_rejected():
    plan = _json_plan()
    body = b'{"data":{"items":[{"title":"A","title":"B","url":"https://api.example.gov.cn/a"},{"title":"C","url":"https://api.example.gov.cn/b"}]}}'
    fetcher = FakeFetcher(ProbeOutcome(SearchProbeResponse(200, "application/json", body, "https://api.example.gov.cn/search", 0), None))
    result = execute_search_plan(plan, ("k",), fetcher=fetcher, policy=POLICY)
    assert result.failure_code == "selector_mismatch"


def test_transport_failure_no_retry():
    plan = _plan()
    fetcher = FakeFetcher(error=RuntimeError("boom"))
    result = execute_search_plan(plan, ("k",), fetcher=fetcher, policy=POLICY)
    assert result.failure_code == "transport_failure"
    assert len(fetcher.calls) == 1


def test_content_type_mismatch_rejected():
    plan = _plan()
    fetcher = FakeFetcher(ProbeOutcome(SearchProbeResponse(200, "text/plain", b"plain", plan.endpoint, 0), None))
    result = execute_search_plan(plan, ("k",), fetcher=fetcher, policy=POLICY)
    assert result.failure_code == "response_rejected"


def test_empty_html_result_is_no_results():
    plan = _plan()
    body = b"<html><body>no results</body></html>"
    fetcher = FakeFetcher(_html_response(body=body))
    result = execute_search_plan(plan, ("k",), fetcher=fetcher, policy=POLICY)
    assert result.failure_code == "no_results"
    assert result.items == ()


def test_result_repr_does_not_leak_body_or_keyword():
    plan = _plan()
    fetcher = FakeFetcher(_html_response())
    result = execute_search_plan(plan, ("secret-keyword",), fetcher=fetcher, policy=POLICY)
    assert "secret-keyword" not in repr(result)
    assert "html" not in repr(result).lower()


def test_multipage_html_plan_executes_through_adapter():
    pagination = SearchPagination(
        enabled=True,
        location="query",
        value_path=("page",),
        start=1,
        step=1,
        max_pages=2,
    )
    base = replace(_plan(), pagination=pagination)
    plan = replace(base, plan_id=compute_plan_id(base))
    fetcher = FakeFetcher(_html_response())
    result = execute_search_plan(plan, ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 2
