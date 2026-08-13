"""Unified SearchPlan execution result models."""

from dataclasses import dataclass

EXECUTION_OK = "ok"
FAILURE_PLAN_INVALID = "plan_invalid"
FAILURE_PLAN_NOT_EXECUTABLE = "plan_not_executable"
FAILURE_TRANSPORT = "transport_failure"
FAILURE_RESPONSE_REJECTED = "response_rejected"
FAILURE_SELECTOR_MISMATCH = "selector_mismatch"
FAILURE_INVALID_RESULT_URL = "invalid_result_url"
FAILURE_NO_RESULTS = "no_results"


@dataclass(frozen=True)
class SearchResultItem:
    title: str
    url: str
    snippet: str = ""
    body: str = ""

    def __repr__(self) -> str:
        return f"SearchResultItem(url={self.url!r}, title_len={len(self.title)})"


@dataclass(frozen=True)
class SearchPlanExecutionResult:
    plan_id: str
    status: str
    items: tuple[SearchResultItem, ...]
    response_kind: str
    failure_code: str | None = None
    retryable: bool = False
    stage: str = ""

    @property
    def success(self) -> bool:
        return self.status == EXECUTION_OK and self.failure_code is None

    def __repr__(self) -> str:
        return (
            f"SearchPlanExecutionResult(status={self.status!r}, "
            f"items={len(self.items)}, failure={self.failure_code!r})"
        )