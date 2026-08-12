"""Redis-backed cache for validated SearchPlan objects."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from crawler.search.search_plan import (
    ProtocolError,
    SearchPlan,
    compute_plan_id,
    validate_search_plan,
)
from crawler.site.normalizer import (
    SiteNormalizationError,
    normalize_target_url,
    normalized_origin,
    same_origin,
)
from crawler.site.security import classify_ip, is_ip_literal

CACHE_SCHEMA_VERSION = 1
CACHE_KEY_PREFIX = "crawler:search_plan:v1:"
DEFAULT_PLAN_CACHE_TTL_SECONDS = 86400

STATUS_HIT = "hit"
STATUS_MISS = "miss"
STATUS_CORRUPT = "corrupt"
STATUS_READ_FAILED = "read_failed"

ERROR_PLAN_CACHE_READ_FAILED = "plan_cache_read_failed"
ERROR_PLAN_CACHE_WRITE_FAILED = "plan_cache_write_failed"
ERROR_UNSAFE_TARGET = "unsafe_target"
ERROR_PLAN_VALIDATION_FAILED = "plan_validation_failed"

_ENVELOPE_FIELDS = {
    "cache_schema_version",
    "target_fingerprint",
    "plan",
}


class RedisClientProtocol(Protocol):
    """Minimal synchronous Redis surface used by the plan cache."""

    def get(self, name: str) -> str | bytes | None:
        ...

    def set(self, name: str, value: str | bytes, *, ex: int | None = None) -> Any:
        ...


@dataclass(frozen=True)
class PlanCacheReadResult:
    """Structured result of one cache read."""

    plan: SearchPlan | None
    status: str
    error_code: str | None

    @property
    def hit(self) -> bool:
        return (
            self.status == STATUS_HIT
            and self.plan is not None
            and self.error_code is None
        )


@dataclass(frozen=True)
class PlanCacheWriteResult:
    """Structured result of one cache write."""

    stored: bool
    error_code: str | None


class _CorruptCacheError(ValueError):
    """Internal marker for payloads that cannot be trusted."""


def _unsafe_host(host: str) -> bool:
    if is_ip_literal(host):
        safe, _ = classify_ip(host)
        return not safe
    return host == "localhost" or host.endswith(".localhost")


def _normalized_safe_target(raw: str) -> str:
    if not isinstance(raw, str):
        raise ValueError("target_url must be a string")
    normalized = normalize_target_url(raw)
    host = normalized_origin(normalized)[1]
    if _unsafe_host(host):
        raise ValueError("target_url is unsafe")
    return normalized


def compute_target_fingerprint(target_url: str) -> str:
    """Return the deterministic SHA-256 fingerprint for a target URL."""
    normalized = _normalized_safe_target(target_url)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_plan_cache_key(target_url: str) -> str:
    """Return the fixed Redis key for a target URL."""
    return CACHE_KEY_PREFIX + compute_target_fingerprint(target_url)


def _decode_cache_envelope(
    text: str,
    expected_fingerprint: str,
    normalized_target: str,
) -> SearchPlan:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise _CorruptCacheError from exc
    if not isinstance(data, dict):
        raise _CorruptCacheError
    if set(data) != _ENVELOPE_FIELDS:
        raise _CorruptCacheError
    if isinstance(data["cache_schema_version"], bool):
        raise _CorruptCacheError
    if (
        not isinstance(data["cache_schema_version"], int)
        or data["cache_schema_version"] != CACHE_SCHEMA_VERSION
    ):
        raise _CorruptCacheError
    if (
        not isinstance(data["target_fingerprint"], str)
        or data["target_fingerprint"] != expected_fingerprint
    ):
        raise _CorruptCacheError
    plan_data = data["plan"]
    if not isinstance(plan_data, dict):
        raise _CorruptCacheError

    try:
        plan = SearchPlan.from_dict(plan_data)
    except (KeyError, TypeError, ProtocolError, ValueError) as exc:
        raise _CorruptCacheError from exc
    try:
        validate_search_plan(plan)
    except ProtocolError as exc:
        raise _CorruptCacheError from exc

    if plan.plan_id != compute_plan_id(plan):
        raise _CorruptCacheError

    try:
        normalized_endpoint = normalize_target_url(plan.endpoint)
    except SiteNormalizationError as exc:
        raise _CorruptCacheError from exc
    if _unsafe_host(normalized_origin(normalized_endpoint)[1]):
        raise _CorruptCacheError
    try:
        same_origin_ok = same_origin(normalized_target, normalized_endpoint)
    except SiteNormalizationError as exc:
        raise _CorruptCacheError from exc
    if not same_origin_ok:
        raise _CorruptCacheError
    return plan


class SearchPlanCache:
    """Read and write SearchPlan cache entries through an injected client."""

    def __init__(
        self,
        redis_client: RedisClientProtocol,
        *,
        ttl_seconds: int = DEFAULT_PLAN_CACHE_TTL_SECONDS,
    ) -> None:
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
            raise TypeError("ttl_seconds must be an integer")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    def get(self, *, target_url: str) -> PlanCacheReadResult:
        """Read, decode, and strictly validate a cached SearchPlan."""
        try:
            normalized_target = _normalized_safe_target(target_url)
        except (SiteNormalizationError, ValueError):
            return PlanCacheReadResult(None, STATUS_CORRUPT, None)

        fingerprint = hashlib.sha256(normalized_target.encode("utf-8")).hexdigest()
        key = CACHE_KEY_PREFIX + fingerprint
        try:
            raw = self._redis.get(key)
        except Exception:
            return PlanCacheReadResult(None, STATUS_READ_FAILED, ERROR_PLAN_CACHE_READ_FAILED)

        if raw is None:
            return PlanCacheReadResult(None, STATUS_MISS, None)

        if isinstance(raw, bytes):
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                return PlanCacheReadResult(None, STATUS_CORRUPT, None)
        elif isinstance(raw, str):
            text = raw
        else:
            return PlanCacheReadResult(None, STATUS_CORRUPT, None)

        try:
            plan = _decode_cache_envelope(text, fingerprint, normalized_target)
        except _CorruptCacheError:
            return PlanCacheReadResult(None, STATUS_CORRUPT, None)
        return PlanCacheReadResult(plan, STATUS_HIT, None)

    def put(
        self,
        *,
        target_url: str,
        plan: SearchPlan,
    ) -> PlanCacheWriteResult:
        """Validate a plan and write it to Redis with a full TTL."""
        try:
            normalized_target = _normalized_safe_target(target_url)
        except (SiteNormalizationError, ValueError):
            return PlanCacheWriteResult(False, ERROR_UNSAFE_TARGET)

        if not isinstance(plan, SearchPlan):
            return PlanCacheWriteResult(False, ERROR_PLAN_VALIDATION_FAILED)
        try:
            validate_search_plan(plan)
        except ProtocolError:
            return PlanCacheWriteResult(False, ERROR_PLAN_VALIDATION_FAILED)
        if plan.plan_id != compute_plan_id(plan):
            return PlanCacheWriteResult(False, ERROR_PLAN_VALIDATION_FAILED)

        try:
            normalized_endpoint = normalize_target_url(plan.endpoint)
        except SiteNormalizationError:
            return PlanCacheWriteResult(False, ERROR_PLAN_VALIDATION_FAILED)
        if _unsafe_host(normalized_origin(normalized_endpoint)[1]):
            return PlanCacheWriteResult(False, ERROR_PLAN_VALIDATION_FAILED)
        try:
            same_origin_ok = same_origin(normalized_target, normalized_endpoint)
        except SiteNormalizationError:
            same_origin_ok = False
        if not same_origin_ok:
            return PlanCacheWriteResult(False, ERROR_PLAN_VALIDATION_FAILED)

        fingerprint = hashlib.sha256(normalized_target.encode("utf-8")).hexdigest()
        key = CACHE_KEY_PREFIX + fingerprint
        envelope = {
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "target_fingerprint": fingerprint,
            "plan": plan.to_dict(),
        }
        payload = json.dumps(
            envelope,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        try:
            self._redis.set(key, payload, ex=self._ttl_seconds)
        except Exception:
            return PlanCacheWriteResult(False, ERROR_PLAN_CACHE_WRITE_FAILED)
        return PlanCacheWriteResult(True, None)
