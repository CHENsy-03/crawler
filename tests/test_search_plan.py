import json
import os

import pytest

from crawler.search.search_plan import (
    PLAN_STATUS_DRAFT,
    PLAN_STATUS_READY,
    SEARCH_STRATEGY_HTML_FORM,
    ADAPTER_HTML,
    KEYWORD_LOCATION_QUERY,
    ProtocolError,
    SearchHit,
    SearchPlan,
    SearchPagination,
    SearchRequestShape,
    canonical_plan_json,
    compute_plan_id,
    validate_search_hit,
    validate_search_plan,
)

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "search_plan_schema_v2.json")
V2_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "redis_protocol_v2.json")


def _load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_v2_fixture():
    with open(V2_FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _fixture_plan():
    return _load_fixture()["search_plan"]


def test_plan_roundtrip():
    plan = SearchPlan.from_dict(_fixture_plan())
    restored = SearchPlan.from_dict(plan.to_dict())
    assert restored == plan
    validate_search_plan(restored)


def test_plan_id_matches_canonical_fixture():
    plan = SearchPlan.from_dict(_fixture_plan())
    assert compute_plan_id(plan) == _load_fixture()["search_plan_id"]


def test_plan_id_deterministic_across_json_order():
    data = _fixture_plan()
    plan = SearchPlan.from_dict(data)
    first = compute_plan_id(plan)
    reordered = {key: data[key] for key in reversed(list(data.keys()))}
    second = compute_plan_id(SearchPlan.from_dict(reordered))
    assert first == second


def test_plan_id_ignores_runtime_fields():
    plan = SearchPlan.from_dict(_fixture_plan())
    base = compute_plan_id(plan)
    changed = SearchPlan.from_dict({**_fixture_plan(), "status": PLAN_STATUS_READY, "created_at": "2030-01-01T00:00:00Z"})
    assert compute_plan_id(changed) == base


def test_plan_id_changes_when_execution_semantics_change():
    plan = SearchPlan.from_dict(_fixture_plan())
    base = compute_plan_id(plan)
    changed = SearchPlan.from_dict({**_fixture_plan(), "request_format": "form_urlencoded", "http_method": "POST"})
    assert compute_plan_id(changed) != base


def test_old_fields_rejected():
    data = {**_fixture_plan(), "query_params": {"q": "{keyword}"}}
    with pytest.raises(ProtocolError):
        SearchPlan.from_dict(data)
    data = {**_fixture_plan(), "request_body_template": "q={keyword}"}
    with pytest.raises(ProtocolError):
        SearchPlan.from_dict(data)


def test_unknown_field_rejected():
    with pytest.raises(ProtocolError):
        SearchPlan.from_dict({**_fixture_plan(), "bogus": 1})


def test_plan_validation_errors():
    plan = SearchPlan.from_dict(_fixture_plan())
    with pytest.raises(ProtocolError):
        validate_search_plan(SearchPlan.from_dict({**_fixture_plan(), "http_method": "PATCH"}))
    with pytest.raises(ProtocolError):
        validate_search_plan(SearchPlan.from_dict({**_fixture_plan(), "adapter": "bad"}))
    with pytest.raises(ProtocolError):
        validate_search_plan(SearchPlan.from_dict({**_fixture_plan(), "endpoint": "https://example.gov.cn/search?x=1"}))


def test_pagination_disabled_exact_state():
    assert SearchPagination().to_dict() == {
        "enabled": False,
        "location": "none",
        "value_path": [],
        "start": 0,
        "step": 0,
        "page_size_path": [],
        "page_size": None,
        "max_pages": 1,
    }


def test_pagination_enabled_bounds():
    with pytest.raises(ProtocolError):
        SearchPagination(enabled=True, location="query", value_path=("page",), start=0, step=0, max_pages=1)
    with pytest.raises(ProtocolError):
        SearchPagination(enabled=True, location="json", value_path=(), start=0, step=1, max_pages=1)


def test_request_shape_keyword_path_rules():
    with pytest.raises(ProtocolError):
        SearchRequestShape(keyword_location="query", keyword_path=("a", "b"))
    with pytest.raises(ProtocolError):
        SearchRequestShape(keyword_location="form", keyword_path=("q",), form_fields=(("q", "x"),))


def test_hit_roundtrip():
    hit = SearchHit.from_dict(_load_v2_fixture()["search_hit"])
    restored = SearchHit.from_dict(hit.to_dict())
    assert restored == hit
    validate_search_hit(restored)


def test_hit_validation_errors():
    data = _load_v2_fixture()["search_hit"]
    with pytest.raises(ProtocolError):
        validate_search_hit(SearchHit.from_dict({**data, "hit_id": ""}))
    with pytest.raises(ProtocolError):
        validate_search_hit(SearchHit.from_dict({**data, "url": "/relative"}))


def test_plan_json_escapes_html_like_go():
    plan = SearchPlan.from_dict(_fixture_plan())
    escaped = SearchPlan(
        plan_id=plan.plan_id,
        endpoint=plan.endpoint,
        plan_schema_version=plan.plan_schema_version,
        protocol_version=plan.protocol_version,
        status=plan.status,
        strategy=plan.strategy,
        adapter=plan.adapter,
        http_method=plan.http_method,
        request_format=plan.request_format,
        response_format=plan.response_format,
        request_shape=SearchRequestShape(
            keyword_location=KEYWORD_LOCATION_QUERY,
            keyword_path=("q",),
            fixed_query_params=(("site", "a<b>&c"),),
        ),
        pagination=plan.pagination,
        selectors=plan.selectors,
        scope=plan.scope,
        discovery=plan.discovery,
        created_from=plan.created_from,
    )
    text = escaped.to_json()
    assert "\\u003c" in text
    assert "\\u003e" in text
    assert "\\u0026" in text
