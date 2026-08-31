"""OSEC Evidence Profile V2 candidate library.

This module is intentionally not imported by any production entrypoint.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
from dataclasses import dataclass
from typing import Any, Sequence

_STRICT_ERROR_CODES = frozenset(
    {
        "strict_decode_invalid_json",
        "strict_decode_invalid_utf8",
        "strict_decode_bom",
        "strict_decode_duplicate_key",
        "strict_decode_lone_surrogate",
        "strict_decode_trailing_data",
    }
)
_LIMIT_ERROR_CODES = frozenset(
    {
        "evidence_limit_file_size",
        "evidence_limit_nesting_depth",
        "evidence_limit_integer_digits",
        "evidence_limit_array_length",
        "evidence_limit_object_members",
        "evidence_limit_string_length",
        "evidence_limit_case_count",
    }
)
_CANONICAL_ERROR_CODES = frozenset(
    {
        "canonical_invalid_value_type",
        "canonical_non_integer_number",
        "canonical_invalid_unicode",
        "canonical_root_not_object",
        "canonical_missing_id",
        "canonical_invalid_id",
    }
)
_AGGREGATE_ERROR_CODES = frozenset(
    {
        "aggregate_empty_set",
        "aggregate_duplicate_id",
        "aggregate_invalid_digest_length",
        "aggregate_unknown_algorithm",
        "aggregate_count_overflow",
        "aggregate_length_overflow",
    }
)
_MANIFEST_ERROR_CODES = frozenset({"manifest_invalid_category"})

FROZEN_ERROR_CODES = frozenset(
    _STRICT_ERROR_CODES
    | _LIMIT_ERROR_CODES
    | _CANONICAL_ERROR_CODES
    | _AGGREGATE_ERROR_CODES
    | _MANIFEST_ERROR_CODES
)

AGGREGATE_V1_MAGIC = b"OSEC-CASE-AGGREGATE-V1\x00"
CATEGORY_AGGREGATE_V1_MAGIC = b"OSEC-CASE-CATEGORY-AGGREGATE-V1\x00"
CASE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
CATEGORY_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
U32_MAX = 0xFFFFFFFF


class OSECError(Exception):
    """Stable machine-code error without raw input."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message if message is not None else code
        super().__init__(f"OSEC error {code}")

    def __str__(self) -> str:
        return f"OSEC error {self.code}: {self.message}"


def _err(code: str) -> OSECError:
    return OSECError(code)


@dataclass(frozen=True)
class EvidenceLimits:
    file_size: int = 16_777_216
    nesting_depth: int = 128
    integer_digits: int = 4096
    array_length: int = 10_000
    object_members: int = 1_000
    string_length: int = 1_048_576
    case_count: int = 10_000


DEFAULT_LIMITS = EvidenceLimits()


class IntegerLexeme(str):
    """Raw integer lexeme used only during parsing."""


class NonIntegerNumber(str):
    """Raw legal JSON number with a decimal point or exponent."""


@dataclass(frozen=True)
class CaseDigest:
    id: str
    digest: bytes


@dataclass(frozen=True)
class CanonicalCaseResult:
    canonical: bytes
    sha256: str


def _normalize_string(value: str) -> str:
    try:
        return value.encode("utf-8", "surrogatepass").decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _err("strict_decode_lone_surrogate") from exc


def _normalize_ast(value: Any) -> Any:
    if isinstance(value, (IntegerLexeme, NonIntegerNumber)):
        return value
    if isinstance(value, str):
        return _normalize_string(value)
    if isinstance(value, list):
        return [_normalize_ast(item) for item in value]
    if isinstance(value, dict):
        return {_normalize_string(key): _normalize_ast(item) for key, item in value.items()}
    return value


def _apply_limits(value: Any, depth: int, raw_objects: list[list[tuple[str, Any]]], index: list[int], limits: EvidenceLimits) -> Any:
    if isinstance(value, IntegerLexeme):
        digits = len(value.lstrip("-"))
        if digits > limits.integer_digits:
            raise _err("evidence_limit_integer_digits")
        return int(value)
    if isinstance(value, NonIntegerNumber):
        return value
    if isinstance(value, dict):
        if depth > limits.nesting_depth:
            raise _err("evidence_limit_nesting_depth")
        pairs = raw_objects[index[0]]
        index[0] += 1
        if len(pairs) > limits.object_members:
            raise _err("evidence_limit_object_members")
        result: dict[str, Any] = {}
        for key, item in sorted(value.items(), key=lambda kv: kv[0].encode("utf-8")):
            if len(key.encode("utf-8")) > limits.string_length:
                raise _err("evidence_limit_string_length")
            result[key] = _apply_limits(item, depth + 1, raw_objects, index, limits)
        return result
    if isinstance(value, list):
        if depth > limits.nesting_depth:
            raise _err("evidence_limit_nesting_depth")
        if len(value) > limits.array_length:
            raise _err("evidence_limit_array_length")
        return [_apply_limits(item, depth + 1, raw_objects, index, limits) for item in value]
    if isinstance(value, str):
        if len(value.encode("utf-8")) > limits.string_length:
            raise _err("evidence_limit_string_length")
        return value
    return value


def strict_decode(raw: bytes, limits: EvidenceLimits = DEFAULT_LIMITS) -> Any:
    if not isinstance(raw, bytes):
        raise TypeError("raw must be bytes")
    if len(raw) > limits.file_size:
        raise _err("evidence_limit_file_size")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise _err("strict_decode_bom")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _err("strict_decode_invalid_utf8") from exc

    stripped = text.lstrip()
    if re.match(r"^-?0[0-9]", stripped):
        raise _err("strict_decode_invalid_json")
    number_prefix = re.match(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]*)?", stripped)
    if number_prefix and re.search(r"[eE][+-]?$", number_prefix.group(0)):
        raise _err("strict_decode_invalid_json")

    raw_objects: list[list[tuple[str, Any]]] = []

    def record_pairs(pairs):
        raw_objects.append(list(pairs))
        return dict(pairs)

    def reject_constant(_value: str) -> Any:
        raise ValueError("non-standard JSON constant")

    decoder = json.JSONDecoder(
        parse_int=IntegerLexeme,
        parse_float=NonIntegerNumber,
        parse_constant=reject_constant,
        object_pairs_hook=record_pairs,
    )
    try:
        value, end = decoder.raw_decode(text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise _err("strict_decode_invalid_json") from exc
    if text[end:].strip():
        raise _err("strict_decode_trailing_data")

    value = _normalize_ast(value)
    for pairs in raw_objects:
        seen = set()
        for key, _item in pairs:
            normalized = _normalize_string(key)
            if normalized in seen:
                raise _err("strict_decode_duplicate_key")
            seen.add(normalized)
    return _apply_limits(value, 1, raw_objects, [0], limits)


def _validate_canonical_value(value: Any, stack: list[int]) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, NonIntegerNumber):
        raise _err("canonical_non_integer_number")
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
        result = [_validate_canonical_value(item, stack) for item in value]
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
            normalized_key = _validate_canonical_value(key, stack)
            result[normalized_key] = _validate_canonical_value(item, stack)
        stack.pop()
        return result
    raise _err("canonical_invalid_value_type")


def _encode_string(value: str) -> bytes:
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


def _encode_canonical(value: Any) -> bytes:
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if isinstance(value, int):
        return str(value).encode("ascii")
    if isinstance(value, str):
        return _encode_string(value)
    if isinstance(value, list):
        return b"[" + b",".join(_encode_canonical(item) for item in value) + b"]"
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda kv: kv[0].encode("utf-8"))
        return b"{" + b",".join(_encode_string(key) + b":" + _encode_canonical(item) for key, item in items) + b"}"
    raise _err("canonical_invalid_value_type")


def canonical_json(value: Any) -> bytes:
    validated = _validate_canonical_value(value, [])
    return _encode_canonical(validated)


def canonical_case(value: Any) -> CanonicalCaseResult:
    if not isinstance(value, dict):
        raise _err("canonical_root_not_object")
    if "id" not in value:
        raise _err("canonical_missing_id")
    case_id = value["id"]
    if not isinstance(case_id, str) or not CASE_ID_RE.match(case_id):
        raise _err("canonical_invalid_id")
    canonical = canonical_json(value)
    return CanonicalCaseResult(canonical=canonical, sha256=hashlib.sha256(canonical).hexdigest())


def validate_case_dataset(cases: Sequence[Any], limits: EvidenceLimits = DEFAULT_LIMITS) -> int:
    count = len(cases)
    if count > limits.case_count:
        raise _err("evidence_limit_case_count")
    return count


def _checked_u32(value: int, code: str) -> int:
    if value < 0 or value > U32_MAX:
        raise _err(code)
    return value


def _aggregate_records(magic: bytes, prefix: bytes | None, digests: Sequence[CaseDigest]) -> str:
    if not digests:
        raise _err("aggregate_empty_set")
    seen = set()
    records = []
    for item in digests:
        if item.id in seen:
            raise _err("aggregate_duplicate_id")
        seen.add(item.id)
        if len(item.digest) != 32:
            raise _err("aggregate_invalid_digest_length")
        records.append((item.id.encode("utf-8"), item.digest))
    records.sort(key=lambda record: record[0])
    _checked_u32(len(records), "aggregate_count_overflow")
    stream = bytearray(magic)
    if prefix is not None:
        stream.extend(prefix)
    stream.extend(struct.pack(">I", _checked_u32(len(records), "aggregate_count_overflow")))
    for case_id, digest in records:
        stream.extend(struct.pack(">I", _checked_u32(len(case_id), "aggregate_length_overflow")))
        stream.extend(case_id)
        stream.extend(digest)
    return hashlib.sha256(bytes(stream)).hexdigest()


def aggregate_v1(digests: Sequence[CaseDigest], algorithm: str = "OSEC-CASE-AGGREGATE-V1") -> str:
    if algorithm != "OSEC-CASE-AGGREGATE-V1":
        raise _err("aggregate_unknown_algorithm")
    return _aggregate_records(AGGREGATE_V1_MAGIC, None, digests)


def category_aggregate_v1(category_name: str, digests: Sequence[CaseDigest]) -> str:
    if not CATEGORY_NAME_RE.match(category_name):
        raise _err("manifest_invalid_category")
    encoded = category_name.encode("utf-8")
    prefix = struct.pack(">I", _checked_u32(len(encoded), "aggregate_length_overflow")) + encoded
    return _aggregate_records(CATEGORY_AGGREGATE_V1_MAGIC, prefix, digests)
