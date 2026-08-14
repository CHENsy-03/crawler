"""TLS policy helpers for TASK-022C pinned connections."""

from __future__ import annotations

import ssl


class TLSPolicyError(ValueError):
    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(message or reason_code)
        self.reason_code = reason_code


def secure_ssl_context() -> ssl.SSLContext:
    """Return a system-root TLS context with mandatory hostname verification."""
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def validate_ssl_context(context: ssl.SSLContext) -> None:
    """Reject contexts that disable certificate or hostname verification."""
    if getattr(context, "verify_mode", None) != ssl.CERT_REQUIRED:
        raise TLSPolicyError("insecure_tls_context")
    if getattr(context, "check_hostname", None) is not True:
        raise TLSPolicyError("insecure_tls_hostname_check")


def validate_tls_server_name(server_name: str, expected_server_name: str) -> None:
    if server_name != expected_server_name:
        raise TLSPolicyError("tls_server_name_mismatch")


def wrap_client_socket(context: ssl.SSLContext, sock, server_name: str):
    """Wrap a connected socket with a validated context and fixed server_name."""
    validate_ssl_context(context)
    return context.wrap_socket(sock, server_hostname=server_name)
