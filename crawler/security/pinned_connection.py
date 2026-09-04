"""Pinned address connection target for TASK-022C/FIX4.

This module only creates and dials PinnedTarget objects. It never resolves a
hostname through the system resolver and never follows redirects. Ordinary
callers cannot construct PinnedTarget directly; only build_pinned_target can
issue a signed target. connect_pinned requires the exact PinnedTarget type,
captures all security fields once into an immutable snapshot, verifies the
content-bound HMAC and structural invariants against that snapshot, and dials
only from the snapshot.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import secrets
from dataclasses import dataclass, field
from importlib import import_module
from typing import Callable, Sequence

from crawler.security.ip_policy import classify_ip
from crawler.security.models import NormalizedURL, OutboundPolicy, PolicyDecision
from crawler.security.outbound_policy import evaluate
from crawler.security.tls_policy import TLSPolicyError, secure_ssl_context, validate_ssl_context, wrap_client_socket
from crawler.security.url_normalizer import normalize_outbound_url

socket = import_module("socket")

MAX_VALIDATED_ADDRESSES = 16


class PinnedConnectionError(ValueError):
    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(message or reason_code)
        self.reason_code = reason_code


def _stable_addresses(addresses: Sequence[str]) -> list[str]:
    parsed = []
    seen = set()
    for raw in addresses:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            raise PinnedConnectionError("invalid_address")
        canonical = str(ip)
        if canonical in seen:
            continue
        seen.add(canonical)
        parsed.append(ip)
    parsed.sort(key=lambda ip: (ip.version, ip.packed))
    return [str(ip) for ip in parsed]


def _validated_addresses(addresses: Sequence[str]) -> list[str]:
    normalized = _stable_addresses(addresses)
    if not normalized:
        raise PinnedConnectionError("empty_addresses")
    if len(normalized) > MAX_VALIDATED_ADDRESSES:
        raise PinnedConnectionError("too_many_addresses")
    for address in normalized:
        classification = classify_ip(address)
        if not classification.allowed:
            raise PinnedConnectionError("ip_not_allowed")
    return normalized


def _build_host_header(scheme: str, host: str, port: int) -> str:
    host_for_authority = f"[{host}]" if ":" in host else host
    default_port = 80 if scheme == "http" else 443
    if port == default_port:
        return host_for_authority
    return f"{host_for_authority}:{port}"


def _install_pinned_security_layer():
    signing_key = secrets.token_bytes(32)

    def _canonical_payload(
        scheme: str,
        normalized_host: str,
        port: int,
        authority: str,
        host_header: str,
        server_name: str,
        validated_addresses: Sequence[str],
        is_ip_literal: bool,
        policy_identity: str,
    ) -> bytes:
        payload = [
            "crawler.pinned-target.v1",
            scheme,
            normalized_host,
            port,
            authority,
            host_header,
            server_name,
            list(validated_addresses),
            is_ip_literal,
            policy_identity,
        ]
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")

    def _compute_tag(
        scheme: str,
        normalized_host: str,
        port: int,
        authority: str,
        host_header: str,
        server_name: str,
        validated_addresses: Sequence[str],
        is_ip_literal: bool,
        policy_identity: str,
    ) -> str:
        payload = _canonical_payload(
            scheme,
            normalized_host,
            port,
            authority,
            host_header,
            server_name,
            validated_addresses,
            is_ip_literal,
            policy_identity,
        )
        return hmac.new(signing_key, payload, hashlib.sha256).hexdigest()

    @dataclass(frozen=True, init=False, slots=True)
    class PinnedTarget:
        scheme: str
        normalized_host: str
        port: int
        authority: str
        host_header: str
        server_name: str
        validated_addresses: tuple[str, ...]
        is_ip_literal: bool
        policy_identity: str
        _integrity_tag: str = field(default="", init=False, repr=False, compare=False)

        def __init__(self, *args, **kwargs):
            raise TypeError("PinnedTarget must be created through build_pinned_target")

        def __repr__(self) -> str:
            return (
                f"PinnedTarget(scheme={self.scheme!r}, host={self.normalized_host!r}, "
                f"port={self.port!r}, addresses={self.validated_addresses!r})"
            )

    @dataclass(frozen=True, slots=True)
    class _VerifiedPinnedSnapshot:
        scheme: str
        normalized_host: str
        port: int
        authority: str
        host_header: str
        server_name: str
        validated_addresses: tuple[str, ...]
        is_ip_literal: bool
        policy_identity: str
        integrity_tag: str

    def _capture_snapshot(target: PinnedTarget) -> _VerifiedPinnedSnapshot:
        try:
            scheme = object.__getattribute__(target, "scheme")
            normalized_host = object.__getattribute__(target, "normalized_host")
            port = object.__getattribute__(target, "port")
            authority = object.__getattribute__(target, "authority")
            host_header = object.__getattribute__(target, "host_header")
            server_name = object.__getattribute__(target, "server_name")
            raw_addresses = object.__getattribute__(target, "validated_addresses")
            is_ip_literal = object.__getattribute__(target, "is_ip_literal")
            policy_identity = object.__getattribute__(target, "policy_identity")
            try:
                integrity_tag = object.__getattribute__(target, "_integrity_tag")
            except AttributeError:
                integrity_tag = ""
        except Exception:
            raise PinnedConnectionError("invalid_pinned_target")
        if not isinstance(raw_addresses, tuple):
            raise PinnedConnectionError("invalid_pinned_target")
        if any(not isinstance(address, str) for address in raw_addresses):
            raise PinnedConnectionError("invalid_pinned_target")
        return _VerifiedPinnedSnapshot(
            scheme=scheme,
            normalized_host=normalized_host,
            port=port,
            authority=authority,
            host_header=host_header,
            server_name=server_name,
            validated_addresses=tuple(raw_addresses),
            is_ip_literal=is_ip_literal,
            policy_identity=policy_identity,
            integrity_tag=integrity_tag,
        )

    def build_pinned_target(
        decision: PolicyDecision,
        policy: OutboundPolicy | None = None,
        *,
        policy_identity: str = "default",
    ) -> PinnedTarget:
        if not decision.allowed or decision.reason_code or decision.normalized is None:
            raise PinnedConnectionError("policy_not_allowed")
        if not isinstance(policy_identity, str):
            raise PinnedConnectionError("invalid_pinned_target")
        normalized: NormalizedURL = decision.normalized
        addresses = _validated_addresses(decision.addresses)
        if policy is not None:
            from crawler.security.models import DNSValidationResult

            dns = DNSValidationResult(
                host=normalized.host,
                addresses=tuple(addresses),
                allowed=True,
                reason_code="",
            )
            redecided = evaluate(normalized, dns, policy, None)
            if not redecided.allowed:
                raise PinnedConnectionError("policy_not_allowed")

        host_header = _build_host_header(normalized.scheme, normalized.host, normalized.port)
        tag = _compute_tag(
            normalized.scheme,
            normalized.host,
            normalized.port,
            host_header,
            host_header,
            normalized.host,
            tuple(addresses),
            normalized.is_ip_literal,
            policy_identity,
        )
        target = object.__new__(PinnedTarget)
        object.__setattr__(target, "_integrity_tag", tag)
        object.__setattr__(target, "scheme", normalized.scheme)
        object.__setattr__(target, "normalized_host", normalized.host)
        object.__setattr__(target, "port", normalized.port)
        object.__setattr__(target, "authority", host_header)
        object.__setattr__(target, "host_header", host_header)
        object.__setattr__(target, "server_name", normalized.host)
        object.__setattr__(target, "validated_addresses", tuple(addresses))
        object.__setattr__(target, "is_ip_literal", normalized.is_ip_literal)
        object.__setattr__(target, "policy_identity", policy_identity)
        return target

    def _verify_snapshot(snapshot: _VerifiedPinnedSnapshot) -> None:
        if not snapshot.validated_addresses:
            raise PinnedConnectionError("empty_addresses")
        tag = snapshot.integrity_tag
        if (
            not isinstance(tag, str)
            or len(tag) != 64
            or any(c not in "0123456789abcdef" for c in tag)
        ):
            raise PinnedConnectionError("invalid_pinned_target")
        expected = _compute_tag(
            snapshot.scheme,
            snapshot.normalized_host,
            snapshot.port,
            snapshot.authority,
            snapshot.host_header,
            snapshot.server_name,
            snapshot.validated_addresses,
            snapshot.is_ip_literal,
            snapshot.policy_identity,
        )
        if not hmac.compare_digest(tag, expected):
            raise PinnedConnectionError("invalid_pinned_target")
        if snapshot.scheme not in ("http", "https"):
            raise PinnedConnectionError("invalid_pinned_target")
        if not isinstance(snapshot.normalized_host, str) or not snapshot.normalized_host:
            raise PinnedConnectionError("invalid_pinned_target")
        if not isinstance(snapshot.policy_identity, str) or not isinstance(snapshot.is_ip_literal, bool):
            raise PinnedConnectionError("invalid_pinned_target")
        if not isinstance(snapshot.port, int) or isinstance(snapshot.port, bool):
            raise PinnedConnectionError("invalid_pinned_target")
        expected_host_header = _build_host_header(snapshot.scheme, snapshot.normalized_host, snapshot.port)
        if (
            snapshot.host_header != expected_host_header
            or snapshot.authority != expected_host_header
            or snapshot.server_name != snapshot.normalized_host
        ):
            raise PinnedConnectionError("invalid_pinned_target")
        checked = tuple(_validated_addresses(snapshot.validated_addresses))
        if checked != snapshot.validated_addresses:
            raise PinnedConnectionError("invalid_pinned_target")

    def _ensure_signed_target(target: PinnedTarget) -> _VerifiedPinnedSnapshot:
        if type(target) is not PinnedTarget:
            raise PinnedConnectionError("invalid_pinned_target")
        snapshot = _capture_snapshot(target)
        _verify_snapshot(snapshot)
        return snapshot

    def _validate_authority_snapshot(request_value: str, snapshot: _VerifiedPinnedSnapshot) -> None:
        if "://" in request_value:
            normalized = normalize_outbound_url(request_value)
            if normalized.scheme != snapshot.scheme:
                raise PinnedConnectionError("scheme_mismatch")
            expected = _build_host_header(normalized.scheme, normalized.host, normalized.port)
            if expected != snapshot.authority:
                raise PinnedConnectionError("authority_mismatch")
            return
        if request_value != snapshot.host_header:
            raise PinnedConnectionError("authority_mismatch")

    def prepare_request_host_header(request_host: str | None, target: PinnedTarget) -> str:
        snapshot = _ensure_signed_target(target)
        if not request_host:
            return snapshot.host_header
        if request_host != snapshot.host_header:
            raise PinnedConnectionError("host_header_mismatch")
        return snapshot.host_header

    def validate_request_authority(request_value: str, target: PinnedTarget) -> None:
        snapshot = _ensure_signed_target(target)
        _validate_authority_snapshot(request_value, snapshot)

    def _connect_snapshot(
        snapshot: _VerifiedPinnedSnapshot,
        *,
        socket_factory: Callable[[int, int], socket.socket] | None = None,
        timeout: float = 5.0,
    ):
        for address in snapshot.validated_addresses:
            ip = ipaddress.ip_address(address)
            family = socket.AF_INET if ip.version == 4 else socket.AF_INET6
            sock = socket_factory(family, socket.SOCK_STREAM) if socket_factory else socket.socket(family, socket.SOCK_STREAM)
            try:
                sock.settimeout(timeout)
                sock.connect((address, snapshot.port))
                return sock
            except Exception:
                try:
                    sock.close()
                except Exception:
                    pass
        raise PinnedConnectionError("connection_failed")

    def connect_pinned(
        target: PinnedTarget,
        *,
        socket_factory: Callable[[int, int], socket.socket] | None = None,
        timeout: float = 5.0,
    ):
        snapshot = _ensure_signed_target(target)
        return _connect_snapshot(snapshot, socket_factory=socket_factory, timeout=timeout)

    def connect_with_authority(
        target: PinnedTarget,
        request_value: str,
        *,
        socket_factory: Callable[[int, int], socket.socket] | None = None,
        timeout: float = 5.0,
    ):
        snapshot = _ensure_signed_target(target)
        _validate_authority_snapshot(request_value, snapshot)
        return _connect_snapshot(snapshot, socket_factory=socket_factory, timeout=timeout)

    return {
        "PinnedTarget": PinnedTarget,
        "build_pinned_target": build_pinned_target,
        "connect_pinned": connect_pinned,
        "connect_with_authority": connect_with_authority,
        "prepare_request_host_header": prepare_request_host_header,
        "validate_request_authority": validate_request_authority,
    }


_security_layer = _install_pinned_security_layer()
PinnedTarget = _security_layer["PinnedTarget"]
build_pinned_target = _security_layer["build_pinned_target"]
connect_pinned = _security_layer["connect_pinned"]
connect_with_authority = _security_layer["connect_with_authority"]
prepare_request_host_header = _security_layer["prepare_request_host_header"]
validate_request_authority = _security_layer["validate_request_authority"]
del _security_layer
del _install_pinned_security_layer
