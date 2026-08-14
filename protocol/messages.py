import hashlib
import json
import math
import uuid
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Union
from urllib.parse import urlparse

PROTOCOL_VERSION = "1.0"
PROTOCOL_VERSION_V2 = "2.0"
MESSAGE_TYPE_SEARCH = "search"
MESSAGE_TYPE_SEARCH_REQUESTED = "search_requested"
DEFAULT_LEVEL = 0
DEFAULT_MAX_PAGES = 1

V1_SEARCH_FIELDS = {
    "protocol_version", "task_id", "message_id", "timestamp", "type",
    "site", "keyword", "level", "max_pages",
}
V2_SEARCH_FIELDS = {
    "protocol_version", "task_id", "message_id", "timestamp", "type",
    "target_url", "keywords", "level", "max_pages",
}


def new_task_id() -> str:
    return uuid.uuid4().hex[:12]


def new_message_id() -> str:
    return uuid.uuid4().hex[:8]


class ProtocolError(ValueError):
    """Structured protocol validation error with a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, kw_only=True)
class MessageEnvelope:
    task_id: str
    message_id: str
    timestamp: str
    protocol_version: str = PROTOCOL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, kw_only=True)
class SearchMessage(MessageEnvelope):
    type: Literal["search"] = "search"
    site: str
    keyword: str
    level: int = DEFAULT_LEVEL
    max_pages: int = DEFAULT_MAX_PAGES

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", _require_protocol_int(self.level, "level"))
        object.__setattr__(self, "max_pages", _require_protocol_int(self.max_pages, "max_pages"))


@dataclass(frozen=True, kw_only=True)
class SearchRequestedMessage(MessageEnvelope):
    type: Literal["search_requested"] = "search_requested"
    target_url: str
    keywords: list[str]
    level: int = DEFAULT_LEVEL
    max_pages: int = DEFAULT_MAX_PAGES

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", _require_protocol_int(self.level, "level"))
        object.__setattr__(self, "max_pages", _require_protocol_int(self.max_pages, "max_pages"))


def validate_target_url(raw: str) -> None:
    if not isinstance(raw, str):
        raise ProtocolError("INVALID_TARGET_URL", "target_url must be a string")
    if raw != raw.strip():
        raise ProtocolError("INVALID_TARGET_URL", "target_url must not have leading or trailing whitespace")
    if not raw:
        raise ProtocolError("INVALID_TARGET_URL", "target_url is required")
    try:
        parsed = urlparse(raw)
        if parsed.scheme.lower() not in ("http", "https"):
            raise ProtocolError("INVALID_TARGET_URL", "target_url must use http or https")
        if not parsed.hostname:
            raise ProtocolError("INVALID_TARGET_URL", "target_url must include a host")
        if parsed.netloc.endswith(":"):
            raise ProtocolError("INVALID_TARGET_URL", "target_url must not have an empty port")
        parsed.port
    except ValueError as exc:
        raise ProtocolError("INVALID_TARGET_URL", "target_url has invalid port or authority") from exc


def normalize_keywords(keywords: list[str]) -> list[str]:
    if not isinstance(keywords, list):
        raise ProtocolError("INVALID_KEYWORD", "keywords must be a JSON array")
    seen: set[str] = set()
    normalized: list[str] = []
    for keyword in keywords:
        if not isinstance(keyword, str):
            raise ProtocolError("INVALID_KEYWORD", "keywords must contain only strings")
        keyword = keyword.strip()
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        normalized.append(keyword)
    if not normalized:
        raise ProtocolError("EMPTY_KEYWORDS", "keywords must contain at least one non-blank keyword")
    return normalized


def _require_protocol_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError("INVALID_INTEGER", f"{field_name} must be an integer")
    return value


def _reject_unknown_fields(data: dict[str, Any], allowed: set[str]) -> None:
    unknown = set(data) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ProtocolError("UNKNOWN_FIELD", f"unknown field(s): {names}")


def _require_non_blank_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError("INVALID_MESSAGE", f"v1 search {field} must be a non-blank string")
    return value.strip()


def _reject_null_optional(data: dict[str, Any], field: str) -> None:
    if field in data and data[field] is None:
        raise ProtocolError("INVALID_MESSAGE", f"{field} must not be null")


def decode_search_request(raw: Union[str, bytes]) -> Union[SearchMessage, SearchRequestedMessage]:
    """Decode a search message by explicit protocol_version, never by field inference."""
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError("INVALID_JSON", "search request is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ProtocolError("INVALID_MESSAGE", "search request must be a JSON object")

    protocol_version = data.get("protocol_version")
    if protocol_version is None:
        raise ProtocolError("MISSING_PROTOCOL_VERSION", "protocol_version is required")

    for field in ("task_id", "message_id", "timestamp"):
        if field not in data:
            raise ProtocolError("INVALID_MESSAGE", f"search request {field} is required")

    if protocol_version == PROTOCOL_VERSION:
        _reject_unknown_fields(data, V1_SEARCH_FIELDS)
        if data.get("type") != MESSAGE_TYPE_SEARCH:
            raise ProtocolError("INVALID_TYPE", "v1 search type must be 'search'")
        for field in ("site", "keyword"):
            if field not in data:
                raise ProtocolError("INVALID_MESSAGE", f"v1 search {field} is required")
        site = _require_non_blank_string(data.get("site"), "site")
        keyword = _require_non_blank_string(data.get("keyword"), "keyword")
        _reject_null_optional(data, "level")
        _reject_null_optional(data, "max_pages")
        try:
            return SearchMessage(
                task_id=data["task_id"],
                message_id=data["message_id"],
                timestamp=data["timestamp"],
                protocol_version=protocol_version,
                site=site,
                keyword=keyword,
                level=data.get("level", DEFAULT_LEVEL),
                max_pages=data.get("max_pages", DEFAULT_MAX_PAGES),
            )
        except TypeError as exc:
            raise ProtocolError("INVALID_MESSAGE", "invalid v1 search message") from exc

    if protocol_version == PROTOCOL_VERSION_V2:
        _reject_unknown_fields(data, V2_SEARCH_FIELDS)
        if data.get("type") != MESSAGE_TYPE_SEARCH_REQUESTED:
            raise ProtocolError("INVALID_TYPE", "v2 search type must be 'search_requested'")
        for field in ("target_url", "keywords"):
            if field not in data:
                raise ProtocolError("INVALID_MESSAGE", f"v2 search {field} is required")
        _reject_null_optional(data, "level")
        _reject_null_optional(data, "max_pages")
        target_url = data["target_url"]
        if not isinstance(target_url, str):
            raise ProtocolError("INVALID_TARGET_URL", "target_url must be a string")
        validate_target_url(target_url)
        normalized = normalize_keywords(data["keywords"])
        try:
            return SearchRequestedMessage(
                task_id=data["task_id"],
                message_id=data["message_id"],
                timestamp=data["timestamp"],
                protocol_version=protocol_version,
                target_url=target_url,
                keywords=normalized,
                level=data.get("level", DEFAULT_LEVEL),
                max_pages=data.get("max_pages", DEFAULT_MAX_PAGES),
            )
        except TypeError as exc:
            raise ProtocolError("INVALID_MESSAGE", "invalid v2 search message") from exc

    raise ProtocolError("UNKNOWN_PROTOCOL_VERSION", f"unsupported protocol_version {protocol_version!r}")


@dataclass(frozen=True, kw_only=True)
class URLMessage(MessageEnvelope):
    type: Literal["url"] = "url"
    url: str
    site: str
    keyword: str
    level: int
    title: str


@dataclass(frozen=True, kw_only=True)
class HTMLMessage(MessageEnvelope):
    type: Literal["html"] = "html"
    url: str
    site: str
    keyword: str
    level: int
    title: str
    html: str


@dataclass(frozen=True, kw_only=True)
class ResultMessage(MessageEnvelope):
    type: Literal["result"] = "result"
    site: str
    keyword: str
    level: int
    url: str
    title: str
    publish_date: str
    content: str
    summary: str
    score: int
    matched_keywords: list[str]


@dataclass(frozen=True, kw_only=True)
class SearchDoneMessage(MessageEnvelope):
    type: Literal["search_done"] = "search_done"
    site: str
    keyword: str
    url_count: int
    level: int


@dataclass(frozen=True, kw_only=True)
class ErrorMessage(MessageEnvelope):
    type: Literal["error"] = "error"
    stage: Literal["search", "download", "parse", "store"]
    site: str
    keyword: str
    level: int
    url: str
    error_code: str
    error: str
    retryable: bool



MESSAGE_TYPE_URL_V2 = "url"
MESSAGE_TYPE_HTML_V2 = "html"
MESSAGE_TYPE_ARTICLE_RESULT_V2 = "article_result"

ARTICLE_RESULT_STATUS_ACCEPTED = "accepted"
ARTICLE_RESULT_STATUS_REVIEW_REQUIRED = "review_required"
ARTICLE_RESULT_STATUS_IRRELEVANT = "irrelevant"
ARTICLE_RESULT_STATUS_EXTRACT_FAILED = "extract_failed"
ARTICLE_RESULT_STATUS_UNSUPPORTED_FORMAT = "unsupported_format"
ARTICLE_RESULT_STATUSES = {
    ARTICLE_RESULT_STATUS_ACCEPTED,
    ARTICLE_RESULT_STATUS_REVIEW_REQUIRED,
    ARTICLE_RESULT_STATUS_IRRELEVANT,
    ARTICLE_RESULT_STATUS_EXTRACT_FAILED,
    ARTICLE_RESULT_STATUS_UNSUPPORTED_FORMAT,
}

EXTRACTION_METHOD_SITE_SELECTOR = "site_selector"
EXTRACTION_METHOD_CMS_RULE = "cms_rule"
EXTRACTION_METHOD_AI = "ai"
EXTRACTION_METHOD_DENSITY = "density"
EXTRACTION_METHOD_FALLBACK = "fallback"
EXTRACTION_METHOD_PDF = "pdf"
EXTRACTION_METHOD_DOCX = "docx"
EXTRACTION_METHOD_XLSX = "xlsx"
EXTRACTION_METHOD_NONE = "none"
EXTRACTION_METHODS = {
    EXTRACTION_METHOD_SITE_SELECTOR,
    EXTRACTION_METHOD_CMS_RULE,
    EXTRACTION_METHOD_AI,
    EXTRACTION_METHOD_DENSITY,
    EXTRACTION_METHOD_FALLBACK,
    EXTRACTION_METHOD_PDF,
    EXTRACTION_METHOD_DOCX,
    EXTRACTION_METHOD_XLSX,
    EXTRACTION_METHOD_NONE,
}

EVIDENCE_ORIGIN_ORIGINAL = "original"
EVIDENCE_ORIGIN_EXPANDED = "expanded"
EVIDENCE_ORIGINS = {EVIDENCE_ORIGIN_ORIGINAL, EVIDENCE_ORIGIN_EXPANDED}
EVIDENCE_FIELD_TITLE = "title"
EVIDENCE_FIELD_SUMMARY = "summary"
EVIDENCE_FIELD_CONTENT = "content"
EVIDENCE_FIELD_URL = "url"
EVIDENCE_FIELDS = {
    EVIDENCE_FIELD_TITLE,
    EVIDENCE_FIELD_SUMMARY,
    EVIDENCE_FIELD_CONTENT,
    EVIDENCE_FIELD_URL,
}

V2_URL_FIELDS = {
    "protocol_version", "task_id", "message_id", "timestamp", "type",
    "hit_id", "plan_id", "original_query", "query_term", "url",
    "title", "snippet", "published_at", "source", "level",
}
V2_HTML_FIELDS = {
    "protocol_version", "task_id", "message_id", "timestamp", "type",
    "hit_id", "plan_id", "original_query", "query_term",
    "requested_url", "final_url", "content_type",
    "title", "snippet", "published_at", "source", "level", "html",
}
V2_ARTICLE_RESULT_FIELDS = {
    "protocol_version", "task_id", "message_id", "timestamp", "type",
    "hit_id", "plan_id", "original_query", "query_term",
    "requested_url", "final_url", "canonical_url",
    "title", "publish_date", "source", "summary", "content",
    "content_hash", "score", "matched_evidence", "status", "extraction_method",
}
V2_EVIDENCE_FIELDS = {"term", "origin", "field", "weight"}


def _require_v2_envelope(data: dict[str, Any]) -> None:
    for field in ("protocol_version", "task_id", "message_id", "timestamp"):
        if field not in data:
            raise ProtocolError("INVALID_MESSAGE", f"v2 article {field} is required")
        if data[field] is None:
            raise ProtocolError("INVALID_MESSAGE", f"v2 article {field} must not be null")
    if data["protocol_version"] != PROTOCOL_VERSION_V2:
        raise ProtocolError("INVALID_PROTOCOL_VERSION", "v2 article protocol_version must be 2.0")


def _require_v2_fields(data: dict[str, Any], allowed: set[str], required: set[str]) -> None:
    _reject_unknown_fields(data, allowed)
    for field in required:
        if field not in data:
            raise ProtocolError("INVALID_MESSAGE", f"v2 article {field} is required")
    for field in allowed:
        if field in data and data[field] is None:
            raise ProtocolError("INVALID_MESSAGE", f"v2 article {field} must not be null")


def _require_non_blank(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError("INVALID_MESSAGE", f"v2 article {field} must be a non-blank string")


def _require_html_content_type(value: Any) -> None:
    if not isinstance(value, str):
        raise ProtocolError("INVALID_MESSAGE", "v2 article content_type must be a string")
    normalized = value.split(";", 1)[0].strip().lower()
    if normalized not in ("text/html", "application/xhtml+xml"):
        raise ProtocolError("INVALID_MESSAGE", "v2 article content_type must be an HTML MIME type")


def _require_optional_absolute_url(value: Any, field: str) -> None:
    if not isinstance(value, str):
        raise ProtocolError("INVALID_MESSAGE", f"v2 article {field} must be a string")
    if value:
        validate_target_url(value)


def _require_score(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError("INVALID_MESSAGE", "v2 article score must be a non-negative integer")
    if value < 0:
        raise ProtocolError("INVALID_MESSAGE", "v2 article score must be a non-negative integer")
    return value


def _require_content_hash(content: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ProtocolError("INVALID_MESSAGE", "v2 article content_hash must be a string")
    if not content:
        if value:
            raise ProtocolError("INVALID_MESSAGE", "v2 article content_hash must be empty when content is empty")
        return ""
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if value != expected:
        raise ProtocolError("INVALID_MESSAGE", "v2 article content_hash must be the SHA-256 of content")
    return value


@dataclass(frozen=True, kw_only=True)
class MatchedEvidence:
    term: str
    origin: Literal["original", "expanded"]
    field: Literal["title", "summary", "content", "url"]
    weight: int | float

    def __post_init__(self) -> None:
        _require_non_blank(self.term, "evidence.term")
        if self.origin not in EVIDENCE_ORIGINS:
            raise ProtocolError("INVALID_MESSAGE", "evidence.origin is invalid")
        if self.field not in EVIDENCE_FIELDS:
            raise ProtocolError("INVALID_MESSAGE", "evidence.field is invalid")
        if isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)):
            raise ProtocolError("INVALID_MESSAGE", "evidence.weight must be a finite non-negative number")
        if not math.isfinite(self.weight) or self.weight < 0:
            raise ProtocolError("INVALID_MESSAGE", "evidence.weight must be a finite non-negative number")

    def to_dict(self) -> dict[str, Any]:
        return {
            "term": self.term,
            "origin": self.origin,
            "field": self.field,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MatchedEvidence":
        if not isinstance(data, dict):
            raise ProtocolError("INVALID_MESSAGE", "matched_evidence element must be an object")
        _reject_unknown_fields(data, V2_EVIDENCE_FIELDS)
        for field in V2_EVIDENCE_FIELDS:
            if field not in data:
                raise ProtocolError("INVALID_MESSAGE", f"matched_evidence.{field} is required")
            if data[field] is None:
                raise ProtocolError("INVALID_MESSAGE", f"matched_evidence.{field} must not be null")
        return cls(
            term=data["term"],
            origin=data["origin"],
            field=data["field"],
            weight=data["weight"],
        )


def _parse_matched_evidence(value: Any) -> tuple[MatchedEvidence, ...]:
    if not isinstance(value, list):
        raise ProtocolError("INVALID_MESSAGE", "matched_evidence must be an array")
    return tuple(MatchedEvidence.from_dict(item) for item in value)


@dataclass(frozen=True, kw_only=True)
class URLMessageV2(MessageEnvelope):
    type: Literal["url"] = MESSAGE_TYPE_URL_V2
    hit_id: str
    plan_id: str
    original_query: str
    query_term: str
    url: str
    title: str
    snippet: str
    published_at: str
    source: str
    level: int

    def __post_init__(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION_V2:
            raise ProtocolError("INVALID_PROTOCOL_VERSION", "url_v2 protocol_version must be 2.0")
        if self.type != MESSAGE_TYPE_URL_V2:
            raise ProtocolError("INVALID_TYPE", "url_v2 type must be url")
        for field in ("hit_id", "plan_id", "original_query", "query_term", "source"):
            _require_non_blank(getattr(self, field), field)
        validate_target_url(self.url)
        object.__setattr__(self, "level", _require_protocol_int(self.level, "level"))
        if self.level < 0:
            raise ProtocolError("INVALID_MESSAGE", "url_v2 level must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "task_id": self.task_id,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "type": self.type,
            "hit_id": self.hit_id,
            "plan_id": self.plan_id,
            "original_query": self.original_query,
            "query_term": self.query_term,
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "published_at": self.published_at,
            "source": self.source,
            "level": self.level,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=False)


@dataclass(frozen=True, kw_only=True)
class HTMLMessageV2(MessageEnvelope):
    type: Literal["html"] = MESSAGE_TYPE_HTML_V2
    hit_id: str
    plan_id: str
    original_query: str
    query_term: str
    requested_url: str
    final_url: str
    content_type: str
    title: str
    snippet: str
    published_at: str
    source: str
    level: int
    html: str

    def __post_init__(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION_V2:
            raise ProtocolError("INVALID_PROTOCOL_VERSION", "html_v2 protocol_version must be 2.0")
        if self.type != MESSAGE_TYPE_HTML_V2:
            raise ProtocolError("INVALID_TYPE", "html_v2 type must be html")
        for field in ("hit_id", "plan_id", "original_query", "query_term", "source"):
            _require_non_blank(getattr(self, field), field)
        validate_target_url(self.requested_url)
        validate_target_url(self.final_url)
        _require_html_content_type(self.content_type)
        object.__setattr__(self, "level", _require_protocol_int(self.level, "level"))
        if self.level < 0:
            raise ProtocolError("INVALID_MESSAGE", "html_v2 level must be non-negative")
        if not isinstance(self.html, str):
            raise ProtocolError("INVALID_MESSAGE", "html_v2 html must be a string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "task_id": self.task_id,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "type": self.type,
            "hit_id": self.hit_id,
            "plan_id": self.plan_id,
            "original_query": self.original_query,
            "query_term": self.query_term,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "content_type": self.content_type,
            "title": self.title,
            "snippet": self.snippet,
            "published_at": self.published_at,
            "source": self.source,
            "level": self.level,
            "html": self.html,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=False)


@dataclass(frozen=True, kw_only=True)
class ArticleResultV2(MessageEnvelope):
    type: Literal["article_result"] = MESSAGE_TYPE_ARTICLE_RESULT_V2
    hit_id: str
    plan_id: str
    original_query: str
    query_term: str
    requested_url: str
    final_url: str
    canonical_url: str = ""
    title: str = ""
    publish_date: str = ""
    source: str = ""
    summary: str = ""
    content: str = ""
    content_hash: str = ""
    score: int = 0
    matched_evidence: tuple[MatchedEvidence, ...] = ()
    status: str = ARTICLE_RESULT_STATUS_ACCEPTED
    extraction_method: str = EXTRACTION_METHOD_NONE

    def __post_init__(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION_V2:
            raise ProtocolError("INVALID_PROTOCOL_VERSION", "article_result protocol_version must be 2.0")
        if self.type != MESSAGE_TYPE_ARTICLE_RESULT_V2:
            raise ProtocolError("INVALID_TYPE", "article_result type must be article_result")
        for field in ("hit_id", "plan_id", "original_query", "query_term", "source"):
            _require_non_blank(getattr(self, field), field)
        validate_target_url(self.requested_url)
        validate_target_url(self.final_url)
        _require_optional_absolute_url(self.canonical_url, "canonical_url")
        object.__setattr__(self, "score", _require_score(self.score))
        object.__setattr__(self, "content_hash", _require_content_hash(self.content, self.content_hash))
        if not isinstance(self.matched_evidence, tuple):
            object.__setattr__(self, "matched_evidence", tuple(self.matched_evidence))
        if not all(isinstance(item, MatchedEvidence) for item in self.matched_evidence):
            raise ProtocolError("INVALID_MESSAGE", "matched_evidence elements must be MatchedEvidence")
        if self.status not in ARTICLE_RESULT_STATUSES:
            raise ProtocolError("INVALID_MESSAGE", "article_result status is invalid")
        if self.extraction_method not in EXTRACTION_METHODS:
            raise ProtocolError("INVALID_MESSAGE", "article_result extraction_method is invalid")
        if not isinstance(self.title, str) or not isinstance(self.publish_date, str):
            raise ProtocolError("INVALID_MESSAGE", "article_result title and publish_date must be strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "task_id": self.task_id,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "type": self.type,
            "hit_id": self.hit_id,
            "plan_id": self.plan_id,
            "original_query": self.original_query,
            "query_term": self.query_term,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "publish_date": self.publish_date,
            "source": self.source,
            "summary": self.summary,
            "content": self.content,
            "content_hash": self.content_hash,
            "score": self.score,
            "matched_evidence": [item.to_dict() for item in self.matched_evidence],
            "status": self.status,
            "extraction_method": self.extraction_method,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def decode_v2_article_message(raw: Union[str, bytes]) -> Union[URLMessageV2, HTMLMessageV2, ArticleResultV2]:
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError("INVALID_JSON", "v2 article message is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ProtocolError("INVALID_MESSAGE", "v2 article message must be a JSON object")
    _require_v2_envelope(data)
    message_type = data.get("type")
    if message_type is None:
        raise ProtocolError("INVALID_MESSAGE", "v2 article type is required")
    if message_type == MESSAGE_TYPE_URL_V2:
        _require_v2_fields(data, V2_URL_FIELDS, V2_URL_FIELDS - {"type"})
        return URLMessageV2(
            protocol_version=data["protocol_version"],
            task_id=data["task_id"],
            message_id=data["message_id"],
            timestamp=data["timestamp"],
            type=data["type"],
            hit_id=data["hit_id"],
            plan_id=data["plan_id"],
            original_query=data["original_query"],
            query_term=data["query_term"],
            url=data["url"],
            title=data["title"],
            snippet=data["snippet"],
            published_at=data["published_at"],
            source=data["source"],
            level=data["level"],
        )
    if message_type == MESSAGE_TYPE_HTML_V2:
        _require_v2_fields(data, V2_HTML_FIELDS, V2_HTML_FIELDS - {"type"})
        return HTMLMessageV2(
            protocol_version=data["protocol_version"],
            task_id=data["task_id"],
            message_id=data["message_id"],
            timestamp=data["timestamp"],
            type=data["type"],
            hit_id=data["hit_id"],
            plan_id=data["plan_id"],
            original_query=data["original_query"],
            query_term=data["query_term"],
            requested_url=data["requested_url"],
            final_url=data["final_url"],
            content_type=data["content_type"],
            title=data["title"],
            snippet=data["snippet"],
            published_at=data["published_at"],
            source=data["source"],
            level=data["level"],
            html=data["html"],
        )
    if message_type == MESSAGE_TYPE_ARTICLE_RESULT_V2:
        _require_v2_fields(data, V2_ARTICLE_RESULT_FIELDS, V2_ARTICLE_RESULT_FIELDS - {"type", "canonical_url", "title", "publish_date", "summary", "content", "content_hash"})
        return ArticleResultV2(
            protocol_version=data["protocol_version"],
            task_id=data["task_id"],
            message_id=data["message_id"],
            timestamp=data["timestamp"],
            type=data["type"],
            hit_id=data["hit_id"],
            plan_id=data["plan_id"],
            original_query=data["original_query"],
            query_term=data["query_term"],
            requested_url=data["requested_url"],
            final_url=data["final_url"],
            canonical_url=data.get("canonical_url", ""),
            title=data.get("title", ""),
            publish_date=data.get("publish_date", ""),
            source=data["source"],
            summary=data.get("summary", ""),
            content=data.get("content", ""),
            content_hash=data.get("content_hash", ""),
            score=data["score"],
            matched_evidence=_parse_matched_evidence(data["matched_evidence"]),
            status=data["status"],
            extraction_method=data["extraction_method"],
        )
    raise ProtocolError("INVALID_TYPE", "unknown v2 article message type")
