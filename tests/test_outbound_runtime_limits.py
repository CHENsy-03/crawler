import copy
import json
import os
import threading

import pytest

from crawler.security.bounded_io import (
    BoundedIOError,
    MAX_READ_CHUNK_BYTES,
    check_request_body_size,
    check_response_body_size,
    check_response_headers_size,
    read_bounded,
    validate_content_length,
    validate_content_lengths,
)
from crawler.security.concurrency_limiter import ConcurrencyError, ConcurrencyLimiter, Lease

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "outbound_runtime_limits_contract.json")


def _load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class FakeClock:
    def __init__(self, values):
        self.values = list(values)
        self.index = 0

    def monotonic_ms(self):
        if self.index < len(self.values):
            value = self.values[self.index]
            self.index += 1
            return value
        return self.values[-1] if self.values else 0


class FakeTimedReader:
    def __init__(self, chunks=None, error=None, deadline_capable=True):
        self.chunks = list(chunks or [])
        self.error = error
        self.deadline_capable = deadline_capable
        self.calls = []

    def read(self, max_bytes, timeout_ms):
        self.calls.append((max_bytes, timeout_ms))
        if self.error is not None:
            err = self.error
            self.error = None
            raise err
        if self.chunks:
            return self.chunks.pop(0)
        return b""


def _reader_for_case(case):
    action = case["action"]
    if action == "empty":
        return FakeTimedReader()
    if action == "single_chunk":
        return FakeTimedReader(chunks=[case["chunk"].encode()])
    if action == "multiple_chunks":
        return FakeTimedReader(chunks=[chunk.encode() for chunk in case["chunks"]])
    if action in ("exact_probe", "chunk_boundary"):
        return FakeTimedReader(chunks=[b"x" * MAX_READ_CHUNK_BYTES] * 16)
    if action in ("over_probe", "content_length_less"):
        return FakeTimedReader(chunks=[b"x" * MAX_READ_CHUNK_BYTES] * 16 + [b"x"])
    if action == "oversized_chunk":
        return FakeTimedReader(chunks=[b"x" * (MAX_READ_CHUNK_BYTES + 1)])
    if action == "reader_error":
        return FakeTimedReader(chunks=[b"a"], error=RuntimeError("boom"))
    if action == "no_progress":
        return FakeTimedReader(chunks=[b"a"], error=BoundedIOError("read_no_progress"))
    if action == "idle_reset":
        return FakeTimedReader(chunks=[b"a", b"b"])
    if action == "reader_not_deadline_capable":
        return FakeTimedReader(deadline_capable=False)
    if action == "late_eof":
        return FakeTimedReader(chunks=[b""])
    return FakeTimedReader(chunks=[b"a"])


def _clock_for_case(case):
    action = case["action"]
    if action == "clock_bool":
        return FakeClock([False, False, False])
    if action == "clock_float":
        return FakeClock([0.0, 0.0, 0.0])
    if action == "clock_str":
        return FakeClock(["0", "0", "0"])
    if action == "clock_none":
        return FakeClock([None, None, None])
    if action == "clock_negative":
        return FakeClock([-1000, -1000, -1000])
    if action == "clock_regression":
        return FakeClock([100, 0, 0])
    if action in ("exact_idle", "idle_timeout", "stop_after_timeout"):
        return FakeClock([0, 0, 0, 15000])
    if action in ("exact_total", "total_timeout", "simultaneous"):
        return FakeClock([0, 0, 0, 30000])
    if action in ("late_chunk", "late_eof"):
        return FakeClock([0, 0, 30000, 30000])
    if action == "idle_reset":
        return FakeClock([0, 0, 0, 5000, 5000, 5000])
    return FakeClock([0] * 100)


def test_size_gate_cases():
    fixture = _load_fixture()
    executed = set()
    expected = {case["id"] for case in fixture["size_gate_cases"]}
    for case in fixture["size_gate_cases"]:
        action = case["action"]
        if action == "request_body":
            fn = lambda: check_request_body_size(case["value"])
        elif action == "response_headers":
            fn = lambda: check_response_headers_size(case["value"])
        elif action == "response_body":
            fn = lambda: check_response_body_size(case["profile"], case["value"])
        elif action == "content_length":
            fn = lambda: validate_content_length(case["value"], case["profile"])
        elif action == "content_length_multi":
            fn = lambda: validate_content_lengths(case["values"], case["profile"])
        elif action == "content_length_multi_nil":
            fn = lambda: validate_content_lengths((), case["profile"])
        elif action == "content_length_conflict":
            fn = lambda: validate_content_lengths(case["values"], case["profile"])
        else:
            raise AssertionError(f"unknown size action {action}")
        if case["allowed"]:
            result = fn()
            if "expected_value" in case:
                assert result == case["expected_value"], case["id"]
        else:
            with pytest.raises(BoundedIOError) as exc_info:
                fn()
            assert exc_info.value.reason_code == case["expected_reason"], case["id"]
        executed.add(case["id"])
    assert executed == expected


def test_bounded_read_cases():
    fixture = _load_fixture()
    executed = set()
    expected = {case["id"] for case in fixture["bounded_read_cases"]}
    for case in fixture["bounded_read_cases"]:
        reader = _reader_for_case(case)
        clock = _clock_for_case(case)
        if case["action"] == "content_length_less":
            validate_content_length(case["content_length"], case["profile"])
        if "expected_reason" in case:
            with pytest.raises(BoundedIOError) as exc_info:
                read_bounded(case["profile"], reader, clock=clock)
            assert exc_info.value.reason_code == case["expected_reason"], case["id"]
            if case["action"] == "stop_after_timeout":
                assert len(reader.calls) == 1, case["id"]
        else:
            result = read_bounded(case["profile"], reader, clock=clock)
            assert result.total_read == case["expected_total"], case["id"]
            assert len(result.data) == case["expected_total"], case["id"]
        executed.add(case["id"])
    assert executed == expected


def test_concurrency_cases():
    fixture = _load_fixture()
    executed = set()
    expected = {case["id"] for case in fixture["concurrency_cases"]}
    for case in fixture["concurrency_cases"]:
        limiter = ConcurrencyLimiter()
        action = case["action"]
        if action == "same_host_1":
            with limiter.acquire("example.com"):
                assert limiter.active_count() == 1
            assert limiter.active_count() == 0
        elif action == "same_host_5":
            leases = [limiter.acquire("example.com") for _ in range(5)]
            with pytest.raises(ConcurrencyError) as exc_info:
                limiter.acquire("example.com")
            assert exc_info.value.reason_code == "host_concurrency_exceeded"
            for lease in leases:
                lease.release()
        elif action == "same_host_6":
            leases = [limiter.acquire("example.com") for _ in range(5)]
            with pytest.raises(ConcurrencyError) as exc_info:
                limiter.acquire("example.com")
            assert exc_info.value.reason_code == "host_concurrency_exceeded"
            for lease in leases:
                lease.release()
        elif action in ("multi_host_20", "multi_host_21"):
            leases = [limiter.acquire(f"host{i}.example") for i in range(20)]
            with pytest.raises(ConcurrencyError) as exc_info:
                limiter.acquire("extra.example")
            assert exc_info.value.reason_code == "global_concurrency_exceeded"
            for lease in leases:
                lease.release()
        elif action == "case_normalization":
            a = limiter.acquire("Example.COM")
            b = limiter.acquire("example.com")
            assert limiter.host_count("example.com") == 2
            a.release(); b.release()
        elif action == "port_independent":
            with pytest.raises(ConcurrencyError) as exc_info:
                limiter.acquire("example.com:8443")
            assert exc_info.value.reason_code == "invalid_host_key"
        elif action in ("invalid_empty", "invalid_space", "invalid_control", "invalid_unicode", "ambiguous_ipv4", "leading_hyphen", "trailing_hyphen", "nested_leading_hyphen", "nested_trailing_hyphen", "single_hyphen", "hyphen_root_dot", "hyphen_leading_root_dot", "bare_punycode", "root_dot_invalid_hyphen"):
            with pytest.raises(ConcurrencyError) as exc_info:
                limiter.acquire(case["host"])
            assert exc_info.value.reason_code == "invalid_host_key"
        elif action == "release_reacquire":
            lease = limiter.acquire("example.com"); lease.release()
            lease2 = limiter.acquire("example.com")
            assert limiter.active_count() == 1
            lease2.release()
        elif action == "double_release":
            lease = limiter.acquire("example.com"); lease.release(); lease.release()
            assert limiter.active_count() == 0
        elif action == "host_entry_cleanup":
            lease = limiter.acquire("example.com"); lease.release()
            assert limiter.host_count("example.com") == 0
        elif action == "ip_literal":
            lease = limiter.acquire("2606:4700:4700::1111")
            assert limiter.host_count("2606:4700:4700::1111") == 1
            lease.release()
        elif action in ("valid_internal_hyphen", "valid_punycode"):
            lease = limiter.acquire(case["host"])
            assert limiter.host_count(case["host"]) == 1
            lease.release()
        elif action == "lease_host_mutation":
            a = limiter.acquire("example.com")
            b = limiter.acquire("other.example")
            try:
                a._host = "other.example"
            except Exception:
                pass
            a.release()
            assert limiter.active_count() == 1
            assert limiter.host_count("example.com") == 0
            assert limiter.host_count("other.example") == 1
            b.release()
            assert limiter.active_count() == 0
            assert limiter.issued_count() == 0
        elif action == "lease_owner_mutation":
            other = ConcurrencyLimiter()
            a = limiter.acquire("example.com")
            try:
                object.__setattr__(a, "_owner", other)
            except Exception:
                pass
            a.release()
            assert other.active_count() == 0
            assert limiter.active_count() == 1
            object.__setattr__(a, "_owner", None)
            assert a.release() is False
            assert limiter.active_count() == 1
            object.__setattr__(a, "_owner", limiter)
            a.release()
            assert limiter.active_count() == 0
            assert limiter.issued_count() == 0
        elif action == "exact_registry_identity":
            a = limiter.acquire("example.com")
            entry = limiter._issued.get(id(a))
            assert entry is not None
            assert getattr(entry, "lease", entry) is a
            a.release()
            assert limiter.active_count() == 0
            assert limiter.issued_count() == 0
        elif action == "forged_lease":
            with pytest.raises((TypeError, ConcurrencyError)):
                Lease(limiter, "example.com")
            assert limiter.active_count() == 0
        elif action in ("copied_lease", "deepcopy_lease"):
            lease = limiter.acquire("example.com")
            cloned = None
            try:
                cloned = copy.copy(lease) if action == "copied_lease" else copy.deepcopy(lease)
            except TypeError:
                pass
            lease.release()
            if cloned is not None:
                try:
                    cloned.release()
                except Exception:
                    pass
            assert limiter.active_count() == 0
        elif action == "cross_limiter":
            other = ConcurrencyLimiter()
            try:
                Lease(limiter, "example.com").release()
            except Exception:
                pass
            assert limiter.active_count() == 0
            assert other.active_count() == 0
        elif action == "context_normal":
            with limiter.acquire("example.com"):
                assert limiter.active_count() == 1
            assert limiter.active_count() == 0
        elif action == "context_exception":
            try:
                with limiter.acquire("example.com"):
                    raise RuntimeError("boom")
            except RuntimeError:
                pass
            assert limiter.active_count() == 0
        elif action == "root_dot_alias":
            a = limiter.acquire("example.com")
            b = limiter.acquire("example.com.")
            assert limiter.host_count("example.com") == 2
            a.release(); b.release()
        elif action == "equivalent_ipv6":
            a = limiter.acquire("2606:4700:4700::1111")
            b = limiter.acquire("2606:4700:4700:0:0:0:0:1111")
            assert limiter.host_count("2606:4700:4700::1111") == 2
            a.release(); b.release()
        elif action == "concurrent_release":
            lease = limiter.acquire("example.com")
            barrier = threading.Barrier(2)
            def release():
                barrier.wait()
                lease.release()
            threads = [threading.Thread(target=release) for _ in range(2)]
            for t in threads: t.start()
            for t in threads: t.join()
            assert limiter.active_count() == 0
        else:
            raise AssertionError(f"unknown concurrency action {action}")
        executed.add(case["id"])
    assert executed == expected
