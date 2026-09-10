"""DEV-005 v3 stream and v1 capacity codecs.

This module is a new contract layer. It intentionally does not replace the v1/v2
classes in protocol.messages.py used by existing workers.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Union

from protocol.messages import ProtocolError, validate_target_url
from protocol.status_error_event import ErrorCode

V3_PROTOCOL_VERSION = "3.0"
CONTROL_PROTOCOL_VERSION = "1.0"
MAX_ARTIFACT_BYTES = 20 * 1024 * 1024

STREAM_BY_TYPE = {
    "search_requested": "crawler:search",
    "url": "crawler:url",
    "html": "crawler:html",
    "result": "crawler:result",
    "error": "crawler:error",
}
WORK_CLASS_BY_TYPE = {
    "search_requested": "ROOT",
    "url": "ROOT",
    "html": "CONTINUATION",
    "result": "CONTINUATION",
    "error": "TERMINAL",
}

_ULID_RE = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_MESSAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_ASSOCIATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
_LOWER_HEX64_RE = re.compile(r"^[a-f0-9]{64}$")
_HTTP_URL_RE = re.compile(r"^https?://\S+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CONTENT_TYPE_RE = re.compile(r"^[^/\s]+/[^/\s]+$")
_ARTIFACT_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")

MAX_ATTEMPT_NO = 4294967295
MAX_SCORE = 4294967295
MAX_LEVEL = 4294967295
MAX_STATE_VERSION = 9007199254740991
MAX_EMERGENCY_RESERVE_BYTES = 9007199254740991

_ROOT_FIELDS = {
    "protocol_version", "type", "event_id", "message_id", "task_id",
    "aggregate_id", "idempotency_key", "causation_id", "correlation_id",
    "attempt_no", "timestamp", "work_class", "payload",
}
_ROOT_REQUIRED = {
    "protocol_version", "type", "event_id", "message_id", "task_id",
    "idempotency_key", "correlation_id", "attempt_no", "timestamp",
    "work_class", "payload",
}

_CANONICAL_ERRORS = {item.value for item in ErrorCode}


@dataclass(frozen=True, kw_only=True)
class V3Envelope:
    protocol_version: str
    type: str
    event_id: str
    message_id: str
    task_id: str
    aggregate_id: str | None
    idempotency_key: str
    causation_id: str | None
    correlation_id: str
    attempt_no: int
    timestamp: str
    work_class: str

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        if out.get("aggregate_id") is None:
            out.pop("aggregate_id", None)
        if out.get("causation_id") is None:
            out.pop("causation_id", None)
        out["payload"] = None
        return out


@dataclass(frozen=True, kw_only=True)
class SearchRequestedPayload:
    target_url: str
    keywords: tuple[str, ...]
    level: int
    max_pages: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, kw_only=True)
class URLPayload:
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, kw_only=True)
class HTMLPayload:
    hit_id: str
    plan_id: str
    original_query: str
    query_term: str
    requested_url: str
    final_url: str
    title: str
    snippet: str
    published_at: str
    source: str
    level: int
    artifact_ref: str
    checksum: str
    content_type: str
    byte_size: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, kw_only=True)
class MatchedEvidenceV3:
    term: str
    origin: Literal["original", "expanded"]
    field: Literal["title", "summary", "content", "url"]
    weight: int | float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, kw_only=True)
class ResultPayloadV3:
    hit_id: str
    plan_id: str
    original_query: str
    query_term: str
    requested_url: str
    final_url: str
    canonical_url: str
    title: str
    publish_date: str
    source: str
    summary: str
    content: str
    content_hash: str
    score: int
    matched_evidence: tuple[MatchedEvidenceV3, ...]
    status: str
    extraction_method: str

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["matched_evidence"] = [item.to_dict() for item in self.matched_evidence]
        return out


@dataclass(frozen=True, kw_only=True)
class ErrorPayload:
    stage: str
    site: str
    keyword: str
    level: int
    url: str
    error_code: str
    error: str
    retryable: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


Payload = Union[
    SearchRequestedPayload,
    URLPayload,
    HTMLPayload,
    ResultPayloadV3,
    ErrorPayload,
]


@dataclass(frozen=True, kw_only=True)
class V3Message:
    envelope: V3Envelope
    payload: Payload

    @property
    def type(self) -> str:
        return self.envelope.type

    def to_dict(self) -> dict[str, Any]:
        out = self.envelope.to_dict()
        out["payload"] = self.payload.to_dict()
        return out


@dataclass(frozen=True, kw_only=True)
class CapacityStateV1:
    protocol_version: str
    event_type: str
    state: str
    state_version: int
    emergency_reserve_bytes: int
    effective_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _json_object(raw: str | bytes) -> dict[str, Any]:
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(
            raw,
            parse_float=Decimal,
            parse_int=int,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError("INVALID_JSON", "v3 message is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ProtocolError("INVALID_MESSAGE", "v3 message must be a JSON object")
    return data


def _reject_json_constant(value: str) -> None:
    raise ProtocolError("INVALID_JSON", f"non-standard JSON number {value} is not allowed")


def _reject_unknown_fields(data: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ProtocolError("UNKNOWN_FIELD", f"{label} contains unknown field {unknown[0]}")


def _reject_null(data: dict[str, Any], fields: set[str], label: str) -> None:
    for field in sorted(fields):
        if field in data and data[field] is None:
            raise ProtocolError("INVALID_MESSAGE", f"{label}.{field} must not be null")


def _require_fields(data: dict[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(fields - set(data))
    if missing:
        raise ProtocolError("INVALID_MESSAGE", f"{label} missing required field {missing[0]}")


def _require_string(value: Any, label: str, *, max_length: int | None = None) -> str:
    if not isinstance(value, str):
        raise ProtocolError("INVALID_MESSAGE", f"{label} must be a string")
    if max_length is not None and len(value) > max_length:
        raise ProtocolError("INVALID_MESSAGE", f"{label} exceeds max length")
    return value


def _require_non_blank(value: Any, label: str, *, max_length: int | None = None) -> str:
    value = _require_string(value, label, max_length=max_length)
    if not value.strip():
        raise ProtocolError("INVALID_MESSAGE", f"{label} must not be blank")
    return value


def _require_ulid(value: Any, label: str) -> str:
    value = _require_string(value, label)
    if not _ULID_RE.fullmatch(value):
        raise ProtocolError("INVALID_MESSAGE", f"{label} must be a canonical ULID")
    return value


def _require_pattern(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    value = _require_string(value, label)
    if not pattern.fullmatch(value):
        raise ProtocolError("INVALID_MESSAGE", f"{label} has invalid format")
    return value


def _require_timestamp(value: Any) -> str:
    value = _require_string(value, "timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProtocolError("INVALID_MESSAGE", "timestamp must be RFC3339 UTC") from exc
    if parsed.tzinfo is None:
        raise ProtocolError("INVALID_MESSAGE", "timestamp must include timezone")
    return value


def _require_url(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if allow_empty and value == "":
        return ""
    value = _require_string(value, label)
    if not _HTTP_URL_RE.fullmatch(value):
        raise ProtocolError("INVALID_TARGET_URL", f"{label} must be an absolute http(s) URL")
    try:
        validate_target_url(value)
    except ProtocolError as exc:
        raise ProtocolError("INVALID_TARGET_URL", f"{label}: {exc}") from exc
    return value


def _require_date(value: Any, label: str) -> str:
    value = _require_string(value, label)
    if value and not _DATE_RE.fullmatch(value):
        raise ProtocolError("INVALID_MESSAGE", f"{label} must be YYYY-MM-DD or empty")
    return value


def _envelope_from_dict(data: dict[str, Any]) -> V3Envelope:
    protocol_version = data.get("protocol_version")
    if not isinstance(protocol_version, str) or protocol_version != V3_PROTOCOL_VERSION:
        raise ProtocolError("UNKNOWN_PROTOCOL_VERSION", "protocol_version must be 3.0")
    _reject_unknown_fields(data, _ROOT_FIELDS, "v3 envelope")
    _reject_null(data, _ROOT_REQUIRED | {"aggregate_id", "causation_id"}, "v3 envelope")
    _require_fields(data, _ROOT_REQUIRED, "v3 envelope")
    msg_type = _require_non_blank(data.get("type"), "type")
    if msg_type not in STREAM_BY_TYPE:
        raise ProtocolError("INVALID_TYPE", f"type {msg_type!r} is not a v3 stream type")
    envelope = V3Envelope(
        protocol_version=protocol_version,
        type=msg_type,
        event_id=_require_ulid(data.get("event_id"), "event_id"),
        message_id=_require_pattern(data.get("message_id"), "message_id", _MESSAGE_ID_RE),
        task_id=_require_ulid(data.get("task_id"), "task_id"),
        aggregate_id=_require_ulid(data["aggregate_id"], "aggregate_id") if "aggregate_id" in data else None,
        idempotency_key=_require_pattern(data.get("idempotency_key"), "idempotency_key", _IDEMPOTENCY_RE),
        causation_id=_require_pattern(data["causation_id"], "causation_id", _MESSAGE_ID_RE) if "causation_id" in data else None,
        correlation_id=_require_pattern(data.get("correlation_id"), "correlation_id", _ASSOCIATION_ID_RE),
        attempt_no=_parse_integer(data.get("attempt_no"), "attempt_no", minimum=0, maximum=MAX_ATTEMPT_NO),
        timestamp=_require_timestamp(data.get("timestamp")),
        work_class=data.get("work_class"),
    )
    work_class = data.get("work_class")
    if work_class != WORK_CLASS_BY_TYPE[msg_type]:
        raise ProtocolError("INVALID_MESSAGE", "work_class does not match v3 message type")
    return envelope


def _check_stream_context(msg_type: str, stream: str) -> None:
    expected = STREAM_BY_TYPE[msg_type]
    if stream != expected:
        raise ProtocolError("INVALID_TYPE", f"type {msg_type!r} is not valid on stream {stream!r}")


def _parse_keywords(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ProtocolError("EMPTY_KEYWORDS", "keywords must be a non-empty array")
    if len(value) > 20:
        raise ProtocolError("TASK_LIMIT_EXCEEDED", "keywords exceeds 20")
    normalized: list[str] = []
    for item in value:
        if item is None:
            raise ProtocolError("INVALID_MESSAGE", "keywords item must not be null")
        keyword = _require_string(item, "keywords item", max_length=500)
        if not keyword.strip():
            raise ProtocolError("EMPTY_KEYWORDS", "keywords must not contain blank values")
        if keyword not in normalized:
            normalized.append(keyword)
    return tuple(normalized)


def _parse_integer(value: Any, label: str, *, minimum: int, maximum: int | None = None) -> int:
    if isinstance(value, bool):
        raise ProtocolError("INVALID_INTEGER", f"{label} must be a mathematical integer")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ProtocolError("INVALID_NUMBER", f"{label} must be finite")
        if value != value.to_integral_value():
            raise ProtocolError("INVALID_INTEGER", f"{label} must be a mathematical integer")
        value = int(value)
    elif not isinstance(value, int):
        raise ProtocolError("INVALID_INTEGER", f"{label} must be a mathematical integer")
    if value < minimum:
        raise ProtocolError("INVALID_INTEGER", f"{label} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ProtocolError("INVALID_INTEGER", f"{label} must be <= {maximum}")
    return value


def _parse_evidence(value: Any) -> tuple[MatchedEvidenceV3, ...]:
    if not isinstance(value, list):
        raise ProtocolError("INVALID_MESSAGE", "matched_evidence must be an array")
    items: list[MatchedEvidenceV3] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ProtocolError("INVALID_MESSAGE", "matched_evidence item must be an object")
        allowed = {"term", "origin", "field", "weight"}
        _reject_unknown_fields(raw, allowed, "matched_evidence")
        _require_fields(raw, allowed, "matched_evidence")
        _reject_null(raw, allowed, "matched_evidence")
        weight = raw["weight"]
        if isinstance(weight, bool):
            raise ProtocolError("INVALID_MESSAGE", "matched_evidence.weight must be a finite number")
        if isinstance(weight, Decimal):
            if not weight.is_finite():
                raise ProtocolError("INVALID_MESSAGE", "matched_evidence.weight must be finite")
            converted = float(weight)
            if not math.isfinite(converted):
                raise ProtocolError("INVALID_MESSAGE", "matched_evidence.weight must be finite")
            if converted.is_integer() and Decimal(converted) == weight:
                weight = int(converted)
            else:
                weight = converted
        elif isinstance(weight, (int, float)):
            if not math.isfinite(weight) or weight < 0:
                raise ProtocolError("INVALID_MESSAGE", "matched_evidence.weight must be finite and non-negative")
        else:
            raise ProtocolError("INVALID_MESSAGE", "matched_evidence.weight must be a finite number")
        items.append(
            MatchedEvidenceV3(
                term=_require_non_blank(raw["term"], "evidence.term", max_length=500),
                origin=raw["origin"],
                field=raw["field"],
                weight=weight,
            )
        )
    return tuple(items)


def _parse_artifact_ref(value: Any) -> str:
    value = _require_non_blank(value, "artifact_ref", max_length=512)
    segments = value.split("/")
    if any(not _ARTIFACT_SEGMENT_RE.fullmatch(segment) for segment in segments):
        raise ProtocolError("INVALID_PATH", "artifact_ref must be an internal content-addressed reference")
    if any(segment in {".", ".."} for segment in segments):
        raise ProtocolError("INVALID_PATH", "artifact_ref must not contain . or .. path segments")
    if _DRIVE_PREFIX_RE.match(segments[0]):
        raise ProtocolError("INVALID_PATH", "artifact_ref must not contain a drive prefix")
    return value


def _decode_payload(msg_type: str, payload: Any) -> Payload:
    if not isinstance(payload, dict):
        raise ProtocolError("INVALID_MESSAGE", "payload must be a JSON object")
    if msg_type == "search_requested":
        allowed = {"target_url", "keywords", "level", "max_pages"}
        _reject_unknown_fields(payload, allowed, "payload")
        _require_fields(payload, allowed, "payload")
        _reject_null(payload, allowed, "payload")
        max_pages = _parse_integer(payload["max_pages"], "max_pages", minimum=1)
        if max_pages > 100:
            raise ProtocolError("INVALID_INTEGER", "max_pages must be <= 100")
        return SearchRequestedPayload(
            target_url=_require_url(payload["target_url"], "target_url"),
            keywords=_parse_keywords(payload["keywords"]),
            level=_parse_integer(payload["level"], "level", minimum=0, maximum=MAX_LEVEL),
            max_pages=max_pages,
        )
    if msg_type == "url":
        allowed = {
            "hit_id", "plan_id", "original_query", "query_term", "url", "title",
            "snippet", "published_at", "source", "level",
        }
        _reject_unknown_fields(payload, allowed, "payload")
        _require_fields(payload, allowed, "payload")
        _reject_null(payload, allowed, "payload")
        return URLPayload(
            hit_id=_require_non_blank(payload["hit_id"], "hit_id", max_length=128),
            plan_id=_require_non_blank(payload["plan_id"], "plan_id", max_length=128),
            original_query=_require_non_blank(payload["original_query"], "original_query", max_length=500),
            query_term=_require_non_blank(payload["query_term"], "query_term", max_length=500),
            url=_require_url(payload["url"], "url"),
            title=_require_string(payload["title"], "title", max_length=500),
            snippet=_require_string(payload["snippet"], "snippet", max_length=2000),
            published_at=_require_date(payload["published_at"], "published_at"),
            source=_require_non_blank(payload["source"], "source", max_length=500),
            level=_parse_integer(payload["level"], "level", minimum=0, maximum=MAX_LEVEL),
        )
    if msg_type == "html":
        allowed = {
            "hit_id", "plan_id", "original_query", "query_term", "requested_url",
            "final_url", "title", "snippet", "published_at", "source", "level",
            "artifact_ref", "checksum", "content_type", "byte_size",
        }
        _reject_unknown_fields(payload, allowed, "payload")
        _require_fields(payload, allowed, "payload")
        _reject_null(payload, allowed, "payload")
        byte_size = _parse_integer(payload["byte_size"], "byte_size", minimum=0)
        if byte_size > MAX_ARTIFACT_BYTES:
            raise ProtocolError("INVALID_MESSAGE", "byte_size exceeds detail artifact limit")
        content_type = _require_string(payload["content_type"], "content_type", max_length=128)
        if not _CONTENT_TYPE_RE.fullmatch(content_type):
            raise ProtocolError("INVALID_MESSAGE", "content_type must be a valid media type")
        checksum = _require_string(payload["checksum"], "checksum", max_length=64)
        if not _LOWER_HEX64_RE.fullmatch(checksum):
            raise ProtocolError("INVALID_MESSAGE", "checksum must be lowercase SHA-256 hex")
        return HTMLPayload(
            hit_id=_require_non_blank(payload["hit_id"], "hit_id", max_length=128),
            plan_id=_require_non_blank(payload["plan_id"], "plan_id", max_length=128),
            original_query=_require_non_blank(payload["original_query"], "original_query", max_length=500),
            query_term=_require_non_blank(payload["query_term"], "query_term", max_length=500),
            requested_url=_require_url(payload["requested_url"], "requested_url"),
            final_url=_require_url(payload["final_url"], "final_url"),
            title=_require_string(payload["title"], "title", max_length=500),
            snippet=_require_string(payload["snippet"], "snippet", max_length=2000),
            published_at=_require_date(payload["published_at"], "published_at"),
            source=_require_non_blank(payload["source"], "source", max_length=500),
            level=_parse_integer(payload["level"], "level", minimum=0, maximum=MAX_LEVEL),
            artifact_ref=_parse_artifact_ref(payload["artifact_ref"]),
            checksum=checksum,
            content_type=content_type,
            byte_size=byte_size,
        )
    if msg_type == "result":
        allowed = {
            "hit_id", "plan_id", "original_query", "query_term", "requested_url",
            "final_url", "canonical_url", "title", "publish_date", "source",
            "summary", "content", "content_hash", "score", "matched_evidence",
            "status", "extraction_method",
        }
        _reject_unknown_fields(payload, allowed, "payload")
        _require_fields(payload, allowed, "payload")
        _reject_null(payload, allowed, "payload")
        content = _require_string(payload["content"], "content", max_length=10485760)
        content_hash = _require_string(payload["content_hash"], "content_hash", max_length=64)
        if content:
            expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if content_hash != expected_hash:
                raise ProtocolError("INVALID_MESSAGE", "content_hash must be SHA-256 of content")
        elif content_hash:
            raise ProtocolError("INVALID_MESSAGE", "content_hash must be empty when content is empty")
        status = payload["status"]
        if status not in {"accepted", "review_required", "irrelevant", "extract_failed", "unsupported_format"}:
            raise ProtocolError("INVALID_MESSAGE", "status is not a canonical task_article status")
        method = payload["extraction_method"]
        if method not in {
            "site_selector", "cms_rule", "ai", "density", "fallback", "pdf",
            "docx", "xlsx", "none",
        }:
            raise ProtocolError("INVALID_MESSAGE", "extraction_method is invalid")
        return ResultPayloadV3(
            hit_id=_require_non_blank(payload["hit_id"], "hit_id", max_length=128),
            plan_id=_require_non_blank(payload["plan_id"], "plan_id", max_length=128),
            original_query=_require_non_blank(payload["original_query"], "original_query", max_length=500),
            query_term=_require_non_blank(payload["query_term"], "query_term", max_length=500),
            requested_url=_require_url(payload["requested_url"], "requested_url"),
            final_url=_require_url(payload["final_url"], "final_url"),
            canonical_url=_require_url(payload["canonical_url"], "canonical_url", allow_empty=True),
            title=_require_string(payload["title"], "title", max_length=500),
            publish_date=_require_date(payload["publish_date"], "publish_date"),
            source=_require_non_blank(payload["source"], "source", max_length=500),
            summary=_require_string(payload["summary"], "summary", max_length=5000),
            content=content,
            content_hash=content_hash,
            score=_parse_integer(payload["score"], "score", minimum=0, maximum=MAX_SCORE),
            matched_evidence=_parse_evidence(payload["matched_evidence"]),
            status=status,
            extraction_method=method,
        )
    if msg_type == "error":
        allowed = {"stage", "site", "keyword", "level", "url", "error_code", "error", "retryable"}
        _reject_unknown_fields(payload, allowed, "payload")
        _require_fields(payload, allowed, "payload")
        _reject_null(payload, allowed, "payload")
        error_code = _require_string(payload["error_code"], "error_code", max_length=128)
        if error_code not in _CANONICAL_ERRORS:
            raise ProtocolError("INVALID_MESSAGE", "error_code is not canonical")
        stage = payload["stage"]
        if stage not in {"search", "download", "parse", "store"}:
            raise ProtocolError("INVALID_MESSAGE", "stage is invalid")
        retryable = payload["retryable"]
        if not isinstance(retryable, bool):
            raise ProtocolError("INVALID_BOOLEAN", "retryable must be a boolean")
        return ErrorPayload(
            stage=stage,
            site=_require_non_blank(payload["site"], "site", max_length=500),
            keyword=_require_string(payload["keyword"], "keyword", max_length=500),
            level=_parse_integer(payload["level"], "level", minimum=0, maximum=MAX_LEVEL),
            url=_require_string(payload["url"], "url", max_length=2048),
            error_code=error_code,
            error=_require_non_blank(payload["error"], "error", max_length=2048),
            retryable=retryable,
        )
    raise ProtocolError("INVALID_TYPE", f"type {msg_type!r} has no payload decoder")


def decode_v3_message(raw: str | bytes, *, stream: str) -> V3Message:
    data = _json_object(raw)
    envelope = _envelope_from_dict(data)
    _check_stream_context(envelope.type, stream)
    payload = _decode_payload(envelope.type, data.get("payload"))
    return V3Message(envelope=envelope, payload=payload)


def encode_v3_message(message: V3Message) -> str:
    return json.dumps(message.to_dict(), ensure_ascii=False, separators=(",", ":"), allow_nan=False)


_CAPACITY_EVENT_STATE = {
    "capacity_normal": "NORMAL",
    "capacity_warning": "WARNING",
    "capacity_blocked": "BLOCKED",
    "stream_drain_only": "DRAIN_ONLY",
}
_CAPACITY_FIELDS = {
    "protocol_version", "event_type", "state", "state_version",
    "emergency_reserve_bytes", "effective_at",
}


def decode_capacity_state(raw: str | bytes) -> CapacityStateV1:
    data = _json_object(raw)
    _reject_unknown_fields(data, _CAPACITY_FIELDS, "capacity state")
    _require_fields(data, _CAPACITY_FIELDS, "capacity state")
    _reject_null(data, _CAPACITY_FIELDS, "capacity state")
    protocol_version = _require_string(data["protocol_version"], "protocol_version")
    if protocol_version != CONTROL_PROTOCOL_VERSION:
        raise ProtocolError("UNKNOWN_PROTOCOL_VERSION", "capacity protocol_version must be 1.0")
    event_type = _require_string(data["event_type"], "event_type")
    if event_type not in _CAPACITY_EVENT_STATE:
        raise ProtocolError("INVALID_TYPE", "capacity event_type is invalid")
    state = _require_string(data["state"], "state")
    if state != _CAPACITY_EVENT_STATE[event_type]:
        raise ProtocolError("INVALID_MESSAGE", "capacity event_type/state mismatch")
    state_version = _parse_integer(data["state_version"], "state_version", minimum=0, maximum=MAX_STATE_VERSION)
    if state_version < 1:
        raise ProtocolError("INVALID_MESSAGE", "state_version must be >= 1")
    reserve = _parse_integer(data["emergency_reserve_bytes"], "emergency_reserve_bytes", minimum=0, maximum=MAX_EMERGENCY_RESERVE_BYTES)
    if reserve < 1:
        raise ProtocolError("INVALID_MESSAGE", "emergency_reserve_bytes must be > 0")
    return CapacityStateV1(
        protocol_version=protocol_version,
        event_type=event_type,
        state=state,
        state_version=state_version,
        emergency_reserve_bytes=reserve,
        effective_at=_require_timestamp(data["effective_at"]),
    )


def encode_capacity_state(state: CapacityStateV1) -> str:
    return json.dumps(state.to_dict(), ensure_ascii=False, separators=(",", ":"), allow_nan=False)


__all__ = [
    "CapacityStateV1",
    "ErrorPayload",
    "HTMLPayload",
    "MatchedEvidenceV3",
    "ResultPayloadV3",
    "STREAM_BY_TYPE",
    "SearchRequestedPayload",
    "URLPayload",
    "V3Envelope",
    "V3Message",
    "decode_capacity_state",
    "decode_v3_message",
    "encode_capacity_state",
    "encode_v3_message",
]
