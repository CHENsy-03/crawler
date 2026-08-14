"""Offline multi-keyword pipeline tests for URLMessageV2 production."""

from dataclasses import replace

from protocol.messages import SearchRequestedMessage

import crawler.search.search_orchestrator as orch
from crawler.search.plan_builder import PlanBuildResult
from crawler.search.plan_cache import PlanCacheReadResult
from crawler.search.plan_executor import (
    FAILURE_NO_RESULTS,
    FAILURE_TRANSPORT,
    SearchPlanExecutionResult,
    SearchResultItem,
)
from crawler.search.search_plan import (
    ADAPTER_HTML,
    KEYWORD_LOCATION_QUERY,
    PLAN_STATUS_READY,
    PROTOCOL_VERSION_V2,
    REQUEST_FORMAT_NONE,
    RESPONSE_FORMAT_HTML,
    SEARCH_STRATEGY_HTML_FORM,
    SearchPagination,
    SearchPlan,
    SearchRequestShape,
    SearchScope,
    compute_plan_id,
)
from crawler.site.models import SearchCandidate, SiteAnalysisResult
from crawler.site.search_probe import SearchProbePolicy, SearchProbeResult
from crawler.site.selector_evidence import SelectorEvidence

POLICY = SearchProbePolicy()
TARGET = "https://example.gov.cn/"
PLAN = None


def _message(keywords=("k1", "k2")):
    return SearchRequestedMessage(
        protocol_version="2.0",
        task_id="task-019b-2",
        message_id="msg-019b-2",
        timestamp="2026-08-13T00:00:00Z",
        target_url=TARGET,
        keywords=list(keywords),
        level=0,
        max_pages=1,
    )


def _ready_plan():
    global PLAN
    if PLAN is None:
        base = SearchPlan(
            plan_id="",
            endpoint="https://example.gov.cn/search",
            protocol_version=PROTOCOL_VERSION_V2,
            status=PLAN_STATUS_READY,
            strategy=SEARCH_STRATEGY_HTML_FORM,
            adapter=ADAPTER_HTML,
            http_method="GET",
            request_format=REQUEST_FORMAT_NONE,
            response_format=RESPONSE_FORMAT_HTML,
            request_shape=SearchRequestShape(KEYWORD_LOCATION_QUERY, ("q",)),
            pagination=SearchPagination(),
            scope=SearchScope(domain="example.gov.cn"),
        )
        PLAN = replace(base, plan_id=compute_plan_id(base))
    return PLAN


def _success(item=None):
    return SearchPlanExecutionResult(
        plan_id=_ready_plan().plan_id,
        status="ok",
        items=(item or SearchResultItem("Title", "https://example.gov.cn/a.html"),),
        response_kind="text/html",
    )


def _no_results():
    return SearchPlanExecutionResult(
        plan_id=_ready_plan().plan_id,
        status="ok",
        items=(),
        response_kind="text/html",
        failure_code=FAILURE_NO_RESULTS,
    )


def _failure(code=FAILURE_TRANSPORT):
    return SearchPlanExecutionResult(
        plan_id=_ready_plan().plan_id,
        status="failed",
        items=(),
        response_kind="text/html",
        failure_code=code,
    )


class FakeCache:
    def __init__(self, read_result=None):
        self.read_result = read_result
        self.read_calls = []
        self.write_calls = []
        self.delete_calls = []

    def get(self, *, target_url):
        self.read_calls.append(target_url)
        return self.read_result

    def put(self, *, target_url, plan):
        self.write_calls.append((target_url, plan))

    def delete(self, *, target_url):
        self.delete_calls.append(target_url)


class SequenceExecutor:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, plan, query_term, *, fetcher, policy):
        self.calls.append(query_term)
        return self.outcomes.pop(0)


class FakePublisher:
    def __init__(self, error=None):
        self.error = error
        self.messages = []

    def publish(self, message):
        if self.error is not None:
            raise self.error
        self.messages.append(message)


class FakeAnalyzer:
    def __init__(self, candidates=()):
        self.candidates = tuple(candidates)
        self.calls = []

    def analyze(self, target_url):
        self.calls.append(target_url)
        return SiteAnalysisResult(
            normalized_url=TARGET,
            final_url=TARGET,
            candidates=self.candidates,
        )


class FakeBuilder:
    def __init__(self, plan):
        self.plan = plan
        self.calls = []

    def build(self, *, target_url, candidates, selector_evidence=None):
        self.calls.append(target_url)
        return PlanBuildResult(self.plan, (), None)


def _candidate():
    return SearchCandidate(
        method="GET",
        endpoint="https://example.gov.cn/search",
        keyword_param="q",
        source="form",
        status="unverified",
    )


def _evidence():
    return SelectorEvidence(
        candidate_key=("GET", "https://example.gov.cn/search", "q", ()),
        candidate_kind="html_form",
        response_kind="html",
        result_item="div.result-item",
        title="a",
        url="a",
        final_origin=TARGET,
        match_count=2,
        validated=True,
        evidence_source="probe",
    )


def _success_probe(*args, **kwargs):
    return SearchProbeResult(("k",), _evidence(), "success", None)


def _run(message, cache, executor, publisher):
    return orch.run_v2_search_pipeline(
        message,
        analyzer=FakeAnalyzer(),
        plan_builder=FakeBuilder(_ready_plan()),
        plan_cache=cache,
        probe_fetcher=None,
        policy=POLICY,
        executor=executor,
        publisher=publisher,
    )


def test_two_keywords_execute_in_order_and_preserve_sources():
    cache = FakeCache(PlanCacheReadResult(_ready_plan(), "hit", None))
    item = SearchResultItem(
        title="Title",
        url="https://example.gov.cn/a.html",
        snippet="snippet",
        body="body",
        published_at="2026-08-13",
        source="custom.gov.cn",
    )
    executor = SequenceExecutor([_success(item), _success(item)])
    publisher = FakePublisher()
    result = _run(_message(("k1", "k2")), cache, executor, publisher)

    assert result.status == "published"
    assert result.published_count == 2
    assert executor.calls == ["k1", "k2"]
    assert len(publisher.messages) == 2
    first = publisher.messages[0].to_dict()
    second = publisher.messages[1].to_dict()
    assert first["original_query"] == "k1"
    assert first["query_term"] == "k1"
    assert second["original_query"] == "k2"
    assert second["query_term"] == "k2"
    assert first["hit_id"] != second["hit_id"]
    assert first["message_id"] != second["message_id"]
    assert first["task_id"] == "task-019b-2"
    assert first["plan_id"] == _ready_plan().plan_id
    assert first["level"] == 0
    assert first["published_at"] == "2026-08-13"
    assert first["source"] == "custom.gov.cn"


def test_no_results_then_success_continues():
    cache = FakeCache(PlanCacheReadResult(_ready_plan(), "hit", None))
    executor = SequenceExecutor([_no_results(), _success()])
    publisher = FakePublisher()
    result = _run(_message(("k1", "k2")), cache, executor, publisher)

    assert result.status == "published"
    assert result.published_count == 1
    assert executor.calls == ["k1", "k2"]
    assert publisher.messages[0].to_dict()["original_query"] == "k2"


def test_all_no_results_returns_no_results():
    cache = FakeCache(PlanCacheReadResult(_ready_plan(), "hit", None))
    executor = SequenceExecutor([_no_results(), _no_results()])
    publisher = FakePublisher()
    result = _run(_message(("k1", "k2")), cache, executor, publisher)

    assert result.status == "no_results"
    assert result.published_count == 0
    assert publisher.messages == []
    assert cache.delete_calls == []


def test_later_execution_failure_is_fail_fast_with_count():
    cache = FakeCache(PlanCacheReadResult(_ready_plan(), "hit", None))
    executor = SequenceExecutor([_success(), _failure()])
    publisher = FakePublisher()
    result = _run(_message(("k1", "k2")), cache, executor, publisher)

    assert result.status == "failed"
    assert result.error_code == FAILURE_TRANSPORT
    assert result.published_count == 1
    assert len(publisher.messages) == 1
    assert executor.calls == ["k1", "k2"]
    assert cache.delete_calls == [TARGET]


def test_publish_failure_returns_publish_failure():
    cache = FakeCache(PlanCacheReadResult(_ready_plan(), "hit", None))
    executor = SequenceExecutor([_success()])
    publisher = FakePublisher(error=RuntimeError("redis down"))
    result = _run(_message(("k1",)), cache, executor, publisher)

    assert result.status == "failed"
    assert result.error_code == "publish_failure"
    assert result.published_count == 0
    assert cache.delete_calls == []


def test_source_falls_back_to_scope_domain():
    cache = FakeCache(PlanCacheReadResult(_ready_plan(), "hit", None))
    item = SearchResultItem("Title", "https://example.gov.cn/a.html")
    executor = SequenceExecutor([_success(item)])
    publisher = FakePublisher()
    result = _run(_message(("k1",)), cache, executor, publisher)

    assert result.status == "published"
    assert publisher.messages[0].to_dict()["source"] == "example.gov.cn"


def test_new_plan_path_supports_multi_keyword_and_writes_cache(monkeypatch):
    cache = FakeCache(PlanCacheReadResult(None, "miss", None))
    executor = SequenceExecutor([_success(), _success()])
    publisher = FakePublisher()
    analyzer = FakeAnalyzer(candidates=(_candidate(),))
    builder = FakeBuilder(_ready_plan())
    monkeypatch.setattr(orch, "probe_search_candidate", _success_probe)

    result = orch.run_v2_search_pipeline(
        _message(("k1", "k2")),
        analyzer=analyzer,
        plan_builder=builder,
        plan_cache=cache,
        probe_fetcher=None,
        policy=POLICY,
        executor=executor,
        publisher=publisher,
    )

    assert result.status == "published"
    assert result.published_count == 2
    assert executor.calls == ["k1", "k2"]
    assert analyzer.calls
    assert builder.calls
    assert len(cache.write_calls) == 1
