"""Pure, network-free URL normalization for discovery."""

import ipaddress
import re
import idna
from urllib.parse import unquote_plus, urlsplit, urlunsplit


class SiteNormalizationError(ValueError):
    code = "INVALID_TARGET_URL"


def effective_port(scheme: str, port: int | None) -> int:
    if port is not None:
        return port
    return 80 if scheme == "http" else 443


def _is_ipv6_literal(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).version == 6
    except ValueError:
        return False


def normalized_origin(raw: str) -> tuple[str, str, int]:
    """Return (scheme, ascii hostname, effective port) for a normalized URL."""
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise SiteNormalizationError("origin must use http or https")
    if not parts.hostname:
        raise SiteNormalizationError("origin must include a host")
    host = parts.hostname.lower()
    try:
        host_ascii = idna.encode(host).decode("ascii") if not host.isascii() else host
    except Exception as exc:
        raise SiteNormalizationError("origin hostname is not valid IDN") from exc
    try:
        port = parts.port
    except ValueError as exc:
        raise SiteNormalizationError("origin has invalid port") from exc
    if port is not None and (port <= 0 or port > 65535):
        raise SiteNormalizationError("origin has invalid port")
    return scheme, host_ascii, effective_port(scheme, port)


def redirect_allowed(current: str, target: str) -> bool:
    """Allow identical origins or a same-host http->https upgrade."""
    current_origin = normalized_origin(current)
    target_origin = normalized_origin(target)
    if current_origin == target_origin:
        return True
    cs, ch, cp = current_origin
    ts, th, tp = target_origin
    return cs == "http" and ts == "https" and ch == th and cp == 80 and tp == 443


def same_origin(a: str, b: str) -> bool:
    return normalized_origin(a) == normalized_origin(b)


def normalize_target_url(raw: str) -> str:
    if not isinstance(raw, str):
        raise SiteNormalizationError("target_url must be a string")
    if raw != raw.strip():
        raise SiteNormalizationError("target_url must not have leading or trailing whitespace")
    if any(ch.isspace() or ord(ch) < 32 for ch in raw):
        raise SiteNormalizationError("target_url must not contain whitespace or control characters")

    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise SiteNormalizationError("target_url has invalid authority") from exc

    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise SiteNormalizationError("target_url must use http or https")
    if parts.netloc.endswith(':'):
        raise SiteNormalizationError("target_url must not have an empty port")
    if parts.username is not None or parts.password is not None:
        raise SiteNormalizationError("target_url must not contain userinfo")
    if not parts.hostname:
        raise SiteNormalizationError("target_url must include a host")

    host = parts.hostname.lower()
    try:
        host_ascii = idna.encode(host).decode("ascii") if not host.isascii() else host
    except Exception as exc:
        raise SiteNormalizationError("target_url hostname is not valid IDN") from exc

    try:
        port = parts.port
    except ValueError as exc:
        raise SiteNormalizationError("target_url has invalid port") from exc
    if port is not None and (port <= 0 or port > 65535):
        raise SiteNormalizationError("target_url has invalid port")

    host_for_netloc = f"[{host_ascii}]" if _is_ipv6_literal(host_ascii) else host_ascii
    netloc = host_for_netloc
    if (scheme == "http" and port not in (None, 80)) or (scheme == "https" and port not in (None, 443)):
        netloc = f"{host_for_netloc}:{port}"

    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))

SENSITIVE_NAME_RE = re.compile(
    r"(csrf|xsrf|token|session|auth|password|passwd|cookie|signature|secret|nonce|captcha|verify_code)",
    re.I,
)
SENSITIVE_QUERY_RE = re.compile(SENSITIVE_NAME_RE.pattern + r"|code", re.I)
EVIDENCE_REDACTION = "[REDACTED]"


def redact_evidence_url(raw: str) -> str:
    """Return a display-safe copy of a URL for evidence only.

    The real Candidate endpoint must remain untouched; callers use this
    helper only when building human-visible evidence strings.
    """
    if not isinstance(raw, str):
        return ""
    if not raw:
        return raw
    try:
        parts = urlsplit(raw)
        if not parts.query:
            return raw
        redacted_segments = []
        for segment in parts.query.split("&"):
            name_part = segment.partition("=")[0]
            if SENSITIVE_QUERY_RE.search(unquote_plus(name_part)):
                redacted_segments.append(f"{name_part}={EVIDENCE_REDACTION}")
            else:
                redacted_segments.append(segment)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(redacted_segments), parts.fragment))
    except Exception:
        try:
            parts = urlsplit(raw)
            return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
        except Exception:
            return ""
