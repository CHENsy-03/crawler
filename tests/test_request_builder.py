"""Offline tests for the pure, network-free RequestBuilder."""

import json

import pytest

from crawler.search.request_builder import build_search_request
from crawler.search.search_plan import (
    ADAPTER_GENERIC_JSON,
    ADAPTER_HTML,
    ADAPTER_JPAAS,
    ADAPTER_TRS,
    KEYWORD_LOCATION_FORM,
    KEYWORD_LOCATION_JSON,
    KEYWORD_LOCATION_QUERY,
    PLAN_STATUS_READY,
    PROTOCOL_VERSION_V2,
    REQUEST_FORMAT_FORM_URLENCODED,
    REQUEST_FORMAT_JSON,
    REQUEST_FORMAT_NONE,
    RESPONSE_FORMAT_HTML,
    RESPONSE_FORMAT_JSON,
    SEARCH_STRATEGY_HTML_FORM,
    SEARCH_STRATEGY_JSON_API,
    ProtocolError,
    SearchPagination,
    SearchPlan,
    SearchRequestShape,
    SearchScope,
    SearchSelectors,
    compute_plan_id,
)
from dataclasses import replace

ENDPOINT = "https://example.gov.cn/search"


def _plan(
    *,
    adapter=ADAPTER_HTML,
    strategy=SEARCH_STRATEGY_HTML_FORM,
    method="GET",
    request_format=REQUEST_FORMAT_NONE,
    response_format=RESPONSE_FORMAT_HTML,
    shape=SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",)),
    pagination=SearchPagination(),
    endpoint=ENDPOINT,
):
    base = SearchPlan(
        plan_id="",
        endpoint=endpoint,
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_READY,
        strategy=strategy,
        adapter=adapter,
        http_method=method,
        request_format=request_format,
        response_format=response_format,
        request_shape=shape,
        pagination=pagination,
        selectors=SearchSelectors("/data/items", "/title", "/url", "", ""),
        scope=SearchScope(domain="example.gov.cn"),
    )
    return replace(base, plan_id=compute_plan_id(base))


def test_html_get_query_shape():
    plan = _plan()
    request = build_search_request(plan, "低空经济")
    assert request.method == "GET"
    assert request.body is None
    assert "q=%E4%BD%8E%E7%A9%BA%E7%BB%8F%E6%B5%8E" in request.url
    assert "Content-Type" not in dict(request.headers)


def test_html_post_form_shape():
    plan = _plan(
        method="POST",
        request_format=REQUEST_FORMAT_FORM_URLENCODED,
        shape=SearchRequestShape(
            KEYWORD_LOCATION_FORM,
            ("q",),
            form_fields=(("siteCode", "abc"),),
        ),
    )
    request = build_search_request(plan, "k")
    assert request.method == "POST"
    assert request.body is not None
    assert dict(request.headers)["Content-Type"] == "application/x-www-form-urlencoded"
    assert "siteCode=abc" in request.body.decode("utf-8")
    assert "q=k" in request.body.decode("utf-8")


def test_trs_form_shape():
    plan = _plan(
        adapter=ADAPTER_TRS,
        strategy=SEARCH_STRATEGY_JSON_API,
        method="POST",
        request_format=REQUEST_FORMAT_FORM_URLENCODED,
        response_format=RESPONSE_FORMAT_JSON,
        shape=SearchRequestShape(
            KEYWORD_LOCATION_FORM,
            ("qt",),
            form_fields=(("siteCode", "abc"), ("pageSize", "20")),
        ),
    )
    request = build_search_request(plan, "k")
    body = request.body.decode("utf-8")
    assert "qt=k" in body
    assert "siteCode=abc" in body
    assert "pageSize=20" in body


def test_jpaas_query_shape():
    plan = _plan(
        adapter=ADAPTER_JPAAS,
        strategy=SEARCH_STRATEGY_JSON_API,
        method="GET",
        response_format=RESPONSE_FORMAT_JSON,
        shape=SearchRequestShape(
            KEYWORD_LOCATION_QUERY,
            ("q",),
            fixed_query_params=(("webId", "3217"),),
        ),
    )
    request = build_search_request(plan, "k")
    assert "q=k" in request.url
    assert "webId=3217" in request.url
    assert "Accept" in dict(request.headers)


def test_generic_json_get_shape():
    plan = _plan(
        adapter=ADAPTER_GENERIC_JSON,
        strategy=SEARCH_STRATEGY_JSON_API,
        method="GET",
        response_format=RESPONSE_FORMAT_JSON,
        shape=SearchRequestShape(
            KEYWORD_LOCATION_QUERY,
            ("kw",),
            fixed_query_params=(("api", "1"),),
        ),
    )
    request = build_search_request(plan, "k")
    assert request.body is None
    assert "kw=k" in request.url
    assert "api=1" in request.url


def test_generic_json_post_shape():
    plan = _plan(
        adapter=ADAPTER_GENERIC_JSON,
        strategy=SEARCH_STRATEGY_JSON_API,
        method="POST",
        request_format=REQUEST_FORMAT_JSON,
        response_format=RESPONSE_FORMAT_JSON,
        shape=SearchRequestShape(
            KEYWORD_LOCATION_JSON,
            ("query", "kw"),
        ),
    )
    request = build_search_request(plan, "k")
    body = json.loads(request.body.decode("utf-8"))
    assert body == {"query": {"kw": "k"}}
    assert dict(request.headers)["Content-Type"] == "application/json"


def test_pagination_index_formula():
    plan = _plan(
        shape=SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",)),
        pagination=SearchPagination(
            enabled=True,
            location="query",
            value_path=("page",),
            start=0,
            step=10,
            page_size_path=("size",),
            page_size=20,
            max_pages=3,
        ),
    )
    request = build_search_request(plan, "k", page_index=2)
    assert "page=20" in request.url
    assert "size=20" in request.url


def test_page_index_out_of_range():
    plan = _plan(pagination=SearchPagination())
    with pytest.raises(ProtocolError):
        build_search_request(plan, "k", page_index=1)


def test_no_placeholders_in_output():
    plan = _plan(
        method="POST",
        request_format=REQUEST_FORMAT_JSON,
        response_format=RESPONSE_FORMAT_JSON,
        shape=SearchRequestShape(KEYWORD_LOCATION_JSON, ("query", "kw")),
    )
    request = build_search_request(plan, "k")
    text = request.url + (request.body or b"").decode("utf-8")
    assert "{keyword}" not in text
    assert "{page}" not in text
    assert "{page_size}" not in text
