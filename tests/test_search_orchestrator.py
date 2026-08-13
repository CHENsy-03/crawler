"""Offline tests for the v2 production search orchestrator."""

from dataclasses import dataclass, replace

from protocol.messages import SearchRequestedMessage, URLMessage

import crawler.search.search_orchestrator as orch
from crawler.search.plan_builder import PlanBuildResult
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
from crawler.search.plan_executor import SearchPlanExecutionResult, SearchResultItem
from crawler.site.models import SearchCandidate
from crawler.site.search_probe import SearchProbePolicy, SearchProbeResult
from crawler.site.selector_evidence import SelectorEvidence


def _message():
    return SearchRequestedMessage(
        protocol_version="2.0",
        task_id="task-1",
        message_id="msg-1",
        timestamp="2026-08-12T00:00:00Z",
        target_url="https://example.gov.cn/",
        keywords=["k1", "k2"],
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
    def __init__(self, read_result=None):
        self.read_result = read_result
        self.read_calls = []
        self.write_calls = []

    def get(self, *, target_url):
        self.read_calls.append(target_url)
        return self.read_result

    def put(self, *, target_url, plan):
        self.write_calls.append((target_url, plan))
        return None


class FakeAnalyzer:
    def __init__(self, candidates=()):
        self.candidates = tuple(candidates)
        self.calls = []

    def analyze(self, target_url):
        self.calls.append(target_url)
        return _FakeAnalysis(self.candidates)


@dataclass
class _FakeAnalysis:
    candidates: tuple


class FakeBuilder:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def build(self, *, target_url, candidates, selector_evidence=None):
        self.calls.append((target_url, candidates, selector_evidence))
        return self.result


class FakeExecutor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, plan, keywords, *, fetcher, policy):
        self.calls.append((plan, keywords))
        return self.result


class FakePublisher:
    def __init__(self, error=None):
        self.messages = []
        self.error = error

    def publish(self, message):
        if self.error is not None:
            raise self.error
        self.messages.append(message)


def _candidate():
    return SearchCandidate(
        method="GET",
        endpoint="https://example.gov.cn/search",
        keyword_param="q",
        status="unverified",
    )


def _success_evidence():
    return SelectorEvidence(
        candidate_key=("GET", "https://example.gov.cn/search", "q", ()),
        candidate_kind="html_form",
        response_kind="html",
        result_item="div.result-item",
        title="a",
        url="a",
        final_origin="https://example.gov.cn/",
        match_count=2,
        validated=True,
        evidence_source="probe",
    )


def _execution_result():
    return SearchPlanExecutionResult(
        plan_id=_ready_plan().plan_id,
        status="ok",
        items=(SearchResultItem("A", "https://example.gov.cn/a.html"),),
        response_kind="text/html",
    )


def test_cache_hit_executes_and_publishes_url_message(monkeypatch):
    plan = _ready_plan()
    cache = FakeCache(orch.PlanCacheReadResult(plan, "hit", None))
    analyzer = FakeAnalyzer()
    builder = FakeBuilder(None)
    executor = FakeExecutor(_execution_result())
    publisher = FakePublisher()
    result = orch.run_v2_search_pipeline(
        _message(),
        analyzer=analyzer,
        plan_builder=builder,
        plan_cache=cache,
        probe_fetcher=None,
        policy=SearchProbePolicy(),
        executor=executor,
        publisher=publisher,
    )
    assert result.status == "published"
    assert result.published_count == 1
    assert analyzer.calls == []
    assert builder.calls == []
    assert len(publisher.messages) == 1
    assert isinstance(publisher.messages[0], URLMessage)
    payload = publisher.messages[0].to_dict()
    assert "time" not in payload
    assert payload["task_id"] == "task-1"
    assert payload["url"] == "https://example.gov.cn/a.html"
    assert payload["site"] == "example.gov.cn"
    assert payload["keyword"] == "k1"
    assert payload["level"] == 0


def test_draft_cache_is_not_treated_as_hit(monkeypatch):
    plan = SearchPlan(
        plan_id="draft-id",
        endpoint="https://example.gov.cn/search",
        protocol_version=PROTOCOL_VERSION_V2,
        status="draft",
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
    cache = FakeCache(orch.PlanCacheReadResult(plan, "hit", None))
    analyzer = FakeAnalyzer(candidates=(_candidate(),))
    builder = FakeBuilder(PlanBuildResult(_ready_plan(), (), None))
    executor = FakeExecutor(_execution_result())
    publisher = FakePublisher()

    def fake_probe(*args, **kwargs):
        return SearchProbeResult(("k",), _success_evidence(), "success", None)

    monkeypatch.setattr(orch, "probe_search_candidate", fake_probe)
    result = orch.run_v2_search_pipeline(
        _message(),
        analyzer=analyzer,
        plan_builder=builder,
        plan_cache=cache,
        probe_fetcher=None,
        policy=SearchProbePolicy(),
        executor=executor,
        publisher=publisher,
    )
    assert result.status == "published"
    assert analyzer.calls
    assert builder.calls
    assert len(cache.write_calls) == 1


def test_miss_pipeline_builds_caches_executes_publishes(monkeypatch):
    cache = FakeCache(orch.PlanCacheReadResult(None, "miss", None))
    analyzer = FakeAnalyzer(candidates=(_candidate(),))
    plan = _ready_plan()
    builder = FakeBuilder(PlanBuildResult(plan, (), None))
    executor = FakeExecutor(_execution_result())
    publisher = FakePublisher()

    def fake_probe(*args, **kwargs):
        return SearchProbeResult(("k",), _success_evidence(), "success", None)

    monkeypatch.setattr(orch, "probe_search_candidate", fake_probe)
    result = orch.run_v2_search_pipeline(
        _message(),
        analyzer=analyzer,
        plan_builder=builder,
        plan_cache=cache,
        probe_fetcher=None,
        policy=SearchProbePolicy(),
        executor=executor,
        publisher=publisher,
    )
    assert result.status == "published"
    assert len(cache.write_calls) == 1
    assert len(publisher.messages) == 1


def test_all_probes_fail_without_publishing(monkeypatch):
    cache = FakeCache(orch.PlanCacheReadResult(None, "miss", None))
    analyzer = FakeAnalyzer(candidates=(_candidate(),))
    builder = FakeBuilder(None)
    publisher = FakePublisher()

    def fake_probe(*args, **kwargs):
        return SearchProbeResult(("k",), None, "no_evidence", None)

    monkeypatch.setattr(orch, "probe_search_candidate", fake_probe)
    result = orch.run_v2_search_pipeline(
        _message(),
        analyzer=analyzer,
        plan_builder=builder,
        plan_cache=cache,
        probe_fetcher=None,
        policy=SearchProbePolicy(),
        executor=FakeExecutor(None),
        publisher=publisher,
    )
    assert result.status == "failed"
    assert result.error_code == "no_executable_plan"
    assert publisher.messages == []


def test_at_most_three_candidates_probed(monkeypatch):
    cache = FakeCache(orch.PlanCacheReadResult(None, "miss", None))
    candidates = tuple(_candidate() for _ in range(4))
    analyzer = FakeAnalyzer(candidates=candidates)
    publisher = FakePublisher()
    calls = []

    def fake_probe(candidate, keywords, *, fetcher, policy):
        calls.append(candidate)
        return SearchProbeResult(("k",), None, "no_evidence", None)

    monkeypatch.setattr(orch, "probe_search_candidate", fake_probe)
    orch.run_v2_search_pipeline(
        _message(),
        analyzer=analyzer,
        plan_builder=FakeBuilder(None),
        plan_cache=cache,
        probe_fetcher=None,
        policy=SearchProbePolicy(),
        executor=FakeExecutor(None),
        publisher=publisher,
    )
    assert len(calls) == 3


def test_publish_failure_returns_failure(monkeypatch):
    plan = _ready_plan()
    cache = FakeCache(orch.PlanCacheReadResult(plan, "hit", None))
    publisher = FakePublisher(error=RuntimeError("redis down"))
    result = orch.run_v2_search_pipeline(
        _message(),
        analyzer=FakeAnalyzer(),
        plan_builder=FakeBuilder(None),
        plan_cache=cache,
        probe_fetcher=None,
        policy=SearchProbePolicy(),
        executor=FakeExecutor(_execution_result()),
        publisher=publisher,
    )
    assert result.status == "failed"
    assert result.error_code == "publish_failure"
    assert result.published_count == 0
