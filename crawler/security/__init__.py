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
from crawler.security.url_normalizer import URLNormalizationError, normalize_outbound_url

__all__ = [
    "DNSValidationError",
    "DNSValidationResult",
    "IPClassification",
    "NormalizedURL",
    "OutboundPolicy",
    "PolicyDecision",
    "URLNormalizationError",
    "classify_ip",
    "decide",
    "default_policy",
    "evaluate",
    "normalize_outbound_url",
    "resolve_and_validate",
]
