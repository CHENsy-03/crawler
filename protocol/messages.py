import json
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
