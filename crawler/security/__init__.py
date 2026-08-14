"""TASK-022B outbound request security foundations."""

from crawler.security.models import (
    DNSValidationResult,
    IPClassification,
    NormalizedURL,
    OutboundPolicy,
    PolicyDecision,
)
from crawler.security.dns_policy import DNSValidationError, resolve_and_validate
from crawler.security.ip_policy import classify_ip
from crawler.security.outbound_policy import decide, default_policy, evaluate
from crawler.security.pinned_connection import (
    PinnedConnectionError,
    PinnedTarget,
    build_pinned_target,
    connect_pinned,
    connect_with_authority,
    prepare_request_host_header,
    validate_request_authority,
)
from crawler.security.tls_policy import TLSPolicyError, secure_ssl_context, validate_ssl_context, validate_tls_server_name, wrap_client_socket
from crawler.security.url_normalizer import URLNormalizationError, normalize_outbound_url

__all__ = [
    "DNSValidationError",
    "DNSValidationResult",
    "IPClassification",
    "NormalizedURL",
    "OutboundPolicy",
    "PolicyDecision",
    "PinnedConnectionError",
    "PinnedTarget",
    "TLSPolicyError",
    "URLNormalizationError",
    "build_pinned_target",
    "classify_ip",
    "connect_pinned",
    "connect_with_authority",
    "decide",
    "default_policy",
    "evaluate",
    "normalize_outbound_url",
    "prepare_request_host_header",
    "resolve_and_validate",
    "secure_ssl_context",
    "validate_request_authority",
    "validate_ssl_context",
    "validate_tls_server_name",
    "wrap_client_socket",
]
