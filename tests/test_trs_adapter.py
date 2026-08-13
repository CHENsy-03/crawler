"""Offline tests for the formal TRS search adapter."""

import json
import os
from dataclasses import replace
from unittest.mock import patch

from crawler.search.adapter import SearchAdapter
from crawler.search.trs_adapter import TRSSearchAdapter
from crawler.search.search_plan import (
    ADAPTER_TRS,
    KEYWORD_LOCATION_FORM,
    PLAN_STATUS_READY,
    PROTOCOL_VERSION_V2,
    REQUEST_FORMAT_FORM_URLENCODED,
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

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "trs_adapter_response.json")
POLICY = SearchProbePolicy()
DOMAIN = "example.gov.cn"
ENDPOINT = "https://example.gov.cn/so/ss/query/s"


def _plan(pagination=None):
    base = SearchPlan(
        plan_id="",
        endpoint=ENDPOINT,
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_READY,
        strategy=SEARCH_STRATEGY_JSON_API,
        adapter=ADAPTER_TRS,
        http_method="POST",
        request_format=REQUEST_FORMAT_FORM_URLENCODED,
        response_format=RESPONSE_FORMAT_JSON,
        request_shape=SearchRequestShape(
            KEYWORD_LOCATION_FORM,
            ("qt",),
            form_fields=(("siteCode", "abc"),),
        ),
        pagination=pagination or SearchPagination(
            enabled=True,
            location="form",
            value_path=("page",),
            start=1,
            step=1,
            page_size_path=("pageSize",),
            page_size=20,
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
            return _response('{"resultDocs":[]}')
        return self.outcomes.pop(0)


def test_adapter_implements_protocol():
    assert isinstance(TRSSearchAdapter(), SearchAdapter)
    assert TRSSearchAdapter().adapter_name == "trs"


def test_valid_trs_plan_executes():
    result = TRSSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response(_fixture_body())]), policy=POLICY)
    assert result.success
    assert len(result.items) == 2


def test_invalid_combinations_return_plan_invalid():
    adapter = TRSSearchAdapter()
    plan = _plan()
    for kwargs in [
        {"adapter": "html"},
        {"strategy": "html_form"},
        {"http_method": "GET"},
        {"request_format": "json"},
        {"response_format": "html"},
    ]:
        bad = replace(plan, plan_id="", **kwargs)
        bad = replace(bad, plan_id=compute_plan_id(bad))
        result = adapter.execute(bad, ("k",), fetcher=FakeFetcher(), policy=POLICY)
        assert result.failure_code == "plan_invalid", kwargs


def test_trs_request_uses_form_urlencoded():
    pagination = SearchPagination(enabled=True, location="form", value_path=("page",), start=1, step=1, page_size_path=("pageSize",), page_size=2, max_pages=2)
    fetcher = FakeFetcher([_response(_fixture_body()), _response('{"resultDocs":[{"titleO":"B","url":"/b.html","summary":"s"}]}')])
    TRSSearchAdapter().execute(_plan(pagination), ("k",), fetcher=fetcher, policy=POLICY)
    body = fetcher.calls[0].body.decode("utf-8")
    assert "qt=k" in body
    assert "siteCode=abc" in body
    assert "page=1" in body
    assert "pageSize=2" in body
    assert "page=2" in fetcher.calls[1].body.decode("utf-8")
    assert dict(fetcher.calls[0].headers)["Content-Type"] == "application/x-www-form-urlencoded"
    assert "{keyword}" not in body


def test_json_content_type_accepts_plus_json_and_charset():
    for ctype in ["application/json", "application/ld+json", "application/json; charset=utf-8"]:
        result = TRSSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response(_fixture_body(), content_type=ctype)]), policy=POLICY)
        assert result.success, ctype


def test_wrong_content_type_is_response_rejected():
    result = TRSSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response("{}", content_type="text/html")]), policy=POLICY)
    assert result.failure_code == "response_rejected"


def test_invalid_json_is_response_rejected():
    result = TRSSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response("{not-json")]), policy=POLICY)
    assert result.failure_code == "response_rejected"


def test_duplicate_json_key_is_response_rejected():
    body = '{"resultDocs":[{"title":"A","title":"B","url":"/a","summary":"s"}]}'
    result = TRSSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.failure_code == "response_rejected"


def test_non_object_root_is_selector_mismatch():
    result = TRSSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response("[1]")]), policy=POLICY)
    assert result.failure_code == "selector_mismatch"


def test_missing_result_docs_is_selector_mismatch():
    result = TRSSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response("{}")]), policy=POLICY)
    assert result.failure_code == "selector_mismatch"


def test_first_page_empty_is_no_results():
    result = TRSSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response('{"resultDocs":[]}')]), policy=POLICY)
    assert result.status == "ok"
    assert result.failure_code == "no_results"
    assert result.items == ()


def test_flat_and_nested_documents_parse():
    result = TRSSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response(_fixture_body())]), policy=POLICY)
    assert result.items[0].title == "北京低空经济政策"
    assert result.items[0].url == "https://example.gov.cn/art/1.html"
    assert result.items[0].snippet == "摘要一"
    assert result.items[1].title == "浙江无人机"


def test_missing_title_or_url_is_selector_mismatch():
    body = '{"resultDocs":[{"url":"/a","summary":"s"}]}'
    result = TRSSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.failure_code == "selector_mismatch"


def test_dangerous_result_url_is_response_rejected():
    body = '{"resultDocs":[{"title":"Bad","url":"javascript:alert(1)","summary":"s"}]}'
    result = TRSSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.failure_code == "response_rejected"
    assert result.items == ()


def test_cross_scope_result_url_is_response_rejected():
    body = '{"resultDocs":[{"title":"Bad","url":"https://other.example/a","summary":"s"}]}'
    result = TRSSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.failure_code == "response_rejected"


def test_short_page_stops():
    pagination = SearchPagination(enabled=True, location="form", value_path=("page",), start=1, step=1, page_size_path=("pageSize",), page_size=20, max_pages=3)
    body = '{"resultDocs":[{"title":"A","url":"/a","summary":"s"}]}'
    fetcher = FakeFetcher([_response(body)])
    result = TRSSearchAdapter().execute(_plan(pagination), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 1


def test_multipage_dedupe_and_stop():
    pagination = SearchPagination(enabled=True, location="form", value_path=("page",), start=1, step=1, page_size_path=("pageSize",), page_size=2, max_pages=3)
    page1 = _fixture_body()
    page2 = json.dumps({"resultDocs": [{"title":"C","url":"/c","summary":"s"}]}, ensure_ascii=False)
    duplicate = _fixture_body()
    fetcher = FakeFetcher([_response(page1), _response(page2), _response(duplicate)])
    result = TRSSearchAdapter().execute(_plan(pagination), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 2
    assert len(result.items) == 3


def test_later_page_failure_is_fail_closed():
    pagination = SearchPagination(enabled=True, location="form", value_path=("page",), start=1, step=1, page_size_path=("pageSize",), page_size=20, max_pages=2)
    fetcher = FakeFetcher([_response(_fixture_body())], error=RuntimeError("boom"))
    result = TRSSearchAdapter().execute(_plan(pagination), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.status == "failed"
    assert result.failure_code == "transport_failure"
    assert result.items == ()


def test_later_page_structure_failure_is_fail_closed():
    pagination = SearchPagination(enabled=True, location="form", value_path=("page",), start=1, step=1, page_size_path=("pageSize",), page_size=2, max_pages=2)
    fetcher = FakeFetcher([_response(_fixture_body()), _response('{"bad":1}')])
    result = TRSSearchAdapter().execute(_plan(pagination), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.failure_code == "selector_mismatch"
    assert result.items == ()


def test_no_network_dns_or_redis_access():
    def fail(*_args, **_kwargs):
        raise AssertionError("external access attempted")

    fetcher = FakeFetcher([_response(_fixture_body())])
    with patch("socket.getaddrinfo", side_effect=fail), patch("urllib.request.urlopen", side_effect=fail):
        result = TRSSearchAdapter().execute(_plan(), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 1


def test_trs_offset_step_uses_form_value():
    pagination = SearchPagination(enabled=True, location="form", value_path=("start",), start=0, step=10, page_size_path=("pageSize",), page_size=2, max_pages=2)
    fetcher = FakeFetcher([_response(_fixture_body()), _response('{"resultDocs":[{"title":"D","url":"/d","summary":"s"}]}')])
    result = TRSSearchAdapter().execute(_plan(pagination), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    assert "start=0" in fetcher.calls[0].body.decode("utf-8")
    assert "start=10" in fetcher.calls[1].body.decode("utf-8")


def test_trs_duplicate_full_page_stops():
    pagination = SearchPagination(enabled=True, location="form", value_path=("page",), start=1, step=1, page_size_path=("pageSize",), page_size=2, max_pages=3)
    page1 = _fixture_body()
    fetcher = FakeFetcher([_response(page1), _response(page1)])
    result = TRSSearchAdapter().execute(_plan(pagination), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.success
    assert len(fetcher.calls) == 2
    assert len(result.items) == 2


def test_trs_resultDocs_titleO_publishTime_mapping():
    body = json.dumps({
        "resultDocs": [
            {"titleO": "标题", "url": "/a", "docDate": "2026-01-01", "summary": "摘要"},
            {"data": {"title": "第二", "url": "/b", "publishTime": "2026-01-02", "summary": "摘要二"}},
        ]
    }, ensure_ascii=False)
    result = TRSSearchAdapter().execute(_plan(), ("k",), fetcher=FakeFetcher([_response(body)]), policy=POLICY)
    assert result.success
    assert result.items[0].title == "标题"
    assert result.items[1].title == "第二"
