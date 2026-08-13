"""Formal TRS search adapter for form-urlencoded POST and JSON resultDocs."""

from urllib.parse import urlsplit

from crawler.search.execution_models import (
    FAILURE_NO_RESULTS,
    FAILURE_PLAN_INVALID,
    FAILURE_RESPONSE_REJECTED,
    FAILURE_SELECTOR_MISMATCH,
    FAILURE_TRANSPORT,
    SearchPlanExecutionResult,
    SearchResultItem,
)
from crawler.search.request_builder import build_search_request
from crawler.search.search_plan import (
    ADAPTER_TRS,
    KEYWORD_LOCATION_FORM,
    REQUEST_FORMAT_FORM_URLENCODED,
    RESPONSE_FORMAT_JSON,
    SEARCH_STRATEGY_JSON_API,
    ProtocolError,
    SearchPlan,
    validate_search_plan,
)
from crawler.search.trs_response_parser import TRSJSONError, TRSParseError, TRSResultURLError, parse_trs_response
from crawler.site.normalizer import SiteNormalizationError, same_origin
from crawler.site.search_probe import SearchProbeFetcher, SearchProbePolicy


def _content_type_matches(raw: str) -> bool:
    value = raw.split(";", 1)[0].strip().lower()
    return value == "application/json" or (
        value.startswith("application/") and value.endswith("+json")
    )


def _validate_result_url(url: str, plan: SearchPlan) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ValueError("result URL uses an unsafe scheme")
    if parts.username is not None or parts.password is not None:
        raise ValueError("result URL contains userinfo")
    try:
        if not same_origin(url, f"https://{plan.scope.domain}"):
            raise ValueError("result URL is outside the plan domain")
    except SiteNormalizationError as exc:
        raise ValueError("result URL could not be normalized") from exc
    if plan.scope.allowed_path_prefixes:
        if not any(parts.path.startswith(prefix) for prefix in plan.scope.allowed_path_prefixes):
            raise ValueError("result URL is outside allowed path prefixes")


def _dedupe(items: list[SearchResultItem]) -> list[SearchResultItem]:
    seen: set[str] = set()
    out: list[SearchResultItem] = []
    for item in items:
        if item.url in seen:
            continue
        seen.add(item.url)
        out.append(item)
    return out


class TRSSearchAdapter:
    adapter_name = ADAPTER_TRS

    def execute(
        self,
        plan: SearchPlan,
        keywords: tuple[str, ...],
        *,
        fetcher: SearchProbeFetcher,
        policy: SearchProbePolicy,
    ) -> SearchPlanExecutionResult:
        if (
            plan.adapter != ADAPTER_TRS
            or plan.strategy != SEARCH_STRATEGY_JSON_API
            or plan.http_method != "POST"
            or plan.request_format != REQUEST_FORMAT_FORM_URLENCODED
            or plan.response_format != RESPONSE_FORMAT_JSON
            or plan.request_shape.keyword_location != KEYWORD_LOCATION_FORM
            or len(plan.request_shape.keyword_path) != 1
        ):
            return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "trs_adapter")
        pagination = plan.pagination
        if (
            not pagination.enabled
            or pagination.location != KEYWORD_LOCATION_FORM
            or len(pagination.value_path) != 1
            or len(pagination.page_size_path) != 1
            or pagination.page_size is None
            or pagination.page_size < 1
        ):
            return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "trs_adapter")
        if not keywords:
            return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_NOT_EXECUTABLE, False, "trs_adapter")
        try:
            validate_search_plan(plan)
        except ProtocolError:
            return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "trs_adapter")

        keyword = keywords[0]
        accumulated: list[SearchResultItem] = []
        page_size = pagination.page_size or 1
        for page_index in range(pagination.max_pages):
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
                parsed = parse_trs_response(response, keyword)
                for item in parsed.items:
                    _validate_result_url(item.url, plan)
            except (TRSJSONError, TRSResultURLError):
                return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_RESPONSE_REJECTED, False, "json")
            except TRSParseError:
                return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_SELECTOR_MISMATCH, False, "parse")
            except ValueError:
                return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_RESPONSE_REJECTED, False, "result_url")

            if page_index == 0 and parsed.result_doc_count == 0:
                return SearchPlanExecutionResult(plan.plan_id, "ok", (), "application/json", FAILURE_NO_RESULTS, False, "trs_adapter")
            if page_index > 0 and parsed.result_doc_count == 0:
                break
            if parsed.result_doc_count < page_size:
                before = {item.url for item in accumulated}
                for item in parsed.items:
                    if item.url not in before:
                        accumulated.append(item)
                        before.add(item.url)
                break

            before = {item.url for item in accumulated}
            new_items = [item for item in parsed.items if item.url not in before]
            accumulated.extend(new_items)
            if page_index > 0 and not new_items:
                break

        normalized = tuple(_dedupe(accumulated))
        if not normalized:
            return SearchPlanExecutionResult(plan.plan_id, "ok", (), "application/json", FAILURE_NO_RESULTS, False, "trs_adapter")
        return SearchPlanExecutionResult(plan.plan_id, "ok", normalized, "application/json", None, False, "trs_adapter")