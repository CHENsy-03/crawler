"""TASK-016 site analysis and candidate discovery package."""

from crawler.site.models import (
    Diagnostic,
    DiscoveryLimits,
    SearchCandidate,
    SiteAnalysisResult,
)
from crawler.site.normalizer import SiteNormalizationError, normalize_target_url
from crawler.site.security import SecurityPolicyError, security_check
from crawler.site.analyzer import SiteAnalyzer, analyze_site

__all__ = [
    "Diagnostic",
    "DiscoveryLimits",
    "SearchCandidate",
    "SiteAnalysisResult",
    "SiteNormalizationError",
    "normalize_target_url",
    "SecurityPolicyError",
    "security_check",
    "SiteAnalyzer",
    "analyze_site",
]
