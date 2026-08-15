"""Bounded runtime I/O primitives for TASK-022D-2.

This module reads all fixed limits from the sealed TASK-022D-1
TransportBudget. It performs no socket, HTTP, DNS, or environment proxy I/O.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol, Sequence

from crawler.security.transport_budget import BUDGET, BudgetProfile, budget_for

MAX_READ_CHUNK_BYTES = 65536


class BoundedIOError(ValueError):
    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(message or reason_code)
        self.reason_code = reason_code


def _validate_size(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BoundedIOError("invalid_size_value")
    if value < 0:
        raise BoundedIOError("negative_size")
    return value


def check_request_body_size(value: int) -> None:
    observed = _validate_size(value)
    if observed > BUDGET.request_body_bytes:
        raise BoundedIOError("request_body_too_large")


def check_response_headers_size(value: int) -> None:
    observed = _validate_size(value)
    if observed > BUDGET.response_headers_bytes:
        raise BoundedIOError("response_headers_too_large")


def check_response_body_size(profile: str, value: int) -> None:
    selected = budget_for(profile)
    observed = _validate_size(value)
    if observed > selected.response_body_bytes:
        raise BoundedIOError("response_body_too_large")


def _parse_content_length_token(token: str) -> int:
    stripped = token.strip(" \t")
    if not stripped or any(char not in "0123456789" for char in stripped):
        raise BoundedIOError("invalid_content_length")
    return int(stripped)


def _content_length_values(value) -> list[int]:
    if isinstance(value, bool) or value is None:
        raise BoundedIOError("invalid_content_length")
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        return [_parse_content_length_token(part) for part in value.split(",")]
    if isinstance(value, (list, tuple)):
        result: list[int] = []
        for item in value:
            if isinstance(item, bool) or not isinstance(item, (int, str)):
                raise BoundedIOError("invalid_content_length")
            if isinstance(item, str):
                result.extend(_parse_content_length_token(part) for part in item.split(","))
            else:
                result.append(item)
        return result
    raise BoundedIOError("invalid_content_length")


def _validate_content_length_values(values: Sequence[int], profile: str) -> int | None:
    selected = budget_for(profile)
    if not values:
        raise BoundedIOError("invalid_content_length")
    first = values[0]
    if first < 0:
        raise BoundedIOError("invalid_content_length")
    for value in values[1:]:
        if value != first:
            raise BoundedIOError("invalid_content_length")
    if first > selected.response_body_bytes:
        raise BoundedIOError("response_body_too_large")
    return first


def validate_content_length(value, profile: str) -> int | None:
    if value is None:
        return None
    parsed = _content_length_values(value)
    return _validate_content_length_values(parsed, profile)


def validate_content_lengths(values: Sequence, profile: str) -> int | None:
    selected = budget_for(profile)
    if not values:
        raise BoundedIOError("invalid_content_length")
    flattened: list[int] = []
    for raw in values:
        if raw is None:
            continue
        flattened.extend(_content_length_values(raw))
    if not flattened:
        raise BoundedIOError("invalid_content_length")
    first = flattened[0]
    if first < 0:
        raise BoundedIOError("invalid_content_length")
    for value in flattened[1:]:
        if value != first:
            raise BoundedIOError("invalid_content_length")
    if first > selected.response_body_bytes:
        raise BoundedIOError("response_body_too_large")
    return first


class TimedReader(Protocol):
    deadline_capable: bool

    def read(self, max_bytes: int, timeout_ms: int) -> bytes:
        ...


class MonotonicClock(Protocol):
    def monotonic_ms(self) -> int:
        ...


class _RealClock:
    def monotonic_ms(self) -> int:
        return int(time.monotonic() * 1000)


@dataclass(frozen=True, slots=True)
class BoundedReadResult:
    data: bytes
    total_read: int


def _validate_clock_sample(value, previous: int | None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BoundedIOError("invalid_clock")
    if value < 0:
        raise BoundedIOError("invalid_clock")
    if previous is not None and value < previous:
        raise BoundedIOError("invalid_clock")
    return value


def _sample_clock(clock: MonotonicClock, previous: int | None) -> int:
    try:
        value = clock.monotonic_ms()
    except Exception as exc:
        raise BoundedIOError("invalid_clock") from exc
    return _validate_clock_sample(value, previous)


def _classify_timeout(
    start: int,
    last_activity: int,
    total_timeout_ms: int,
    read_idle_timeout_ms: int,
    now: int,
) -> None:
    if now - start >= total_timeout_ms:
        raise BoundedIOError("total_timeout_exceeded")
    if now - last_activity >= read_idle_timeout_ms:
        raise BoundedIOError("read_idle_timeout")


def _read_bounded(
    profile: BudgetProfile,
    read_idle_timeout_ms: int,
    reader: TimedReader,
    clock: MonotonicClock,
) -> BoundedReadResult:
    start = _sample_clock(clock, None)
    last_clock = start
    last_activity = start
    data = bytearray()
    total = 0
    while True:
        now = _sample_clock(clock, last_clock)
        last_clock = now
        _classify_timeout(start, last_activity, profile.total_timeout_ms, read_idle_timeout_ms, now)

        total_remaining = profile.total_timeout_ms - (now - start)
        timeout_ms = min(read_idle_timeout_ms, total_remaining)
        allowed = min(MAX_READ_CHUNK_BYTES, profile.response_body_bytes - total + 1)
        if allowed <= 0:
            allowed = 1

        try:
            chunk = reader.read(allowed, timeout_ms)
        except BoundedIOError as exc:
            now2 = _sample_clock(clock, last_clock)
            last_clock = now2
            _classify_timeout(start, last_activity, profile.total_timeout_ms, read_idle_timeout_ms, now2)
            raise
        except Exception as exc:
            now2 = _sample_clock(clock, last_clock)
            last_clock = now2
            _classify_timeout(start, last_activity, profile.total_timeout_ms, read_idle_timeout_ms, now2)
            raise BoundedIOError("read_failed") from exc

        now2 = _sample_clock(clock, last_clock)
        last_clock = now2
        _classify_timeout(start, last_activity, profile.total_timeout_ms, read_idle_timeout_ms, now2)

        if not isinstance(chunk, bytes):
            raise BoundedIOError("read_failed")
        if len(chunk) > allowed:
            raise BoundedIOError("response_body_too_large")
        if not chunk:
            return BoundedReadResult(bytes(data), total)
        total += len(chunk)
        if total > profile.response_body_bytes:
            raise BoundedIOError("response_body_too_large")
        data.extend(chunk)
        last_activity = now2


def read_bounded(
    profile: str,
    reader: TimedReader,
    *,
    clock: MonotonicClock | None = None,
) -> BoundedReadResult:
    selected = budget_for(profile)
    if not getattr(reader, "deadline_capable", False):
        raise BoundedIOError("reader_not_deadline_capable")
    return _read_bounded(
        selected,
        BUDGET.read_idle_timeout_ms,
        reader,
        clock or _RealClock(),
    )
