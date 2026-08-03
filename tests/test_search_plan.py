import json
import os

import pytest

from crawler.search.search_plan import (
    PLAN_STATUS_DRAFT,
    SEARCH_STRATEGY_HTML_FORM,
    ProtocolError,
    SearchHit,
    SearchPlan,
    canonical_plan_json,
    compute_plan_id,
    validate_search_hit,
    validate_search_plan,
)

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "redis_protocol_v2.json")


def _load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
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
    expected = _load_fixture()["search_plan_id"]
    assert compute_plan_id(plan) == expected


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
    changed = SearchPlan.from_dict({**_fixture_plan(), "status": "ready", "created_at": "2030-01-01T00:00:00Z"})
    assert compute_plan_id(changed) == base


def test_unicode_plan_canonical_and_id():
    fixture = _load_fixture()
    plan = SearchPlan.from_dict(fixture["unicode_plan"])
    assert canonical_plan_json(plan) == fixture["unicode_plan_json"]
    assert compute_plan_id(plan) == fixture["unicode_plan_id"]


def test_empty_collections_normalized():
    fixture = _load_fixture()
    plan = SearchPlan.from_dict(fixture["empty_collections_plan"])
    assert plan.to_dict() == fixture["empty_collections_plan_normalized"]
    hit = SearchHit.from_dict(fixture["empty_collections_hit"])
    assert hit.to_dict() == fixture["empty_collections_hit_normalized"]


def test_plan_validation_errors():
    plan = SearchPlan.from_dict(_fixture_plan())
    with pytest.raises(ProtocolError):
        validate_search_plan(SearchPlan.from_dict({**_fixture_plan(), "http_method": "PATCH"}))
    with pytest.raises(ProtocolError):
        validate_search_plan(SearchPlan.from_dict({**_fixture_plan(), "endpoint": "ftp://x.test"}))
    with pytest.raises(ProtocolError):
        validate_search_plan(SearchPlan.from_dict({**_fixture_plan(), "pagination": {"max_pages": 0, "page_param": "", "page_size_param": "", "page_size": 10}}))


def test_hit_roundtrip():
    fixture = _load_fixture()
    hit = SearchHit.from_dict(fixture["search_hit"])
    restored = SearchHit.from_dict(hit.to_dict())
    assert restored == hit
    validate_search_hit(restored)


def test_hit_validation_errors():
    fixture = _load_fixture()
    data = fixture["search_hit"]
    with pytest.raises(ProtocolError):
        validate_search_hit(SearchHit.from_dict({**data, "hit_id": ""}))
    with pytest.raises(ProtocolError):
        validate_search_hit(SearchHit.from_dict({**data, "url": "/relative"}))


@pytest.mark.parametrize("field,value", [
    ("confidence", True),
    ("confidence", 1.0),
    ("confidence", "1"),
    ("score", True),
    ("score", 1.0),
    ("score", "1"),
])
def test_strict_integer_rejection(field, value):
    fixture = _load_fixture()
    if field == "score":
        data = fixture["search_hit"]
        with pytest.raises(ProtocolError):
            SearchHit.from_dict({**data, field: value})
    else:
        data = fixture["search_plan"]
        discovery = dict(data["discovery"])
        discovery[field] = value
        with pytest.raises(ProtocolError):
            SearchPlan.from_dict({**data, "discovery": discovery})


def test_pagination_int_rejection():
    data = _fixture_plan()
    with pytest.raises(ProtocolError):
        SearchPlan.from_dict({**data, "pagination": {"max_pages": True, "page_param": "", "page_size_param": "", "page_size": 10}})
    with pytest.raises(ProtocolError):
        SearchPlan.from_dict({**data, "pagination": {"max_pages": 1, "page_param": "", "page_size_param": "", "page_size": 10.0}})
def test_plan_json_escapes_html_like_go():
    fixture = _load_fixture()
    plan = SearchPlan.from_dict(fixture["unicode_plan"])
    text = plan.to_json()
    assert "\\u003c" in text
    assert "\\u003e" in text
    assert "\\u0026" in text
    assert "\\u2028" in text
    assert "\\u2029" in text

@pytest.mark.parametrize("key,model", [
    ("search_plan_null_int", SearchPlan),
    ("search_plan_null_pagination", SearchPlan),
    ("search_hit_null_score", SearchHit),
])
def test_null_int_fields_rejected(key, model):
    data = _load_fixture()[key]
    with pytest.raises(ProtocolError):
        model.from_dict(data)
