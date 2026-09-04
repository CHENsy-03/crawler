"""Immutable data models for TASK-022B outbound request security foundations."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Tuple


@dataclass(frozen=True)
class NormalizedURL:
    scheme: str
    host: str
    port: int
    explicit_port: bool
    authority: str
    normalized_url: str
    is_ip_literal: bool


@dataclass(frozen=True)
class IPClassification:
    address: str
    version: int
    category: str
    allowed: bool


@dataclass(frozen=True)
class DNSValidationResult:
    host: str
    addresses: Tuple[str, ...]
    allowed: bool
    reason_code: str


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason_code: str
    normalized: NormalizedURL | None
    addresses: Tuple[str, ...] = ()


@dataclass(frozen=True)
class OutboundPolicy:
    allowed_hosts: frozenset[str]
    allowed_http: bool
    allowed_ports_by_scheme: Mapping[str, frozenset[int]]
    max_dns_addresses: int = 16
    allow_controlled_subdomains: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_hosts", frozenset(self.allowed_hosts))
        object.__setattr__(
            self,
            "allowed_ports_by_scheme",
            MappingProxyType(
                {scheme: frozenset(ports) for scheme, ports in self.allowed_ports_by_scheme.items()}
            ),
        )

    @classmethod
    def default(cls) -> "OutboundPolicy":
        return cls(
            allowed_hosts=frozenset(),
            allowed_http=False,
            allowed_ports_by_scheme={"http": frozenset({80}), "https": frozenset({443})},
            max_dns_addresses=16,
            allow_controlled_subdomains=False,
        )
