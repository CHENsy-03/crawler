"""Pure, network-free outbound URL normalization for TASK-022B."""

from __future__ import annotations

import ipaddress
import re
import string
import unicodedata

import idna

from crawler.security.models import NormalizedURL

MAX_URL_UTF8_BYTES = 8192
MAX_HOSTNAME_OCTETS = 253
MAX_LABEL_OCTETS = 63

_UNRESERVED = set(string.ascii_letters + string.digits + "-._~")
_HEX = set("0123456789abcdefABCDEF")
_NUMERIC_DOTTED = re.compile(r"^[0-9.]+$")
_HEX_IP = re.compile(r"^0[xX][0-9a-fA-F]+$")
_MIXED_HEX_IP = re.compile(r"^[0-9a-fA-F.xX]+$")
_IPV4_QUAD = re.compile(r"^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$")
_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):")


class URLNormalizationError(ValueError):
    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(message or reason_code)
        self.reason_code = reason_code


def _fail(reason_code: str) -> None:
    raise URLNormalizationError(reason_code)


def _reject_control_and_backslash(raw: str) -> None:
    for ch in raw:
        cat = unicodedata.category(ch)
        if cat in ("Cc", "Cf", "Zs", "Zl", "Zp") or ch.isspace():
            _fail("control_character")
        if ch == "\\":
            _fail("backslash_not_allowed")


def _parse_strict_ipv4(host: str) -> str | None:
    match = _IPV4_QUAD.fullmatch(host)
    if not match:
        return None
    parts = list(match.groups())
    if any(len(part) > 1 and part.startswith("0") for part in parts):
        return None
    values = [int(part) for part in parts]
    if any(value > 255 for value in values):
        return None
    return ".".join(str(value) for value in values)


def _looks_numeric_ambiguous(host: str) -> bool:
    if _NUMERIC_DOTTED.fullmatch(host):
        return True
    if _HEX_IP.fullmatch(host):
        return True
    if _MIXED_HEX_IP.fullmatch(host) and ("x" in host.lower()):
        return True
    return False


_UNICODE_LABEL_SEPARATORS = {".", "\u3002", "\uff0e", "\uff61"}


def _looks_like_unicode_numeric_host(value: str) -> bool:
    has_non_ascii_digit = False
    remaining = value[:-1] if value.endswith(".") else value
    for ch in remaining:
        if ch.isdecimal() and not ch.isascii():
            has_non_ascii_digit = True
        if ch.isdecimal() or ch in _UNICODE_LABEL_SEPARATORS:
            continue
        return False
    return has_non_ascii_digit and bool(remaining)


def _normalize_arabic_indic_digits(value: str) -> str:
    out: list[str] = []
    for ch in value:
        code = ord(ch)
        if 0x0660 <= code <= 0x0669:
            out.append(chr(ord("0") + code - 0x0660))
        elif 0x06F0 <= code <= 0x06F9:
            out.append(chr(ord("0") + code - 0x06F0))
        else:
            out.append(ch)
    return "".join(out)


def _parse_authority(authority: str) -> tuple[str, int | None]:
    if not authority:
        _fail("authority_required")
    if "@" in authority:
        _fail("userinfo_not_allowed")

    if authority.startswith("["):
        close = authority.find("]")
        if close < 0:
            _fail("invalid_url")
        host = authority[1:close]
        suffix = authority[close + 1 :]
        port: int | None = None
        if suffix:
            if not suffix.startswith(":") or len(suffix) == 1:
                _fail("invalid_port")
            port = _parse_port(suffix[1:])
        if not host:
            _fail("invalid_host")
        return host, port

    if "[" in authority or "]" in authority:
        _fail("invalid_host")
    colon = authority.rfind(":")
    if colon >= 0:
        if authority.count(":") > 1:
            _fail("invalid_host")
        host = authority[:colon]
        port = _parse_port(authority[colon + 1 :])
    else:
        host = authority
        port = None
    if not host:
        _fail("invalid_host")
    return host, port


def _parse_port(value: str) -> int:
    if not value or not re.fullmatch(r"[0-9]+", value):
        _fail("invalid_port")
    port = int(value)
    if port <= 0 or port > 65535:
        _fail("invalid_port")
    return port


def _parse_raw_url(raw: str) -> tuple[str, str, str, str]:
    match = _SCHEME_RE.match(raw)
    if not match:
        _fail("absolute_url_required")
    scheme = match.group(1).lower()
    if scheme not in ("http", "https"):
        _fail("scheme_not_allowed")
    rest = raw[match.end() :]
    if not rest.startswith("//"):
        _fail("absolute_url_required")
    rest = rest[2:]
    auth_end = len(rest)
    for marker in ("/", "?", "#"):
        pos = rest.find(marker)
        if pos >= 0 and pos < auth_end:
            auth_end = pos
    authority = rest[:auth_end]
    path_query = rest[auth_end:]
    if "#" in path_query:
        path_query = path_query[: path_query.index("#")]
    if "?" in path_query:
        path, query = path_query.split("?", 1)
    else:
        path, query = path_query, ""
    return scheme, authority, path, query


def _normalize_host(raw_authority: str, host: str) -> tuple[str, bool]:
    if not host:
        _fail("invalid_host")
    if "%" in host:
        _fail("invalid_host")

    if raw_authority.startswith("["):
        try:
            addr = ipaddress.IPv6Address(host)
        except ValueError:
            _fail("invalid_host")
        return addr.compressed, True

    strict_ipv4 = _parse_strict_ipv4(host)
    if strict_ipv4 is not None:
        return strict_ipv4, True

    if _looks_like_unicode_numeric_host(host):
        _fail("ambiguous_ip_literal")
    if _looks_numeric_ambiguous(host):
        _fail("ambiguous_ip_literal")

    root_dot = host.endswith(".")
    candidate = host[:-1] if root_dot else host
    if not candidate:
        _fail("invalid_host")
    if candidate.startswith(".") or ".." in candidate:
        _fail("invalid_host")
    if len(candidate.encode("utf-8")) > MAX_HOSTNAME_OCTETS:
        _fail("host_too_long")
    labels = candidate.split(".")
    if not labels or any(not label for label in labels):
        _fail("invalid_host")
    for label in labels:
        if len(label.encode("utf-8")) > MAX_LABEL_OCTETS:
            _fail("label_too_long")
    candidate = _normalize_arabic_indic_digits(candidate)
    try:
        ascii_host = idna.encode(candidate, uts46=True, std3_rules=True, transitional=False).decode("ascii").lower()
    except Exception:
        _fail("invalid_idna")
    if not ascii_host or len(ascii_host.encode("ascii")) > MAX_HOSTNAME_OCTETS:
        _fail("host_too_long")
    for label in ascii_host.split("."):
        if not label or len(label.encode("ascii")) > MAX_LABEL_OCTETS:
            _fail("label_too_long")
        if label.startswith("xn--"):
            try:
                decoded = idna.decode(label, uts46=True, std3_rules=True)
            except Exception:
                _fail("invalid_idna")
            if not any(ord(ch) > 127 for ch in decoded):
                _fail("invalid_idna")
    if _parse_strict_ipv4(ascii_host) is not None or _looks_numeric_ambiguous(ascii_host):
        _fail("ambiguous_ip_literal")
    return ascii_host, False


def _canonical_percent(value: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "%":
            if i + 2 >= len(value) or value[i + 1] not in _HEX or value[i + 2] not in _HEX:
                _fail("invalid_percent_encoding")
            code = int(value[i + 1 : i + 3], 16)
            if code < 0x20 or code == 0x7F:
                _fail("invalid_percent_encoding")
            char = chr(code)
            if char in _UNRESERVED:
                out.append(char)
            else:
                out.append("%" + value[i + 1 : i + 3].upper())
            i += 3
            continue
        if ch in _UNRESERVED:
            out.append(ch)
        elif ord(ch) < 128:
            if unicodedata.category(ch) in ("Cc", "Cf"):
                _fail("invalid_percent_encoding")
            out.append(ch)
        else:
            for byte in ch.encode("utf-8"):
                out.append("%" + format(byte, "02X"))
        i += 1
    return "".join(out)


def _remove_last_segment(output: str) -> str:
    idx = output.rfind("/")
    if idx < 0:
        return ""
    return output[:idx]


def _remove_dot_segments(path: str) -> str:
    remaining = path
    output = ""
    while remaining:
        if remaining.startswith("../"):
            remaining = remaining[3:]
        elif remaining.startswith("./"):
            remaining = remaining[2:]
        elif remaining.startswith("/./"):
            remaining = "/" + remaining[3:]
        elif remaining == "/.":
            remaining = "/"
        elif remaining.startswith("/../"):
            remaining = "/" + remaining[4:]
            output = _remove_last_segment(output)
        elif remaining == "/..":
            remaining = "/"
            output = _remove_last_segment(output)
        elif remaining in (".", ".."):
            remaining = ""
        else:
            if remaining.startswith("/"):
                next_slash = remaining.find("/", 1)
                if next_slash < 0:
                    output += remaining
                    remaining = ""
                else:
                    output += remaining[:next_slash]
                    remaining = remaining[next_slash:]
            else:
                next_slash = remaining.find("/")
                if next_slash < 0:
                    output += remaining
                    remaining = ""
                else:
                    output += remaining[:next_slash]
                    remaining = remaining[next_slash:]
    return output


def normalize_outbound_url(raw: str) -> NormalizedURL:
    if not isinstance(raw, str):
        _fail("invalid_url")
    if raw == "":
        _fail("empty_url")
    if len(raw.encode("utf-8")) > MAX_URL_UTF8_BYTES:
        _fail("url_too_long")
    _reject_control_and_backslash(raw)

    scheme, authority, path, query = _parse_raw_url(raw)
    if not authority:
        _fail("authority_required")
    host, raw_port = _parse_authority(authority)
    port = raw_port if raw_port is not None else (80 if scheme == "http" else 443)
    explicit_port = raw_port is not None

    host, is_ip_literal = _normalize_host(authority, host)
    host_for_authority = f"[{host}]" if is_ip_literal and ":" in host else host
    canonical_authority = host_for_authority
    default_port = 80 if scheme == "http" else 443
    if explicit_port and port != default_port:
        canonical_authority = f"{host_for_authority}:{port}"

    canonical_path = _canonical_percent(path)
    canonical_query = _canonical_percent(query)
    canonical_path = _remove_dot_segments(canonical_path)
    if not canonical_path:
        canonical_path = "/"

    normalized_url = scheme + "://" + canonical_authority + canonical_path
    if canonical_query:
        normalized_url += "?" + canonical_query
    if len(normalized_url.encode("utf-8")) > MAX_URL_UTF8_BYTES:
        _fail("url_too_long")

    return NormalizedURL(
        scheme=scheme,
        host=host,
        port=port,
        explicit_port=explicit_port,
        authority=canonical_authority,
        normalized_url=normalized_url,
        is_ip_literal=is_ip_literal,
    )
