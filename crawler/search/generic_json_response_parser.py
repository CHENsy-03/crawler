"""Strict Generic JSON response parser using SearchPlan JSON Pointer selectors."""

from dataclasses import dataclass
from urllib.parse import urljoin

from crawler.search.execution_models import SearchResultItem
from crawler.search.json_pointer import JSONPointerError, resolve_json_pointer
from crawler.search.json_utils import load_strict_json
from crawler.search.search_plan import SearchPlan
from crawler.site.normalizer import SiteNormalizationError, normalize_target_url
from crawler.site.search_probe import SearchProbeResponse


class GenericJSONResponseError(ValueError):
    """Invalid JSON or unsafe response payload."""


class GenericJSONParseError(ValueError):
    """Response structure does not match the frozen selector contract."""


class GenericJSONResultURLError(ValueError):
    """Result URL cannot be safely normalized."""


@dataclass(frozen=True)
class GenericJSONPageParseOutcome:
    items: tuple[SearchResultItem, ...]
    result_item_count: int


def _optional_string(element, pointer: str) -> str:
    if not pointer:
        return ""
    try:
        value = resolve_json_pointer(element, pointer)
    except JSONPointerError:
        return ""
    if not isinstance(value, str):
        raise GenericJSONParseError("optional JSON selector resolved to a non-string")
    return value


def parse_generic_json_response(response: SearchProbeResponse, plan: SearchPlan) -> GenericJSONPageParseOutcome:
    try:
        data = load_strict_json(response.body)
    except Exception as exc:
        raise GenericJSONResponseError("Generic JSON response is not strict JSON") from exc

    try:
        container = resolve_json_pointer(data, plan.selectors.result_item)
    except JSONPointerError as exc:
        raise GenericJSONParseError("result_item pointer could not be resolved") from exc
    if not isinstance(container, list):
        raise GenericJSONParseError("result_item pointer did not resolve to a list")
    if not container:
        return GenericJSONPageParseOutcome((), 0)

    items = []
    for element in container:
        if not isinstance(element, dict):
            raise GenericJSONParseError("result element must be an object")
        title = _optional_string(element, plan.selectors.title)
        url = _optional_string(element, plan.selectors.url)
        if not title or not url:
            raise GenericJSONParseError("result element is missing title or url")
        snippet = _optional_string(element, plan.selectors.snippet)
        body = _optional_string(element, plan.selectors.body)
        try:
            normalized_url = normalize_target_url(urljoin(response.final_url, url))
        except (SiteNormalizationError, ValueError) as exc:
            raise GenericJSONResultURLError("result URL is invalid") from exc
        items.append(SearchResultItem(title=title, url=normalized_url, snippet=snippet, body=body))
    return GenericJSONPageParseOutcome(tuple(items), len(container))