"""Serializable SearchPlan and SearchHit models shared with the Go protocol layer."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from protocol.messages import PROTOCOL_VERSION_V2, ProtocolError, validate_target_url

PLAN_STATUS_DRAFT = "draft"
PLAN_STATUS_READY = "ready"
PLAN_STATUS_ACTIVE = "active"
PLAN_STATUS_EXPIRED = "expired"
PLAN_STATUSES = {PLAN_STATUS_DRAFT, PLAN_STATUS_READY, PLAN_STATUS_ACTIVE, PLAN_STATUS_EXPIRED}

SEARCH_STRATEGY_HTML_FORM = "html_form"
SEARCH_STRATEGY_JSON_API = "json_api"
SEARCH_STRATEGY_RSS = "rss"
SEARCH_STRATEGY_SITEMAP = "sitemap"
SEARCH_STRATEGY_UNKNOWN = "unknown"
SEARCH_STRATEGIES = {
    SEARCH_STRATEGY_HTML_FORM,
    SEARCH_STRATEGY_JSON_API,
    SEARCH_STRATEGY_RSS,
    SEARCH_STRATEGY_SITEMAP,
    SEARCH_STRATEGY_UNKNOWN,
}

ALLOWED_HTTP_METHODS = {"GET", "POST"}


def _require_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError("INVALID_INTEGER", f"{field_name} must be an integer")
    return value


@dataclass(frozen=True)
class SearchPagination:
    max_pages: int
    page_param: str
    page_size_param: str
    page_size: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_pages", _require_int(self.max_pages, "pagination.max_pages"))
        object.__setattr__(self, "page_size", _require_int(self.page_size, "pagination.page_size"))


@dataclass(frozen=True)
class SearchSelectors:
    result_item: str
    title: str
    url: str
    snippet: str
    body: str


@dataclass(frozen=True)
class SearchScope:
    domain: str
    allowed_path_prefixes: list[str] = field(default_factory=list)
    max_depth: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_path_prefixes", list(self.allowed_path_prefixes or []))
        object.__setattr__(self, "max_depth", _require_int(self.max_depth, "scope.max_depth"))


@dataclass(frozen=True)
class SearchDiscovery:
    evidence: list[str] = field(default_factory=list)
    confidence: int = 0
    source: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", list(self.evidence or []))
        object.__setattr__(self, "confidence", _require_int(self.confidence, "discovery.confidence"))


@dataclass(frozen=True)
class SearchPlan:
    plan_id: str
    endpoint: str
    protocol_version: str = PROTOCOL_VERSION_V2
    status: str = PLAN_STATUS_DRAFT
    strategy: str = SEARCH_STRATEGY_UNKNOWN
    http_method: str = "GET"
    query_params: dict[str, str] = field(default_factory=dict)
    request_body_template: str = ""
    pagination: SearchPagination = field(
        default_factory=lambda: SearchPagination(1, "page", "size", 10)
    )
    selectors: SearchSelectors = field(default_factory=lambda: SearchSelectors("", "", "", "", ""))
    scope: SearchScope = field(default_factory=SearchScope)
    discovery: SearchDiscovery = field(default_factory=SearchDiscovery)
    created_from: str = ""
    created_at: str = ""
    expires_at: str = ""
    invalid_reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "query_params", dict(self.query_params or {}))
        if self.pagination is None:
            object.__setattr__(self, "pagination", SearchPagination(1, "page", "size", 10))
        if self.selectors is None:
            object.__setattr__(self, "selectors", SearchSelectors("", "", "", "", ""))
        if self.scope is None:
            object.__setattr__(self, "scope", SearchScope(""))
        if self.discovery is None:
            object.__setattr__(self, "discovery", SearchDiscovery())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return _go_style_json(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchPlan":
        return cls(
            plan_id=data["plan_id"],
            endpoint=data["endpoint"],
            protocol_version=data.get("protocol_version", PROTOCOL_VERSION_V2),
            status=data.get("status", PLAN_STATUS_DRAFT),
            strategy=data.get("strategy", SEARCH_STRATEGY_UNKNOWN),
            http_method=data.get("http_method", "GET"),
            query_params=dict(data.get("query_params") or {}),
            request_body_template=data.get("request_body_template", ""),
            pagination=SearchPagination(**data.get("pagination", {})),
            selectors=SearchSelectors(**data.get("selectors", {})),
            scope=SearchScope(**data.get("scope", {})),
            discovery=SearchDiscovery(**data.get("discovery", {})),
            created_from=data.get("created_from", ""),
            created_at=data.get("created_at", ""),
            expires_at=data.get("expires_at", ""),
            invalid_reason=data.get("invalid_reason", ""),
        )


@dataclass(frozen=True)
class SearchHit:
    hit_id: str
    plan_id: str
    url: str
    title: str = ""
    snippet: str = ""
    published_at: str = ""
    score: int = 0
    matched_keywords: list[str] = field(default_factory=list)
    source: str = ""
    discovered_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "matched_keywords", list(self.matched_keywords or []))
        object.__setattr__(self, "score", _require_int(self.score, "search_hit.score"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return _go_style_json(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchHit":
        return cls(
            hit_id=data["hit_id"],
            plan_id=data["plan_id"],
            url=data["url"],
            title=data.get("title", ""),
            snippet=data.get("snippet", ""),
            published_at=data.get("published_at", ""),
            score=data.get("score", 0),
            matched_keywords=list(data.get("matched_keywords") or []),
            source=data.get("source", ""),
            discovered_at=data.get("discovered_at", ""),
        )


def validate_search_plan(plan: SearchPlan) -> None:
    if plan.protocol_version != PROTOCOL_VERSION_V2:
        raise ProtocolError(
            "INVALID_PLAN_VERSION",
            f"search_plan protocol_version must be {PROTOCOL_VERSION_V2!r}",
        )
    if not plan.plan_id:
        raise ProtocolError("INVALID_PLAN_ID", "search_plan plan_id is required")
    if plan.status not in PLAN_STATUSES:
        raise ProtocolError("INVALID_PLAN_STATUS", f"search_plan status {plan.status!r} is not allowed")
    if plan.strategy not in SEARCH_STRATEGIES:
        raise ProtocolError(
            "INVALID_PLAN_STRATEGY",
            f"search_plan strategy {plan.strategy!r} is not allowed",
        )
    if plan.http_method not in ALLOWED_HTTP_METHODS:
        raise ProtocolError(
            "INVALID_HTTP_METHOD",
            f"search_plan http_method {plan.http_method!r} is not allowed",
        )
    try:
        validate_target_url(plan.endpoint)
    except ProtocolError as exc:
        raise ProtocolError("INVALID_PLAN_ENDPOINT", f"search_plan endpoint: {exc}") from exc
    if plan.pagination.max_pages < 1:
        raise ProtocolError("INVALID_PAGINATION", "search_plan pagination.max_pages must be >= 1")
    if plan.pagination.page_size < 1:
        raise ProtocolError("INVALID_PAGINATION", "search_plan pagination.page_size must be >= 1")
    if not plan.scope.domain:
        raise ProtocolError("INVALID_SCOPE", "search_plan scope.domain is required")
    if plan.scope.max_depth < 0:
        raise ProtocolError("INVALID_SCOPE", "search_plan scope.max_depth must be >= 0")
    if not 0 <= plan.discovery.confidence <= 100:
        raise ProtocolError(
            "INVALID_CONFIDENCE",
            "search_plan discovery.confidence must be between 0 and 100",
        )


def validate_search_hit(hit: SearchHit) -> None:
    if not hit.hit_id:
        raise ProtocolError("INVALID_HIT_ID", "search_hit hit_id is required")
    if not hit.plan_id:
        raise ProtocolError("INVALID_HIT_PLAN_ID", "search_hit plan_id is required")
    try:
        validate_target_url(hit.url)
    except ProtocolError as exc:
        raise ProtocolError("INVALID_HIT_URL", f"search_hit url: {exc}") from exc


def _go_style_json(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    text = text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    text = text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return text


def _canonical_plan_content(plan: SearchPlan) -> dict[str, Any]:
    return {
        "protocol_version": plan.protocol_version,
        "strategy": plan.strategy,
        "endpoint": plan.endpoint,
        "http_method": plan.http_method,
        "query_params": dict(plan.query_params),
        "request_body_template": plan.request_body_template,
        "pagination": {
            "max_pages": plan.pagination.max_pages,
            "page_param": plan.pagination.page_param,
            "page_size_param": plan.pagination.page_size_param,
            "page_size": plan.pagination.page_size,
        },
        "selectors": {
            "result_item": plan.selectors.result_item,
            "title": plan.selectors.title,
            "url": plan.selectors.url,
            "snippet": plan.selectors.snippet,
            "body": plan.selectors.body,
        },
        "scope": {
            "domain": plan.scope.domain,
            "allowed_path_prefixes": list(plan.scope.allowed_path_prefixes),
            "max_depth": plan.scope.max_depth,
        },
        "discovery": {
            "evidence": list(plan.discovery.evidence),
            "confidence": plan.discovery.confidence,
            "source": plan.discovery.source,
        },
        "created_from": plan.created_from,
    }


def _canonical_json(content: dict[str, Any]) -> str:
    canonical = json.dumps(
        content,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    canonical = canonical.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return canonical


def canonical_plan_json(plan: SearchPlan) -> str:
    """Return the stable canonical JSON used for plan_id."""
    return _canonical_json(_canonical_plan_content(plan))


def compute_plan_id(plan: SearchPlan) -> str:
    """Compute a stable SHA-256 plan_id over sorted canonical JSON."""
    canonical = canonical_plan_json(plan).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
