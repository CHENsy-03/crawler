"""Offline tests for SearchPlan cache lifecycle semantics."""

import pytest

from protocol.messages import SearchRequestedMessage, URLMessage

from crawler.search.plan_builder import PlanBuildResult
from crawler.search.plan_cache import PlanCacheReadResult
from crawler.search.plan_executor import (
    FAILURE_NO_RESULTS,
    FAILURE_PLAN_INVALID,
    FAILURE_PLAN_NOT_EXECUTABLE,
    FAILURE_RESPONSE_REJECTED,
    FAILURE_SELECTOR_MISMATCH,
    FAILURE_TRANSPORT,
    SearchPlanExecutionResult,
    SearchResultItem,
)
from crawler.search.search_plan import (
    PLAN_STATUS_READY,
    PROTOCOL_VERSION_V2,
    SEARCH_STRATEGY_HTML_FORM,
    SearchPlan,
    SearchScope,
    compute_plan_id,
)
from crawler.site.models import SearchCandidate
from crawler.site.search_probe import SearchProbePolicy, SearchProbeResult
from crawler.site.selector_evidence import SelectorEvidence

import crawler.search.search_orchestrator as orch

POLICY = SearchProbePolicy()
TARGET = "https://example.gov.cn/"


def _message():
    return SearchRequestedMessage(
        protocol_version="2.0",
        task_id="task-1",
        message_id="msg-1",
        timestamp="2026-08-12T00:00:00Z",
        target_url=TARGET,
        keywords=["k1"],
        level=0,
        max_pages=1,
    )


def _ready_plan():
    base = SearchPlan(
        plan_id="",
        endpoint="https://example.gov.cn/search",
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_READY,
        strategy=SEARCH_STRATEGY_HTML_FORM,
        http_method="GET",
        query_params={"q": "{keyword}"},
        scope=SearchScope(domain="example.gov.cn"),
    )
    return SearchPlan(
        plan_id=compute_plan_id(base),
        endpoint=base.endpoint,
        protocol_version=base.protocol_version,
        status=base.status,
        strategy=base.strategy,
        http_method=base.http_method,
        query_params=base.query_params,
        request_body_template=base.request_body_template,
        pagination=base.pagination,
        selectors=base.selectors,
        scope=base.scope,
        discovery=base.discovery,
        created_from=base.created_from,
    )


def _candidate():
    return SearchCandidate(
        method="GET",
        endpoint="https://example.gov.cn/search",
        keyword_param="q",
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


def _execution_result(failure=None, items=None):
    return SearchPlanExecutionResult(
        plan_id=_ready_plan().plan_id,
        status="failed" if failure else "ok",
        items=tuple(items or ()),
        response_kind="text/html",
        failure_code=failure,
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
        return None

    def delete(self, *, target_url):
        self.delete_calls.append(target_url)
        return True


class FakeAnalyzer:
    def __init__(self, candidates=()):
        self.candidates = tuple(candidates)
        self.calls = []

    def analyze(self, target_url):
        self.calls.append(target_url)
        return _Analysis(self.candidates)


class _Analysis:
    def __init__(self, candidates):
        self.candidates = tuple(candidates)


class FakeBuilder:
    def __init__(self, plan):
        self.plan = plan
        self.calls = []

    def build(self, *, target_url, candidates, selector_evidence=None):
        self.calls.append((target_url, tuple(candidates), selector_evidence))
        return PlanBuildResult(self.plan, (), None)


class FakeExecutor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, plan, keywords, *, fetcher, policy):
        self.calls.append(plan)
        return self.result


class FakePublisher:
    def __init__(self, error=None):
        self.error = error
        self.messages = []

    def publish(self, message):
        if self.error is not None:
            raise self.error
        self.messages.append(message)


def _success_probe(*args, **kwargs):
    return SearchProbeResult(("k",), _evidence(), "success", None)


def _run(cache, executor_result, publisher=None, analyzer=None, builder=None, probe=_success_probe, monkeypatch=None):
    if publisher is None:
        publisher = FakePublisher()
    if analyzer is None:
        analyzer = FakeAnalyzer(candidates=(_candidate(),))
    if builder is None:
        builder = FakeBuilder(_ready_plan())
    if monkeypatch is not None:
        monkeypatch.setattr(orch, "probe_search_candidate", probe)
    return orch.run_v2_search_pipeline(
        _message(),
        analyzer=analyzer,
        plan_builder=builder,
        plan_cache=cache,
        probe_fetcher=None,
        policy=POLICY,
        executor=FakeExecutor(executor_result),
        publisher=publisher,
    )


def test_new_plan_execution_failure_does_not_cache(monkeypatch):
    cache = FakeCache(PlanCacheReadResult(None, "miss", None))
    result = _run(cache, _execution_result(failure=FAILURE_SELECTOR_MISMATCH), monkeypatch=monkeypatch)
    assert result.status == "failed"
    assert result.error_code == FAILURE_SELECTOR_MISMATCH
    assert cache.write_calls == []
    assert cache.delete_calls == []


def test_next_task_rebuilds_after_failure(monkeypatch):
    cache = FakeCache(PlanCacheReadResult(None, "miss", None))
    analyzer = FakeAnalyzer(candidates=(_candidate(),))
    builder = FakeBuilder(_ready_plan())
    failure = _execution_result(failure=FAILURE_SELECTOR_MISMATCH)
    _run(cache, failure, analyzer=analyzer, builder=builder, monkeypatch=monkeypatch)
    assert len(analyzer.calls) == 1
    assert len(builder.calls) == 1

    success = _execution_result(items=(SearchResultItem("A", "https://example.gov.cn/a.html"),))
    _run(cache, success, analyzer=analyzer, builder=builder, publisher=FakePublisher(), monkeypatch=monkeypatch)
    assert len(analyzer.calls) == 2
    assert len(builder.calls) == 2
    assert len(cache.write_calls) == 1


@pytest.mark.parametrize(
    "failure",
    [
        FAILURE_PLAN_INVALID,
        FAILURE_PLAN_NOT_EXECUTABLE,
        FAILURE_TRANSPORT,
        FAILURE_RESPONSE_REJECTED,
        FAILURE_SELECTOR_MISMATCH,
    ],
)
def test_cache_hit_failure_deletes_cache(failure):
    plan = _ready_plan()
    cache = FakeCache(PlanCacheReadResult(plan, "hit", None))
    publisher = FakePublisher()
    result = orch.run_v2_search_pipeline(
        _message(),
        analyzer=FakeAnalyzer(),
        plan_builder=FakeBuilder(plan),
        plan_cache=cache,
        probe_fetcher=None,
        policy=POLICY,
        executor=FakeExecutor(_execution_result(failure=failure)),
        publisher=publisher,
    )
    assert result.status == "failed"
    assert cache.delete_calls == [TARGET]
    assert cache.write_calls == []
    assert publisher.messages == []


def test_no_results_new_plan_is_cached_and_not_published(monkeypatch):
    cache = FakeCache(PlanCacheReadResult(None, "miss", None))
    result = _run(cache, _execution_result(failure=FAILURE_NO_RESULTS), monkeypatch=monkeypatch)
    assert result.status == "no_results"
    assert len(cache.write_calls) == 1
    assert cache.delete_calls == []


def test_no_results_cache_hit_keeps_plan():
    plan = _ready_plan()
    cache = FakeCache(PlanCacheReadResult(plan, "hit", None))
    publisher = FakePublisher()
    result = orch.run_v2_search_pipeline(
        _message(),
        analyzer=FakeAnalyzer(),
        plan_builder=FakeBuilder(plan),
        plan_cache=cache,
        probe_fetcher=None,
        policy=POLICY,
        executor=FakeExecutor(_execution_result(failure=FAILURE_NO_RESULTS)),
        publisher=publisher,
    )
    assert result.status == "no_results"
    assert cache.delete_calls == []
    assert publisher.messages == []


def test_publish_failure_keeps_new_plan(monkeypatch):
    cache = FakeCache(PlanCacheReadResult(None, "miss", None))
    publisher = FakePublisher(error=RuntimeError("redis down"))
    result = _run(
        cache,
        _execution_result(items=(SearchResultItem("A", "https://example.gov.cn/a.html"),)),
        publisher=publisher,
        monkeypatch=monkeypatch,
    )
    assert result.status == "failed"
    assert result.error_code == "publish_failure"
    assert result.published_count == 0
    assert len(cache.write_calls) == 1
    assert cache.delete_calls == []


def test_publish_failure_keeps_cache_hit_plan():
    plan = _ready_plan()
    cache = FakeCache(PlanCacheReadResult(plan, "hit", None))
    publisher = FakePublisher(error=RuntimeError("redis down"))
    result = orch.run_v2_search_pipeline(
        _message(),
        analyzer=FakeAnalyzer(),
        plan_builder=FakeBuilder(plan),
        plan_cache=cache,
        probe_fetcher=None,
        policy=POLICY,
        executor=FakeExecutor(_execution_result(items=(SearchResultItem("A", "https://example.gov.cn/a.html"),))),
        publisher=publisher,
    )
    assert result.status == "failed"
    assert result.error_code == "publish_failure"
    assert cache.delete_calls == []
    assert cache.write_calls == []
