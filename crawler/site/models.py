"""Internal models for TASK-016 analysis output."""

from dataclasses import dataclass, field
from typing import Any, Tuple


@dataclass(frozen=True)
class Diagnostic:
    code: str
    stage: str
    message: str
    severity: str = "error"
    retryable: bool = False
    details: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "stage": self.stage,
            "message": self.message,
            "severity": self.severity,
            "retryable": self.retryable,
            "details": list(self.details),
        }


@dataclass(frozen=True)
class DiscoveryLimits:
    timeout: float = 10.0
    max_redirects: int = 5
    max_response_bytes: int = 2_000_000
    allowed_content_types: Tuple[str, ...] = ("text/html", "application/xhtml+xml")
    max_forms: int = 50
    max_inputs_per_form: int = 50
    max_candidates: int = 30
    max_script_chars: int = 50_000
    max_links_meta: int = 200
    max_common_paths: int = 5
    max_evidence_items: int = 20
    max_evidence_chars: int = 500


@dataclass(frozen=True)
class SearchCandidate:
    method: str
    endpoint: str
    keyword_param: str
    fixed_params: Tuple[Tuple[str, str], ...] = ()
    request_encoding: str = ""
    source: str = ""
    priority: int = 0
    scope: str = "same_origin"
    evidence: Tuple[str, ...] = ()
    status: str = "unverified"

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "endpoint": self.endpoint,
            "keyword_param": self.keyword_param,
            "fixed_params": list(self.fixed_params),
            "request_encoding": self.request_encoding,
            "source": self.source,
            "priority": self.priority,
            "scope": self.scope,
            "evidence": list(self.evidence),
            "status": self.status,
        }


@dataclass(frozen=True)
class SiteAnalysisResult:
    normalized_url: str
    final_url: str
    candidates: Tuple[SearchCandidate, ...] = ()
    diagnostics: Tuple[Diagnostic, ...] = ()
    fetch_summary: dict[str, Any] = field(default_factory=dict)
    analyzer_version: str = "0.1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized_url": self.normalized_url,
            "final_url": self.final_url,
            "candidates": [c.to_dict() for c in self.candidates],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "fetch_summary": self.fetch_summary,
            "analyzer_version": self.analyzer_version,
        }
