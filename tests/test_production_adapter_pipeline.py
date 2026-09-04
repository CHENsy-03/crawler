"""Offline production pipeline tests through orchestrator and default registry."""

import json
from dataclasses import replace
from unittest.mock import patch

from protocol.messages import SearchRequestedMessage, URLMessageV2

import crawler.search.search_orchestrator as orch
from crawler.search.adapter_composition import build_default_adapter_registry
from crawler.search.plan_builder import PlanBuilder, PlanBuildResult
from crawler.search.plan_executor import RegistryPlanExecutor
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
    REQUEST_FORMAT_JSON,
    REQUEST_FORMAT_NONE,
    RESPONSE_FORMAT_HTML,
    RESPONSE_FORMAT_JSON,
    SEARCH_STRATEGY_HTML_FORM,
    SEARCH_STRATEGY_JSON_API,
    SearchPagination,
    SearchPlan,
    SearchRequestShape,
    SearchScope,
    SearchSelectors,
    compute_plan_id,
)
from crawler.site.models import CandidateRequestShape, SearchCandidate
from crawler.site.normalizer import normalize_target_url
from crawler.site.search_probe import ProbeOutcome, SearchProbePolicy, SearchProbeResponse, SearchProbeResult
from crawler.site.selector_evidence import SelectorEvidence

POLICY = SearchProbePolicy()
DOMAIN = "example.gov.cn"
TARGET = f"https://{DOMAIN}/"
ENDPOINT = f"https://{DOMAIN}/search"


def _message():
    return SearchRequestedMessage(
        protocol_version="2.0",
        task_id="task-pipeline",
        message_id="msg-pipeline",
        timestamp="2026-08-13T00:00:00Z",
        target_url=TARGET,
        keywords=["k"],
        level=0,
        max_pages=1,
    )


class FakeCache:
    def __init__(self):
        self.write_calls = []
        self.delete_calls = []

    def get(self, *, target_url):
        return orch.PlanCacheReadResult(None, "miss", None)

    def put(self, *, target_url, plan):
        self.write_calls.append((target_url, plan))

    def delete(self, *, target_url):
        self.delete_calls.append(target_url)


class FakeAnalyzer:
    def __init__(self, candidates):
        self.candidates = tuple(candidates)
        self.calls = []

    def analyze(self, target_url):
        self.calls.append(target_url)
        return orch.SiteAnalysisResult(
            normalized_url=TARGET,
            final_url=TARGET,
            candidates=self.candidates,
        )


class FakeBuilder:
    def __init__(self, plan):
        self.plan = plan
        self.calls = []

    def build(self, *, target_url, candidates, selector_evidence=None):
        self.calls.append((target_url, candidates))
        return PlanBuildResult(self.plan, (), None)


class FakePublisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


class FakeFetcher:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def fetch(self, request, *, policy):
        self.calls.append(request)
        return self.outcomes.pop(0)


def _html_response():
    body = b'<div class="result-item"><h3><a href="/a.html">A</a></h3><p>s</p></div>'
    return ProbeOutcome(SearchProbeResponse(200, "text/html", body, ENDPOINT, 0), None)


def _json_response(body, url=ENDPOINT):
    return ProbeOutcome(
        SearchProbeResponse(200, "application/json", body.encode("utf-8"), url, 0),
        None,
    )


def _candidate(source, method, shape):
    return SearchCandidate(
        method=method,
        endpoint=ENDPOINT,
        keyword_param=(shape.keyword_param if shape is not None else "q") or "q",
        fixed_params=(),
        source=source,
        scope="same_origin",
        status="unverified",
        request_shape=shape,
    )


def _evidence(candidate, kind, result_item, title, url):
    return SelectorEvidence(
        candidate_key=(
            candidate.method,
            normalize_target_url(candidate.endpoint),
            candidate.keyword_param,
            tuple(sorted(candidate.fixed_params)),
        ),
        candidate_kind=kind,
        response_kind="json" if kind == "json_api" else "html",
        result_item=result_item,
        title=title,
        url=url,
        final_origin=TARGET,
        match_count=2,
        validated=True,
        evidence_source="probe",
    )


def _form_evidence():
    c = SearchCandidate(method="POST", endpoint=ENDPOINT, keyword_param="q", source="form", status="unverified")
    return _evidence(c, "html_form", ".result-item", "h3 a", "h3 a")


def _json_evidence(candidate):
    return _evidence(candidate, "json_api", "/data/items", "/title", "/url")


def _success_probe(*args, **kwargs):
    return SearchProbeResult(("k",), _form_evidence(), "success", None)


def _ready_plan(adapter, method, request_format, response_format, shape, pagination, selectors):
    base = SearchPlan(
        plan_id="",
        endpoint=ENDPOINT,
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_READY,
        strategy=SEARCH_STRATEGY_HTML_FORM if adapter == ADAPTER_HTML else SEARCH_STRATEGY_JSON_API,
        adapter=adapter,
        http_method=method,
        request_format=request_format,
        response_format=response_format,
        request_shape=shape,
        pagination=pagination,
        selectors=selectors,
        scope=SearchScope(domain=DOMAIN, allowed_path_prefixes=["/"]),
    )
    return replace(base, plan_id=compute_plan_id(base))


def _run(plan, fetcher):
    cache = FakeCache()
    publisher = FakePublisher()
    analyzer = FakeAnalyzer((_candidate("form", "GET", None),))
    builder = FakeBuilder(plan)
    registry = build_default_adapter_registry()
    with patch.object(orch, "probe_search_candidate", side_effect=_success_probe):
        result = orch.run_v2_search_pipeline(
            _message(),
            analyzer=analyzer,
            plan_builder=builder,
            plan_cache=cache,
            probe_fetcher=fetcher,
            policy=POLICY,
            executor=RegistryPlanExecutor(registry),
            publisher=publisher,
        )
    return result, cache, publisher, fetcher


def test_html_get_production_chain():
    shape = CandidateRequestShape(
        method="GET", endpoint=ENDPOINT, keyword_location="query", keyword_param="q",
        approved_origins=(TARGET, ENDPOINT),
    )
    candidate = _candidate("form", "GET", shape)
    evidence = _evidence(candidate, "html_form", ".result-item", "h3 a", "h3 a")
    built = PlanBuilder().build(target_url=TARGET, candidates=(candidate,), selector_evidence=evidence)
    assert built.success
    result, cache, publisher, fetcher = _run(built.plan, FakeFetcher([_html_response()]))
    assert result.status == "published"
    assert cache.write_calls
    assert len(publisher.messages) == 1
    assert isinstance(publisher.messages[0], URLMessageV2)
    msg = publisher.messages[0].to_dict()
    assert msg["original_query"] == "k"
    assert msg["query_term"] == "k"
    assert msg["hit_id"]


def test_html_post_production_chain():
    shape = CandidateRequestShape(
        method="POST", endpoint=ENDPOINT, keyword_location="form", keyword_param="q",
        form_fields=(("site", "abc"),), content_type="application/x-www-form-urlencoded",
        approved_origins=(TARGET, ENDPOINT),
    )
    candidate = _candidate("form", "POST", shape)
    evidence = _evidence(candidate, "html_form", ".result-item", "h3 a", "h3 a")
    built = PlanBuilder().build(target_url=TARGET, candidates=(candidate,), selector_evidence=evidence)
    assert built.success
    result, cache, publisher, fetcher = _run(built.plan, FakeFetcher([_html_response()]))
    assert result.status == "published"
    assert cache.write_calls
    assert len(publisher.messages) == 1


def test_trs_production_chain_explicit_plan():
    shape = SearchRequestShape(
        KEYWORD_LOCATION_FORM, ("qt",), form_fields=(("siteCode", "abc"),)
    )
    pagination = SearchPagination(enabled=True, location="form", value_path=("page",), start=1, step=1, page_size_path=("pageSize",), page_size=20, max_pages=1)
    plan = _ready_plan(ADAPTER_TRS, "POST", "form_urlencoded", RESPONSE_FORMAT_JSON, shape, pagination, SearchSelectors("", "", "", "", ""))
    body = '{"resultDocs":[{"title":"A","url":"/a.html","summary":"s"}]}'
    result, cache, publisher, fetcher = _run(plan, FakeFetcher([_json_response(body)]))
    assert result.status == "published"
    assert cache.write_calls
    assert len(publisher.messages) == 1
    assert "qt=k" in fetcher.calls[0].body.decode("utf-8")


def test_jpaas_production_chain_explicit_plan():
    shape = SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",), fixed_query_params=(("webId", "3217"),))
    pagination = SearchPagination(enabled=True, location="query", value_path=("p",), start=1, step=1, page_size_path=("pg",), page_size=10, max_pages=1)
    plan = _ready_plan(ADAPTER_JPAAS, "GET", REQUEST_FORMAT_NONE, RESPONSE_FORMAT_JSON, shape, pagination, SearchSelectors("", "", "", "", ""))
    body = '{"code":"200","data":{"appSearchResultBeanList":[{"title":"A","url":"/a.html"}]}}'
    result, cache, publisher, fetcher = _run(plan, FakeFetcher([_json_response(body)]))
    assert result.status == "published"
    assert cache.write_calls
    assert len(publisher.messages) == 1
    assert "q=k" in fetcher.calls[0].url


def test_generic_json_get_production_chain_explicit_plan():
    shape = SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",), fixed_query_params=(("api", "1"),))
    pagination = SearchPagination(enabled=True, location="query", value_path=("page",), start=1, step=1, page_size_path=("size",), page_size=10, max_pages=1)
    plan = _ready_plan(ADAPTER_GENERIC_JSON, "GET", REQUEST_FORMAT_NONE, RESPONSE_FORMAT_JSON, shape, pagination, SearchSelectors("/data/items", "/title", "/url", "", ""))
    body = '{"data":{"items":[{"title":"A","url":"/a.html"}]}}'
    result, cache, publisher, fetcher = _run(plan, FakeFetcher([_json_response(body)]))
    assert result.status == "published"
    assert cache.write_calls
    assert len(publisher.messages) == 1
    assert "q=k" in fetcher.calls[0].url


def test_generic_json_post_production_chain_explicit_plan():
    shape = SearchRequestShape(KEYWORD_LOCATION_JSON, ("query", "kw"))
    pagination = SearchPagination(enabled=True, location="json", value_path=("page",), start=1, step=1, page_size_path=("size",), page_size=10, max_pages=1)
    plan = _ready_plan(ADAPTER_GENERIC_JSON, "POST", REQUEST_FORMAT_JSON, RESPONSE_FORMAT_JSON, shape, pagination, SearchSelectors("/data/items", "/title", "/url", "", ""))
    body = '{"data":{"items":[{"title":"A","url":"/a.html"}]}}'
    result, cache, publisher, fetcher = _run(plan, FakeFetcher([_json_response(body)]))
    assert result.status == "published"
    assert cache.write_calls
    assert len(publisher.messages) == 1
    payload = json.loads(fetcher.calls[0].body.decode("utf-8"))
    assert payload["query"]["kw"] == "k"


def test_no_results_caches_and_publishes_zero():
    shape = SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",))
    plan = _ready_plan(ADAPTER_GENERIC_JSON, "GET", REQUEST_FORMAT_NONE, RESPONSE_FORMAT_JSON, shape, SearchPagination(enabled=True, location="query", value_path=("page",), start=1, step=1, page_size_path=("size",), page_size=10, max_pages=1), SearchSelectors("/data/items", "/title", "/url", "", ""))
    result, cache, publisher, fetcher = _run(plan, FakeFetcher([_json_response('{"data":{"items":[]}}')]))
    assert result.status == "no_results"
    assert result.published_count == 0
    assert cache.write_calls
    assert publisher.messages == []


def test_failed_does_not_cache_or_publish():
    shape = SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",))
    plan = _ready_plan(ADAPTER_GENERIC_JSON, "GET", REQUEST_FORMAT_NONE, RESPONSE_FORMAT_JSON, shape, SearchPagination(enabled=True, location="query", value_path=("page",), start=1, step=1, page_size_path=("size",), page_size=10, max_pages=1), SearchSelectors("/data/items", "/title", "/url", "", ""))
    result, cache, publisher, fetcher = _run(plan, FakeFetcher([_json_response('{"data":{}}')]))
    assert result.status == "failed"
    assert result.published_count == 0
    assert cache.write_calls == []
    assert publisher.messages == []


def test_no_network_dns_or_redis_access_in_pipeline():
    def fail(*_args, **_kwargs):
        raise AssertionError("external access attempted")

    shape = SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",))
    plan = _ready_plan(ADAPTER_GENERIC_JSON, "GET", REQUEST_FORMAT_NONE, RESPONSE_FORMAT_JSON, shape, SearchPagination(enabled=True, location="query", value_path=("page",), start=1, step=1, page_size_path=("size",), page_size=10, max_pages=1), SearchSelectors("/data/items", "/title", "/url", "", ""))
    with patch("socket.getaddrinfo", side_effect=fail), patch("urllib.request.urlopen", side_effect=fail):
        result, cache, publisher, fetcher = _run(plan, FakeFetcher([_json_response('{"data":{"items":[{"title":"A","url":"/a.html"}]}}')]))
    assert result.status == "published"
    assert cache.write_calls
    assert len(publisher.messages) == 1
