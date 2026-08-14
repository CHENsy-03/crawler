import ipaddress
import json
import os
import socket
import ssl
import threading
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crawler.security.models import NormalizedURL, OutboundPolicy, PolicyDecision
from crawler.security.outbound_policy import decide
from crawler.security.pinned_connection import (
    PinnedConnectionError,
    PinnedTarget,
    build_pinned_target,
    connect_pinned,
    connect_with_authority,
    prepare_request_host_header,
    validate_request_authority,
)
from crawler.security.tls_policy import (
    TLSPolicyError,
    secure_ssl_context,
    validate_ssl_context,
    validate_tls_server_name,
    wrap_client_socket,
)
from crawler.security.url_normalizer import normalize_outbound_url

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "pinned_connection_contract.json")


def _load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_policy(raw):
    return OutboundPolicy(
        allowed_hosts=frozenset(raw["allowed_hosts"]),
        allowed_http=raw["allowed_http"],
        allowed_ports_by_scheme={k: frozenset(v) for k, v in raw["allowed_ports_by_scheme"].items()},
        max_dns_addresses=raw["max_dns_addresses"],
        allow_controlled_subdomains=raw["allow_controlled_subdomains"],
    )


class FakeResolver:
    def __init__(self, addresses):
        self.addresses = list(addresses)
        self.calls = 0

    def resolve(self, host, timeout_seconds):
        self.calls += 1
        return list(self.addresses)


class FakeSocket:
    def __init__(self, family, socktype, fail_connect=False):
        self.family = family
        self.socktype = socktype
        self.fail_connect = fail_connect
        self.connections = []
        self.closed = False

    def settimeout(self, timeout):
        pass

    def connect(self, address):
        self.connections.append(address)
        if self.fail_connect:
            raise OSError("connect failed")

    def close(self):
        self.closed = True


class FakeSocketFactory:
    def __init__(self, fail_indices=(), fail_all=False):
        self.fail_indices = set(fail_indices)
        self.fail_all = fail_all
        self.calls = []
        self.sockets = []

    def __call__(self, family, socktype):
        self.calls.append((family, socktype))
        index = len(self.sockets)
        sock = FakeSocket(family, socktype, self.fail_all or index in self.fail_indices)
        self.sockets.append(sock)
        return sock


def _unsigned_target_for_test(scheme, host, port, addresses, *, policy_identity="test"):
    parsed = []
    seen = set()
    for raw in addresses:
        ip = ipaddress.ip_address(raw)
        canonical = str(ip)
        if canonical in seen:
            continue
        seen.add(canonical)
        parsed.append(ip)
    parsed.sort(key=lambda ip: (ip.version, ip.packed))
    normalized = [str(ip) for ip in parsed]
    host_for_authority = f"[{host}]" if ":" in host else host
    default_port = 80 if scheme == "http" else 443
    host_header = host_for_authority if port == default_port else f"{host_for_authority}:{port}"
    target = object.__new__(PinnedTarget)
    object.__setattr__(target, "scheme", scheme)
    object.__setattr__(target, "normalized_host", host)
    object.__setattr__(target, "port", port)
    object.__setattr__(target, "authority", host_header)
    object.__setattr__(target, "host_header", host_header)
    object.__setattr__(target, "server_name", host)
    object.__setattr__(target, "validated_addresses", tuple(normalized))
    object.__setattr__(target, "is_ip_literal", False)
    object.__setattr__(target, "policy_identity", policy_identity)
    return target


def _signed_target_for_fixture(raw, addresses, policy):
    decision = decide(raw, policy, resolver=FakeResolver(addresses))
    return build_pinned_target(decision, policy)


_SIGNED_FIELDS = (
    "scheme",
    "normalized_host",
    "port",
    "authority",
    "host_header",
    "server_name",
    "validated_addresses",
    "is_ip_literal",
    "policy_identity",
)


def _clone_signed_target(source, **changes):
    target = object.__new__(PinnedTarget)
    proof_field = "_integrity_tag" if hasattr(source, "_integrity_tag") else "_source_token"
    for name in _SIGNED_FIELDS + (proof_field,):
        object.__setattr__(target, name, object.__getattribute__(source, name))
    for name, value in changes.items():
        object.__setattr__(target, name, value)
    return target


def _signed_target_for_fields(scheme, host, port):
    host_for_authority = f"[{host}]" if ":" in host else host
    default_port = 80 if scheme == "http" else 443
    authority = host_for_authority if port == default_port else f"{host_for_authority}:{port}"
    try:
        ipaddress.ip_address(host)
        is_ip_literal = True
        address = host
    except ValueError:
        is_ip_literal = False
        address = "2606:4700:4700::1111" if ":" in host else "93.184.216.34"
    normalized = NormalizedURL(
        scheme=scheme,
        host=host,
        port=port,
        explicit_port=port != default_port,
        authority=authority,
        normalized_url=f"{scheme}://{host_for_authority}:{port}/",
        is_ip_literal=is_ip_literal,
    )
    decision = PolicyDecision(allowed=True, reason_code="", normalized=normalized, addresses=(address,))
    return build_pinned_target(decision)


def _https_policy_for(host):
    return OutboundPolicy(
        allowed_hosts=frozenset({host}),
        allowed_http=False,
        allowed_ports_by_scheme={"http": frozenset({80}), "https": frozenset({443})},
        max_dns_addresses=16,
        allow_controlled_subdomains=False,
    )


@pytest.mark.parametrize("case", _load_fixture()["plan_cases"], ids=lambda c: c["id"])
def test_plan_cases(case):
    policy = _make_policy(case["policy"])
    if case.get("forged"):
        normalized = normalize_outbound_url(case["raw"])
        decision = PolicyDecision(allowed=True, reason_code="", normalized=normalized, addresses=tuple(case["addresses"]))
    else:
        decision = decide(case["raw"], policy, resolver=FakeResolver(case["addresses"]))
    if case["expected_reason"]:
        with pytest.raises(PinnedConnectionError) as exc_info:
            build_pinned_target(decision, policy)
        assert exc_info.value.reason_code == case["expected_reason"]
        return
    target = build_pinned_target(decision, policy)
    assert target.scheme == case["expected_scheme"]
    assert target.normalized_host == case["expected_host"]
    assert target.port == case["expected_port"]
    assert target.authority == case["expected_authority"]
    assert target.host_header == case["expected_host_header"]
    assert target.server_name == case["expected_server_name"]
    assert list(target.validated_addresses) == case["expected_addresses"]
    assert target.is_ip_literal == case["expected_is_ip_literal"]


@pytest.mark.parametrize("case", _load_fixture()["host_header_cases"], ids=lambda c: c["id"])
def test_host_header_cases(case):
    addresses = ["2606:4700:4700::1111"] if ":" in case["host"] else ["93.184.216.34"]
    target = _signed_target_for_fields(case["scheme"], case["host"], case["port"])
    if "expected_reason" in case:
        with pytest.raises(PinnedConnectionError) as exc_info:
            prepare_request_host_header(case["request_host"], target)
        assert exc_info.value.reason_code == case["expected_reason"]
        return
    assert prepare_request_host_header(case["request_host"], target) == case["expected"]


@pytest.mark.parametrize("case", _load_fixture()["dial_cases"], ids=lambda c: c["id"])
def test_dial_cases(case):
    factory = FakeSocketFactory(fail_indices=(0,) if case.get("fail_first") else (), fail_all=bool(case.get("fail_all")))
    if not case["addresses"]:
        target = _unsigned_target_for_test("https", "fixture.example", case["port"], [])
        with pytest.raises(PinnedConnectionError) as exc_info:
            connect_pinned(target, socket_factory=factory)
        assert exc_info.value.reason_code == case["expected_reason"]
        return
    policy = OutboundPolicy(
        allowed_hosts=frozenset({"fixture.example"}),
        allowed_http=False,
        allowed_ports_by_scheme={"http": frozenset({80}), "https": frozenset({case["port"]})},
        max_dns_addresses=16,
        allow_controlled_subdomains=False,
    )
    target = _signed_target_for_fixture(f"https://fixture.example:{case['port']}/", case["addresses"], policy)
    if case["expected_reason"]:
        with pytest.raises(PinnedConnectionError):
            connect_pinned(target, socket_factory=factory)
        return
    sock = connect_pinned(target, socket_factory=factory)
    sequence = [conn[0] for sock in factory.sockets for conn in sock.connections]
    assert sequence == case["expected_sequence"]


@pytest.mark.parametrize("case", _load_fixture()["authority_cases"], ids=lambda c: c["id"])
def test_authority_cases(case):
    target = _signed_target_for_fields(case["scheme"], case["host"], case["port"])
    if case["expected_reason"]:
        with pytest.raises(PinnedConnectionError) as exc_info:
            validate_request_authority(case["request_authority"], target)
        assert exc_info.value.reason_code == case["expected_reason"]
        return
    validate_request_authority(case["request_authority"], target)


@pytest.mark.parametrize("case", _load_fixture()["tls_cases"], ids=lambda c: c["id"])
def test_tls_cases(case):
    if case["insecure_skip_verify"]:
        context = secure_ssl_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with pytest.raises(TLSPolicyError) as exc_info:
            validate_ssl_context(context)
        assert exc_info.value.reason_code == case["expected_reason"]
        return
    if case["server_name"] != case["expected_server_name"]:
        with pytest.raises(TLSPolicyError) as exc_info:
            validate_tls_server_name(case["server_name"], case["expected_server_name"])
        assert exc_info.value.reason_code == case["expected_reason"]
        return
    validate_ssl_context(secure_ssl_context())
    validate_tls_server_name(case["server_name"], case["expected_server_name"])


def test_direct_constructor_rejected():
    with pytest.raises(TypeError):
        PinnedTarget(
            scheme="http",
            normalized_host="example.test",
            port=80,
            authority="example.test",
            host_header="example.test",
            server_name="example.test",
            validated_addresses=("127.0.0.1",),
            is_ip_literal=False,
            policy_identity="default",
        )


def test_forged_targets_rejected_before_socket():
    for addresses in [("127.0.0.1",), ("93.184.216.34",)]:
        target = _unsigned_target_for_test("http", "example.test", 80, addresses)
        factory = FakeSocketFactory()
        with pytest.raises(PinnedConnectionError) as exc_info:
            connect_pinned(target, socket_factory=factory)
        assert exc_info.value.reason_code == "invalid_pinned_target"
        assert factory.sockets == []


def test_dataclasses_replace_cannot_bypass():
    policy = OutboundPolicy(
        allowed_hosts=frozenset({"example.com"}),
        allowed_http=False,
        allowed_ports_by_scheme={"http": frozenset({80}), "https": frozenset({443})},
        max_dns_addresses=16,
        allow_controlled_subdomains=False,
    )
    decision = decide("https://example.com/", policy, resolver=FakeResolver(["93.184.216.34"]))
    target = build_pinned_target(decision, policy)
    with pytest.raises(TypeError):
        replace(target, port=80)


def test_builder_target_uses_global_fake_socket(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("getaddrinfo called")

    monkeypatch.setattr("crawler.security.pinned_connection.socket.getaddrinfo", boom)
    policy = OutboundPolicy(
        allowed_hosts=frozenset({"example.com"}),
        allowed_http=False,
        allowed_ports_by_scheme={"http": frozenset({80}), "https": frozenset({443})},
        max_dns_addresses=16,
        allow_controlled_subdomains=False,
    )
    decision = decide("https://example.com/", policy, resolver=FakeResolver(["93.184.216.34"]))
    target = build_pinned_target(decision, policy)
    factory = FakeSocketFactory()
    sock = connect_pinned(target, socket_factory=factory)
    assert sock.connections[0][0] == "93.184.216.34"


def test_pinned_target_immutable_and_defensive_copy():
    policy = OutboundPolicy(
        allowed_hosts=frozenset({"example.com"}),
        allowed_http=False,
        allowed_ports_by_scheme={"http": frozenset({80}), "https": frozenset({443})},
        max_dns_addresses=16,
        allow_controlled_subdomains=False,
    )
    decision = decide("https://example.com/", policy, resolver=FakeResolver(["93.184.216.34"]))
    target = build_pinned_target(decision, policy)
    with pytest.raises(FrozenInstanceError):
        target.port = 444


def test_authority_mismatch_does_not_call_socket():
    target = _unsigned_target_for_test("http", "example.com", 80, ["93.184.216.34"])
    factory = FakeSocketFactory()
    with pytest.raises(PinnedConnectionError):
        connect_with_authority(target, "other.example", socket_factory=factory)
    assert factory.sockets == []


def test_error_does_not_include_raw_url():
    policy = OutboundPolicy(
        allowed_hosts=frozenset({"example.com"}),
        allowed_http=False,
        allowed_ports_by_scheme={"http": frozenset({80}), "https": frozenset({443})},
        max_dns_addresses=16,
        allow_controlled_subdomains=False,
    )
    decision = decide("https://example.com/", policy, resolver=FakeResolver(["93.184.216.34"]))
    target = build_pinned_target(decision, policy)
    factory = FakeSocketFactory(fail_all=True)
    with pytest.raises(PinnedConnectionError) as exc_info:
        connect_pinned(target, socket_factory=factory)
    assert "example.com" not in str(exc_info.value)
    assert exc_info.value.reason_code == "connection_failed"


def test_secure_context_and_server_name():
    context = secure_ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    validate_ssl_context(context)
    validate_tls_server_name("fixture.example", "fixture.example")


def test_no_module_level_source_token_or_signing_key():
    import crawler.security.pinned_connection as module
    import crawler.security as package

    for name in ("_SOURCE_TOKEN", "_SIGNING_KEY", "_HMAC_KEY", "_INTEGRITY_KEY", "_SECRET", "_SEAL", "_install_pinned_security_layer"):
        assert not hasattr(module, name), name
    assert not hasattr(package, "_SOURCE_TOKEN")
    source = Path("crawler/security/pinned_connection.py").read_text(encoding="utf-8")
    assert "_SOURCE_TOKEN" not in source


def test_leaked_token_cannot_forge_consistent_global_target():
    import crawler.security.pinned_connection as module

    proof_field = "_source_token" if hasattr(module, "_SOURCE_TOKEN") else "_integrity_tag"
    target = object.__new__(PinnedTarget)
    object.__setattr__(target, "scheme", "https")
    object.__setattr__(target, "normalized_host", "other.example")
    object.__setattr__(target, "port", 443)
    object.__setattr__(target, "authority", "other.example")
    object.__setattr__(target, "host_header", "other.example")
    object.__setattr__(target, "server_name", "other.example")
    object.__setattr__(target, "validated_addresses", ("93.184.216.35",))
    object.__setattr__(target, "is_ip_literal", False)
    object.__setattr__(target, "policy_identity", "forged")
    object.__setattr__(target, proof_field, getattr(module, "_SOURCE_TOKEN", ""))
    factory = FakeSocketFactory()
    with pytest.raises(PinnedConnectionError) as exc_info:
        connect_pinned(target, socket_factory=factory)
    assert exc_info.value.reason_code == "invalid_pinned_target"
    assert factory.sockets == []


def test_copied_proof_cannot_retarget_other_global_host():
    valid = _signed_target_for_fixture("https://example.com/", ["93.184.216.34"], _https_policy_for("example.com"))
    target = _clone_signed_target(
        valid,
        scheme="https",
        normalized_host="other.example",
        port=443,
        authority="other.example",
        host_header="other.example",
        server_name="other.example",
        validated_addresses=("93.184.216.35",),
        is_ip_literal=False,
        policy_identity="forged",
    )
    factory = FakeSocketFactory()
    with pytest.raises(PinnedConnectionError) as exc_info:
        connect_pinned(target, socket_factory=factory)
    assert exc_info.value.reason_code == "invalid_pinned_target"
    assert factory.sockets == []


def test_copied_proof_rejects_field_mutations():
    valid = _signed_target_for_fixture("https://example.com/", ["93.184.216.34"], _https_policy_for("example.com"))
    mutations = {
        "host": {
            "normalized_host": "other.example",
            "authority": "other.example",
            "host_header": "other.example",
            "server_name": "other.example",
        },
        "port": {
            "port": 8443,
            "authority": "example.com:8443",
            "host_header": "example.com:8443",
        },
        "authority": {
            "authority": "other.example",
            "host_header": "other.example",
        },
        "host_header": {
            "host_header": "other.example",
        },
        "server_name": {
            "server_name": "other.example",
        },
        "addresses": {
            "validated_addresses": ("93.184.216.35",),
        },
        "policy_identity": {
            "policy_identity": "forged",
        },
    }
    for label, changes in mutations.items():
        target = _clone_signed_target(valid, **changes)
        factory = FakeSocketFactory()
        with pytest.raises(PinnedConnectionError) as exc_info:
            connect_pinned(target, socket_factory=factory)
        assert exc_info.value.reason_code == "invalid_pinned_target", label
        assert factory.sockets == [], label


def test_wrong_or_missing_integrity_tag_rejected():
    valid = _signed_target_for_fixture("https://example.com/", ["93.184.216.34"], _https_policy_for("example.com"))
    proof_field = "_integrity_tag" if hasattr(valid, "_integrity_tag") else "_source_token"
    for tag in ("", "0" * 63, "0" * 64, "0" * 65, "g" * 64):
        target = _clone_signed_target(valid)
        object.__setattr__(target, proof_field, tag)
        factory = FakeSocketFactory()
        with pytest.raises(PinnedConnectionError) as exc_info:
            connect_pinned(target, socket_factory=factory)
        assert exc_info.value.reason_code == "invalid_pinned_target"
        assert factory.sockets == []


def test_identical_capability_copy_accepted():
    valid = _signed_target_for_fixture("https://example.com/", ["93.184.216.34"], _https_policy_for("example.com"))
    target = _clone_signed_target(valid)
    factory = FakeSocketFactory()
    sock = connect_pinned(target, socket_factory=factory)
    assert sock.connections[0][0] == "93.184.216.34"


def test_no_independent_signing_helper_in_module():
    import crawler.security.pinned_connection as module

    for name in ("_sign_target", "_create_target", "_issue_target", "_mint_target", "_for_test"):
        assert not hasattr(module, name), name


def test_subclass_dynamic_addresses_rejected_before_read():
    valid = _signed_target_for_fixture("https://example.com/", ["93.184.216.34"], _https_policy_for("example.com"))

    class Evil(PinnedTarget):
        @property
        def validated_addresses(self):
            self.reads += 1
            return self.safe if self.reads < 5 else ("127.0.0.1",)

        @validated_addresses.setter
        def validated_addresses(self, value):
            self.safe = value

    target = object.__new__(Evil)
    object.__setattr__(target, "reads", 0)
    for name in ("scheme", "normalized_host", "port", "authority", "host_header", "server_name", "is_ip_literal", "policy_identity"):
        object.__setattr__(target, name, object.__getattribute__(valid, name))
    object.__setattr__(target, "validated_addresses", object.__getattribute__(valid, "validated_addresses"))
    object.__setattr__(target, "_integrity_tag", object.__getattribute__(valid, "_integrity_tag"))
    factory = FakeSocketFactory()
    with pytest.raises(PinnedConnectionError) as exc_info:
        connect_pinned(target, socket_factory=factory)
    assert exc_info.value.reason_code == "invalid_pinned_target"
    assert factory.sockets == []
    assert target.reads == 0


def test_benign_identical_subclass_rejected():
    valid = _signed_target_for_fixture("https://example.com/", ["93.184.216.34"], _https_policy_for("example.com"))

    class Copy(PinnedTarget):
        pass

    target = object.__new__(Copy)
    for name in ("scheme", "normalized_host", "port", "authority", "host_header", "server_name", "validated_addresses", "is_ip_literal", "policy_identity", "_integrity_tag"):
        object.__setattr__(target, name, object.__getattribute__(valid, name))
    factory = FakeSocketFactory()
    with pytest.raises(PinnedConnectionError) as exc_info:
        connect_pinned(target, socket_factory=factory)
    assert exc_info.value.reason_code == "invalid_pinned_target"
    assert factory.sockets == []


def test_exact_type_descriptor_snapshot_used_for_dial():
    valid = _signed_target_for_fixture("https://example.com/", ["93.184.216.34"], _https_policy_for("example.com"))
    original_descriptor = PinnedTarget.validated_addresses

    class SnapshotProbe:
        def __init__(self, safe):
            self.safe = safe
            self.reads = 0

        def __get__(self, obj, owner):
            if obj is None:
                return self
            self.reads += 1
            return self.safe if self.reads <= 4 else ("127.0.0.1",)

    try:
        PinnedTarget.validated_addresses = SnapshotProbe(("93.184.216.34",))
        factory = FakeSocketFactory()
        sock = connect_pinned(valid, socket_factory=factory)
        assert sock.connections[0][0] == "93.184.216.34"
        assert PinnedTarget.validated_addresses.reads == 1
    finally:
        PinnedTarget.validated_addresses = original_descriptor


def test_class_property_cannot_spoof_exact_type():
    class Fake:
        @property
        def __class__(self):
            return PinnedTarget

    target = object.__new__(Fake)
    for name, value in dict(
        scheme="https",
        normalized_host="fixture.example",
        port=443,
        authority="fixture.example",
        host_header="fixture.example",
        server_name="fixture.example",
        validated_addresses=("93.184.216.34",),
        is_ip_literal=False,
        policy_identity="default",
        _integrity_tag="0" * 64,
    ).items():
        object.__setattr__(target, name, value)
    factory = FakeSocketFactory()
    with pytest.raises(PinnedConnectionError) as exc_info:
        connect_pinned(target, socket_factory=factory)
    assert exc_info.value.reason_code == "invalid_pinned_target"
    assert factory.sockets == []


def test_no_production_test_switches():
    source = open("crawler/security/pinned_connection.py", encoding="utf-8").read()
    for token in ("allow_loopback", "allow_private", "test_mode", "skip_policy", "PYTEST_CURRENT_TEST"):
        assert token not in source, token


def test_production_has_no_loopback_helper():
    import crawler.security.pinned_connection as module
    import crawler.security as package

    assert not hasattr(module, "_pinned_target_for_test")
    assert not hasattr(package, "_pinned_target_for_test")
    for path in Path("crawler/security").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "_pinned_target_for_test" not in source, path


def test_public_builder_rejects_loopback():
    normalized = normalize_outbound_url("https://example.com/")
    decision = PolicyDecision(allowed=True, reason_code="", normalized=normalized, addresses=("127.0.0.1",))
    with pytest.raises(PinnedConnectionError) as exc_info:
        build_pinned_target(decision)
    assert exc_info.value.reason_code == "ip_not_allowed"


class RoutingSocket:
    def __init__(self, family, socktype, listener_port):
        self._real = socket.socket(family, socktype)
        self.listener_port = listener_port
        self.connections = []

    def settimeout(self, timeout):
        self._real.settimeout(timeout)

    def connect(self, address):
        self.connections.append(address)
        self._real.connect(("127.0.0.1", self.listener_port))

    def send(self, data):
        return self._real.send(data)

    def sendall(self, data):
        return self._real.sendall(data)

    def recv(self, size):
        return self._real.recv(size)

    def close(self):
        self._real.close()


class RoutingSocketFactory:
    def __init__(self, listener_port):
        self.listener_port = listener_port
        self.sockets = []

    def __call__(self, family, socktype):
        sock = RoutingSocket(family, socktype, self.listener_port)
        self.sockets.append(sock)
        return sock


def test_local_http_listener_through_test_router():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    listener_port = server.getsockname()[1]
    received = []

    def accept_one():
        conn, _ = server.accept()
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
        received.append(data)
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
        conn.close()
        server.close()

    thread = threading.Thread(target=accept_one, daemon=True)
    thread.start()
    policy = OutboundPolicy(
        allowed_hosts=frozenset({"example.test"}),
        allowed_http=True,
        allowed_ports_by_scheme={"http": frozenset({listener_port}), "https": frozenset({443})},
        max_dns_addresses=16,
        allow_controlled_subdomains=False,
    )
    decision = decide(f"http://example.test:{listener_port}/", policy, resolver=FakeResolver(["93.184.216.34"]))
    target = build_pinned_target(decision, policy)
    assert "127.0.0.1" not in target.validated_addresses
    factory = RoutingSocketFactory(listener_port)
    sock = connect_pinned(target, socket_factory=factory, timeout=5)
    assert sock.connections[0][0] == "93.184.216.34"
    sock.sendall(f"GET / HTTP/1.1\r\nHost: {target.host_header}\r\nConnection: close\r\n\r\n".encode())
    sock.close()
    thread.join(timeout=5)
    assert received
    assert f"Host: {target.host_header}".encode() in received[0]
