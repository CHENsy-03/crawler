"""Injectable DNS resolver and all-address validation for TASK-022B."""

from __future__ import annotations

import ipaddress
from typing import List, Protocol, Sequence

from crawler.security.ip_policy import classify_ip
from crawler.security.models import DNSValidationResult


class Resolver(Protocol):
    def resolve(self, host: str, timeout_seconds: float) -> List[str]:
        """Return all addresses for an ASCII hostname or raise."""
        ...


class DNSValidationError(ValueError):
    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(message or reason_code)
        self.reason_code = reason_code


def _stable_sort(addresses: Sequence[str]) -> List[str]:
    parsed = []
    seen = set()
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise DNSValidationError("invalid_dns_answer")
        canonical = str(ip)
        if canonical in seen:
            continue
        seen.add(canonical)
        parsed.append(ip)
    parsed.sort(key=lambda ip: (ip.version, ip.packed))
    return [str(ip) for ip in parsed]


def resolve_and_validate(
    host: str,
    resolver: Resolver,
    *,
    timeout_seconds: float = 5.0,
    max_addresses: int = 16,
) -> DNSValidationResult:
    if not host:
        raise DNSValidationError("invalid_host")

    try:
        ipaddress.ip_address(host)
        raw_addresses = [host]
    except ValueError:
        try:
            raw_addresses = list(resolver.resolve(host, timeout_seconds))
        except TimeoutError:
            raise DNSValidationError("dns_timeout")
        except Exception:
            raise DNSValidationError("dns_failed")

    addresses = _stable_sort(raw_addresses)
    if not addresses:
        raise DNSValidationError("dns_no_addresses")
    if len(addresses) > max_addresses:
        raise DNSValidationError("dns_too_many_addresses")

    for address in addresses:
        classification = classify_ip(address)
        if not classification.allowed:
            return DNSValidationResult(
                host=host,
                addresses=tuple(addresses),
                allowed=False,
                reason_code="ip_not_allowed",
            )

    return DNSValidationResult(
        host=host,
        addresses=tuple(addresses),
        allowed=True,
        reason_code="",
    )
