"""Conservative HTML/JSON selector evidence extraction and validation."""

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

MAX_JSON_DEPTH = 20
MAX_JSON_NODES = 10_000
MAX_JSON_ARRAYS = 100
MAX_JSON_SAMPLES = 20
MAX_JSON_STRING_LENGTH = 1_000_000
MAX_RESULT_ITEMS = 200

_DYNAMIC_CLASS_RE = re.compile(r"(^|[^a-z])([a-f0-9]{8,}|\d{6,})([^a-z]|$)", re.I)


@dataclass(frozen=True)
class SelectorEvidence:
    """Validated, in-memory selector evidence for one candidate."""

    candidate_key: tuple[str, ...]
    candidate_kind: str
    response_kind: str
    result_item: str
    title: str
    url: str
    final_origin: str
    match_count: int
    validated: bool
    evidence_source: str
    snippet: str = ""
    body: str = ""

    def __repr__(self) -> str:
        return (
            f"SelectorEvidence(kind={self.candidate_kind!r}, "
            f"result_item={self.result_item!r}, match_count={self.match_count})"
        )


@dataclass(frozen=True)
class SelectorExtractionResult:
    evidence: SelectorEvidence | None
    code: str
    reason: str = ""


def _looks_dynamic_class(token: str) -> bool:
    return bool(_DYNAMIC_CLASS_RE.search(token))


def _stable_classes(class_attr: Any) -> tuple[str, ...]:
    if not class_attr:
        return ()
    if isinstance(class_attr, list):
        tokens = [str(t) for t in class_attr]
    else:
        tokens = str(class_attr).split()
    return tuple(t for t in tokens if not _looks_dynamic_class(t))


def _safe_href(href: str) -> bool:
    href = href.strip()
    if not href or href.startswith("#"):
        return False
    try:
        parts = urlsplit(href)
    except ValueError:
        return False
    if parts.scheme and parts.scheme.lower() not in ("http", "https"):
        return False
    return True


def _css_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _selector_for(tag: Tag) -> str:
    parts = [tag.name or ""]
    if tag.get("id"):
        parts.append("#" + _css_escape(str(tag.get("id"))))
    classes = _stable_classes(tag.get("class"))
    if not classes and not tag.get("id"):
        return ""
    parts.extend("." + _css_escape(c) for c in classes)
    for key in sorted(tag.attrs):
        if key.startswith("data-"):
            value = str(tag.attrs[key])
            parts.append(f'[{_css_escape(key)}="{_css_escape(value)}"]')
    return "".join(parts)


def _structural_key(tag: Tag) -> tuple[str, ...]:
    return (
        tag.name or "",
        tuple(sorted(_stable_classes(tag.get("class")))),
        str(tag.get("id", "")),
        tuple(sorted(k for k in tag.attrs if k.startswith("data-"))),
    )


def _non_empty_texts(child: Tag) -> tuple[str, ...]:
    values = []
    for node in child.find_all(["a", "h1", "h2", "h3", "h4", "h5", "h6"]):
        text = node.get_text(" ", strip=True)
        if text:
            values.append(text)
    return tuple(dict.fromkeys(values))


def _child_evidence(child: Tag) -> tuple[str, str] | None:
    links = child.find_all("a", href=True)
    if len(links) != 1 or not _safe_href(links[0].get("href", "")):
        return None
    link_text = links[0].get_text(" ", strip=True)
    headings = child.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    heading_tags = [h for h in headings if h.get_text(" ", strip=True)]
    if link_text:
        return "a", "a"
    if len(heading_tags) == 1:
        return heading_tags[0].name or "", heading_tags[0].name or ""
    return None


def _validate_html_selectors(soup: BeautifulSoup, result_item: str, title: str, url: str) -> int:
    try:
        items = soup.select(result_item)
    except Exception:
        return 0
    if len(items) < 2 or len(items) > MAX_RESULT_ITEMS:
        return 0
    for item in items:
        links = item.select(url)
        titles = item.select(title)
        if len(links) != 1 or not _safe_href(links[0].get("href", "")):
            return 0
        if len(titles) != 1 or not titles[0].get_text(" ", strip=True):
            return 0
    return len(items)


def _escape_pointer_part(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def _pointer(tokens: tuple[str, ...]) -> str:
    if not tokens:
        return ""
    return "/" + "/".join(_escape_pointer_part(t) for t in tokens)


def _resolve_pointer(data: Any, pointer: str) -> Any:
    if not pointer:
        return data
    if not pointer.startswith("/"):
        raise ValueError("invalid pointer")
    node = data
    for raw in pointer[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            node = node[part]
        elif isinstance(node, list):
            node = node[int(part)]
        else:
            raise ValueError("invalid pointer traversal")
    return node


def _json_leaf_paths(value: Any, prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], str]:
    leaves: dict[tuple[str, ...], str] = {}
    if isinstance(value, dict):
        for key in sorted(value):
            leaves.update(_json_leaf_paths(value[key], prefix + (str(key),)))
    elif isinstance(value, str):
        leaves[prefix] = value
    return leaves


def _is_url_string(value: str) -> bool:
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme.lower() in ("http", "https") and bool(parts.netloc)


def _json_candidate_evidence(array_pointer: str, array: list[Any]) -> tuple[str, str, int] | None:
    if len(array) < 2:
        return None
    samples = array[:MAX_JSON_SAMPLES]
    if not all(isinstance(item, dict) for item in samples):
        return None
    leaf_sets = [_json_leaf_paths(item) for item in samples]
    common = set(leaf_sets[0])
    for leaf_set in leaf_sets[1:]:
        common.intersection_update(leaf_set)
    if not common:
        return None

    url_paths = []
    title_paths = []
    for path in common:
        values = [leaf_set[path] for leaf_set in leaf_sets]
        if all(_is_url_string(v) for v in values):
            url_paths.append(path)
        elif all(v and not _is_url_string(v) for v in values):
            title_paths.append(path)
    if len(url_paths) != 1 or len(title_paths) != 1:
        return None
    if url_paths[0] == title_paths[0]:
        return None
    return _pointer(url_paths[0]), _pointer(title_paths[0]), len(array)


def _walk_json(value: Any, pointer: str, depth: int, state: dict[str, Any]) -> None:
    state["nodes"] += 1
    if state["nodes"] > MAX_JSON_NODES:
        raise ValueError("json node budget exceeded")
    if depth > MAX_JSON_DEPTH:
        raise ValueError("json depth budget exceeded")
    if isinstance(value, dict):
        for key in value:
            _walk_json(value[key], pointer + "/" + _escape_pointer_part(str(key)), depth + 1, state)
    elif isinstance(value, list):
        if len(value) >= 2:
            state["arrays"].append((pointer, value))
            if len(state["arrays"]) > MAX_JSON_ARRAYS:
                raise ValueError("json array budget exceeded")
        for index, item in enumerate(value):
            _walk_json(item, pointer + "/" + str(index), depth + 1, state)
    elif isinstance(value, str):
        if len(value) > MAX_JSON_STRING_LENGTH:
            raise ValueError("json string budget exceeded")


def _load_json_strict(body: bytes) -> Any:
    def _pairs_hook(pairs):
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate object key")
            result[key] = value
        return result

    return json.loads(body.decode("utf-8"), object_pairs_hook=_pairs_hook)


def extract_html_selector_evidence(
    html: str,
    *,
    final_origin: str,
    candidate_key: tuple[str, ...],
    evidence_source: str,
) -> SelectorExtractionResult:
    soup = BeautifulSoup(html, "html.parser")
    seen: dict[tuple[str, str, str], SelectorEvidence] = {}

    for element in soup.find_all(True):
        if element.name in ("html", "body", "script", "style"):
            continue
        children = [c for c in element.find_all(recursive=False) if isinstance(c, Tag)]
        groups: dict[tuple[str, ...], list[Tag]] = {}
        for child in children:
            groups.setdefault(_structural_key(child), []).append(child)
        for key, group in groups.items():
            if len(group) < 2:
                continue
            result_item = _selector_for(group[0])
            if not result_item:
                continue
            title_url = _child_evidence(group[0])
            if title_url is None:
                continue
            title_selector, url_selector = title_url
            match_count = _validate_html_selectors(soup, result_item, title_selector, url_selector)
            if match_count < 2:
                continue
            evidence = SelectorEvidence(
                candidate_key=candidate_key,
                candidate_kind="html_form",
                response_kind="html",
                result_item=result_item,
                title=title_selector,
                url=url_selector,
                final_origin=final_origin,
                match_count=match_count,
                validated=True,
                evidence_source=evidence_source,
            )
            seen[(result_item, title_selector, url_selector)] = evidence

    if len(seen) > 1:
        return SelectorExtractionResult(None, "ambiguous", "multiple conflicting HTML selector candidates")
    if len(seen) == 1:
        return SelectorExtractionResult(next(iter(seen.values())), "success")
    return SelectorExtractionResult(None, "no_evidence", "no stable HTML result structure found")


def extract_json_selector_evidence(
    body: bytes,
    *,
    final_origin: str,
    candidate_key: tuple[str, ...],
    evidence_source: str,
) -> SelectorExtractionResult:
    try:
        data = _load_json_strict(body)
    except Exception:
        return SelectorExtractionResult(None, "rejected", "strict JSON parsing failed")

    state = {"nodes": 0, "arrays": []}
    try:
        _walk_json(data, "", 0, state)
    except Exception:
        return SelectorExtractionResult(None, "rejected", "JSON budget exceeded")

    seen: dict[tuple[str, str, str], SelectorEvidence] = {}
    for array_pointer, array in state["arrays"]:
        candidate = _json_candidate_evidence(array_pointer, array)
        if candidate is None:
            continue
        url_pointer, title_pointer, match_count = candidate
        try:
            resolved = _resolve_pointer(data, array_pointer)
            for item in resolved[:MAX_JSON_SAMPLES]:
                _resolve_pointer(item, url_pointer)
                _resolve_pointer(item, title_pointer)
        except Exception:
            continue
        evidence = SelectorEvidence(
            candidate_key=candidate_key,
            candidate_kind="json_api",
            response_kind="json",
            result_item=array_pointer,
            title=title_pointer,
            url=url_pointer,
            final_origin=final_origin,
            match_count=len(resolved),
            validated=True,
            evidence_source=evidence_source,
        )
        seen[(array_pointer, url_pointer, title_pointer)] = evidence

    if len(seen) > 1:
        return SelectorExtractionResult(None, "ambiguous", "multiple conflicting JSON selector candidates")
    if len(seen) == 1:
        return SelectorExtractionResult(next(iter(seen.values())), "success")
    return SelectorExtractionResult(None, "no_evidence", "no stable JSON result structure found")
