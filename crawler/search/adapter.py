"""SearchAdapter protocol used by the unified execution layer."""

from typing import Protocol, runtime_checkable

from crawler.search.execution_models import SearchPlanExecutionResult
from crawler.search.search_plan import SearchPlan
from crawler.site.search_probe import SearchProbeFetcher, SearchProbePolicy


@runtime_checkable
class SearchAdapter(Protocol):
    """Contract implemented by concrete adapters in later TASK-018 subtasks."""

    adapter_name: str

    def execute(
        self,
        plan: SearchPlan,
        keywords: tuple[str, ...],
        *,
        fetcher: SearchProbeFetcher,
        policy: SearchProbePolicy,
    ) -> SearchPlanExecutionResult:
        ...