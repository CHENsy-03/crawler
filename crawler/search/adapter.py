"""SearchAdapter protocol used by the unified execution layer."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


def path_allowed(path: str, prefixes: Sequence[str]) -> bool:
    if not prefixes:
        return True
    for prefix in prefixes:
        if not prefix:
            continue
        if prefix == "/" or path == prefix:
            return True
        if path.startswith(prefix.rstrip("/") + "/"):
            return True
    return False


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