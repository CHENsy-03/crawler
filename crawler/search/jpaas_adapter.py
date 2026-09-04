"""Formal JPAAS search adapter for GET and JSON response execution."""

from urllib.parse import urlsplit

from crawler.search.adapter import path_allowed
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
from crawler.search.jpaas_parser import (
    JPAASParseError,
    JPAASResponseError,
    JPAASResultURLError,
    parse_jpaas_response,
)
from crawler.search.request_builder import build_search_request
from crawler.search.search_plan import (
    ADAPTER_JPAAS,
    KEYWORD_LOCATION_QUERY,
    REQUEST_FORMAT_NONE,
    RESPONSE_FORMAT_JSON,
    SEARCH_STRATEGY_JSON_API,
    ProtocolError,
    SearchPlan,
    validate_search_plan,
)
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
    if not path_allowed(parts.path, plan.scope.allowed_path_prefixes):
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


class JPAASSearchAdapter:
    adapter_name = ADAPTER_JPAAS

    def execute(
        self,
        plan: SearchPlan,
        query_term: str,
        *,
        fetcher: SearchProbeFetcher,
        policy: SearchProbePolicy,
    ) -> SearchPlanExecutionResult:
        if (
            plan.adapter != ADAPTER_JPAAS
            or plan.strategy != SEARCH_STRATEGY_JSON_API
            or plan.http_method != "GET"
            or plan.request_format != REQUEST_FORMAT_NONE
            or plan.response_format != RESPONSE_FORMAT_JSON
            or plan.request_shape.keyword_location != KEYWORD_LOCATION_QUERY
            or len(plan.request_shape.keyword_path) != 1
        ):
            return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "jpaas_adapter")
        pagination = plan.pagination
        if (
            not pagination.enabled
            or pagination.location != KEYWORD_LOCATION_QUERY
            or len(pagination.value_path) != 1
            or len(pagination.page_size_path) != 1
            or pagination.page_size is None
            or pagination.page_size < 1
        ):
            return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "jpaas_adapter")
        if not isinstance(query_term, str) or not query_term:
            return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_NOT_EXECUTABLE, False, "jpaas_adapter")
        try:
            validate_search_plan(plan)
        except ProtocolError:
            return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_PLAN_INVALID, False, "jpaas_adapter")

        keyword = query_term
        accumulated: list[SearchResultItem] = []
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
                parsed = parse_jpaas_response(response, keyword)
                for item in parsed.items:
                    _validate_result_url(item.url, plan)
            except (JPAASResponseError, JPAASResultURLError):
                return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_RESPONSE_REJECTED, False, "json")
            except JPAASParseError:
                return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_SELECTOR_MISMATCH, False, "parse")
            except ValueError:
                return SearchPlanExecutionResult(plan.plan_id, "failed", (), "", FAILURE_RESPONSE_REJECTED, False, "result_url")

            if page_index == 0 and parsed.result_container_count == 0:
                return SearchPlanExecutionResult(plan.plan_id, "ok", (), "application/json", FAILURE_NO_RESULTS, False, "jpaas_adapter")
            if page_index > 0 and parsed.result_container_count == 0:
                break

            before = {item.url for item in accumulated}
            new_items = [item for item in parsed.items if item.url not in before]
            accumulated.extend(new_items)
            if page_index > 0 and not new_items:
                break

        normalized = tuple(_dedupe(accumulated))
        if not normalized:
            return SearchPlanExecutionResult(plan.plan_id, "ok", (), "application/json", FAILURE_NO_RESULTS, False, "jpaas_adapter")
        return SearchPlanExecutionResult(plan.plan_id, "ok", normalized, "application/json", None, False, "jpaas_adapter")
