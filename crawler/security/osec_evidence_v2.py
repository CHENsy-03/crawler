"""Canonical V2 candidate runtime based on Amendment 1."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from crawler.security.osec_evidence import (
    CanonicalCaseResult,
    CaseDigest,
    EvidenceLimits,
    NonIntegerNumber,
    OSECError,
    aggregate_v1,
    canonical_case,
    canonical_json,
    category_aggregate_v1,
    strict_decode,
    validate_case_dataset,
)

NONINTEGER_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")
CASE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


@dataclass(frozen=True)
class EvidenceLimitsV2:
    file_size: int = 16_777_216
    nesting_depth: int = 128
    number_digits: int = 4096
    array_length: int = 10_000
    object_members: int = 1_000
    string_length: int = 1_048_576
    case_count: int = 10_000


DEFAULT_LIMITS_V2 = EvidenceLimitsV2()


def _err(code: str) -> OSECError:
    return OSECError(code)


def _number_digits(lexeme: str) -> int:
    return sum(1 for char in lexeme if char.isdigit())


def _is_valid_noninteger(raw: str) -> bool:
    if not NONINTEGER_RE.match(raw):
        return False
    return "." in raw or "e" in raw or "E" in raw


def _apply_v2_limits(value: Any, depth: int, limits: EvidenceLimitsV2) -> Any:
    if isinstance(value, NonIntegerNumber):
        if _number_digits(str(value)) > limits.number_digits:
            raise _err("evidence_limit_number_digits")
        return value
    if isinstance(value, dict):
        if depth > limits.nesting_depth:
            raise _err("evidence_limit_nesting_depth")
        if len(value) > limits.object_members:
            raise _err("evidence_limit_object_members")
        result: dict[str, Any] = {}
        for key in sorted(value, key=lambda k: k.encode("utf-8")):
            if len(key.encode("utf-8")) > limits.string_length:
                raise _err("evidence_limit_string_length")
            result[key] = _apply_v2_limits(value[key], depth + 1, limits)
        return result
    if isinstance(value, list):
        if depth > limits.nesting_depth:
            raise _err("evidence_limit_nesting_depth")
        if len(value) > limits.array_length:
            raise _err("evidence_limit_array_length")
        return [_apply_v2_limits(item, depth + 1, limits) for item in value]
    if isinstance(value, str):
        if len(value.encode("utf-8")) > limits.string_length:
            raise _err("evidence_limit_string_length")
        return value
    return value


def strict_decode_v2(raw: bytes, limits: EvidenceLimitsV2 = DEFAULT_LIMITS_V2) -> Any:
    bridge = EvidenceLimits(
        file_size=limits.file_size,
        nesting_depth=2**31 - 1,
        integer_digits=limits.number_digits,
        array_length=2**31 - 1,
        object_members=2**31 - 1,
        string_length=2**31 - 1,
        case_count=2**31 - 1,
    )
    try:
        value = strict_decode(raw, bridge)
    except OSECError as exc:
        if exc.code == "evidence_limit_integer_digits":
            raise _err("evidence_limit_number_digits") from exc
        raise
    return _apply_v2_limits(value, 1, limits)


def _validate_v2_value(value: Any, stack: list[int]) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, NonIntegerNumber):
        raw = str(value)
        if not _is_valid_noninteger(raw):
            raise _err("canonical_invalid_number_lexeme")
        if _number_digits(raw) > DEFAULT_LIMITS_V2.number_digits:
            raise _err("evidence_limit_number_digits")
        return value
    if isinstance(value, str):
        try:
            return value.encode("utf-8", "surrogatepass").decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _err("canonical_invalid_unicode") from exc
    if isinstance(value, list):
        marker = id(value)
        if marker in stack:
            raise _err("canonical_invalid_value_type")
        stack.append(marker)
        result = [_validate_v2_value(item, stack) for item in value]
        stack.pop()
        return result
    if isinstance(value, dict):
        marker = id(value)
        if marker in stack:
            raise _err("canonical_invalid_value_type")
        stack.append(marker)
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise _err("canonical_invalid_value_type")
            normalized_key = _validate_v2_value(key, stack)
            result[normalized_key] = _validate_v2_value(item, stack)
        stack.pop()
        return result
    raise _err("canonical_invalid_value_type")


def _encode_v2_string(value: str) -> bytes:
    out: list[str] = ['"']
    for char in value:
        code = ord(char)
        if char == '"':
            out.append('\\"')
        elif char == "\\":
            out.append("\\\\")
        elif char == "\b":
            out.append("\\b")
        elif char == "\t":
            out.append("\\t")
        elif char == "\n":
            out.append("\\n")
        elif char == "\f":
            out.append("\\f")
        elif char == "\r":
            out.append("\\r")
        elif code < 0x20:
            out.append("\\u%04x" % code)
        else:
            out.append(char)
    out.append('"')
    return "".join(out).encode("utf-8")


def _encode_v2_value(value: Any) -> bytes:
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if isinstance(value, int):
        return str(value).encode("ascii")
    if isinstance(value, NonIntegerNumber):
        return str(value).encode("ascii")
    if isinstance(value, str):
        return _encode_v2_string(value)
    if isinstance(value, list):
        return b"[" + b",".join(_encode_v2_value(item) for item in value) + b"]"
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda kv: kv[0].encode("utf-8"))
        return b"{" + b",".join(_encode_v2_string(key) + b":" + _encode_v2_value(item) for key, item in items) + b"}"
    raise _err("canonical_invalid_value_type")


def canonical_json_v2(value: Any) -> bytes:
    validated = _validate_v2_value(value, [])
    return _encode_v2_value(validated)


def canonical_case_v2(value: Any) -> CanonicalCaseResult:
    if not isinstance(value, dict):
        raise _err("canonical_root_not_object")
    if "id" not in value:
        raise _err("canonical_missing_id")
    case_id = value["id"]
    if not isinstance(case_id, str) or not CASE_ID_RE.match(case_id):
        raise _err("canonical_invalid_id")
    canonical = canonical_json_v2(value)
    return CanonicalCaseResult(canonical=canonical, sha256=hashlib.sha256(canonical).hexdigest())


__all__ = [
    "EvidenceLimitsV2",
    "DEFAULT_LIMITS_V2",
    "strict_decode_v2",
    "canonical_json_v2",
    "canonical_case_v2",
    "CaseDigest",
    "aggregate_v1",
    "category_aggregate_v1",
    "validate_case_dataset",
]
