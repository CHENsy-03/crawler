"""Fixed transport budget and proxy contract for TASK-022D-1.

This module is pure decision logic. It performs no I/O, does not read proxy
environment variables, and never creates sockets or DNS requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


class BudgetError(ValueError):
    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(message or reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class TransportBudget:
    dns_timeout_ms: int = 5000
    connect_timeout_ms: int = 5000
    tls_timeout_ms: int = 5000
    response_header_timeout_ms: int = 10000
    read_idle_timeout_ms: int = 15000
    request_body_bytes: int = 1048576
    response_headers_bytes: int = 262144
    max_redirects: int = 3
    global_active: int = 20
    per_host_active: int = 5
    per_host_idle: int = 2


@dataclass(frozen=True, slots=True)
class BudgetProfile:
    name: str
    total_timeout_ms: int
    response_body_bytes: int


BUDGET = TransportBudget()
PROFILES = MappingProxyType(
    {
        "probe": BudgetProfile("probe", 30000, 1048576),
        "search": BudgetProfile("search", 30000, 8388608),
        "detail": BudgetProfile("detail", 60000, 20971520),
    }
)
MAX_REDIRECTS = BUDGET.max_redirects


def _as_int(value: int, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BudgetError("invalid_budget_value")
    return value


def budget_for(profile: str) -> BudgetProfile:
    if profile not in PROFILES:
        raise BudgetError("unknown_profile")
    return PROFILES[profile]


def remaining_deadline(profile: str, elapsed_ms: int) -> int:
    selected = budget_for(profile)
    elapsed = _as_int(elapsed_ms, field="elapsed_ms")
    if elapsed < 0:
        raise BudgetError("negative_budget")
    if elapsed > selected.total_timeout_ms:
        raise BudgetError("total_timeout_exceeded")
    return selected.total_timeout_ms - elapsed


def capped_stage_timeout(profile: str, stage_timeout_ms: int, elapsed_ms: int) -> int:
    stage = _as_int(stage_timeout_ms, field="stage_timeout_ms")
    if stage <= 0:
        raise BudgetError("non_positive_budget")
    remaining = remaining_deadline(profile, elapsed_ms)
    if remaining == 0:
        raise BudgetError("total_timeout_exceeded")
    return min(stage, remaining)


def check_byte_limit(value: int, limit: int, *, reason_code: str) -> None:
    count = _as_int(value, field="value")
    if count < 0:
        raise BudgetError("negative_budget")
    if count > limit:
        raise BudgetError(reason_code)


def check_request_body_size(value: int) -> None:
    check_byte_limit(value, BUDGET.request_body_bytes, reason_code="request_body_limit")


def check_response_headers_size(value: int) -> None:
    check_byte_limit(value, BUDGET.response_headers_bytes, reason_code="response_headers_limit")


def check_response_body_size(profile: str, value: int) -> None:
    selected = budget_for(profile)
    check_byte_limit(value, selected.response_body_bytes, reason_code="response_body_limit")


def validate_proxy(proxy: str | None) -> None:
    if proxy is None or proxy == "":
        return
    raise BudgetError("proxy_not_allowed")
