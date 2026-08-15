"""Fail-fast process-wide concurrency limiter for TASK-022D-2.

The limiter reads global/per-host limits from the sealed D1
TransportBudget. It never creates waiting queues or sockets.
"""

from __future__ import annotations

import ipaddress
import threading
import unicodedata
from dataclasses import dataclass

from crawler.security.transport_budget import BUDGET

_MAX_HOSTNAME_OCTETS = 253
_MAX_LABEL_OCTETS = 63


class ConcurrencyError(ValueError):
    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(message or reason_code)
        self.reason_code = reason_code


def _invalid_host() -> None:
    raise ConcurrencyError("invalid_host_key")


def _canonical_ipv4(host: str) -> str | None:
    parts = host.split(".")
    if len(parts) != 4:
        return None
    numeric = []
    for part in parts:
        if not part.isascii() or not part.isdigit():
            return None
        if len(part) > 1 and part.startswith("0"):
            return None
        if len(part) > 3:
            return None
        value = int(part)
        if value > 255:
            return None
        numeric.append(str(value))
    return ".".join(numeric)


def _normalize_host(host: str) -> str:
    if not isinstance(host, str) or not host:
        _invalid_host()
    if not host.isascii():
        _invalid_host()
    if host != host.strip() or any(unicodedata.category(ch) in ("Cc", "Cf") for ch in host):
        _invalid_host()
    if any(ch in host for ch in "@/?#\\"):
        _invalid_host()

    normalized = host.lower()
    if ":" in normalized:
        if normalized.startswith("[") or "%" in normalized:
            _invalid_host()
        try:
            return ipaddress.ip_address(normalized).compressed
        except ValueError:
            _invalid_host()

    if "." in normalized:
        parts = normalized.split(".")
        if len(parts) == 4 and all(part.isascii() and part.isdigit() for part in parts):
            canonical = _canonical_ipv4(normalized)
            if canonical is None:
                _invalid_host()
            return canonical

    if normalized.endswith("."):
        normalized = normalized[:-1]
        if not normalized or normalized.endswith("."):
            _invalid_host()

    labels = normalized.split(".")
    if any(not label for label in labels):
        _invalid_host()
    if any(len(label) > _MAX_LABEL_OCTETS for label in labels):
        _invalid_host()
    if len(normalized) > _MAX_HOSTNAME_OCTETS:
        _invalid_host()
    for label in labels:
        if not label[0].isalnum() or not label[-1].isalnum():
            _invalid_host()
        if any(not (ch.isascii() and (ch.isalnum() or ch == "-")) for ch in label):
            _invalid_host()
    return normalized


class Lease:
    __slots__ = ("_owner",)

    def __init__(self, *args, **kwargs):
        raise TypeError("Lease must be created through ConcurrencyLimiter.acquire")

    def _activate(self, limiter: "ConcurrencyLimiter") -> None:
        object.__setattr__(self, "_owner", limiter)

    def release(self) -> bool:
        owner = self._owner
        if type(owner) is not ConcurrencyLimiter:
            return False
        return owner._release_lease(self)

    def __enter__(self) -> "Lease":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.release()
        return False

    def __copy__(self):
        raise TypeError("Lease cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("Lease cannot be copied")

    def __reduce_ex__(self, protocol):
        raise TypeError("Lease cannot be pickled")


@dataclass(slots=True)
class _LeaseEntry:
    lease: Lease
    host: str


class ConcurrencyLimiter:
    def __init__(self) -> None:
        self._global_limit = BUDGET.global_active
        self._per_host_limit = BUDGET.per_host_active
        self._active = 0
        self._host_counts: dict[str, int] = {}
        self._issued: dict[int, _LeaseEntry] = {}
        self._lock = threading.Lock()

    def acquire(self, host: str) -> Lease:
        key = _normalize_host(host)
        with self._lock:
            if self._active >= self._global_limit:
                raise ConcurrencyError("global_concurrency_exceeded")
            if self._host_counts.get(key, 0) >= self._per_host_limit:
                raise ConcurrencyError("host_concurrency_exceeded")
            self._active += 1
            self._host_counts[key] = self._host_counts.get(key, 0) + 1
            lease = object.__new__(Lease)
            lease._activate(self)
            self._issued[id(lease)] = _LeaseEntry(lease=lease, host=key)
            return lease

    def _release_lease(self, lease: Lease) -> bool:
        with self._lock:
            if type(lease) is not Lease:
                return False
            if getattr(lease, "_owner", None) is not self:
                return False
            entry = self._issued.get(id(lease))
            if entry is None or entry.lease is not lease:
                return False
            host = entry.host
            if self._active <= 0 or self._host_counts.get(host, 0) <= 0:
                return False
            self._issued.pop(id(lease), None)
            self._active -= 1
            count = self._host_counts.get(host, 0) - 1
            if count <= 0:
                self._host_counts.pop(host, None)
            else:
                self._host_counts[host] = count
            return True

    def active_count(self) -> int:
        with self._lock:
            return self._active

    def host_count(self, host: str) -> int:
        key = _normalize_host(host)
        with self._lock:
            return self._host_counts.get(key, 0)

    def issued_count(self) -> int:
        with self._lock:
            return len(self._issued)
