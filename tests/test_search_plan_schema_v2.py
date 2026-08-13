"""Offline schema v2 contract tests."""

import math
from dataclasses import replace

import pytest

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
    validate_search_plan,
)


def _base_plan(adapter=ADAPTER_HTML, method="GET", request_format=REQUEST_FORMAT_NONE, response_format=RESPONSE_FORMAT_HTML, shape=None):
    return SearchPlan(
        plan_id="",
        endpoint="https://example.gov.cn/search",
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_READY,
        strategy=SEARCH_STRATEGY_HTML_FORM if adapter == ADAPTER_HTML else SEARCH_STRATEGY_JSON_API,
        adapter=adapter,
        http_method=method,
        request_format=request_format,
        response_format=response_format,
        request_shape=shape or SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",)),
        pagination=SearchPagination(),
        selectors=SearchSelectors("/data/items", "/title", "/url", "", ""),
        scope=SearchScope(domain="example.gov.cn"),
    )


def _valid_plan(*args, **kwargs):
    base = _base_plan(*args, **kwargs)
    return replace(base, plan_id=compute_plan_id(base))


def test_six_legal_combinations_validate():
    cases = [
        (ADAPTER_HTML, "GET", REQUEST_FORMAT_NONE, RESPONSE_FORMAT_HTML, SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",))),
        (ADAPTER_HTML, "POST", REQUEST_FORMAT_FORM_URLENCODED, RESPONSE_FORMAT_HTML, SearchRequestShape(KEYWORD_LOCATION_FORM, ("q",))),
        (ADAPTER_TRS, "POST", REQUEST_FORMAT_FORM_URLENCODED, RESPONSE_FORMAT_JSON, SearchRequestShape(KEYWORD_LOCATION_FORM, ("qt",))),
        (ADAPTER_JPAAS, "GET", REQUEST_FORMAT_NONE, RESPONSE_FORMAT_JSON, SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",))),
        (ADAPTER_GENERIC_JSON, "GET", REQUEST_FORMAT_NONE, RESPONSE_FORMAT_JSON, SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",))),
        (ADAPTER_GENERIC_JSON, "POST", REQUEST_FORMAT_JSON, RESPONSE_FORMAT_JSON, SearchRequestShape(KEYWORD_LOCATION_JSON, ("query", "kw"))),
    ]
    for adapter, method, req, resp, shape in cases:
        plan = _valid_plan(adapter, method, req, resp, shape)
        validate_search_plan(plan)


def test_unknown_adapter_rejected():
    plan = _valid_plan()
    bad = replace(plan, adapter="custom", plan_id="")
    with pytest.raises(ProtocolError):
        validate_search_plan(replace(bad, plan_id=compute_plan_id(bad)))


def test_adapter_strategy_mismatch_rejected():
    plan = _valid_plan()
    bad = replace(plan, strategy=SEARCH_STRATEGY_JSON_API, plan_id="")
    with pytest.raises(ProtocolError):
        validate_search_plan(replace(bad, plan_id=compute_plan_id(bad)))


def test_endpoint_query_rejected():
    plan = _valid_plan()
    bad = replace(plan, endpoint="https://example.gov.cn/search?q=1", plan_id="")
    with pytest.raises(ProtocolError):
        validate_search_plan(replace(bad, plan_id=compute_plan_id(bad)))


def test_endpoint_fragment_rejected():
    plan = _valid_plan()
    bad = replace(plan, endpoint="https://example.gov.cn/search#frag", plan_id="")
    with pytest.raises(ProtocolError):
        validate_search_plan(replace(bad, plan_id=compute_plan_id(bad)))


def test_fixed_query_duplicate_rejected():
    with pytest.raises(ProtocolError):
        SearchRequestShape(
            KEYWORD_LOCATION_QUERY,
            ("q",),
            fixed_query_params=(("site", "a"), ("site", "b")),
        )


def test_json_keyword_ancestor_conflict_rejected():
    with pytest.raises(ProtocolError):
        SearchRequestShape(
            KEYWORD_LOCATION_JSON,
            ("query", "kw"),
            json_object_template=((("query",), {"x": 1}),),
        )


def test_json_template_nan_rejected():
    with pytest.raises(ProtocolError):
        SearchRequestShape(
            KEYWORD_LOCATION_JSON,
            ("query", "kw"),
            json_object_template=((("query", "v"), float("nan")),),
        )


def test_infinity_rejected():
    with pytest.raises(ProtocolError):
        SearchRequestShape(
            KEYWORD_LOCATION_JSON,
            ("query", "kw"),
            json_object_template=((("query", "v"), float("inf")),),
        )


def test_json_pagination_conflicts_with_fixed_template_rejected():
    shape = SearchRequestShape(
        KEYWORD_LOCATION_JSON,
        ("query", "kw"),
        json_object_template=((("page",), {"size": 1}),),
    )
    plan = _base_plan(
        ADAPTER_GENERIC_JSON,
        "POST",
        REQUEST_FORMAT_JSON,
        RESPONSE_FORMAT_JSON,
        shape,
    )
    pagination = SearchPagination(
        enabled=True,
        location=KEYWORD_LOCATION_JSON,
        value_path=("page",),
        start=1,
        step=1,
        max_pages=1,
    )
    bad = replace(plan, pagination=pagination, plan_id="")
    with pytest.raises(ProtocolError):
        validate_search_plan(replace(bad, plan_id=compute_plan_id(bad)))


def test_pagination_value_and_page_size_conflict_rejected():
    plan = _base_plan(
        ADAPTER_GENERIC_JSON,
        "GET",
        REQUEST_FORMAT_NONE,
        RESPONSE_FORMAT_JSON,
        SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",)),
    )
    pagination = SearchPagination(
        enabled=True,
        location=KEYWORD_LOCATION_QUERY,
        value_path=("page",),
        start=1,
        step=1,
        page_size_path=("page",),
        page_size=10,
        max_pages=1,
    )
    bad = replace(plan, pagination=pagination, plan_id="")
    with pytest.raises(ProtocolError):
        validate_search_plan(replace(bad, plan_id=compute_plan_id(bad)))
