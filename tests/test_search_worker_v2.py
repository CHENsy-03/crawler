"""Offline tests for v2 SearchPlan generation in the search worker."""

import json
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

import pytest

from crawler.search.plan_executor import RegistryPlanExecutor
from crawler.search.plan_builder import (
    ERROR_NO_CANDIDATES,
    ERROR_NO_EXECUTABLE_PLAN,
    PlanBuildResult,
)
from crawler.search.plan_cache import (
    PlanCacheReadResult,
    PlanCacheWriteResult,
)
from crawler.search.search_plan import (
    ADAPTER_HTML,
    ADAPTER_GENERIC_JSON,
    ADAPTER_JPAAS,
    ADAPTER_TRS,
    KEYWORD_LOCATION_QUERY,
    REQUEST_FORMAT_NONE,
    RESPONSE_FORMAT_HTML,
    SearchPagination,
    SearchRequestShape,

    PLAN_STATUS_DRAFT,
    PROTOCOL_VERSION_V2,
    SEARCH_STRATEGY_HTML_FORM,
    SearchPlan,
    SearchScope,
    compute_plan_id,
)
from crawler.search.search_orchestrator import V2PipelineResult
from crawler.site.models import SearchCandidate, SiteAnalysisResult
from workers.search_worker import (
    V2PlanGenerationResult,
    handle_search_message,
    handle_v2_search_message,
    run_worker,
)

TARGET = "https://example.gov.cn/"
ENDPOINT = "https://example.gov.cn/search"


def _valid_plan():
    base = SearchPlan(
        plan_id="",
        endpoint=ENDPOINT,
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_DRAFT,
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


def _candidate(index=0):
    return SearchCandidate(
        method="GET",
        endpoint=ENDPOINT,
        keyword_param="q",
        fixed_params=(),
        source="form",
        priority=3,
        scope="same_origin",
        evidence=(f"candidate-{index}",),
        status="unverified",
    )


def _v2_raw(
    *,
    task_id="task-1",
    message_id="msg-1",
    target_url=TARGET,
    keywords=("低空经济",),
    type_="search_requested",
):
    payload = {
        "protocol_version": "2.0",
        "task_id": task_id,
        "message_id": message_id,
        "timestamp": "2026-08-12T00:00:00Z",
        "type": type_,
        "target_url": target_url,
        "keywords": list(keywords),
    }
    return json.dumps(payload)


def _v1_raw():
    return json.dumps({
        "protocol_version": "1.0",
        "task_id": "task-v1",
        "message_id": "msg-v1",
        "timestamp": "2026-08-12T00:00:00Z",
        "type": "search",
        "site": "czj_beijing",
        "keyword": "低空经济",
        "level": 1,
        "max_pages": 1,
    })


class FakeAnalyzer:
    def __init__(self, candidates=(), error=None, events=None):
        self.candidates = candidates
        self.error = error
        self.calls = []
        self.events = events

    def analyze(self, target_url):
        self.calls.append(target_url)
        if self.events is not None:
            self.events.append("analyzer")
        if self.error is not None:
            raise self.error
        return SiteAnalysisResult(
            normalized_url=target_url,
            final_url=target_url,
            candidates=tuple(self.candidates),
        )


class FakePlanBuilder:
    def __init__(self, result, events=None):
        self.result = result
        self.calls = []
        self.events = events

    def build(self, *, target_url, candidates):
        self.calls.append((target_url, tuple(candidates)))
        if self.events is not None:
            self.events.append("builder")
        return self.result


class FakePlanCache:
    def __init__(self, read_result=None, write_result=None, events=None):
        self.read_result = read_result or PlanCacheReadResult(None, "miss", None)
        self.write_result = write_result or PlanCacheWriteResult(True, None)
        self.read_calls = []
        self.write_calls = []
        self.deleted = False
        self.events = events

    def get(self, *, target_url):
        self.read_calls.append(target_url)
        if self.events is not None:
            self.events.append("cache_get")
        return self.read_result

    def put(self, *, target_url, plan):
        self.write_calls.append((target_url, plan))
        if self.events is not None:
            self.events.append("cache_put")
        return self.write_result

    def delete(self, *args, **kwargs):
        self.deleted = True


def _success_builder(plan=_valid_plan()):
    return FakePlanBuilder(PlanBuildResult(plan, (), None))


def test_v2_message_is_recognized():
    plan = _valid_plan()
    cache = FakePlanCache(PlanCacheReadResult(plan, "hit", None))
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert result.success
    assert result.plan == plan


def test_v1_message_returns_none_from_generic_handler():
    result = handle_search_message(
        _v1_raw(),
        analyzer=FakeAnalyzer(),
        plan_builder=_success_builder(),
        plan_cache=FakePlanCache(),
    )
    assert result is None


def test_unknown_version_not_treated_as_v2():
    raw = json.dumps({
        "protocol_version": "9.9",
        "task_id": "t",
        "message_id": "m",
        "timestamp": "now",
        "type": "search_requested",
        "target_url": TARGET,
        "keywords": ["k"],
    })
    cache = FakePlanCache()
    result = handle_v2_search_message(
        raw,
        analyzer=FakeAnalyzer(),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert result.error_code == "invalid_message"
    assert cache.read_calls == []


def test_unknown_task_type_not_treated_as_v2():
    raw = _v2_raw(type_="search")
    cache = FakePlanCache()
    result = handle_v2_search_message(
        raw,
        analyzer=FakeAnalyzer(),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert result.error_code == "invalid_message"
    assert cache.read_calls == []


def test_missing_target_is_rejected():
    raw = json.dumps({
        "protocol_version": "2.0",
        "task_id": "t",
        "message_id": "m",
        "timestamp": "now",
        "type": "search_requested",
        "keywords": ["k"],
    })
    cache = FakePlanCache()
    result = handle_v2_search_message(
        raw,
        analyzer=FakeAnalyzer(),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert result.error_code == "invalid_message"
    assert cache.read_calls == []


def test_missing_keywords_is_rejected():
    raw = json.dumps({
        "protocol_version": "2.0",
        "task_id": "t",
        "message_id": "m",
        "timestamp": "now",
        "type": "search_requested",
        "target_url": TARGET,
    })
    cache = FakePlanCache()
    result = handle_v2_search_message(
        raw,
        analyzer=FakeAnalyzer(),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert result.error_code == "invalid_message"
    assert cache.read_calls == []


def test_task_id_preserved_on_success():
    cache = FakePlanCache(PlanCacheReadResult(_valid_plan(), "hit", None))
    result = handle_v2_search_message(
        _v2_raw(task_id="task-keep"),
        analyzer=FakeAnalyzer(),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert result.task_id == "task-keep"


def test_message_id_preserved_on_failure():
    cache = FakePlanCache()
    analyzer = FakeAnalyzer(error=RuntimeError("boom"))
    result = handle_v2_search_message(
        _v2_raw(message_id="msg-keep"),
        analyzer=analyzer,
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert result.message_id == "msg-keep"
    assert result.error_code == "analysis_failed"


def test_cache_hit_returns_plan_directly():
    plan = _valid_plan()
    cache = FakePlanCache(PlanCacheReadResult(plan, "hit", None))
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert result.success
    assert result.plan == plan


def test_hit_does_not_call_analyzer():
    analyzer = FakeAnalyzer()
    handle_v2_search_message(
        _v2_raw(),
        analyzer=analyzer,
        plan_builder=_success_builder(),
        plan_cache=FakePlanCache(PlanCacheReadResult(_valid_plan(), "hit", None)),
    )
    assert analyzer.calls == []


def test_hit_does_not_call_plan_builder():
    builder = _success_builder()
    handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(),
        plan_builder=builder,
        plan_cache=FakePlanCache(PlanCacheReadResult(_valid_plan(), "hit", None)),
    )
    assert builder.calls == []


def test_hit_does_not_call_cache_put():
    cache = FakePlanCache(PlanCacheReadResult(_valid_plan(), "hit", None))
    handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert cache.write_calls == []


def test_hit_does_not_execute_legacy_pipeline():
    with patch("workers.search_worker.plugin_search", side_effect=AssertionError("legacy search called")):
        result = handle_v2_search_message(
            _v2_raw(),
            analyzer=FakeAnalyzer(),
            plan_builder=_success_builder(),
            plan_cache=FakePlanCache(PlanCacheReadResult(_valid_plan(), "hit", None)),
        )
    assert result.success


def test_hit_does_not_publish_search_result_url():
    with patch("redis.Redis.lpush", side_effect=AssertionError("publish called")):
        result = handle_v2_search_message(
            _v2_raw(),
            analyzer=FakeAnalyzer(),
            plan_builder=_success_builder(),
            plan_cache=FakePlanCache(PlanCacheReadResult(_valid_plan(), "hit", None)),
        )
    assert result.success


def test_miss_calls_analyzer_once():
    analyzer = FakeAnalyzer(candidates=(_candidate(),))
    handle_v2_search_message(
        _v2_raw(),
        analyzer=analyzer,
        plan_builder=_success_builder(),
        plan_cache=FakePlanCache(),
    )
    assert analyzer.calls == [TARGET]


def test_miss_passes_candidates_to_builder():
    candidates = (_candidate(0), _candidate(1))
    analyzer = FakeAnalyzer(candidates=candidates)
    builder = _success_builder()
    handle_v2_search_message(
        _v2_raw(),
        analyzer=analyzer,
        plan_builder=builder,
        plan_cache=FakePlanCache(),
    )
    assert builder.calls[0][0] == TARGET
    assert builder.calls[0][1] == candidates


def test_candidate_order_is_preserved():
    candidates = (_candidate(0), _candidate(1), _candidate(2))
    analyzer = FakeAnalyzer(candidates=candidates)
    builder = _success_builder()
    handle_v2_search_message(
        _v2_raw(),
        analyzer=analyzer,
        plan_builder=builder,
        plan_cache=FakePlanCache(),
    )
    assert [c.evidence[0] for c in builder.calls[0][1]] == ["candidate-0", "candidate-1", "candidate-2"]


def test_builder_success_calls_put_once():
    cache = FakePlanCache()
    handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert len(cache.write_calls) == 1


def test_put_uses_original_target_and_same_plan():
    plan = _valid_plan()
    cache = FakePlanCache()
    handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=_success_builder(plan),
        plan_cache=cache,
    )
    assert cache.write_calls[0][0] == TARGET
    assert cache.write_calls[0][1] == plan


def test_miss_returns_builder_plan():
    plan = _valid_plan()
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=_success_builder(plan),
        plan_cache=FakePlanCache(),
    )
    assert result.success
    assert result.plan == plan


def test_corrupt_is_soft_miss():
    plan = _valid_plan()
    cache = FakePlanCache(PlanCacheReadResult(None, "corrupt", None))
    analyzer = FakeAnalyzer(candidates=(_candidate(),))
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=analyzer,
        plan_builder=_success_builder(plan),
        plan_cache=cache,
    )
    assert result.success
    assert result.plan == plan
    assert analyzer.calls == [TARGET]


def test_corrupt_does_not_return_half_plan():
    cache = FakePlanCache(PlanCacheReadResult(None, "corrupt", None))
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=FakePlanBuilder(PlanBuildResult(None, (), ERROR_NO_EXECUTABLE_PLAN)),
        plan_cache=cache,
    )
    assert result.plan is None
    assert result.error_code == ERROR_NO_EXECUTABLE_PLAN


def test_corrupt_is_not_deleted_by_worker():
    cache = FakePlanCache(PlanCacheReadResult(None, "corrupt", None))
    handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert cache.deleted is False


def test_read_failed_still_generates_plan():
    plan = _valid_plan()
    cache = FakePlanCache(PlanCacheReadResult(None, "read_failed", "plan_cache_read_failed"))
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=_success_builder(plan),
        plan_cache=cache,
    )
    assert result.success
    assert result.plan == plan


def test_read_failed_success_returns_plan():
    plan = _valid_plan()
    cache = FakePlanCache(PlanCacheReadResult(None, "read_failed", "plan_cache_read_failed"))
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=_success_builder(plan),
        plan_cache=cache,
    )
    assert result.success


def test_write_failed_still_returns_plan():
    plan = _valid_plan()
    cache = FakePlanCache(write_result=PlanCacheWriteResult(False, "plan_cache_write_failed"))
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=_success_builder(plan),
        plan_cache=cache,
    )
    assert result.success
    assert result.plan == plan


def test_write_failed_does_not_retry():
    cache = FakePlanCache(write_result=PlanCacheWriteResult(False, "plan_cache_write_failed"))
    handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert len(cache.write_calls) == 1


def test_analyzer_empty_candidates_returns_no_candidates():
    cache = FakePlanCache()
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=()),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert result.error_code == ERROR_NO_CANDIDATES
    assert cache.write_calls == []


def test_analyzer_controlled_failure_returns_analysis_failed():
    cache = FakePlanCache()
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(error=RuntimeError("boom")),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert result.error_code == "analysis_failed"
    assert cache.write_calls == []


def test_builder_no_candidates_returns_no_candidates():
    cache = FakePlanCache()
    builder = FakePlanBuilder(PlanBuildResult(None, (), ERROR_NO_CANDIDATES))
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=builder,
        plan_cache=cache,
    )
    assert result.error_code == ERROR_NO_CANDIDATES
    assert cache.write_calls == []


def test_builder_no_executable_plan_returns_error():
    cache = FakePlanCache()
    builder = FakePlanBuilder(PlanBuildResult(None, (), ERROR_NO_EXECUTABLE_PLAN))
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=builder,
        plan_cache=cache,
    )
    assert result.error_code == ERROR_NO_EXECUTABLE_PLAN
    assert cache.write_calls == []


def test_builder_failure_does_not_write_cache():
    cache = FakePlanCache()
    handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=FakePlanBuilder(PlanBuildResult(None, (), ERROR_NO_EXECUTABLE_PLAN)),
        plan_cache=cache,
    )
    assert cache.write_calls == []


def test_analyzer_failure_does_not_write_cache():
    cache = FakePlanCache()
    handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(error=RuntimeError("boom")),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert cache.write_calls == []


def test_failure_does_not_execute_plan():
    with patch("workers.search_worker.plugin_search", side_effect=AssertionError("legacy search called")):
        result = handle_v2_search_message(
            _v2_raw(),
            analyzer=FakeAnalyzer(error=RuntimeError("boom")),
            plan_builder=_success_builder(),
            plan_cache=FakePlanCache(),
        )
    assert result.error_code == "analysis_failed"


def test_failure_does_not_publish_search_result_url():
    with patch("redis.Redis.lpush", side_effect=AssertionError("publish called")):
        result = handle_v2_search_message(
            _v2_raw(),
            analyzer=FakeAnalyzer(error=RuntimeError("boom")),
            plan_builder=_success_builder(),
            plan_cache=FakePlanCache(),
        )
    assert result.error_code == "analysis_failed"


def test_plan_uses_existing_serialization_entry():
    plan = _valid_plan()
    cache = FakePlanCache(PlanCacheReadResult(plan, "hit", None))
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert result.plan is not None
    assert result.plan.to_dict() == plan.to_dict()


def test_returned_plan_id_is_unchanged():
    plan = _valid_plan()
    cache = FakePlanCache(PlanCacheReadResult(plan, "hit", None))
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert result.plan is not None
    assert result.plan.plan_id == plan.plan_id


def test_worker_does_not_generate_plan_id():
    plan = _valid_plan()
    cache = FakePlanCache()
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=_success_builder(plan),
        plan_cache=cache,
    )
    assert result.plan is not None
    assert result.plan.plan_id == plan.plan_id


def test_cache_get_called_once():
    cache = FakePlanCache()
    handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert len(cache.read_calls) == 1


def test_analyzer_called_once():
    analyzer = FakeAnalyzer(candidates=(_candidate(),))
    handle_v2_search_message(
        _v2_raw(),
        analyzer=analyzer,
        plan_builder=_success_builder(),
        plan_cache=FakePlanCache(),
    )
    assert len(analyzer.calls) == 1


def test_builder_called_once():
    builder = _success_builder()
    handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=builder,
        plan_cache=FakePlanCache(),
    )
    assert len(builder.calls) == 1


def test_put_called_once():
    cache = FakePlanCache()
    handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert len(cache.write_calls) == 1


def test_call_order_is_cache_analyzer_builder_put():
    events = []
    cache = FakePlanCache(events=events)
    analyzer = FakeAnalyzer(candidates=(_candidate(),), events=events)
    builder = _success_builder()
    builder.events = events
    handle_v2_search_message(
        _v2_raw(),
        analyzer=analyzer,
        plan_builder=builder,
        plan_cache=cache,
    )
    assert events == ["cache_get", "analyzer", "builder", "cache_put"]


def test_second_same_task_hit_does_not_analyze():
    analyzer = FakeAnalyzer()
    cache = FakePlanCache(PlanCacheReadResult(_valid_plan(), "hit", None))
    for _ in range(2):
        result = handle_v2_search_message(
            _v2_raw(),
            analyzer=analyzer,
            plan_builder=_success_builder(),
            plan_cache=cache,
        )
        assert result.success
    assert analyzer.calls == []
    assert len(cache.read_calls) == 2


def test_v2_does_not_enter_legacy_pipeline():
    with patch("workers.search_worker.plugin_search", side_effect=AssertionError("legacy search called")), patch(
        "crawler.pipeline.run_pipeline", side_effect=AssertionError("pipeline called")
    ):
        result = handle_v2_search_message(
            _v2_raw(),
            analyzer=FakeAnalyzer(candidates=(_candidate(),)),
            plan_builder=_success_builder(),
            plan_cache=FakePlanCache(),
        )
    assert result.success


def test_errors_do_not_contain_sensitive_or_traceback():
    analyzer = FakeAnalyzer(error=RuntimeError("token=SECRET traceback detail"))
    cache = FakePlanCache()
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=analyzer,
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert result.error_code == "analysis_failed"
    assert "SECRET" not in (result.error_code or "")
    assert "traceback" not in (result.error_code or "")


def test_redis_exception_text_is_not_leaked():
    cache = FakePlanCache(PlanCacheReadResult(None, "read_failed", "plan_cache_read_failed"))
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(candidates=(_candidate(),)),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert result.success
    assert "connection" not in (result.error_code or "")


def test_no_network_dns_redis_database_or_time_access():
    with patch("socket.getaddrinfo", side_effect=AssertionError("dns called")), patch(
        "urllib.request.urlopen", side_effect=AssertionError("network called")
    ), patch("time.time", side_effect=AssertionError("time called")):
        result = handle_v2_search_message(
            _v2_raw(),
            analyzer=FakeAnalyzer(candidates=(_candidate(),)),
            plan_builder=_success_builder(),
            plan_cache=FakePlanCache(),
        )
    assert result.success


def test_result_dataclass_is_immutable():
    result = V2PlanGenerationResult("t", "m", None, None)
    with pytest.raises(FrozenInstanceError):
        result.error_code = "invalid_message"


def test_plan_fields_are_not_rewritten():
    plan = _valid_plan()
    cache = FakePlanCache(PlanCacheReadResult(plan, "hit", None))
    result = handle_v2_search_message(
        _v2_raw(),
        analyzer=FakeAnalyzer(),
        plan_builder=_success_builder(),
        plan_cache=cache,
    )
    assert result.plan == plan
    assert result.plan.to_dict() == plan.to_dict()


def test_worker_v2_default_executor_uses_production_registry():
    import workers.search_worker as sw

    captured = {}

    class FakeRedis:
        def __init__(self):
            self.sent = False

        def brpop(self, name, timeout=0):
            if self.sent:
                raise KeyboardInterrupt
            self.sent = True
            return (name, _v2_raw())

    def fake_pipeline(message, **kwargs):
        captured["executor"] = kwargs["executor"]
        return V2PipelineResult("published", "plan-1", 1)

    with patch.object(sw._redis, "Redis", return_value=FakeRedis()), patch.object(sw, "run_v2_search_pipeline", side_effect=fake_pipeline), patch.object(sw, "_load_plan_cache_ttl", return_value=86400), patch("signal.signal"):
        try:
            run_worker("localhost:6379")
        except KeyboardInterrupt:
            pass
    assert isinstance(captured["executor"], RegistryPlanExecutor)
    registry = captured["executor"]._registry
    assert set(registry._adapters) == {ADAPTER_HTML, ADAPTER_TRS, ADAPTER_JPAAS, ADAPTER_GENERIC_JSON}
