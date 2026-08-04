"""Request-before security policy for discovery."""

import ipaddress
import socket
from urllib.parse import urlsplit

from crawler.site.models import Diagnostic


class SecurityPolicyError(ValueError):
    code = "TARGET_BLOCKED_BY_POLICY"


def classify_ip(ip_text: str) -> tuple[bool, str]:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False, "invalid_ip"
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped

    reasons = []
    checks = [
        ("loopback", ip.is_loopback),
        ("private", ip.is_private),
        ("link_local", ip.is_link_local),
        ("multicast", ip.is_multicast),
        ("unspecified", ip.is_unspecified),
        ("reserved", ip.is_reserved),
        ("site_local", bool(getattr(ip, "is_site_local", False))),
    ]
    for name, flag in checks:
        if flag:
            reasons.append(name)
    if str(ip) == "169.254.169.254":
        reasons.append("metadata")
    return (True, "") if not reasons else (False, ",".join(reasons))


def is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def resolve_host(host: str, resolver=None) -> list[str]:
    if resolver is not None:
        return list(resolver(host))
    return [addr[4][0] for addr in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)]


def security_check(url: str, resolver=None) -> tuple[bool, list[str], str]:
    host = urlsplit(url).hostname or ""
    if not host:
        raise SecurityPolicyError("target_url must include a host")
    ips = [host] if is_ip_literal(host) else resolve_host(host, resolver)
    if not ips:
        raise SecurityPolicyError("target_url has no resolvable addresses")
    for ip in ips:
        safe, reason = classify_ip(ip)
        if not safe:
            return False, ips, reason
    return True, ips, ""


def blocked_diagnostic(url: str, reason: str) -> Diagnostic:
    return Diagnostic(
        code="TARGET_BLOCKED_BY_POLICY",
        stage="security",
        message=f"target blocked by discovery policy: {reason}",
        details=(url,),
    )
