"""Isolated secure HTTP executor for TASK-022D-3.

The executor combines pinned addressing, policy, redirect planning, runtime
budgets, and the shared concurrency limiter. It does not use requests/httpx
and never follows redirects automatically.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from crawler.security.bounded_io import BoundedIOError
from crawler.security.concurrency_limiter import ConcurrencyError, ConcurrencyLimiter
from crawler.security.http_transport import (
    SecureHTTPError,
    SecureHTTPRequest,
    SecureHTTPResponse,
    build_request_bytes,
    read_raw_response,
    validate_request,
)
from crawler.security.outbound_policy import decide
from crawler.security.pinned_connection import PinnedConnectionError, build_pinned_target, connect_pinned
from crawler.security.redirect_policy import RedirectPolicyError, plan_redirect_hop
from crawler.security.tls_policy import TLSPolicyError, secure_ssl_context, wrap_client_socket
from crawler.security.transport_budget import BUDGET, BudgetError, budget_for, remaining_deadline

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_SENSITIVE_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie"})


class SecureHTTPExecutor:
    def __init__(
        self,
        policy,
        resolver,
        limiter: ConcurrencyLimiter,
        profile: str,
        *,
        socket_factory: Callable[[int, int], Any] | None = None,
    ):
        if limiter is None:
            raise ValueError("limiter is required")
        self.policy = policy
        self.resolver = resolver
        self.limiter = limiter
        self.profile = profile
        self.socket_factory = socket_factory
        budget_for(profile)

    def execute(self, request: SecureHTTPRequest) -> SecureHTTPResponse:
        validate_request(request)
        start_ms = int(time.monotonic() * 1000)
        current_url = request.url
        current_normalized = request.url
        headers = request.headers
        body = request.body
        hops = 0
        previous_host: str | None = None

        for hop_count in range(1, BUDGET.max_redirects + 2):
            if hop_count == 1:
                decision = decide(current_url, self.policy, resolver=self.resolver)
                if not decision.allowed:
                    raise SecureHTTPError(decision.reason_code)
                current_normalized = decision.normalized.normalized_url
                target = build_pinned_target(decision, self.policy)
            else:
                try:
                    hop = plan_redirect_hop(
                        current_normalized,
                        current_url,
                        self.policy,
                        resolver=self.resolver,
                        hop_count=hop_count - 1,
                    )
                except RedirectPolicyError as exc:
                    raise SecureHTTPError(exc.reason_code) from exc
                if previous_host is not None and hop.pinned_target.normalized_host != previous_host:
                    headers = _strip_sensitive(headers)
                current_normalized = hop.url
                target = hop.pinned_target
                hops += 1

            current_host = target.normalized_host
            remaining = self._remaining(start_ms)
            try:
                lease = self.limiter.acquire(target.normalized_host)
            except ConcurrencyError as exc:
                raise SecureHTTPError(exc.reason_code) from exc
            conn = None
            try:
                connect_timeout = min(BUDGET.connect_timeout_ms, remaining)
                conn = connect_pinned(
                    target,
                    socket_factory=self.socket_factory,
                    timeout=connect_timeout / 1000.0,
                )
                if target.scheme == "https":
                    tls_remaining = self._remaining(start_ms)
                    tls_timeout = min(BUDGET.tls_timeout_ms, tls_remaining)
                    conn.settimeout(tls_timeout / 1000.0)
                    context = secure_ssl_context()
                    conn = wrap_client_socket(context, conn, target.server_name)
                request_bytes = build_request_bytes(
                    SecureHTTPRequest(
                        profile=self.profile,
                        method=request.method,
                        url=current_normalized,
                        headers=headers,
                        body=body,
                    ),
                    target.host_header,
                )
                write_remaining = self._remaining(start_ms)
                conn.settimeout(min(BUDGET.response_header_timeout_ms, write_remaining) / 1000.0)
                conn.sendall(request_bytes)
                read_remaining = self._remaining(start_ms)
                status, response_headers, response_body = read_raw_response(
                    conn,
                    request.method,
                    self.profile,
                    start_ms,
                    read_remaining,
                    _clock,
                )
                if status in _REDIRECT_STATUSES:
                    location = ""
                    for name, value in response_headers:
                        if name.lower() == "location":
                            location = value
                    if not location:
                        raise SecureHTTPError("redirect_location_missing")
                    if request.method == "POST":
                        raise SecureHTTPError("redirect_body_replay_not_allowed")
                    previous_host = current_host
                    current_url = location
                    continue
                return SecureHTTPResponse(
                    status_code=status,
                    final_url=current_normalized,
                    headers=response_headers,
                    body=response_body,
                    redirect_hops=hops,
                )
            except (SecureHTTPError, BoundedIOError, PinnedConnectionError, TLSPolicyError, BudgetError) as exc:
                raise SecureHTTPError(getattr(exc, "reason_code", "transport_failed")) from exc
            except TimeoutError as exc:
                raise SecureHTTPError("timeout") from exc
            except OSError as exc:
                raise SecureHTTPError("transport_failed") from exc
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
                lease.release()
        raise SecureHTTPError("redirect_limit_exceeded")

    def _remaining(self, start_ms: int) -> int:
        elapsed = int(time.monotonic() * 1000) - start_ms
        try:
            remaining = remaining_deadline(self.profile, elapsed)
        except BudgetError as exc:
            raise SecureHTTPError(exc.reason_code) from exc
        if remaining <= 0:
            raise SecureHTTPError("total_timeout_exceeded")
        return remaining


def _strip_sensitive(headers: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    return tuple(
        (name, value)
        for name, value in headers
        if name.lower() not in _SENSITIVE_HEADERS
    )


def _clock() -> int:
    return int(time.monotonic() * 1000)
