"""Execute a validated SearchPlan v2 through an injected AdapterRegistry."""

from crawler.search.adapter_composition import build_default_adapter_registry
from crawler.search.adapter_registry import AdapterRegistry
from crawler.search.execution_models import (
    EXECUTION_OK,
    FAILURE_INVALID_RESULT_URL,
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
    PLAN_STATUS_ACTIVE,
    PLAN_STATUS_READY,
    ProtocolError,
    SearchPlan,
    compute_plan_id,
    validate_search_plan,
)
from crawler.site.search_probe import SearchProbeFetcher, SearchProbePolicy

ALLOWED_STATUSES = {PLAN_STATUS_READY, PLAN_STATUS_ACTIVE}


class RegistryPlanExecutor:
    """Callable executor that resolves only through an injected registry."""

    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry

    def __call__(
        self,
        plan: SearchPlan,
        query_term: str,
        *,
        fetcher: SearchProbeFetcher,
        policy: SearchProbePolicy,
    ) -> SearchPlanExecutionResult:
        return execute_plan_with_registry(
            plan,
            query_term,
            registry=self._registry,
            fetcher=fetcher,
            policy=policy,
        )


def execute_plan_with_registry(
    plan: SearchPlan,
    query_term: str,
    *,
    registry: AdapterRegistry,
    fetcher: SearchProbeFetcher,
    policy: SearchProbePolicy,
) -> SearchPlanExecutionResult:
    if plan.status not in ALLOWED_STATUSES:
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_NOT_EXECUTABLE, False, "plan_status")
    try:
        validate_search_plan(plan)
    except ProtocolError:
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "plan_validation")
    if plan.plan_id != compute_plan_id(plan):
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "plan_validation")
    if not isinstance(query_term, str) or not query_term:
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_NOT_EXECUTABLE, False, "plan_validation")

    resolution = registry.resolve_plan(plan)
    if not resolution.found or resolution.adapter is None:
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "registry")
    return resolution.adapter.execute(plan, query_term, fetcher=fetcher, policy=policy)


def execute_search_plan(
    plan: SearchPlan,
    query_term: str,
    *,
    fetcher: SearchProbeFetcher,
    policy: SearchProbePolicy,
) -> SearchPlanExecutionResult:
    """Default production executor backed by a fresh default registry."""
    return execute_plan_with_registry(
        plan,
        query_term,
        registry=build_default_adapter_registry(),
        fetcher=fetcher,
        policy=policy,
    )
