"""Pure, network-free URL normalization for discovery."""

import idna
from urllib.parse import urlsplit, urlunsplit


class SiteNormalizationError(ValueError):
    code = "INVALID_TARGET_URL"


def effective_port(scheme: str, port: int | None) -> int:
    if port is not None:
        return port
    return 80 if scheme == "http" else 443


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

    netloc = host_ascii
    if (scheme == "http" and port not in (None, 80)) or (scheme == "https" and port not in (None, 443)):
        netloc = f"{netloc}:{port}"

    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))
