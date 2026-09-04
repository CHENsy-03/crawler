"""Pure outbound policy decisions for TASK-022B."""

from __future__ import annotations

from crawler.security.dns_policy import DNSValidationError, Resolver, resolve_and_validate
from crawler.security.models import DNSValidationResult, NormalizedURL, OutboundPolicy, PolicyDecision
from crawler.security.url_normalizer import URLNormalizationError, normalize_outbound_url


def default_policy() -> OutboundPolicy:
    return OutboundPolicy.default()


def _pre_dns_decision(
    normalized: NormalizedURL,
    policy: OutboundPolicy,
    previous: NormalizedURL | None = None,
) -> PolicyDecision | None:
    if normalized.scheme not in ("http", "https"):
        return PolicyDecision(False, "scheme_not_allowed", normalized, ())
    if normalized.scheme == "http" and not policy.allowed_http:
        return PolicyDecision(False, "http_not_allowed", normalized, ())

    allowed_hosts = {host.lower() for host in policy.allowed_hosts}
    if previous is None:
        if normalized.host not in allowed_hosts:
            return PolicyDecision(False, "host_not_allowed", normalized, ())
    else:
        if normalized.host not in allowed_hosts:
            return PolicyDecision(False, "redirect_host_not_allowed", normalized, ())

    allowed_ports = set(policy.allowed_ports_by_scheme.get(normalized.scheme, frozenset()))
    if normalized.port not in allowed_ports:
        return PolicyDecision(False, "port_not_allowed", normalized, ())

    if previous is not None and previous.scheme == "https" and normalized.scheme == "http":
        return PolicyDecision(False, "https_downgrade", normalized, ())
    return None


def _post_dns_decision(
    normalized: NormalizedURL,
    dns: DNSValidationResult,
    policy: OutboundPolicy,
) -> PolicyDecision:
    if not dns.allowed:
        return PolicyDecision(False, dns.reason_code or "ip_not_allowed", normalized, dns.addresses)
    return PolicyDecision(True, "", normalized, dns.addresses)


def evaluate(
    normalized: NormalizedURL,
    dns: DNSValidationResult,
    policy: OutboundPolicy,
    previous: NormalizedURL | None = None,
) -> PolicyDecision:
    pre = _pre_dns_decision(normalized, policy, previous=previous)
    if pre is not None:
        return pre
    return _post_dns_decision(normalized, dns, policy)


def decide(
    raw_url: str,
    policy: OutboundPolicy,
    *,
    resolver: Resolver | None = None,
    timeout_seconds: float = 5.0,
    previous_raw: str | None = None,
) -> PolicyDecision:
    try:
        normalized = normalize_outbound_url(raw_url)
    except URLNormalizationError as exc:
        return PolicyDecision(False, exc.reason_code, None, ())

    previous: NormalizedURL | None = None
    if previous_raw is not None:
        try:
            previous = normalize_outbound_url(previous_raw)
        except URLNormalizationError as exc:
            return PolicyDecision(False, exc.reason_code, None, ())

    pre = _pre_dns_decision(normalized, policy, previous=previous)
    if pre is not None:
        return pre

    if resolver is None and not normalized.is_ip_literal:
        raise ValueError("resolver is required for hostname URLs")
    try:
        dns = resolve_and_validate(normalized.host, resolver, timeout_seconds=timeout_seconds)
    except DNSValidationError as exc:
        return PolicyDecision(False, exc.reason_code, normalized, ())

    return _post_dns_decision(normalized, dns, policy)
