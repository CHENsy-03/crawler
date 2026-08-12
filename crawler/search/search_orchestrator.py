"""Production orchestration for v2 SearchPlan generation, execution and publishing."""

import json
from dataclasses import dataclass
from typing import Protocol

from protocol.messages import SearchRequestedMessage, URLMessage

from crawler.search.plan_builder import PlanBuildResult, PlanBuilder
from crawler.search.plan_cache import (
    PlanCacheReadResult,
    PlanCacheWriteResult,
    SearchPlanCache,
)
from crawler.search.plan_executor import (
    FAILURE_NO_RESULTS,
    SearchPlanExecutionResult,
    execute_search_plan,
)
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
        keywords: tuple[str, ...],
        *,
        fetcher: SearchProbeFetcher,
        policy: SearchProbePolicy,
    ) -> SearchPlanExecutionResult:
        ...


class URLMessagePublisher(Protocol):
    def publish(self, message: URLMessage) -> None:
        ...


class RedisURLMessagePublisher:
    """Publish formal URLMessage objects to the existing crawler:url list."""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def publish(self, message: URLMessage) -> None:
        payload = json.dumps(message.to_dict(), ensure_ascii=False)
        self._redis.lpush("crawler:url", payload)


def _candidate_key(candidate: SearchCandidate) -> tuple[str, ...]:
    return (
        candidate.method,
        candidate.endpoint,
        candidate.keyword_param,
        tuple(sorted(candidate.fixed_params)),
    )


def _publish_execution(
    message: SearchRequestedMessage,
    plan: SearchPlan,
    execution: SearchPlanExecutionResult,
    publisher: URLMessagePublisher,
) -> V2PipelineResult:
    if execution.failure_code == FAILURE_NO_RESULTS:
        return V2PipelineResult(STATUS_NO_RESULTS, plan.plan_id, 0, FAILURE_NO_RESULTS)
    if not execution.success:
        return V2PipelineResult(
            STATUS_FAILED,
            plan.plan_id,
            0,
            execution.failure_code or "execution_failed",
        )
    if not execution.items:
        return V2PipelineResult(STATUS_NO_RESULTS, plan.plan_id, 0, FAILURE_NO_RESULTS)

    published = 0
    keyword = message.keywords[0]
    for item in execution.items:
        url_message = URLMessage(
            protocol_version=message.protocol_version,
            task_id=message.task_id,
            message_id=message.message_id,
            timestamp=message.timestamp,
            url=item.url,
            site=plan.scope.domain,
            keyword=keyword,
            level=message.level,
            title=item.title,
        )
        try:
            publisher.publish(url_message)
        except Exception:
            return V2PipelineResult(
                STATUS_FAILED,
                plan.plan_id,
                published,
                "publish_failure",
            )
        published += 1
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
        execution = executor(
            read.plan,
            tuple(message.keywords),
            fetcher=probe_fetcher,
            policy=policy,
        )
        return _publish_execution(message, read.plan, execution, publisher)

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

        plan_cache.put(target_url=message.target_url, plan=built.plan)
        execution = executor(
            built.plan,
            tuple(message.keywords),
            fetcher=probe_fetcher,
            policy=policy,
        )
        return _publish_execution(message, built.plan, execution, publisher)

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
        "executor": execute_search_plan,
        "publisher": RedisURLMessagePublisher(redis_client),
    }
