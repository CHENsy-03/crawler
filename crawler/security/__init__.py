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
from crawler.security.transport_budget import (
    BudgetError,
    BudgetProfile,
    TransportBudget,
    budget_for,
    capped_stage_timeout,
    check_request_body_size,
    check_response_body_size,
    check_response_headers_size,
    remaining_deadline,
    validate_proxy,
)
from crawler.security.redirect_policy import (
    RedirectHop,
    RedirectPlan,
    RedirectPolicyError,
    plan_redirect_hop,
    plan_redirects,
)

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
    "BudgetError",
    "BudgetProfile",
    "RedirectHop",
    "RedirectPlan",
    "RedirectPolicyError",
    "TransportBudget",
    "budget_for",
    "capped_stage_timeout",
    "check_request_body_size",
    "check_response_body_size",
    "check_response_headers_size",
    "plan_redirect_hop",
    "plan_redirects",
    "remaining_deadline",
    "validate_proxy",
    "wrap_client_socket",
]
