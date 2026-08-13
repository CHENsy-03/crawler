"""Execute a validated SearchPlan v2 through the unified SearchAdapter layer."""

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
from crawler.search.generic_json_adapter import GenericJSONSearchAdapter
from crawler.search.html_adapter import HTMLSearchAdapter
from crawler.search.jpaas_adapter import JPAASSearchAdapter
from crawler.search.trs_adapter import TRSSearchAdapter
from crawler.search.search_plan import (
    ADAPTER_GENERIC_JSON,
    ADAPTER_HTML,
    ADAPTER_JPAAS,
    ADAPTER_TRS,
    PLAN_STATUS_ACTIVE,
    PLAN_STATUS_READY,
    ProtocolError,
    SearchPlan,
    compute_plan_id,
    validate_search_plan,
)
from crawler.site.search_probe import SearchProbeFetcher, SearchProbePolicy

ALLOWED_STATUSES = {PLAN_STATUS_READY, PLAN_STATUS_ACTIVE}


def execute_search_plan(
    plan: SearchPlan,
    keywords: tuple[str, ...],
    *,
    fetcher: SearchProbeFetcher,
    policy: SearchProbePolicy,
) -> SearchPlanExecutionResult:
    """Dispatch a validated plan to the formal adapter selected by plan.adapter."""
    if plan.status not in ALLOWED_STATUSES:
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_NOT_EXECUTABLE, False, "plan_status")
    try:
        validate_search_plan(plan)
    except ProtocolError:
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "plan_validation")
    if plan.plan_id != compute_plan_id(plan):
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "plan_validation")
    if not keywords:
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_NOT_EXECUTABLE, False, "plan_validation")

    if plan.adapter == ADAPTER_HTML:
        return HTMLSearchAdapter().execute(plan, keywords, fetcher=fetcher, policy=policy)
    if plan.adapter == ADAPTER_TRS:
        return TRSSearchAdapter().execute(plan, keywords, fetcher=fetcher, policy=policy)
    if plan.adapter == ADAPTER_JPAAS:
        return JPAASSearchAdapter().execute(plan, keywords, fetcher=fetcher, policy=policy)
    if plan.adapter == ADAPTER_GENERIC_JSON:
        return GenericJSONSearchAdapter().execute(plan, keywords, fetcher=fetcher, policy=policy)
    return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "plan_validation")