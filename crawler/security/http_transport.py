"""Isolated secure HTTP/1.1 transport primitives for TASK-022D-3.

This module performs raw HTTP/1.1 framing over a pinned connection. It does
not use requests/httpx, does not read environment proxies, and never follows
redirects itself.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Sequence
from urllib.parse import urlsplit

from crawler.security.bounded_io import (
    BoundedIOError,
    read_bounded,
    validate_content_lengths,
)
from crawler.security.transport_budget import BUDGET, budget_for

_MAX_HEADER_BYTES = BUDGET.response_headers_bytes
_ALLOWED_METHODS = frozenset({"GET", "HEAD", "POST"})
_FORBIDDEN_HEADERS = frozenset(
    {"host", "transfer-encoding", "proxy-authorization", "connection", "content-length"}
)
_TOKEN_CHARS = frozenset("!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
_CHUNK_LINE_MAX = 8192


class SecureHTTPError(ValueError):
    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(message or reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class SecureHTTPRequest:
    profile: str
    method: str
    url: str
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes = b""


@dataclass(frozen=True, slots=True)
class SecureHTTPResponse:
    status_code: int
    final_url: str
    headers: tuple[tuple[str, str], ...]
    body: bytes
    redirect_hops: int


def _invalid_header(value: str) -> bool:
    return any(ch in value for ch in "\r\n\x00")


def _is_http_token(value: str) -> bool:
    return bool(value) and all(ch in _TOKEN_CHARS for ch in value)


def _trim_ows(value: bytes) -> bytes:
    return value.strip(b" \t")


def validate_request(request: SecureHTTPRequest) -> None:
    if request.method not in _ALLOWED_METHODS:
        raise SecureHTTPError("method_not_allowed")
    if not isinstance(request.body, bytes):
        raise SecureHTTPError("invalid_request_body")
    if request.method in ("GET", "HEAD") and request.body:
        raise SecureHTTPError("method_body_not_allowed")
    if request.body:
        from crawler.security.bounded_io import check_request_body_size

        check_request_body_size(len(request.body))
    for name, value in request.headers:
        if _invalid_header(name) or _invalid_header(value):
            raise SecureHTTPError("invalid_header")
        if not _is_http_token(name):
            raise SecureHTTPError("invalid_header")
        if name.lower() in _FORBIDDEN_HEADERS:
            raise SecureHTTPError("forbidden_header")


def build_request_bytes(request: SecureHTTPRequest, host_header: str) -> bytes:
    validate_request(request)
    parsed = urlsplit(request.url)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    lines = [f"{request.method} {path} HTTP/1.1", f"Host: {host_header}"]
    sent_encoding = False
    for name, value in request.headers:
        if name.lower() == "accept-encoding":
            sent_encoding = True
        lines.append(f"{name}: {value}")
    if not sent_encoding:
        lines.append("Accept-Encoding: identity")
    if request.method == "POST":
        lines.append(f"Content-Length: {len(request.body)}")
    lines.append("Connection: close")
    header_block = "\r\n".join(lines) + "\r\n\r\n"
    return header_block.encode("latin-1") + request.body


def _parse_status_and_headers(head: bytes) -> tuple[int, list[tuple[str, str]]]:
    lines = head.split(b"\r\n")
    first_line = lines[0]
    for byte in first_line:
        if byte < 0x20 and byte not in (0x09, 0x20):
            raise SecureHTTPError("invalid_http_response")
        if byte == 0x7f:
            raise SecureHTTPError("invalid_http_response")
    status_parts = first_line.split(b" ", 2)
    if len(status_parts) < 2:
        raise SecureHTTPError("invalid_http_response")
    if status_parts[0] not in (b"HTTP/1.0", b"HTTP/1.1"):
        raise SecureHTTPError("invalid_http_response")
    status_text = status_parts[1]
    if len(status_text) != 3 or not status_text.isdigit():
        raise SecureHTTPError("invalid_http_response")
    status = int(status_text)
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            raise SecureHTTPError("invalid_http_response")
        if line.startswith((b" ", b"\t")):
            raise SecureHTTPError("invalid_http_response")
        if b"\r" in line or b"\n" in line or b"\x00" in line:
            raise SecureHTTPError("invalid_http_response")
        name, sep, value = line.partition(b":")
        if not sep or not name:
            raise SecureHTTPError("invalid_http_response")
        name_text = name.decode("latin-1")
        if not _is_http_token(name_text):
            raise SecureHTTPError("invalid_http_response")
        value_text = _trim_ows(value).decode("latin-1")
        if "\x00" in value_text or "\r" in value_text or "\n" in value_text:
            raise SecureHTTPError("invalid_http_response")
        headers.append((name_text, value_text))
    return status, headers


def _read_response_headers(conn: Any, timeout_ms: int) -> tuple[int, list[tuple[str, str]], bytes]:
    conn.settimeout(timeout_ms / 1000.0)
    pending = bytearray()
    used = 0
    try:
        while True:
            delimiter = pending.find(b"\r\n\r\n")
            if delimiter >= 0:
                head_end = delimiter + 4
                total = used + head_end
                if total > _MAX_HEADER_BYTES:
                    raise SecureHTTPError("response_headers_too_large")
                status, headers = _parse_status_and_headers(bytes(pending[:delimiter]))
                del pending[:head_end]
                used = total
                if status == 101:
                    raise SecureHTTPError("protocol_upgrade_not_allowed")
                if 100 <= status <= 199:
                    continue
                if not (200 <= status <= 599):
                    raise SecureHTTPError("invalid_http_response")
                return status, headers, bytes(pending)
            if used + len(pending) >= _MAX_HEADER_BYTES:
                raise SecureHTTPError("response_headers_too_large")
            chunk = conn.recv(4096)
            if not chunk:
                raise SecureHTTPError("connection_failed")
            pending.extend(chunk)
    except TimeoutError as exc:
        raise SecureHTTPError("response_header_timeout") from exc
    raise SecureHTTPError("connection_failed")


class _SocketTimedReader:
    deadline_capable = True

    def __init__(self, conn: Any, start_ms: int, total_ms: int, clock, pending: bytes = b""):
        self.conn = conn
        self.start_ms = start_ms
        self.total_ms = total_ms
        self.clock = clock
        self.pending = pending

    def read(self, max_bytes: int, timeout_ms: int) -> bytes:
        if self.pending:
            out = self.pending[:max_bytes]
            self.pending = self.pending[max_bytes:]
            return out
        now = self.clock()
        if now - self.start_ms >= self.total_ms:
            raise BoundedIOError("total_timeout_exceeded")
        remaining = self.total_ms - (now - self.start_ms)
        read_timeout = min(timeout_ms, remaining)
        self.conn.settimeout(max(1, read_timeout) / 1000.0)
        try:
            data = self.conn.recv(max_bytes)
        except TimeoutError:
            now2 = self.clock()
            if now2 - self.start_ms >= self.total_ms:
                raise BoundedIOError("total_timeout_exceeded")
            raise TimeoutError()
        if not data:
            return b""
        return data


class _LengthLimitedReader(_SocketTimedReader):
    def __init__(self, conn, start_ms, total_ms, clock, limit, pending=b""):
        super().__init__(conn, start_ms, total_ms, clock, pending)
        self.remaining = limit

    def read(self, max_bytes: int, timeout_ms: int) -> bytes:
        if self.remaining <= 0:
            return b""
        allowed = min(max_bytes, self.remaining)
        data = super().read(allowed, timeout_ms)
        self.remaining -= len(data)
        return data


class _ClockAdapter:
    def __init__(self, fn):
        self.fn = fn

    def monotonic_ms(self):
        return self.fn()


class _ChunkedTimedReader(_SocketTimedReader):
    def __init__(self, conn, start_ms, total_ms, clock, pending=b""):
        super().__init__(conn, start_ms, total_ms, clock, pending)
        self._buffer = bytearray(pending)
        self._done = False

    def _read_line(self):
        data = bytearray()
        while True:
            idx = self._buffer.find(b"\r\n")
            if idx >= 0:
                line = bytes(self._buffer[:idx])
                del self._buffer[:idx + 2]
                return line
            chunk = super().read(4096, 1000)
            if not chunk:
                raise SecureHTTPError("connection_failed")
            self._buffer.extend(chunk)

    def _read_exact(self, size):
        while len(self._buffer) < size:
            chunk = super().read(size - len(self._buffer), 1000)
            if not chunk:
                raise SecureHTTPError("connection_failed")
            self._buffer.extend(chunk)
        out = bytes(self._buffer[:size])
        del self._buffer[:size]
        return out

    def read(self, max_bytes, timeout_ms):
        while not self._done and len(self._buffer) < max_bytes:
            line = self._read_line()
            size_text = line.split(b";", 1)[0].strip()
            try:
                size = int(size_text, 16)
            except ValueError:
                raise SecureHTTPError("invalid_chunked_encoding")
            if size == 0:
                self._read_exact(2)
                self._done = True
                break
            data = self._read_exact(size)
            trailer = self._read_exact(2)
            if trailer != b"\r\n":
                raise SecureHTTPError("invalid_chunked_encoding")
            self._buffer.extend(data)
        out = bytes(self._buffer[:max_bytes])
        del self._buffer[:max_bytes]
        return out


def _read_chunked_body_manual(conn, profile, start_ms, total_ms, clock, initial=b""):
    selected = budget_for(profile)
    pending = bytearray(initial)
    result = bytearray()

    def fill_needed(size):
        while len(pending) < size:
            now = clock()
            if now - start_ms >= total_ms:
                raise SecureHTTPError("total_timeout_exceeded")
            conn.settimeout(min(1000, total_ms - (now - start_ms)) / 1000.0)
            try:
                data = conn.recv(size - len(pending))
            except TimeoutError as exc:
                if now - start_ms >= total_ms:
                    raise SecureHTTPError("total_timeout_exceeded") from exc
                raise SecureHTTPError("read_idle_timeout") from exc
            if not data:
                raise SecureHTTPError("connection_failed")
            pending.extend(data)

    def read_line(max_len=_CHUNK_LINE_MAX):
        while True:
            idx = pending.find(b"\r\n")
            if idx >= 0:
                line = bytes(pending[:idx])
                del pending[:idx + 2]
                return line
            if len(pending) >= max_len:
                raise SecureHTTPError("invalid_chunked_encoding")
            now = clock()
            if now - start_ms >= total_ms:
                raise SecureHTTPError("total_timeout_exceeded")
            conn.settimeout(min(1000, total_ms - (now - start_ms)) / 1000.0)
            try:
                data = conn.recv(4096)
            except TimeoutError as exc:
                if now - start_ms >= total_ms:
                    raise SecureHTTPError("total_timeout_exceeded") from exc
                raise SecureHTTPError("read_idle_timeout") from exc
            if not data:
                raise SecureHTTPError("connection_failed")
            pending.extend(data)

    while True:
        line = read_line()
        if b";" in line:
            raise SecureHTTPError("chunk_extension_not_allowed")
        if not line or any(ch not in b"0123456789abcdefABCDEF" for ch in line):
            raise SecureHTTPError("invalid_chunked_encoding")
        size = int(line, 16)
        if size > (1 << 63) - 1:
            raise SecureHTTPError("invalid_chunked_encoding")
        if size == 0:
            if read_line():
                raise SecureHTTPError("invalid_chunked_trailer")
            break
        fill_needed(size)
        result.extend(pending[:size])
        del pending[:size]
        if len(result) > selected.response_body_bytes:
            raise SecureHTTPError("response_body_too_large")
        fill_needed(2)
        if bytes(pending[:2]) != b"\r\n":
            raise SecureHTTPError("invalid_chunked_encoding")
        del pending[:2]
    return bytes(result)


def _validate_framing_headers(header_map: dict[str, list[str]]) -> None:
    te_values = header_map.get("transfer-encoding")
    cl_values = header_map.get("content-length")
    if te_values is None:
        return
    if cl_values is not None:
        raise SecureHTTPError("invalid_transfer_encoding")
    codings: list[str] = []
    for value in te_values:
        for part in value.split(","):
            coding = part.strip(" \t").lower()
            codings.append(coding)
    if codings != ["chunked"]:
        raise SecureHTTPError("invalid_transfer_encoding")


def _read_body(
    conn,
    request_method: str,
    status: int,
    headers: Sequence[tuple[str, str]],
    profile: str,
    start_ms: int,
    total_ms: int,
    clock,
    initial: bytes = b"",
) -> bytes:
    header_map: dict[str, list[str]] = {}
    for name, value in headers:
        header_map.setdefault(name.lower(), []).append(value)
    if request_method == "HEAD" or status in (204, 304):
        _validate_framing_headers(header_map)
        return b""
    _validate_framing_headers(header_map)
    encoding = header_map.get("content-encoding", [])
    if encoding and encoding[0].lower() not in ("identity", ""):
        raise SecureHTTPError("unsupported_content_encoding")
    if header_map.get("transfer-encoding") is not None:
        return _read_chunked_body_manual(conn, profile, start_ms, total_ms, clock, initial)
    length_values = header_map.get("content-length")
    if length_values is not None:
        declared = validate_content_lengths([v for v in length_values], profile)
        if declared is None:
            declared = 0
        reader = _LengthLimitedReader(conn, start_ms, total_ms, clock, declared, initial)
        result = read_bounded(profile, reader, clock=_ClockAdapter(clock))
        if result.total_read < declared:
            raise SecureHTTPError("connection_failed")
        return result.data
    reader = _SocketTimedReader(conn, start_ms, total_ms, clock, initial)
    result = read_bounded(profile, reader, clock=_ClockAdapter(clock))
    return result.data


def read_raw_response(
    conn,
    request_method: str,
    profile: str,
    start_ms: int,
    total_ms: int,
    clock,
) -> tuple[int, tuple[tuple[str, str], ...], bytes]:
    if total_ms <= 0:
        raise SecureHTTPError("total_timeout_exceeded")
    budget_for(profile)
    header_timeout = min(BUDGET.response_header_timeout_ms, total_ms)
    status, headers, rest = _read_response_headers(conn, header_timeout)
    body = _read_body(
        conn,
        request_method,
        status,
        headers,
        profile,
        start_ms,
        total_ms,
        clock,
        rest,
    )
    return status, tuple(headers), body
