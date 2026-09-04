"""Explicit special-purpose IP classification for TASK-022B."""

from __future__ import annotations

import ipaddress
from typing import Tuple

from crawler.security.models import IPClassification

# Order is stable and cross-language identical. More-specific prefixes are
# checked first; category is resolved from the first matching range.
_IPV4_TABLE: Tuple[Tuple[str, str], ...] = (
    ("0.0.0.0/8", "protocol"),
    ("10.0.0.0/8", "private"),
    ("100.64.0.0/10", "shared"),
    ("127.0.0.0/8", "loopback"),
    ("169.254.0.0/16", "link_local"),
    ("172.16.0.0/12", "private"),
    ("192.0.0.0/24", "protocol"),
    ("192.0.2.0/24", "documentation"),
    ("192.168.0.0/16", "private"),
    ("198.18.0.0/15", "benchmark"),
    ("198.51.100.0/24", "documentation"),
    ("203.0.113.0/24", "documentation"),
    ("224.0.0.0/4", "multicast"),
    ("240.0.0.0/4", "reserved"),
    ("255.255.255.255/32", "reserved"),
)

_IPV6_TABLE: Tuple[Tuple[str, str], ...] = (
    ("::/128", "unspecified"),
    ("::1/128", "loopback"),
    ("::/96", "transition"),
    ("64:ff9b::/96", "transition"),
    ("64:ff9b:1::/48", "transition"),
    ("100::/64", "reserved"),
    ("2001::/32", "transition"),
    ("2001:2::/48", "benchmark"),
    ("2001:db8::/32", "documentation"),
    ("2001::/23", "reserved"),
    ("2002::/16", "transition"),
    ("3fff::/20", "documentation"),
    ("fc00::/7", "private"),
    ("fe80::/10", "link_local"),
    ("fec0::/10", "reserved"),
    ("ff00::/8", "multicast"),
)

_NETWORKS: Tuple[Tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, str], ...] = tuple(
    sorted(
        [(ipaddress.ip_network(cidr), category) for cidr, category in _IPV4_TABLE + _IPV6_TABLE],
        key=lambda item: item[0].prefixlen,
        reverse=True,
    )
)


def classify_ip(address: str) -> IPClassification:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        raise ValueError(f"invalid IP address: {address!r}")

    version = ip.version
    canonical = ip.compressed
    if ip.version == 6 and ip.ipv4_mapped is not None:
        return IPClassification(
            address=canonical,
            version=6,
            category="mapped_ipv4",
            allowed=False,
        )

    for network, category in _NETWORKS:
        if isinstance(network, ipaddress.IPv4Network) != (ip.version == 4):
            continue
        if ip in network:
            return IPClassification(
                address=canonical,
                version=version,
                category=category,
                allowed=category == "global",
            )

    return IPClassification(
        address=canonical,
        version=version,
        category="global",
        allowed=True,
    )
