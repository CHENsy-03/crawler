"""Production orchestration for v2 SearchPlan generation, execution and publishing."""

import json
import logging
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from protocol.messages import SearchRequestedMessage, URLMessageV2, new_message_id

from crawler.search.plan_builder import PlanBuildResult, PlanBuilder
from crawler.search.plan_cache import (
    PlanCacheReadResult,
    PlanCacheWriteResult,
    SearchPlanCache,
)
from crawler.search.adapter_composition import build_default_adapter_registry
from crawler.search.plan_executor import (
    FAILURE_NO_RESULTS,
    RegistryPlanExecutor,
    SearchPlanExecutionResult,
)
from crawler.search.search_hit_builder import build_search_hit
from crawler.search.search_plan import SearchPlan
from crawler.site.analyzer import SiteAnalyzer
from crawler.site.models import SearchCandidate, SiteAnalysisResult
from crawler.site.search_probe import (
    SearchProbeFetcher,
    SearchProbePolicy,
    SearchProbeResult,
    PinnedProbeFetcher,
    probe_search_candidate,
)

STATUS_PUBLISHED = "published"
STATUS_NO_RESULTS = "no_results"
STATUS_FAILED = "failed"

_EXECUTABLE_STATUSES = {"ready", "active"}

log = logging.getLogger("crawler.search.orchestrator")


def _is_reusable_execution(execution: SearchPlanExecutionResult) -> bool:
    return execution.success or execution.failure_code == FAILURE_NO_RESULTS


def _now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass(frozen=True)
class V2PipelineResult:
    status: str
    plan_id: str | None
    published_count: int
    error_code: str | None = None


class AnalyzerProtocol(Protocol):
    def analyze(self, target_url: str) -> SiteAnalysisResult:
        ...


class PlanBuilderProtocol(Protocol):
    def build(
        self,
        *,
        target_url: str,
        candidates: tuple[SearchCandidate, ...],
        selector_evidence=None,
    ) -> PlanBuildResult:
        ...


class PlanCacheProtocol(Protocol):
    def get(self, *, target_url: str) -> PlanCacheReadResult:
        ...

    def put(self, *, target_url: str, plan: SearchPlan) -> PlanCacheWriteResult:
        ...


class PlanExecutorProtocol(Protocol):
    def __call__(
        self,
        plan: SearchPlan,
        query_term: str,
        *,
        fetcher: SearchProbeFetcher,
        policy: SearchProbePolicy,
    ) -> SearchPlanExecutionResult:
        ...


class URLMessagePublisher(Protocol):
    def publish(self, message: URLMessageV2) -> None:
        ...


class RedisURLMessagePublisher:
    """Publish formal URLMessage objects to the existing crawler:url list."""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def publish(self, message) -> None:
        payload = json.dumps(message.to_dict(), ensure_ascii=False)
        self._redis.lpush("crawler:url", payload)


def _safe_hostname(raw: str) -> str:
    try:
        host = urlsplit(raw).hostname
        return host.lower() if host else "<unknown>"
    except Exception:
        return "<unknown>"


def _candidate_key(candidate: SearchCandidate) -> tuple[str, ...]:
    return (
        candidate.method,
        candidate.endpoint,
        candidate.keyword_param,
        tuple(sorted(candidate.fixed_params)),
    )


def _run_keyword_hits(
    message: SearchRequestedMessage,
    plan: SearchPlan,
    *,
    executor: PlanExecutorProtocol,
    fetcher: SearchProbeFetcher,
    policy: SearchProbePolicy,
    publisher: URLMessagePublisher,
    cache: PlanCacheProtocol | None = None,
) -> V2PipelineResult:
    published = 0
    any_results = False
    cache_written = False

    def _write_cache() -> None:
        nonlocal cache_written
        if cache is not None and not cache_written:
            cache.put(target_url=message.target_url, plan=plan)
            cache_written = True

    for original_query in message.keywords:
        execution = executor(plan, original_query, fetcher=fetcher, policy=policy)
        if not _is_reusable_execution(execution):
            return V2PipelineResult(
                STATUS_FAILED,
                plan.plan_id,
                published,
                execution.failure_code or "execution_failed",
            )
        if execution.failure_code == FAILURE_NO_RESULTS or not execution.items or not execution.success:
            continue

        any_results = True
        for item in execution.items:
            timestamp = _now_utc()
            hit = build_search_hit(
                task_id=message.task_id,
                plan=plan,
                original_query=original_query,
                query_term=original_query,
                item=item,
                discovered_at=timestamp,
            )
            url_message = URLMessageV2(
                protocol_version=message.protocol_version,
                task_id=message.task_id,
                message_id=new_message_id(),
                timestamp=timestamp,
                hit_id=hit.hit_id,
                plan_id=hit.plan_id,
                original_query=original_query,
                query_term=original_query,
                url=hit.url,
                title=hit.title,
                snippet=hit.snippet,
                published_at=hit.published_at,
                source=hit.source,
                level=message.level,
            )
            try:
                publisher.publish(url_message)
            except Exception:
                _write_cache()
                return V2PipelineResult(
                    STATUS_FAILED,
                    plan.plan_id,
                    published,
                    "publish_failure",
                )
            published += 1

    _write_cache()
    if not any_results:
        return V2PipelineResult(STATUS_NO_RESULTS, plan.plan_id, 0, FAILURE_NO_RESULTS)
    return V2PipelineResult(STATUS_PUBLISHED, plan.plan_id, published, None)


def run_v2_search_pipeline(
    message: SearchRequestedMessage,
    *,
    analyzer: AnalyzerProtocol,
    plan_builder: PlanBuilderProtocol,
    plan_cache: PlanCacheProtocol,
    probe_fetcher: SearchProbeFetcher,
    policy: SearchProbePolicy,
    executor: PlanExecutorProtocol,
    publisher: URLMessagePublisher,
) -> V2PipelineResult:
    """Run the complete v2 cache→analyze→probe→build→execute→publish pipeline."""

    read = plan_cache.get(target_url=message.target_url)
    if read.hit and read.plan is not None and read.plan.status in _EXECUTABLE_STATUSES:
        result = _run_keyword_hits(
            message,
            read.plan,
            executor=executor,
            fetcher=probe_fetcher,
            policy=policy,
            publisher=publisher,
        )
        if result.status == STATUS_FAILED and result.error_code != "publish_failure":
            try:
                plan_cache.delete(target_url=message.target_url)
            except Exception as exc:
                log.warning(
                    "search_plan_cache_delete_failed task_id=%s target_host=%s error_type=%s",
                    message.task_id,
                    _safe_hostname(message.target_url),
                    type(exc).__name__,
                )
        return result

    try:
        analysis = analyzer.analyze(message.target_url)
    except Exception:
        return V2PipelineResult(STATUS_FAILED, None, 0, "analysis_failed")
    candidates = tuple(getattr(analysis, "candidates", ()) or ())
    if not candidates:
        return V2PipelineResult(STATUS_FAILED, None, 0, "no_candidate")

    for candidate in candidates[: policy.max_candidates]:
        probe: SearchProbeResult = probe_search_candidate(
            candidate,
            tuple(message.keywords),
            fetcher=probe_fetcher,
            policy=policy,
        )
        if probe.status != "success" or probe.selector_evidence is None:
            continue

        built = plan_builder.build(
            target_url=message.target_url,
            candidates=(candidate,),
            selector_evidence=probe.selector_evidence,
        )
        if not built.success or built.plan is None:
            continue
        if built.plan.status not in _EXECUTABLE_STATUSES:
            continue

        return _run_keyword_hits(
            message,
            built.plan,
            executor=executor,
            fetcher=probe_fetcher,
            policy=policy,
            publisher=publisher,
            cache=plan_cache,
        )

    return V2PipelineResult(STATUS_FAILED, None, 0, "no_executable_plan")


def default_v2_components(redis_client, *, ttl_seconds: int = 86400):
    """Build production components used by run_worker without creating a second client."""
    from crawler.site.analyzer import SiteAnalyzer

    return {
        "analyzer": SiteAnalyzer(),
        "plan_builder": PlanBuilder(),
        "plan_cache": SearchPlanCache(redis_client, ttl_seconds=ttl_seconds),
        "probe_fetcher": PinnedProbeFetcher(),
        "policy": SearchProbePolicy(),
        "executor": RegistryPlanExecutor(build_default_adapter_registry()),
        "publisher": RedisURLMessagePublisher(redis_client),
    }
