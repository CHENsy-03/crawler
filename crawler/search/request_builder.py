"""Pure, network-free deterministic SearchPlan request construction."""

import json
from urllib.parse import urlencode, urlsplit, urlunsplit

from crawler.search.search_plan import (
    KEYWORD_LOCATION_FORM,
    KEYWORD_LOCATION_JSON,
    KEYWORD_LOCATION_QUERY,
    REQUEST_FORMAT_FORM_URLENCODED,
    REQUEST_FORMAT_JSON,
    REQUEST_FORMAT_NONE,
    RESPONSE_FORMAT_HTML,
    RESPONSE_FORMAT_JSON,
    ProtocolError,
    SearchPlan,
    _thaw_json,
    validate_search_plan,
)
from crawler.site.search_probe import SearchProbeRequest


def _json_leaf(value: object):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_leaf(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_leaf(item) for key, item in value.items()}
    raise ProtocolError("INVALID_JSON_VALUE", "JSON template value is not JSON-serializable")


def _set_path(root: dict[str, object], path: tuple[str, ...], value: object) -> None:
    node = root
    for part in path[:-1]:
        child = node.get(part)
        if child is None:
            child = {}
            node[part] = child
        if not isinstance(child, dict):
            raise ProtocolError("INVALID_REQUEST_SHAPE", "JSON path crosses a non-object node")
        node = child
    node[path[-1]] = value


def _build_query(plan: SearchPlan, keyword: str, page_value: int | None, page_size: int | None) -> list[tuple[str, str]]:
    params = list(plan.request_shape.fixed_query_params)
    if plan.request_shape.keyword_location == KEYWORD_LOCATION_QUERY:
        params.append((plan.request_shape.keyword_path[0], keyword))
    if plan.pagination.enabled and plan.pagination.location == KEYWORD_LOCATION_QUERY:
        params.append((plan.pagination.value_path[0], str(page_value)))
        if plan.pagination.page_size_path:
            params.append((plan.pagination.page_size_path[0], str(page_size)))
    return sorted(params, key=lambda pair: pair[0])


def _build_form(plan: SearchPlan, keyword: str, page_value: int | None, page_size: int | None) -> bytes:
    fields = list(plan.request_shape.form_fields)
    if plan.request_shape.keyword_location == KEYWORD_LOCATION_FORM:
        fields.append((plan.request_shape.keyword_path[0], keyword))
    if plan.pagination.enabled and plan.pagination.location == KEYWORD_LOCATION_FORM:
        fields.append((plan.pagination.value_path[0], str(page_value)))
        if plan.pagination.page_size_path:
            fields.append((plan.pagination.page_size_path[0], str(page_size)))
    return urlencode(sorted(fields, key=lambda pair: pair[0]), doseq=True).encode("utf-8")


def _build_json_body(plan: SearchPlan, keyword: str, page_value: int | None, page_size: int | None) -> bytes:
    body: dict[str, object] = {}
    for path, value in plan.request_shape.json_object_template:
        _set_path(body, path, _json_leaf(_thaw_json(value)))
    if plan.request_shape.keyword_location == KEYWORD_LOCATION_JSON:
        _set_path(body, plan.request_shape.keyword_path, keyword)
    if plan.pagination.enabled and plan.pagination.location == KEYWORD_LOCATION_JSON:
        _set_path(body, plan.pagination.value_path, page_value)
        if plan.pagination.page_size_path:
            _set_path(body, plan.pagination.page_size_path, page_size)
    return json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def build_search_request(plan: SearchPlan, keyword: str, page_index: int = 0) -> SearchProbeRequest:
    validate_search_plan(plan)
    if not isinstance(keyword, str) or not keyword:
        raise ProtocolError("INVALID_KEYWORD", "keyword must be a non-empty string")
    if not isinstance(page_index, int) or isinstance(page_index, bool):
        raise ProtocolError("INVALID_PAGE_INDEX", "page_index must be an integer")
    if page_index < 0 or page_index >= plan.pagination.max_pages:
        raise ProtocolError("INVALID_PAGE_INDEX", "page_index is out of range")

    page_value: int | None = None
    page_size: int | None = None
    if plan.pagination.enabled:
        page_value = plan.pagination.start + page_index * plan.pagination.step
        page_size = plan.pagination.page_size

    parts = urlsplit(plan.endpoint)
    query_pairs = _build_query(plan, keyword, page_value, page_size)
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query_pairs, doseq=True), ""))

    body: bytes | None = None
    headers: list[tuple[str, str]] = [("User-Agent", "crawler-platform-probe/1.0")]
    if plan.response_format == RESPONSE_FORMAT_HTML:
        headers.append(("Accept", "text/html, application/xhtml+xml"))
    else:
        headers.append(("Accept", "application/json, application/*+json"))

    if plan.http_method == "POST":
        if plan.request_format == REQUEST_FORMAT_FORM_URLENCODED:
            body = _build_form(plan, keyword, page_value, page_size)
            headers.append(("Content-Type", "application/x-www-form-urlencoded"))
        elif plan.request_format == REQUEST_FORMAT_JSON:
            body = _build_json_body(plan, keyword, page_value, page_size)
            headers.append(("Content-Type", "application/json"))
        elif plan.request_format != REQUEST_FORMAT_NONE:
            raise ProtocolError("INVALID_REQUEST_FORMAT", "unsupported POST request format")
    elif plan.request_format != REQUEST_FORMAT_NONE:
        raise ProtocolError("INVALID_REQUEST_FORMAT", "GET plan has a request body format")

    return SearchProbeRequest(
        method=plan.http_method,
        url=url,
        headers=tuple(headers),
        body=body,
        approved_origins=(plan.endpoint,),
    )