"""Execute a validated SearchPlan through the safe probe HTTP foundation."""

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from crawler.search.search_plan import (
    PLAN_STATUS_ACTIVE,
    PLAN_STATUS_READY,
    SEARCH_STRATEGY_HTML_FORM,
    SEARCH_STRATEGY_JSON_API,
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
    SearchProbeRequest,
    SearchProbeResponse,
)

EXECUTION_OK = "ok"
FAILURE_PLAN_INVALID = "plan_invalid"
FAILURE_PLAN_NOT_EXECUTABLE = "plan_not_executable"
FAILURE_TRANSPORT = "transport_failure"
FAILURE_RESPONSE_REJECTED = "response_rejected"
FAILURE_SELECTOR_MISMATCH = "selector_mismatch"
FAILURE_INVALID_RESULT_URL = "invalid_result_url"
FAILURE_NO_RESULTS = "no_results"

_ALLOWED_STATUSES = {PLAN_STATUS_READY, PLAN_STATUS_ACTIVE}


@dataclass(frozen=True)
class SearchResultItem:
    title: str
    url: str
    snippet: str = ""
    body: str = ""

    def __repr__(self) -> str:
        return f"SearchResultItem(url={self.url!r}, title_len={len(self.title)})"


@dataclass(frozen=True)
class SearchPlanExecutionResult:
    plan_id: str
    status: str
    items: tuple[SearchResultItem, ...]
    response_kind: str
    failure_code: str | None = None
    retryable: bool = False

    @property
    def success(self) -> bool:
        return self.status == EXECUTION_OK and self.failure_code is None

    def __repr__(self) -> str:
        return (
            f"SearchPlanExecutionResult(status={self.status!r}, "
            f"items={len(self.items)}, failure={self.failure_code!r})"
        )


def _replace_url_query(endpoint: str, params: dict[str, str]) -> str:
    parts = urlsplit(endpoint)
    query = urlencode(params, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def _replace_placeholders(value: str, keyword: str, page_size: int) -> str:
    return (
        value.replace("{keyword}", keyword)
        .replace("{page}", "1")
        .replace("{page_size}", str(page_size))
    )


def _replace_json_placeholders(value: str, keyword: str, page_size: int) -> str:
    keyword_json = json.dumps(keyword, ensure_ascii=False)[1:-1]
    return (
        value.replace("{keyword}", keyword_json)
        .replace("{page}", "1")
        .replace("{page_size}", str(page_size))
    )


def _build_request(plan: SearchPlan, keyword: str) -> SearchProbeRequest:
    query_params = {
        name: _replace_placeholders(value, keyword, plan.pagination.page_size)
        for name, value in plan.query_params.items()
    }
    if plan.pagination.page_param:
        query_params[plan.pagination.page_param] = "1"
    if plan.pagination.page_size_param:
        query_params[plan.pagination.page_size_param] = str(plan.pagination.page_size)

    body: bytes | None = None
    content_type = "text/html"
    headers = [("User-Agent", "crawler-platform-probe/1.0")]

    if plan.http_method == "GET":
        url = _replace_url_query(plan.endpoint, query_params)
        headers.append(("Accept", "text/html, application/xhtml+xml"))
    else:
        if not plan.request_body_template:
            raise ProtocolError("INVALID_PLAN", "POST plan requires request_body_template")
        url = _replace_url_query(plan.endpoint, query_params)
        if plan.strategy == SEARCH_STRATEGY_HTML_FORM:
            template = _replace_placeholders(plan.request_body_template, quote(keyword, safe=""), plan.pagination.page_size)
            body = template.encode("utf-8")
            content_type = "application/x-www-form-urlencoded"
            headers.append(("Accept", "text/html, application/xhtml+xml"))
        elif plan.strategy == SEARCH_STRATEGY_JSON_API:
            template = _replace_json_placeholders(
                plan.request_body_template,
                keyword,
                plan.pagination.page_size,
            )
            body = template.encode("utf-8")
            content_type = "application/json"
            headers.append(("Accept", "application/json, application/*+json"))
        else:
            raise ProtocolError("INVALID_PLAN", "unsupported plan strategy")
        headers.append(("Content-Type", content_type))

    return SearchProbeRequest(
        method=plan.http_method,
        url=url,
        headers=tuple(headers),
        body=body,
        approved_origins=(plan.endpoint,),
    )


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
        )
    try:
        validate_search_plan(plan)
    except ProtocolError:
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False)
    if not (plan.selectors.result_item and plan.selectors.title and plan.selectors.url):
        return SearchPlanExecutionResult(
            plan.plan_id,
            "failed",
            (),
            "",
            FAILURE_PLAN_NOT_EXECUTABLE,
            False,
        )
    if plan.plan_id != compute_plan_id(plan):
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False)
    if plan.strategy not in (SEARCH_STRATEGY_HTML_FORM, SEARCH_STRATEGY_JSON_API):
        return SearchPlanExecutionResult(
            plan.plan_id,
            "failed",
            (),
            "",
            FAILURE_PLAN_NOT_EXECUTABLE,
            False,
        )
    if not keywords:
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_NOT_EXECUTABLE, False)

    try:
        request = _build_request(plan, keywords[0])
    except ProtocolError:
        return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False)

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
        )
    if outcome.rejection is not None or outcome.response is None:
        return SearchPlanExecutionResult(
            plan.plan_id,
            "failed",
            (),
            "",
            FAILURE_TRANSPORT,
            False,
        )

    response = outcome.response
    if plan.strategy == SEARCH_STRATEGY_HTML_FORM and not (
        response.content_type.startswith("text/html") or response.content_type == "application/xhtml+xml"
    ):
        return SearchPlanExecutionResult(
            plan.plan_id,
            "failed",
            (),
            response.content_type,
            FAILURE_RESPONSE_REJECTED,
            False,
        )
    if plan.strategy == SEARCH_STRATEGY_JSON_API and not (
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
        )
    try:
        if response.content_type.startswith("text/html") or response.content_type == "application/xhtml+xml":
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
        )
    return SearchPlanExecutionResult(
        plan.plan_id,
        "ok",
        normalized_items,
        response.content_type,
        None,
        False,
    )
