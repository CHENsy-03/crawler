"""Internal SearchPlan schema v2 and shared SearchHit model."""

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlsplit

from protocol.messages import PROTOCOL_VERSION_V2, ProtocolError, validate_target_url

PLAN_SCHEMA_VERSION = 2
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

ADAPTER_HTML = "html"
ADAPTER_TRS = "trs"
ADAPTER_JPAAS = "jpaas"
ADAPTER_GENERIC_JSON = "generic_json"
ADAPTERS = {ADAPTER_HTML, ADAPTER_TRS, ADAPTER_JPAAS, ADAPTER_GENERIC_JSON}

REQUEST_FORMAT_NONE = "none"
REQUEST_FORMAT_FORM_URLENCODED = "form_urlencoded"
REQUEST_FORMAT_JSON = "json"
REQUEST_FORMATS = {
    REQUEST_FORMAT_NONE,
    REQUEST_FORMAT_FORM_URLENCODED,
    REQUEST_FORMAT_JSON,
}

RESPONSE_FORMAT_HTML = "html"
RESPONSE_FORMAT_JSON = "json"
RESPONSE_FORMATS = {RESPONSE_FORMAT_HTML, RESPONSE_FORMAT_JSON}

KEYWORD_LOCATION_QUERY = "query"
KEYWORD_LOCATION_FORM = "form"
KEYWORD_LOCATION_JSON = "json"
KEYWORD_LOCATIONS = {
    KEYWORD_LOCATION_QUERY,
    KEYWORD_LOCATION_FORM,
    KEYWORD_LOCATION_JSON,
}

PAGINATION_LOCATION_NONE = "none"
PAGINATION_LOCATIONS = {
    PAGINATION_LOCATION_NONE,
    KEYWORD_LOCATION_QUERY,
    KEYWORD_LOCATION_FORM,
    KEYWORD_LOCATION_JSON,
}

ADAPTER_STRATEGIES = {
    ADAPTER_HTML: SEARCH_STRATEGY_HTML_FORM,
    ADAPTER_TRS: SEARCH_STRATEGY_JSON_API,
    ADAPTER_JPAAS: SEARCH_STRATEGY_JSON_API,
    ADAPTER_GENERIC_JSON: SEARCH_STRATEGY_JSON_API,
}

ALLOWED_HTTP_METHODS = {"GET", "POST"}

_SEARCH_PLAN_FIELDS = {
    "plan_schema_version",
    "plan_id",
    "endpoint",
    "protocol_version",
    "status",
    "strategy",
    "adapter",
    "http_method",
    "request_format",
    "response_format",
    "request_shape",
    "pagination",
    "selectors",
    "scope",
    "discovery",
    "created_from",
    "created_at",
    "expires_at",
    "invalid_reason",
}


def _require_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError("INVALID_INTEGER", f"{field_name} must be an integer")
    return value


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ProtocolError("INVALID_BOOLEAN", f"{field_name} must be a boolean")
    return value


def _tuple_of_str(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (tuple, list)):
        raise ProtocolError("INVALID_PATH", f"{field_name} must be a path sequence")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ProtocolError("INVALID_PATH", f"{field_name} contains an empty or non-string segment")
        out.append(item)
    return tuple(out)


def _pairs(value: Any, field_name: str) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, (tuple, list)):
        raise ProtocolError("INVALID_PAIRS", f"{field_name} must be a sequence of pairs")
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for pair in value:
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ProtocolError("INVALID_PAIRS", f"{field_name} contains a malformed pair")
        name, item = pair
        if not isinstance(name, str) or not name:
            raise ProtocolError("INVALID_PAIRS", f"{field_name} contains an invalid name")
        if not isinstance(item, str):
            raise ProtocolError("INVALID_PAIRS", f"{field_name} values must be strings")
        if name in seen:
            raise ProtocolError("INVALID_PAIRS", f"{field_name} contains a duplicate name")
        seen.add(name)
        out.append((name, item))
    return tuple(out)


def _freeze_json(value: Any) -> Any:
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProtocolError("INVALID_JSON_VALUE", "JSON value must be finite")
        return ("float", value)
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, (list, tuple)):
        return ("array", tuple(_freeze_json(item) for item in value))
    if isinstance(value, dict):
        items: list[tuple[str, Any]] = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProtocolError("INVALID_JSON_VALUE", "JSON object keys must be strings")
            items.append((key, _freeze_json(item)))
        return ("object", tuple(sorted(items)))
    raise ProtocolError("INVALID_JSON_VALUE", "JSON value is not JSON-serializable")


def _thaw_json(value: Any) -> Any:
    if not isinstance(value, tuple) or not value:
        raise ProtocolError("INVALID_JSON_VALUE", "frozen JSON value is malformed")
    tag = value[0]
    if tag == "null":
        return None
    if tag == "bool":
        return value[1]
    if tag == "int":
        return value[1]
    if tag == "float":
        return value[1]
    if tag == "str":
        return value[1]
    if tag == "array":
        return [_thaw_json(item) for item in value[1]]
    if tag == "object":
        return {key: _thaw_json(item) for key, item in value[1]}
    raise ProtocolError("INVALID_JSON_VALUE", "unknown frozen JSON tag")


def _json_template(
    value: Any,
    field_name: str,
) -> tuple[tuple[tuple[str, ...], Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, (tuple, list)):
        raise ProtocolError("INVALID_JSON_TEMPLATE", f"{field_name} must be a sequence")
    out: list[tuple[tuple[str, ...], Any]] = []
    seen: set[tuple[str, ...]] = set()
    for entry in value:
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            raise ProtocolError("INVALID_JSON_TEMPLATE", f"{field_name} contains a malformed entry")
        path, item = entry
        path_tuple = _tuple_of_str(path, f"{field_name}.path")
        if not path_tuple:
            raise ProtocolError("INVALID_JSON_TEMPLATE", f"{field_name} path must not be empty")
        if path_tuple in seen:
            raise ProtocolError("INVALID_JSON_TEMPLATE", f"{field_name} contains a duplicate path")
        seen.add(path_tuple)
        out.append((path_tuple, _freeze_json(item)))
    return tuple(out)


def _path_conflict(first: tuple[str, ...], second: tuple[str, ...]) -> bool:
    if first == second:
        return True
    if len(first) < len(second) and second[: len(first)] == first:
        return True
    if len(second) < len(first) and first[: len(second)] == second:
        return True
    return False


@dataclass(frozen=True)
class SearchRequestShape:
    keyword_location: str
    keyword_path: tuple[str, ...]
    fixed_query_params: tuple[tuple[str, str], ...] = ()
    form_fields: tuple[tuple[str, str], ...] = ()
    json_object_template: tuple[tuple[tuple[str, ...], Any], ...] = ()

    def __post_init__(self) -> None:
        if self.keyword_location not in KEYWORD_LOCATIONS:
            raise ProtocolError("INVALID_KEYWORD_LOCATION", "request_shape.keyword_location is invalid")
        keyword_path = _tuple_of_str(self.keyword_path, "request_shape.keyword_path")
        if not keyword_path:
            raise ProtocolError("INVALID_KEYWORD_PATH", "request_shape.keyword_path must not be empty")
        if self.keyword_location in (KEYWORD_LOCATION_QUERY, KEYWORD_LOCATION_FORM) and len(keyword_path) != 1:
            raise ProtocolError("INVALID_KEYWORD_PATH", "query/form keyword_path must have exactly one segment")
        object.__setattr__(self, "keyword_path", keyword_path)
        object.__setattr__(self, "fixed_query_params", _pairs(self.fixed_query_params, "request_shape.fixed_query_params"))
        object.__setattr__(self, "form_fields", _pairs(self.form_fields, "request_shape.form_fields"))
        object.__setattr__(self, "json_object_template", _json_template(self.json_object_template, "request_shape.json_object_template"))

        fixed_names = {name for name, _ in self.fixed_query_params}
        form_names = {name for name, _ in self.form_fields}
        if self.keyword_location == KEYWORD_LOCATION_QUERY and keyword_path[0] in fixed_names:
            raise ProtocolError("INVALID_KEYWORD_PATH", "query keyword_path conflicts with fixed_query_params")
        if self.keyword_location == KEYWORD_LOCATION_FORM and keyword_path[0] in form_names:
            raise ProtocolError("INVALID_KEYWORD_PATH", "form keyword_path conflicts with form_fields")
        if self.keyword_location == KEYWORD_LOCATION_JSON:
            for path, _ in self.json_object_template:
                if _path_conflict(keyword_path, path):
                    raise ProtocolError("INVALID_KEYWORD_PATH", "json keyword_path conflicts with json_object_template")

    def to_dict(self) -> dict[str, Any]:
        return {
            "keyword_location": self.keyword_location,
            "keyword_path": list(self.keyword_path),
            "fixed_query_params": [list(pair) for pair in self.fixed_query_params],
            "form_fields": [list(pair) for pair in self.form_fields],
            "json_object_template": [
                [list(path), _thaw_json(value)]
                for path, value in self.json_object_template
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchRequestShape":
        return cls(
            keyword_location=data["keyword_location"],
            keyword_path=data["keyword_path"],
            fixed_query_params=data.get("fixed_query_params", ()),
            form_fields=data.get("form_fields", ()),
            json_object_template=data.get("json_object_template", ()),
        )


@dataclass(frozen=True)
class SearchPagination:
    enabled: bool = False
    location: str = PAGINATION_LOCATION_NONE
    value_path: tuple[str, ...] = ()
    start: int = 0
    step: int = 0
    page_size_path: tuple[str, ...] = ()
    page_size: int | None = None
    max_pages: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", _require_bool(self.enabled, "pagination.enabled"))
        if self.location not in PAGINATION_LOCATIONS:
            raise ProtocolError("INVALID_PAGINATION", "pagination.location is invalid")
        object.__setattr__(self, "value_path", _tuple_of_str(self.value_path, "pagination.value_path"))
        object.__setattr__(self, "page_size_path", _tuple_of_str(self.page_size_path, "pagination.page_size_path"))
        object.__setattr__(self, "start", _require_int(self.start, "pagination.start"))
        object.__setattr__(self, "step", _require_int(self.step, "pagination.step"))
        object.__setattr__(self, "max_pages", _require_int(self.max_pages, "pagination.max_pages"))
        if self.page_size is not None:
            object.__setattr__(self, "page_size", _require_int(self.page_size, "pagination.page_size"))

        if self.enabled:
            if self.location == PAGINATION_LOCATION_NONE or not self.value_path:
                raise ProtocolError("INVALID_PAGINATION", "enabled pagination requires location and value_path")
            if self.start < 0 or self.step < 1 or self.max_pages < 1:
                raise ProtocolError("INVALID_PAGINATION", "enabled pagination has invalid start/step/max_pages")
            if self.location in (KEYWORD_LOCATION_QUERY, KEYWORD_LOCATION_FORM):
                if len(self.value_path) != 1:
                    raise ProtocolError("INVALID_PAGINATION", "query/form pagination value_path must have one segment")
                if self.page_size_path and len(self.page_size_path) != 1:
                    raise ProtocolError("INVALID_PAGINATION", "query/form page_size_path must have one segment")
            if self.location == KEYWORD_LOCATION_JSON:
                if not self.value_path:
                    raise ProtocolError("INVALID_PAGINATION", "json pagination value_path is required")
        else:
            disabled = (
                self.location == PAGINATION_LOCATION_NONE
                and self.value_path == ()
                and self.start == 0
                and self.step == 0
                and self.page_size_path == ()
                and self.page_size is None
                and self.max_pages == 1
            )
            if not disabled:
                raise ProtocolError("INVALID_PAGINATION", "disabled pagination must use the exact default state")

        if self.page_size_path:
            if self.page_size is None or self.page_size < 1:
                raise ProtocolError("INVALID_PAGINATION", "page_size_path requires a positive page_size")
        elif self.page_size is not None:
            raise ProtocolError("INVALID_PAGINATION", "page_size must be null when page_size_path is empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "location": self.location,
            "value_path": list(self.value_path),
            "start": self.start,
            "step": self.step,
            "page_size_path": list(self.page_size_path),
            "page_size": self.page_size,
            "max_pages": self.max_pages,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchPagination":
        return cls(
            enabled=data.get("enabled", False),
            location=data.get("location", PAGINATION_LOCATION_NONE),
            value_path=data.get("value_path", ()),
            start=data.get("start", 0),
            step=data.get("step", 0),
            page_size_path=data.get("page_size_path", ()),
            page_size=data.get("page_size"),
            max_pages=data.get("max_pages", 1),
        )


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
    plan_schema_version: int = PLAN_SCHEMA_VERSION
    protocol_version: str = PROTOCOL_VERSION_V2
    status: str = PLAN_STATUS_DRAFT
    strategy: str = SEARCH_STRATEGY_UNKNOWN
    adapter: str = ""
    http_method: str = "GET"
    request_format: str = REQUEST_FORMAT_NONE
    response_format: str = RESPONSE_FORMAT_HTML
    request_shape: SearchRequestShape = field(default_factory=lambda: SearchRequestShape("query", ("q",)))
    pagination: SearchPagination = field(default_factory=SearchPagination)
    selectors: SearchSelectors = field(default_factory=lambda: SearchSelectors("", "", "", "", ""))
    scope: SearchScope = field(default_factory=SearchScope)
    discovery: SearchDiscovery = field(default_factory=SearchDiscovery)
    created_from: str = ""
    created_at: str = ""
    expires_at: str = ""
    invalid_reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_schema_version", _require_int(self.plan_schema_version, "plan_schema_version"))
        if self.request_shape is None:
            raise ProtocolError("INVALID_REQUEST_SHAPE", "request_shape is required")
        if not isinstance(self.request_shape, SearchRequestShape):
            raise ProtocolError("INVALID_REQUEST_SHAPE", "request_shape must be SearchRequestShape")
        if self.pagination is None:
            raise ProtocolError("INVALID_PAGINATION", "pagination is required")
        if not isinstance(self.pagination, SearchPagination):
            raise ProtocolError("INVALID_PAGINATION", "pagination must be SearchPagination")
        if self.selectors is None:
            object.__setattr__(self, "selectors", SearchSelectors("", "", "", "", ""))
        if self.scope is None:
            object.__setattr__(self, "scope", SearchScope(""))
        if self.discovery is None:
            object.__setattr__(self, "discovery", SearchDiscovery())

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_schema_version": self.plan_schema_version,
            "plan_id": self.plan_id,
            "endpoint": self.endpoint,
            "protocol_version": self.protocol_version,
            "status": self.status,
            "strategy": self.strategy,
            "adapter": self.adapter,
            "http_method": self.http_method,
            "request_format": self.request_format,
            "response_format": self.response_format,
            "request_shape": self.request_shape.to_dict(),
            "pagination": self.pagination.to_dict(),
            "selectors": asdict(self.selectors),
            "scope": asdict(self.scope),
            "discovery": asdict(self.discovery),
            "created_from": self.created_from,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "invalid_reason": self.invalid_reason,
        }

    def to_json(self) -> str:
        return _go_style_json(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SearchPlan":
        if not isinstance(data, dict):
            raise ProtocolError("INVALID_PLAN", "search_plan must be a JSON object")
        unknown = set(data) - _SEARCH_PLAN_FIELDS
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ProtocolError("UNKNOWN_FIELD", f"unknown search_plan field(s): {names}")
        if "plan_schema_version" not in data:
            raise ProtocolError("INVALID_SCHEMA", "plan_schema_version is required")
        return cls(
            plan_id=data["plan_id"],
            endpoint=data["endpoint"],
            plan_schema_version=data["plan_schema_version"],
            protocol_version=data.get("protocol_version", PROTOCOL_VERSION_V2),
            status=data.get("status", PLAN_STATUS_DRAFT),
            strategy=data.get("strategy", SEARCH_STRATEGY_UNKNOWN),
            adapter=data["adapter"],
            http_method=data.get("http_method", "GET"),
            request_format=data["request_format"],
            response_format=data["response_format"],
            request_shape=SearchRequestShape.from_dict(data["request_shape"]),
            pagination=SearchPagination.from_dict(data["pagination"]),
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


def _validate_endpoint_no_query(plan: SearchPlan) -> None:
    try:
        validate_target_url(plan.endpoint)
    except ProtocolError as exc:
        raise ProtocolError("INVALID_PLAN_ENDPOINT", f"search_plan endpoint: {exc}") from exc
    parts = urlsplit(plan.endpoint)
    if parts.query:
        raise ProtocolError("INVALID_PLAN_ENDPOINT", "search_plan endpoint must not contain query")
    if parts.fragment:
        raise ProtocolError("INVALID_PLAN_ENDPOINT", "search_plan endpoint must not contain fragment")


def _validate_pagination_location(plan: SearchPlan) -> None:
    if not plan.pagination.enabled:
        return
    if plan.http_method == "GET":
        if plan.request_format != REQUEST_FORMAT_NONE:
            raise ProtocolError("INVALID_PAGINATION", "GET plans cannot use a request body format")
        if plan.pagination.location not in (PAGINATION_LOCATION_NONE, KEYWORD_LOCATION_QUERY):
            raise ProtocolError("INVALID_PAGINATION", "GET pagination must use none or query")
    elif plan.request_format == REQUEST_FORMAT_FORM_URLENCODED:
        if plan.pagination.location not in (PAGINATION_LOCATION_NONE, KEYWORD_LOCATION_QUERY, KEYWORD_LOCATION_FORM):
            raise ProtocolError("INVALID_PAGINATION", "form POST pagination must use none/query/form")
    elif plan.request_format == REQUEST_FORMAT_JSON:
        if plan.pagination.location not in (PAGINATION_LOCATION_NONE, KEYWORD_LOCATION_QUERY, KEYWORD_LOCATION_JSON):
            raise ProtocolError("INVALID_PAGINATION", "json POST pagination must use none/query/json")


def _validate_pagination_conflicts(plan: SearchPlan) -> None:
    keyword_path = plan.request_shape.keyword_path
    if plan.pagination.enabled:
        if _path_conflict(keyword_path, plan.pagination.value_path):
            raise ProtocolError("INVALID_PAGINATION", "pagination.value_path conflicts with keyword_path")
        if plan.pagination.page_size_path and _path_conflict(keyword_path, plan.pagination.page_size_path):
            raise ProtocolError("INVALID_PAGINATION", "pagination.page_size_path conflicts with keyword_path")
    fixed_paths = [pair[0] for pair in plan.request_shape.fixed_query_params]
    fixed_paths += [pair[0] for pair in plan.request_shape.form_fields]
    if plan.pagination.enabled and plan.pagination.location in (KEYWORD_LOCATION_QUERY, KEYWORD_LOCATION_FORM):
        if plan.pagination.value_path[0] in fixed_paths:
            raise ProtocolError("INVALID_PAGINATION", "pagination.value_path conflicts with a fixed field")
        if plan.pagination.page_size_path and plan.pagination.page_size_path[0] in fixed_paths:
            raise ProtocolError("INVALID_PAGINATION", "pagination.page_size_path conflicts with a fixed field")


def validate_search_plan(plan: SearchPlan) -> None:
    if plan.plan_schema_version != PLAN_SCHEMA_VERSION:
        raise ProtocolError("INVALID_PLAN_SCHEMA", "search_plan schema version is not supported")
    if plan.protocol_version != PROTOCOL_VERSION_V2:
        raise ProtocolError("INVALID_PLAN_VERSION", f"search_plan protocol_version must be {PROTOCOL_VERSION_V2!r}")
    if not plan.plan_id:
        raise ProtocolError("INVALID_PLAN_ID", "search_plan plan_id is required")
    if plan.status not in PLAN_STATUSES:
        raise ProtocolError("INVALID_PLAN_STATUS", f"search_plan status {plan.status!r} is not allowed")
    if plan.strategy not in SEARCH_STRATEGIES:
        raise ProtocolError("INVALID_PLAN_STRATEGY", f"search_plan strategy {plan.strategy!r} is not allowed")
    if plan.adapter not in ADAPTERS:
        raise ProtocolError("INVALID_ADAPTER", "search_plan adapter is not allowed")
    if ADAPTER_STRATEGIES[plan.adapter] != plan.strategy:
        raise ProtocolError("INVALID_ADAPTER_STRATEGY", "adapter and strategy are inconsistent")
    if plan.http_method not in ALLOWED_HTTP_METHODS:
        raise ProtocolError("INVALID_HTTP_METHOD", f"search_plan http_method {plan.http_method!r} is not allowed")
    if plan.request_format not in REQUEST_FORMATS:
        raise ProtocolError("INVALID_REQUEST_FORMAT", "search_plan request_format is not allowed")
    if plan.response_format not in RESPONSE_FORMATS:
        raise ProtocolError("INVALID_RESPONSE_FORMAT", "search_plan response_format is not allowed")
    if plan.request_format == REQUEST_FORMAT_NONE and plan.http_method == "POST":
        raise ProtocolError("INVALID_REQUEST_FORMAT", "POST plans require form_urlencoded or json")
    if plan.request_format != REQUEST_FORMAT_NONE and plan.http_method == "GET":
        raise ProtocolError("INVALID_REQUEST_FORMAT", "GET plans cannot send a request body")
    _validate_endpoint_no_query(plan)
    _validate_pagination_location(plan)
    _validate_pagination_conflicts(plan)
    if plan.pagination.max_pages < 1:
        raise ProtocolError("INVALID_PAGINATION", "search_plan pagination.max_pages must be >= 1")
    if not plan.scope.domain:
        raise ProtocolError("INVALID_SCOPE", "search_plan scope.domain is required")
    if plan.scope.max_depth < 0:
        raise ProtocolError("INVALID_SCOPE", "search_plan scope.max_depth must be >= 0")
    if not 0 <= plan.discovery.confidence <= 100:
        raise ProtocolError("INVALID_CONFIDENCE", "search_plan discovery.confidence must be between 0 and 100")


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
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    text = text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    text = text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return text


def _canonical_request_shape(shape: SearchRequestShape) -> dict[str, Any]:
    fixed = sorted([list(pair) for pair in shape.fixed_query_params])
    form = sorted([list(pair) for pair in shape.form_fields])
    json_entries = sorted(
        [[list(path), _thaw_json(value)] for path, value in shape.json_object_template],
        key=lambda entry: tuple(entry[0]),
    )
    return {
        "keyword_location": shape.keyword_location,
        "keyword_path": list(shape.keyword_path),
        "fixed_query_params": fixed,
        "form_fields": form,
        "json_object_template": json_entries,
    }


def _canonical_plan_content(plan: SearchPlan) -> dict[str, Any]:
    return {
        "plan_schema_version": plan.plan_schema_version,
        "protocol_version": plan.protocol_version,
        "strategy": plan.strategy,
        "adapter": plan.adapter,
        "endpoint": plan.endpoint,
        "http_method": plan.http_method,
        "request_format": plan.request_format,
        "response_format": plan.response_format,
        "request_shape": _canonical_request_shape(plan.request_shape),
        "pagination": plan.pagination.to_dict(),
        "selectors": asdict(plan.selectors),
        "scope": {
            "domain": plan.scope.domain,
            "allowed_path_prefixes": list(plan.scope.allowed_path_prefixes),
            "max_depth": plan.scope.max_depth,
        },
    }


def _canonical_json(content: dict[str, Any]) -> str:
    canonical = json.dumps(
        content,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    canonical = canonical.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return canonical


def canonical_plan_json(plan: SearchPlan) -> str:
    return _canonical_json(_canonical_plan_content(plan))


def compute_plan_id(plan: SearchPlan) -> str:
    canonical = canonical_plan_json(plan).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()