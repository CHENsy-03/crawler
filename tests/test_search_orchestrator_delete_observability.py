"""Offline tests for SearchPlan cache delete observability."""

import logging
from dataclasses import replace

from protocol.messages import SearchRequestedMessage

from crawler.search.plan_cache import PlanCacheReadResult
from crawler.search.plan_executor import (
    FAILURE_SELECTOR_MISMATCH,
    SearchPlanExecutionResult,
)
from crawler.search.search_plan import (
    ADAPTER_HTML,
    KEYWORD_LOCATION_QUERY,
    REQUEST_FORMAT_NONE,
    RESPONSE_FORMAT_HTML,
    SearchPagination,
    SearchRequestShape,

    PLAN_STATUS_READY,
    PROTOCOL_VERSION_V2,
    SEARCH_STRATEGY_HTML_FORM,
    SearchPlan,
    SearchScope,
    compute_plan_id,
)
from crawler.site.models import SearchCandidate

import crawler.search.search_orchestrator as orch
from crawler.search.search_orchestrator import _safe_hostname


def _message():
    return SearchRequestedMessage(
        protocol_version="2.0",
        task_id="task-delete-obs",
        message_id="msg-1",
        timestamp="2026-08-12T00:00:00Z",
        target_url="https://Example.GOV.CN:8443/search?secret=1#frag",
        keywords=["k"],
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
        adapter=ADAPTER_HTML,
        http_method="GET",
        request_format=REQUEST_FORMAT_NONE,
        response_format=RESPONSE_FORMAT_HTML,
        request_shape=SearchRequestShape(
            keyword_location=KEYWORD_LOCATION_QUERY,
            keyword_path=("q",),
        ),
        pagination=SearchPagination(),
        scope=SearchScope(domain="example.gov.cn"),
    )
    return replace(base, plan_id=compute_plan_id(base))


class FakeCache:
    def __init__(self, read_result, delete_error=None):
        self.read_result = read_result
        self.delete_error = delete_error
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
        if self.delete_error is not None:
            raise self.delete_error
        return True


class FakeAnalyzer:
    def __init__(self):
        self.calls = []

    def analyze(self, target_url):
        self.calls.append(target_url)
        return _Analysis(())


class _Analysis:
    def __init__(self, candidates):
        self.candidates = tuple(candidates)


class FakeBuilder:
    def __init__(self):
        self.calls = []

    def build(self, *, target_url, candidates, selector_evidence=None):
        self.calls.append(target_url)
        return None


class FakeExecutor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, plan, keywords, *, fetcher, policy):
        self.calls.append(plan)
        return self.result


class FakePublisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


def _failure():
    return SearchPlanExecutionResult(
        plan_id=_ready_plan().plan_id,
        status="failed",
        items=(),
        response_kind="text/html",
        failure_code=FAILURE_SELECTOR_MISMATCH,
    )


def _run(cache, caplog):
    analyzer = FakeAnalyzer()
    builder = FakeBuilder()
    publisher = FakePublisher()
    result = orch.run_v2_search_pipeline(
        _message(),
        analyzer=analyzer,
        plan_builder=builder,
        plan_cache=cache,
        probe_fetcher=None,
        policy=orch.SearchProbePolicy(),
        executor=FakeExecutor(_failure()),
        publisher=publisher,
    )
    return result, analyzer, builder, publisher


def test_delete_exception_logs_warning_and_keeps_original_failure(caplog):
    caplog.set_level(logging.WARNING, logger="crawler.search.orchestrator")
    plan = _ready_plan()
    cache = FakeCache(
        PlanCacheReadResult(plan, "hit", None),
        delete_error=RuntimeError("redis delete boom"),
    )
    result, analyzer, builder, publisher = _run(cache, caplog)
    assert result.status == "failed"
    assert result.error_code == FAILURE_SELECTOR_MISMATCH
    assert len(cache.delete_calls) == 1
    assert cache.write_calls == []
    assert publisher.messages == []
    assert analyzer.calls == []
    assert builder.calls == []

    records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(records) == 1
    assert "search_plan_cache_delete_failed" in records[0].getMessage()
    assert "task-delete-obs" in records[0].getMessage()
    assert "example.gov.cn" in records[0].getMessage()
    assert "RuntimeError" in records[0].getMessage()
    assert "secret" not in records[0].getMessage()
    assert "/search" not in records[0].getMessage()
    assert ":8443" not in records[0].getMessage()
    assert "#frag" not in records[0].getMessage()


def test_delete_success_does_not_log_failure_warning(caplog):
    caplog.set_level(logging.WARNING, logger="crawler.search.orchestrator")
    plan = _ready_plan()
    cache = FakeCache(PlanCacheReadResult(plan, "hit", None))
    result, _, _, _ = _run(cache, caplog)
    assert result.status == "failed"
    assert result.error_code == FAILURE_SELECTOR_MISMATCH
    assert len(cache.delete_calls) == 1
    assert all("search_plan_cache_delete_failed" not in r.getMessage() for r in caplog.records)


def test_safe_hostname_extraction():
    assert _safe_hostname("https://Example.GOV.CN:8443/search?q=1#f") == "example.gov.cn"
    assert _safe_hostname("not a url") == "<unknown>"
    assert _safe_hostname("") == "<unknown>"
