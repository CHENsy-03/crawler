"""Strict RFC 6901 JSON Pointer resolution."""

from typing import Any


class JSONPointerError(ValueError):
    """Invalid pointer or traversal failure."""


def resolve_json_pointer(data: Any, pointer: str) -> Any:
    if pointer == "":
        return data
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise JSONPointerError("pointer must be empty or start with /")
    node = data
    for raw in pointer[1:].split("/"):
        part = _unescape(raw)
        if isinstance(node, dict):
            if part not in node:
                raise JSONPointerError("pointer key not found")
            node = node[part]
        elif isinstance(node, list):
            if not part.isdigit() or (len(part) > 1 and part.startswith("0")):
                raise JSONPointerError("invalid array index")
            index = int(part)
            if index < 0 or index >= len(node):
                raise JSONPointerError("array index out of range")
            node = node[index]
        else:
            raise JSONPointerError("pointer traversal hit a non-container")
    return node


def _unescape(raw: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(raw):
        if raw[i] == "~":
            if i + 1 >= len(raw):
                raise JSONPointerError("invalid pointer escape")
            token = raw[i + 1]
            if token == "0":
                out.append("~")
            elif token == "1":
                out.append("/")
            else:
                raise JSONPointerError("invalid pointer escape")
            i += 2
        else:
            out.append(raw[i])
            i += 1
    return "".join(out)