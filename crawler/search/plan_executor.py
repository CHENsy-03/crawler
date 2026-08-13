"""Execute a validated SearchPlan v2 through the safe probe HTTP foundation."""

import json
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from crawler.search.execution_models import (
    FAILURE_INVALID_RESULT_URL,
    FAILURE_NO_RESULTS,
    FAILURE_PLAN_INVALID,
    FAILURE_PLAN_NOT_EXECUTABLE,
    FAILURE_RESPONSE_REJECTED,
    FAILURE_SELECTOR_MISMATCH,
    FAILURE_TRANSPORT,
    SearchPlanExecutionResult,
    SearchResultItem,
)
from crawler.search.request_builder import build_search_request
from crawler.search.search_plan import (
    PLAN_STATUS_ACTIVE,
    PLAN_STATUS_READY,
    RESPONSE_FORMAT_HTML,
    RESPONSE_FORMAT_JSON,
    ProtocolError,
    SearchPlan,
    compute_plan_id,
    validate_search_plan,
)
from crawler.site.normalizer import (
    SiteNormalizationError,
    normalize_target_url,
)
from crawler.site.search_probe import (
    ProbeOutcome,
    SearchProbeFetcher,
    SearchProbePolicy,
    SearchProbeResponse,
)

EXECUTION_OK = "ok"
FAILURE_PLAN_INVALID = FAILURE_PLAN_INVALID
FAILURE_PLAN_NOT_EXECUTABLE = FAILURE_PLAN_NOT_EXECUTABLE
FAILURE_TRANSPORT = FAILURE_TRANSPORT
FAILURE_RESPONSE_REJECTED = FAILURE_RESPONSE_REJECTED
FAILURE_SELECTOR_MISMATCH = FAILURE_SELECTOR_MISMATCH
FAILURE_INVALID_RESULT_URL = FAILURE_INVALID_RESULT_URL
FAILURE_NO_RESULTS = FAILURE_NO_RESULTS

_ALLOWED_STATUSES = {PLAN_STATUS_READY, PLAN_STATUS_ACTIVE}


def _strict_json(body: bytes) -> Any:
    def _pairs_hook(pairs):
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate object key")
            result[key] = value
        return result

    return json.loads(body.decode("utf-8"), object_pairs_hook=_pairs_hook)


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


def _extract_html_items(response: SearchProbeResponse, plan: SearchPlan) -> list[SearchResultItem]:
    soup = BeautifulSoup(response.body.decode("utf-8", errors="ignore"), "html.parser")
    try:
        containers = soup.select(plan.selectors.result_item)
    except Exception as exc:
        raise SelectorApplicationError(str(exc)) from exc
    if not containers:
        raise SelectorApplicationError("result_item selector matched nothing")

    items: list[SearchResultItem] = []
    for container in containers:
        links = container.select(plan.selectors.url)
        titles = container.select(plan.selectors.title)
        if len(links) != 1 or len(titles) != 1:
            raise SelectorApplicationError("result item selector structure changed")
        href = links[0].get("href", "")
        title = titles[0].get_text(" ", strip=True)
        if not href or not title:
            raise SelectorApplicationError("result item is missing title or url")
        try:
            normalized = normalize_target_url(urljoin(response.final_url, href))
        except SiteNormalizationError as exc:
            raise SelectorApplicationError("result URL is invalid") from exc
        snippet = ""
        body = ""
        if plan.selectors.snippet:
            node = container.select_one(plan.selectors.snippet)
            snippet = node.get_text(" ", strip=True) if node else ""
        if plan.selectors.body:
            node = container.select_one(plan.selectors.body)
            body = node.get_text(" ", strip=True) if node else ""
        items.append(SearchResultItem(title=title, url=normalized, snippet=snippet, body=body))
    return items


def _extract_json_items(response: SearchProbeResponse, plan: SearchPlan) -> list[SearchResultItem]:
    try:
        data = _strict_json(response.body)
        container = _resolve_pointer(data, plan.selectors.result_item)
    except Exception as exc:
        raise SelectorApplicationError("JSON selector application failed") from exc
    if not isinstance(container, list):
        raise SelectorApplicationError("result_item pointer did not resolve to an array")
    if not container:
        raise SelectorApplicationError("result_item array is empty")

    items: list[SearchResultItem] = []
    for element in container:
        try:
            title = _resolve_pointer(element, plan.selectors.title)
            url = _resolve_pointer(element, plan.selectors.url)
        except Exception as exc:
            raise SelectorApplicationError("result element structure changed") from exc
        if not isinstance(title, str) or not title:
            raise SelectorApplicationError("result title is missing or not a string")
        if not isinstance(url, str) or not url:
            raise SelectorApplicationError("result url is missing or not a string")
        try:
            normalized = normalize_target_url(urljoin(response.final_url, url))
        except SiteNormalizationError as exc:
            raise SelectorApplicationError("result URL is invalid") from exc
        snippet = ""
        body = ""
        if plan.selectors.snippet:
            try:
                value = _resolve_pointer(element, plan.selectors.snippet)
                snippet = value if isinstance(value, str) else ""
            except Exception:
                snippet = ""
        if plan.selectors.body:
            try:
                value = _resolve_pointer(element, plan.selectors.body)
                body = value if isinstance(value, str) else ""
            except Exception:
                body = ""
        items.append(SearchResultItem(title=title, url=normalized, snippet=snippet, body=body))
    return items


class SelectorApplicationError(ValueError):
    pass


def _dedupe(items: list[SearchResultItem]) -> tuple[SearchResultItem, ...]:
    seen: set[str] = set()
    ordered: list[SearchResultItem] = []
    for item in items:
        if item.url in seen:
            continue
        seen.add(item.url)
        ordered.append(item)
    return tuple(ordered)


def execute_search_plan(
    plan: SearchPlan,
    keywords: tuple[str, ...],
    *,
    fetcher: SearchProbeFetcher,
    policy: SearchProbePolicy,
) -> SearchPlanExecutionResult:
    """Execute one SearchPlan against the first keyword using safe transport."""
    if plan.status not in _ALLOWED_STATUSES:
        return SearchPlanExecutionResult(
            plan.plan_id,
            "failed",
            (),
            "",
            FAILURE_PLAN_NOT_EXECUTABLE,
            False,
            "plan_status",
        )
    try:
        validate_search_plan(plan)
    except ProtocolError:
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "plan_validation")
    if not (plan.selectors.result_item and plan.selectors.title and plan.selectors.url):
        return SearchPlanExecutionResult(
            plan.plan_id,
            "failed",
            (),
            "",
            FAILURE_PLAN_NOT_EXECUTABLE,
            False,
            "plan_validation",
        )
    if plan.plan_id != compute_plan_id(plan):
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "plan_validation")
    if plan.pagination.max_pages > 1:
        return SearchPlanExecutionResult(
            plan.plan_id,
            "failed",
            (),
            "",
            FAILURE_PLAN_NOT_EXECUTABLE,
            False,
            "pagination",
        )
    if not keywords:
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_NOT_EXECUTABLE, False, "plan_validation")

    try:
        request = build_search_request(plan, keywords[0], page_index=0)
    except ProtocolError:
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "request")

    try:
        outcome = fetcher.fetch(request, policy=policy)
    except Exception:
        return SearchPlanExecutionResult(
            plan.plan_id,
            "failed",
            (),
            "",
            FAILURE_TRANSPORT,
            False,
            "transport",
        )
    if outcome.rejection is not None or outcome.response is None:
        return SearchPlanExecutionResult(
            plan.plan_id,
            "failed",
            (),
            "",
            FAILURE_TRANSPORT,
            False,
            "transport",
        )

    response = outcome.response
    if plan.response_format == RESPONSE_FORMAT_HTML and not (
        response.content_type.startswith("text/html") or response.content_type == "application/xhtml+xml"
    ):
        return SearchPlanExecutionResult(
            plan.plan_id,
            "failed",
            (),
            response.content_type,
            FAILURE_RESPONSE_REJECTED,
            False,
            "response",
        )
    if plan.response_format == RESPONSE_FORMAT_JSON and not (
        response.content_type == "application/json" or (
            response.content_type.startswith("application/") and response.content_type.endswith("+json")
        )
    ):
        return SearchPlanExecutionResult(
            plan.plan_id,
            "failed",
            (),
            response.content_type,
            FAILURE_RESPONSE_REJECTED,
            False,
            "response",
        )
    try:
        if plan.response_format == RESPONSE_FORMAT_HTML:
            items = _extract_html_items(response, plan)
        else:
            items = _extract_json_items(response, plan)
    except SelectorApplicationError:
        return SearchPlanExecutionResult(
            plan.plan_id,
            "failed",
            (),
            response.content_type,
            FAILURE_SELECTOR_MISMATCH,
            False,
            "parse",
        )

    normalized_items = _dedupe(items)
    if not normalized_items:
        return SearchPlanExecutionResult(
            plan.plan_id,
            "ok",
            (),
            response.content_type,
            FAILURE_NO_RESULTS,
            False,
            "parse",
        )
    return SearchPlanExecutionResult(
        plan.plan_id,
        "ok",
        normalized_items,
        response.content_type,
        None,
        False,
        "parse",
    )