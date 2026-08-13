"""Formal HTML search adapter for GET and POST form execution."""

from urllib.parse import urlsplit

from crawler.search.execution_models import (
    FAILURE_NO_RESULTS,
    FAILURE_PLAN_INVALID,
    FAILURE_PLAN_NOT_EXECUTABLE,
    FAILURE_RESPONSE_REJECTED,
    FAILURE_SELECTOR_MISMATCH,
    FAILURE_TRANSPORT,
    SearchPlanExecutionResult,
    SearchResultItem,
)
from crawler.search.html_response_parser import (
    HTMLParseError,
    HTMLResultURLError,
    parse_html_response,
)
from crawler.search.request_builder import build_search_request
from crawler.search.search_plan import (
    ADAPTER_HTML,
    REQUEST_FORMAT_FORM_URLENCODED,
    REQUEST_FORMAT_NONE,
    RESPONSE_FORMAT_HTML,
    SEARCH_STRATEGY_HTML_FORM,
    ProtocolError,
    SearchPlan,
    validate_search_plan,
)
from crawler.site.normalizer import SiteNormalizationError, same_origin
from crawler.site.search_probe import SearchProbeFetcher, SearchProbePolicy

_HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}


def _content_type_matches(raw: str) -> bool:
    return raw.split(";", 1)[0].strip().lower() in _HTML_CONTENT_TYPES


def _validate_result_url(url: str, plan: SearchPlan) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise HTMLResultURLError("result URL uses an unsafe scheme")
    if parts.username is not None or parts.password is not None:
        raise HTMLResultURLError("result URL contains userinfo")
    try:
        if not same_origin(url, f"https://{plan.scope.domain}"):
            raise HTMLResultURLError("result URL is outside the plan domain")
    except SiteNormalizationError as exc:
        raise HTMLResultURLError("result URL could not be normalized") from exc
    if plan.scope.allowed_path_prefixes:
        if not any(parts.path.startswith(prefix) for prefix in plan.scope.allowed_path_prefixes):
            raise HTMLResultURLError("result URL is outside allowed path prefixes")


def _dedupe(items: list[SearchResultItem]) -> list[SearchResultItem]:
    seen: set[str] = set()
    out: list[SearchResultItem] = []
    for item in items:
        if item.url in seen:
            continue
        seen.add(item.url)
        out.append(item)
    return out


class HTMLSearchAdapter:
    adapter_name = ADAPTER_HTML

    def execute(
        self,
        plan: SearchPlan,
        keywords: tuple[str, ...],
        *,
        fetcher: SearchProbeFetcher,
        policy: SearchProbePolicy,
    ) -> SearchPlanExecutionResult:
        if plan.adapter != ADAPTER_HTML or plan.strategy != SEARCH_STRATEGY_HTML_FORM or plan.response_format != RESPONSE_FORMAT_HTML:
            return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "html_adapter")
        if not (
            (plan.http_method == "GET" and plan.request_format == REQUEST_FORMAT_NONE)
            or (plan.http_method == "POST" and plan.request_format == REQUEST_FORMAT_FORM_URLENCODED)
        ):
            return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "html_adapter")
        if not (plan.selectors.result_item and plan.selectors.title and plan.selectors.url):
            return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_NOT_EXECUTABLE, False, "html_adapter")
        if not keywords:
            return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_NOT_EXECUTABLE, False, "html_adapter")
        try:
            validate_search_plan(plan)
        except ProtocolError:
            return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "html_adapter")

        keyword = keywords[0]
        accumulated: list[SearchResultItem] = []
        for page_index in range(plan.pagination.max_pages):
            try:
                request = build_search_request(plan, keyword, page_index=page_index)
            except ProtocolError:
                return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "request")
            try:
                outcome = fetcher.fetch(request, policy=policy)
            except Exception:
                return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_TRANSPORT, False, "transport")
            if outcome.rejection is not None or outcome.response is None:
                return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_TRANSPORT, False, "transport")

            response = outcome.response
            if not _content_type_matches(response.content_type):
                return SearchPlanExecutionResult(plan.plan_id, "failed", (), response.content_type, FAILURE_RESPONSE_REJECTED, False, "response")

            try:
                parsed = parse_html_response(response, plan)
                for item in parsed.items:
                    _validate_result_url(item.url, plan)
            except HTMLResultURLError:
                return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_RESPONSE_REJECTED, False, "result_url")
            except HTMLParseError:
                return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_SELECTOR_MISMATCH, False, "parse")

            if page_index == 0 and parsed.result_item_count == 0:
                return SearchPlanExecutionResult(plan.plan_id, "ok", (), "text/html", FAILURE_NO_RESULTS, False, "html_adapter")
            if page_index > 0 and parsed.result_item_count == 0:
                break

            before = {item.url for item in accumulated}
            new_items = [item for item in parsed.items if item.url not in before]
            accumulated.extend(new_items)
            if page_index > 0 and not new_items:
                break

        normalized = tuple(_dedupe(accumulated))
        if not normalized:
            return SearchPlanExecutionResult(plan.plan_id, "ok", (), "text/html", FAILURE_NO_RESULTS, False, "html_adapter")
        return SearchPlanExecutionResult(plan.plan_id, "ok", normalized, "text/html", None, False, "html_adapter")