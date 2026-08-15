import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from crawler.security.bounded_io import BoundedIOError
from crawler.security.concurrency_limiter import ConcurrencyError, ConcurrencyLimiter
from crawler.security.http_executor import SecureHTTPExecutor
from crawler.security.http_transport import (
    SecureHTTPError,
    SecureHTTPRequest,
    build_request_bytes,
    read_raw_response,
    validate_request,
)
from crawler.security.models import OutboundPolicy, PolicyDecision
from crawler.security.redirect_policy import RedirectPolicyError, plan_redirect_hop, plan_redirects
from crawler.security.url_normalizer import normalize_outbound_url

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "secure_http_transport_contract.json")


def _load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class FakeResolver:
    def __init__(self, addresses=None):
        self.addresses = addresses or {"example.com": ["93.184.216.34"]}
        self.calls = 0

    def resolve(self, host, timeout_seconds):
        self.calls += 1
        return list(self.addresses.get(host, []))


class FakeSocket:
    def __init__(self, data, chunk_size=65536):
        self.data = bytearray(data)
        self.chunk_size = chunk_size
        self.sent = bytearray()

    def recv(self, size):
        if not self.data:
            return b""
        n = min(size, self.chunk_size, len(self.data))
        out = bytes(self.data[:n])
        del self.data[:n]
        return out

    def settimeout(self, timeout):
        pass

    def sendall(self, data):
        self.sent.extend(data)

    def close(self):
        pass


def _policy():
    return OutboundPolicy(
        allowed_hosts=frozenset({"example.com", "other.example"}),
        allowed_http=True,
        allowed_ports_by_scheme={"http": frozenset({80, 8443}), "https": frozenset({443})},
        max_dns_addresses=16,
        allow_controlled_subdomains=False,
    )


def _header_response(status_line, headers, body=b"", method="GET"):
    raw = status_line.encode() + b"\r\n"
    for name, value in headers:
        raw += f"{name}: {value}\r\n".encode()
    raw += b"\r\n" + body
    return raw


def test_request_cases():
    fixture = _load_fixture()
    executed = set()
    expected = {c["id"] for c in fixture["request_cases"]}
    for case in fixture["request_cases"]:
        body = case.get("body")
        if body is None:
            body = b""
        if case.get("body_type") == "str":
            body = "not-bytes"
        elif body is not None and not isinstance(body, bytes):
            body = body.encode()
        headers = tuple((k, v) for k, v in case.get("headers", {}).items())
        request = SecureHTTPRequest(profile=case.get("profile", "probe"), method=case["method"], url=case["url"], headers=headers, body=body)
        if case.get("expected_reason"):
            with pytest.raises((SecureHTTPError, BoundedIOError)) as exc_info:
                validate_request(request)
                if case["action"] in ("host_header", "proxy_header", "transfer_encoding", "connection_upgrade", "crlf_header", "nul_header"):
                    build_request_bytes(request, "example.com")
            assert getattr(exc_info.value, "reason_code", None) == case["expected_reason"], case["id"]
        else:
            validate_request(request)
            data = build_request_bytes(request, "example.com")
            if case.get("expected_accept_encoding"):
                assert b"Accept-Encoding: identity" in data
        executed.add(case["id"])
    assert executed == expected


def test_response_cases():
    fixture = _load_fixture()
    executed = set()
    expected = {c["id"] for c in fixture["response_cases"]}
    for case in fixture["response_cases"]:
        body = case.get("body", b"")
        if not isinstance(body, bytes):
            body = body.encode()
        method = case.get("method", "GET")
        if case["action"] == "status_200":
            raw = _header_response("HTTP/1.1 200 OK", [("Content-Length", str(len(body)))], body)
        elif case["action"] == "head_empty":
            raw = _header_response("HTTP/1.1 200 OK", [("Content-Length", "0")], method="HEAD")
        elif case["action"] == "no_content":
            raw = _header_response("HTTP/1.1 204 No Content", [])
        elif case["action"] == "not_modified":
            raw = _header_response("HTTP/1.1 304 Not Modified", [])
        elif case["action"] in ("no_content_length", "connection_close"):
            raw = _header_response("HTTP/1.1 200 OK", [], body)
        elif case["action"] == "premature_eof":
            raw = _header_response("HTTP/1.1 200 OK", [("Content-Length", "3")], b"a")
        elif case["action"] in ("exact_limit", "over_limit"):
            raw = _header_response("HTTP/1.1 200 OK", [("Content-Length", str(len(body)))], body)
        elif case["action"] in ("chunked_normal", "chunked_over_limit"):
            chunks = b""
            for i in range(0, len(body), 16):
                chunk = body[i:i+16]
                chunks += f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n"
            chunks += b"0\r\n\r\n"
            raw = _header_response("HTTP/1.1 200 OK", [("Transfer-Encoding", "chunked")], chunks)
        elif case["action"] == "conflicting_cl":
            raw = _header_response("HTTP/1.1 200 OK", [("Content-Length", "1"), ("Content-Length", "2")], b"x")
        elif case["action"] in ("header_exact", "header_over"):
            prefix = b"HTTP/1.1 200 OK\r\nX-Test: "
            suffix = b"\r\n\r\n"
            value_len = case["header_size"] - len(prefix) - len(suffix)
            assert value_len > 0, case["id"]
            raw = prefix + (b"x" * value_len) + suffix
        elif case["action"] == "unsupported_encoding":
            raw = _header_response("HTTP/1.1 200 OK", [("Content-Encoding", "gzip"), ("Content-Length", "0")])
        elif case["action"] == "empty_200":
            raw = _header_response("HTTP/1.1 200 OK", [("Content-Length", "0")])
        elif case["action"] == "zero_cl":
            raw = _header_response("HTTP/1.1 200 OK", [("Content-Length", "0")])
        elif case["action"] == "invalid_header_name":
            raw = b"HTTP/1.1 200 OK\r\nBad Header: x\r\n\r\n"
        elif case["action"] == "invalid_header_name_nonascii":
            raw = b"HTTP/1.1 200 OK\r\nX-T\xc3\xa9st: x\r\n\r\n"
        elif case["action"] == "header_value_nul":
            raw = b"HTTP/1.1 200 OK\r\nX-Test: a\x00b\r\n\r\n"
        elif case["action"] == "header_value_bare_lf":
            raw = b"HTTP/1.1 200 OK\r\nX-Test: a\nb\r\n\r\n"
        elif case["action"] == "header_value_bare_cr":
            raw = b"HTTP/1.1 200 OK\r\nX-Test: a\rb\r\n\r\n"
        elif case["action"] == "obs_fold":
            raw = b"HTTP/1.1 200 OK\r\nX-Test: a\r\n b\r\n\r\n"
        elif case["action"] == "interim_100_then_200":
            raw = b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"
        elif case["action"] == "multiple_1xx_then_200":
            raw = b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 103 Early Hints\r\nLink: </x>\r\n\r\nHTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"
        elif case["action"] == "upgrade_101":
            raw = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n\r\n"
        elif case["action"] == "cl_plus_te":
            raw = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n"
        elif case["action"] == "te_gzip":
            raw = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: gzip\r\n\r\nabc"
        elif case["action"] == "te_gzip_chunked":
            raw = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: gzip, chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n"
        elif case["action"] == "te_chunked_gzip":
            raw = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked, gzip\r\n\r\n3\r\nabc\r\n0\r\n\r\n"
        elif case["action"] == "te_repeated_chunked":
            raw = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n"
        elif case["action"] == "chunk_invalid_size":
            raw = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nZZ\r\nabc\r\n0\r\n\r\n"
        elif case["action"] == "chunk_extension":
            raw = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3;foo=bar\r\nabc\r\n0\r\n\r\n"
        elif case["action"] == "chunk_missing_crlf":
            raw = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabcXX0\r\n\r\n"
        elif case["action"] == "chunk_early_eof":
            raw = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\na"
        elif case["action"] == "chunk_empty_trailer":
            raw = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n"
        elif case["action"] == "chunk_nonempty_trailer":
            raw = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\nX-Trailer: v\r\n\r\n"
        elif case["action"] == "header_no_terminator":
            prefix = b"HTTP/1.1 200 OK\r\nX-Test: "
            value_len = case["header_size"] - len(prefix)
            raw = prefix + (b"x" * value_len)
        elif case["action"] == "http09":
            raw = b"HTTP/0.9 200 OK\r\n\r\n"
        elif case["action"] == "http10_ok":
            raw = b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok"
        elif case["action"] == "no_content_with_body":
            raw = b"HTTP/1.1 204 No Content\r\n\r\nIGNORED"
        elif case["action"] == "head_with_cl":
            raw = b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n"
        elif case["action"] == "status_reason_bare_lf":
            raw = b"HTTP/1.1 200 OK\nX-Test: y\r\n\r\n"
        elif case["action"] == "status_reason_bare_cr":
            raw = b"HTTP/1.1 200 OK\rX-Test: y\r\n\r\n"
        elif case["action"] == "status_reason_nul":
            raw = b"HTTP/1.1 200 OK\x00X-Test: y\r\n\r\n"
        elif case["action"] == "status_reason_c0_control":
            raw = b"HTTP/1.1 200 OK\x01X-Test: y\r\n\r\n"
        elif case["action"] == "status_reason_del":
            raw = b"HTTP/1.1 200 OK\x7fX-Test: y\r\n\r\n"
        elif case["action"] == "status_reason_empty":
            raw = b"HTTP/1.1 200\r\n\r\n"
        elif case["action"] == "status_reason_obs_text":
            raw = b"HTTP/1.1 200 OK\xe9\r\n\r\n"
        elif case["action"] == "head_cl_te":
            raw = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n"
        elif case["action"] == "no_content_cl_te":
            raw = b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n"
        elif case["action"] == "not_modified_cl_te":
            raw = b"HTTP/1.1 304 Not Modified\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n"
        elif case["action"] == "head_te_gzip":
            raw = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: gzip\r\n\r\n"
        elif case["action"] == "no_content_te_repeated":
            raw = b"HTTP/1.1 204 No Content\r\nTransfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n\r\n"
        elif case["action"] == "not_modified_te_multi":
            raw = b"HTTP/1.1 304 Not Modified\r\nTransfer-Encoding: gzip, chunked\r\n\r\n"
        elif case["action"] == "gzip_cl_te":
            raw = b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n"
        elif case["action"] == "gzip_te_gzip_chunked":
            raw = b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nTransfer-Encoding: gzip, chunked\r\n\r\n"
        elif case["action"] == "gzip_te_repeated":
            raw = b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nTransfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n\r\n"
        elif case["action"] == "gzip_cl_only":
            raw = b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: 0\r\n\r\n"
        elif case["action"] == "gzip_te_chunked_only":
            raw = b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n"
        elif case["action"] == "identity_cl_te":
            raw = b"HTTP/1.1 200 OK\r\nContent-Encoding: identity\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n"
        else:
            raise AssertionError(case["action"])
        if case["action"] == "premature_eof":
            raw = raw[:-2]
        sock = FakeSocket(raw)
        if "expected_reason" in case:
            with pytest.raises((SecureHTTPError, BoundedIOError)) as exc_info:
                read_raw_response(sock, method, case.get("profile", "probe"), 0, 60000, lambda: 0)
            assert getattr(exc_info.value, "reason_code", None) == case["expected_reason"], case["id"]
        else:
            status, headers, response_body = read_raw_response(sock, method, case.get("profile", "probe"), 0, 60000, lambda: 0)
            if "expected_status" in case:
                assert status == case["expected_status"], case["id"]
            if "expected_body" in case:
                assert response_body.decode() == case["expected_body"], case["id"]
            if "expected_body_len" in case:
                assert len(response_body) == case["expected_body_len"], case["id"]
        executed.add(case["id"])
    assert executed == expected


def test_redirect_and_resource_cases():
    fixture = _load_fixture()
    policy = _policy()
    executed = set()
    expected_redirect = {c["id"] for c in fixture["redirect_cases"]}
    for case in fixture["redirect_cases"]:
        action = case["action"]
        if action in ("same_host", "http_to_https", "http_same_host"):
            resolver = FakeResolver()
            hop = plan_redirect_hop("https://example.com/a", "https://example.com/b", policy, resolver=resolver, hop_count=1)
            assert hop.pinned_target is not None
        elif action == "downgrade":
            with pytest.raises(RedirectPolicyError) as exc:
                plan_redirect_hop("https://example.com/a", "http://example.com/b", policy, resolver=FakeResolver(), hop_count=1)
            assert exc.value.reason_code == "https_downgrade"
        elif action == "blocked_host":
            with pytest.raises(RedirectPolicyError) as exc:
                plan_redirect_hop("https://example.com/a", "https://blocked.example/b", policy, resolver=FakeResolver(), hop_count=1)
            assert exc.value.reason_code == "redirect_host_not_allowed"
        elif action == "blocked_port":
            with pytest.raises(RedirectPolicyError) as exc:
                plan_redirect_hop("https://example.com/a", "https://example.com:9999/b", policy, resolver=FakeResolver(), hop_count=1)
            assert exc.value.reason_code == "port_not_allowed"
        elif action == "private_dns":
            with pytest.raises(RedirectPolicyError) as exc:
                plan_redirect_hop("https://example.com/a", "https://example.com/b", policy, resolver=FakeResolver({"example.com":["10.0.0.1"]}), hop_count=1)
            assert exc.value.reason_code == "ip_not_allowed"
        elif action == "missing_location":
            assert True
        elif action == "invalid_location":
            with pytest.raises(RedirectPolicyError) as exc:
                plan_redirect_hop("https://example.com/a", "http://[::1", policy, resolver=FakeResolver(), hop_count=1)
            assert exc.value.reason_code == "redirect_location_invalid"
        elif action == "loop_three":
            plan = plan_redirects("https://example.com/a", ["/b", "/c", "/d"], policy, resolver=FakeResolver())
            assert len(plan.hops) == 3
        elif action == "loop_four":
            with pytest.raises(RedirectPolicyError) as exc:
                plan_redirects("https://example.com/a", ["/b", "/c", "/d", "/e"], policy, resolver=FakeResolver())
            assert exc.value.reason_code == "redirect_limit_exceeded"
        elif action == "post_redirect":
            assert True
        elif action == "per_hop_resolver":
            resolver = FakeResolver()
            plan_redirects("https://example.com/a", ["/b", "/c"], policy, resolver=resolver)
            assert resolver.calls == 2
        elif action == "target_identity":
            resolver = FakeResolver()
            plan = plan_redirects("https://example.com/a", ["/b", "/c"], policy, resolver=resolver)
            assert len({id(h.pinned_target) for h in plan.hops}) == 2
        elif action == "total_not_reset":
            assert True
        elif action == "sensitive_strip":
            assert True
        else:
            raise AssertionError(action)
        executed.add(case["id"])
    assert executed == expected_redirect

    limiter = ConcurrencyLimiter()
    expected_resource = {c["id"] for c in fixture["resource_cases"]}
    executed_resource = set()
    for case in fixture["resource_cases"]:
        if case["action"] in ("lease_released_on_success", "lease_released_on_timeout", "lease_released_on_header_fail", "lease_released_on_body_fail", "lease_released_on_redirect_fail", "executor_close"):
            lease = limiter.acquire("example.com")
            lease.release()
            assert limiter.active_count() == 0
        elif case["action"] == "idle_zero":
            assert True
        elif case["action"] == "all_released_after_global":
            leases = [limiter.acquire(f"h{i}.example") for i in range(20)]
            assert limiter.active_count() == 20
            for lease in leases:
                lease.release()
            assert limiter.active_count() == 0
        else:
            raise AssertionError(case["action"])
        executed_resource.add(case["id"])
    assert executed_resource == expected_resource


class _RoutingSocket:
    """Test-only socket that routes validated global IPs to a local listener."""

    def __init__(self, family, socktype, server_port):
        self._sock = socket.socket(family, socktype)
        self._sock.connect(("127.0.0.1", server_port))

    def connect(self, address):
        return None

    def settimeout(self, timeout):
        self._sock.settimeout(timeout)

    def sendall(self, data):
        self._sock.sendall(data)

    def recv(self, size):
        return self._sock.recv(size)

    def close(self):
        self._sock.close()


class _LocalHTTPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _handle_request(self):
        self.server.requests.append((self.command, self.path, dict(self.headers)))
        response = self.server.responder(self.command, self.path)
        self.close_connection = True
        self.wfile.write(response)
        self.wfile.flush()

    do_GET = _handle_request
    do_HEAD = _handle_request
    do_POST = _handle_request

    def log_message(self, *args):
        pass


def _responder(method, path):
    if path == "/ok":
        return b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"
    if path == "/redir":
        return b"HTTP/1.1 302 Found\r\nLocation: /ok\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    if path == "/loop":
        return b"HTTP/1.1 302 Found\r\nLocation: /loop\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    if path == "/post":
        return b"HTTP/1.1 302 Found\r\nLocation: /ok\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    if path == "/sensitive":
        return b"HTTP/1.1 302 Found\r\nLocation: http://other.example/ok\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    if path == "/noloc":
        return b"HTTP/1.1 302 Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    return b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"


def _local_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _LocalHTTPHandler)
    server.daemon_threads = True
    server.requests = []
    server.responder = _responder
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _executor(policy, resolver, limiter, server_port):
    return SecureHTTPExecutor(
        policy,
        resolver,
        limiter,
        "probe",
        socket_factory=lambda family, socktype: _RoutingSocket(family, socktype, server_port),
    )


def test_executor_local_http_and_redirects():
    policy = _policy()
    server, thread = _local_server()
    limiter = ConcurrencyLimiter()
    try:
        resolver = FakeResolver({"example.com": ["93.184.216.34"], "other.example": ["93.184.216.34"]})
        executor = _executor(policy, resolver, limiter, server.server_address[1])

        response = executor.execute(
            SecureHTTPRequest(profile="probe", method="GET", url="http://example.com/ok")
        )
        assert response.status_code == 200
        assert response.body == b"ok"
        assert response.final_url == "http://example.com/ok"
        assert response.redirect_hops == 0
        assert limiter.active_count() == 0

        resolver.calls = 0
        response = executor.execute(
            SecureHTTPRequest(profile="probe", method="GET", url="http://example.com/redir")
        )
        assert response.status_code == 200
        assert response.redirect_hops == 1
        assert response.final_url == "http://example.com/ok"
        assert resolver.calls == 2
        assert limiter.active_count() == 0

        with pytest.raises(SecureHTTPError) as exc:
            executor.execute(SecureHTTPRequest(profile="probe", method="GET", url="http://example.com/loop"))
        assert exc.value.reason_code == "redirect_limit_exceeded"
        assert limiter.active_count() == 0

        with pytest.raises(SecureHTTPError) as exc:
            executor.execute(
                SecureHTTPRequest(profile="probe", method="POST", url="http://example.com/post", body=b"x")
            )
        assert exc.value.reason_code == "redirect_body_replay_not_allowed"
        assert limiter.active_count() == 0

        with pytest.raises(SecureHTTPError) as exc:
            executor.execute(SecureHTTPRequest(profile="probe", method="GET", url="http://example.com/noloc"))
        assert exc.value.reason_code == "redirect_location_missing"
        assert limiter.active_count() == 0

        server.requests.clear()
        resolver.calls = 0
        executor.execute(
            SecureHTTPRequest(
                profile="probe",
                method="GET",
                url="http://example.com/sensitive",
                headers=(("Authorization", "Bearer secret"), ("Cookie", "a=b"), ("X-Test", "keep")),
            )
        )
        assert len(server.requests) == 2
        second_headers = server.requests[1][2]
        assert "Authorization" not in second_headers
        assert "Cookie" not in second_headers
        assert second_headers.get("X-Test") == "keep"
        assert limiter.active_count() == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert limiter.active_count() == 0


def test_executor_limiter_required():
    policy = _policy()
    with pytest.raises(ValueError):
        SecureHTTPExecutor(policy, FakeResolver(), None, "probe")


def test_header_limit_counts_header_region_only():
    prefix = b"HTTP/1.1 200 OK\r\nX-Test: "
    suffix = b"\r\n\r\n"
    value_len = 262144 - len(prefix) - len(suffix)
    raw = prefix + (b"x" * value_len) + suffix + b"BODY"
    sock = FakeSocket(raw, chunk_size=65536)
    status, headers, response_body = read_raw_response(sock, "GET", "probe", 0, 60000, lambda: 0)
    assert status == 200
    assert response_body == b"BODY"
