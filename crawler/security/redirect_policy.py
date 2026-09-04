"""Redirect per-hop revalidation planner for TASK-022D-1.

The planner is pure decision logic: it resolves each Location, re-runs the
TASK-022B/C policy pipeline, and produces a fresh PinnedTarget for every hop.
It never performs network requests, DNS, redirect following, or body I/O.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Sequence
from urllib.parse import urljoin, urlsplit

from crawler.security.models import NormalizedURL, OutboundPolicy, PolicyDecision
from crawler.security.outbound_policy import decide
from crawler.security.pinned_connection import PinnedTarget, build_pinned_target
from crawler.security.transport_budget import MAX_REDIRECTS

_LOCATION_SYNTAX_REASONS = frozenset(
    {
        "absolute_url_required",
        "ambiguous_ip_literal",
        "authority_required",
        "backslash_not_allowed",
        "control_character",
        "empty_url",
        "host_too_long",
        "invalid_host",
        "invalid_idna",
        "invalid_percent_encoding",
        "invalid_port",
        "invalid_scheme",
        "invalid_url",
        "label_too_long",
        "scheme_not_allowed",
        "url_too_long",
    }
)


class RedirectPolicyError(ValueError):
    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(message or reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class RedirectHop:
    hop: int
    url: str
    normalized: NormalizedURL
    decision: PolicyDecision
    pinned_target: PinnedTarget
    addresses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RedirectPlan:
    hops: tuple[RedirectHop, ...]
    final_hop: RedirectHop | None


def _resolve_location(current_url: str, location: str) -> str:
    if location is None:
        raise RedirectPolicyError("redirect_location_missing")
    if not isinstance(location, str):
        raise RedirectPolicyError("redirect_location_invalid")
    if location == "":
        raise RedirectPolicyError("redirect_location_missing")
    if location.strip() == "":
        raise RedirectPolicyError("redirect_location_missing")
    if location != location.strip():
        raise RedirectPolicyError("redirect_location_invalid")
    if any(unicodedata.category(char) in ("Cc", "Cf") for char in location):
        raise RedirectPolicyError("redirect_location_invalid")
    try:
        if location.startswith("//"):
            current_scheme = urlsplit(current_url).scheme
            if current_scheme not in ("http", "https"):
                raise RedirectPolicyError("redirect_location_invalid")
            return f"{current_scheme}:{location}"
        if "://" in location:
            return location
        return urljoin(current_url, location)
    except RedirectPolicyError:
        raise
    except Exception:
        raise RedirectPolicyError("redirect_location_invalid")


def plan_redirect_hop(
    current_url: str,
    location: str,
    policy: OutboundPolicy,
    *,
    resolver,
    hop_count: int = 1,
) -> RedirectHop:
    if isinstance(hop_count, bool) or not isinstance(hop_count, int) or hop_count <= 0:
        raise RedirectPolicyError("invalid_redirect_hop")
    if hop_count > MAX_REDIRECTS:
        raise RedirectPolicyError("redirect_limit_exceeded")

    target_raw = _resolve_location(current_url, location)
    decision = decide(target_raw, policy, resolver=resolver, previous_raw=current_url)
    if not decision.allowed:
        reason = decision.reason_code
        if reason in _LOCATION_SYNTAX_REASONS:
            raise RedirectPolicyError("redirect_location_invalid")
        raise RedirectPolicyError(reason)

    normalized = decision.normalized
    assert normalized is not None
    pinned_target = build_pinned_target(decision, policy, policy_identity="redirect")
    return RedirectHop(
        hop=hop_count,
        url=normalized.normalized_url,
        normalized=normalized,
        decision=decision,
        pinned_target=pinned_target,
        addresses=tuple(decision.addresses),
    )


def plan_redirects(
    current_url: str,
    locations: Sequence[str],
    policy: OutboundPolicy,
    *,
    resolver,
) -> RedirectPlan:
    hops: list[RedirectHop] = []
    current = current_url
    for index, location in enumerate(locations, start=1):
        if index > MAX_REDIRECTS:
            raise RedirectPolicyError("redirect_limit_exceeded")
        hop = plan_redirect_hop(current, location, policy, resolver=resolver, hop_count=index)
        hops.append(hop)
        current = hop.url
    return RedirectPlan(tuple(hops), hops[-1] if hops else None)
