"""Deterministic, network-free conversion of SearchCandidate to SearchPlan v2."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from crawler.site.models import SearchCandidate
from crawler.site.normalizer import (
    SiteNormalizationError,
    normalize_target_url,
    normalized_origin,
    same_origin,
)
from crawler.site.selector_evidence import SelectorEvidence
from crawler.site.security import classify_ip, is_ip_literal
from crawler.search.search_plan import (
    ADAPTER_GENERIC_JSON,
    ADAPTER_HTML,
    ADAPTER_JPAAS,
    ADAPTER_TRS,
    KEYWORD_LOCATION_FORM,
    KEYWORD_LOCATION_JSON,
    KEYWORD_LOCATION_QUERY,
    PLAN_STATUS_DRAFT,
    PLAN_STATUS_READY,
    PROTOCOL_VERSION_V2,
    REQUEST_FORMAT_FORM_URLENCODED,
    REQUEST_FORMAT_JSON,
    REQUEST_FORMAT_NONE,
    RESPONSE_FORMAT_HTML,
    RESPONSE_FORMAT_JSON,
    SEARCH_STRATEGY_HTML_FORM,
    SEARCH_STRATEGY_JSON_API,
    ProtocolError,
    SearchDiscovery,
    SearchPagination,
    SearchPlan,
    SearchRequestShape,
    SearchScope,
    SearchSelectors,
    compute_plan_id,
    validate_search_plan,
)

ERROR_NO_CANDIDATES = "no_candidates"
ERROR_NO_EXECUTABLE_PLAN = "no_executable_plan"
ERROR_UNSAFE_TARGET = "unsafe_target"

REJECTION_UNSUPPORTED_CANDIDATE = "unsupported_candidate"
REJECTION_MISSING_REQUIRED_FIELD = "missing_required_field"
REJECTION_UNSUPPORTED_METHOD = "unsupported_method"
REJECTION_INVALID_URL = "invalid_url"
REJECTION_CROSS_ORIGIN_URL = "cross_origin_url"
REJECTION_UNSAFE_URL = "unsafe_url"
REJECTION_PLAN_VALIDATION_FAILED = "plan_validation_failed"

_ALLOWED_METHODS = {"GET", "POST"}
_SOURCE_ADAPTER = {
    "form": ADAPTER_HTML,
    "trs_signature": ADAPTER_TRS,
    "jpaas_signature": ADAPTER_JPAAS,
    "generic_json": ADAPTER_GENERIC_JSON,
}
_SOURCE_STRATEGY = {
    "form": SEARCH_STRATEGY_HTML_FORM,
    "trs_signature": SEARCH_STRATEGY_JSON_API,
    "jpaas_signature": SEARCH_STRATEGY_JSON_API,
    "generic_json": SEARCH_STRATEGY_JSON_API,
}
_PERCENT_RE = re.compile(r"[0-9A-Fa-f]{2}")


def _valid_percent_encoding(value: str) -> bool:
    rest = value
    while "%" in rest:
        index = rest.index("%")
        if index + 2 >= len(rest) or not _PERCENT_RE.fullmatch(rest[index + 1 : index + 3]):
            return False
        rest = rest[index + 3 :]
    return True


def _split_endpoint_query(raw: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    parts = urlsplit(raw)
    if parts.fragment:
        raise ProtocolError("INVALID_PLAN_ENDPOINT", "endpoint must not contain a fragment")
    query = parse_qsl(parts.query, keep_blank_values=True)
    names = [name for name, _ in query]
    if len(names) != len(set(names)):
        raise ProtocolError("INVALID_PLAN_ENDPOINT", "endpoint query contains duplicate parameter names")
    for name, value in query:
        if not _valid_percent_encoding(name) or not _valid_percent_encoding(value):
            raise ProtocolError("INVALID_PLAN_ENDPOINT", "endpoint query contains invalid percent encoding")
    clean = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return clean, tuple(query)


def _merge_pairs(first: tuple[tuple[str, str], ...], second: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for pair in (*first, *second):
        name, value = pair
        if name in seen:
            raise ProtocolError("INVALID_REQUEST_SHAPE", "fixed query parameter name is duplicated")
        seen.add(name)
        out.append((name, value))
    return tuple(out)


@dataclass(frozen=True)
class CandidateRejection:
    """Structured reason why one candidate cannot become a SearchPlan."""

    candidate_index: int
    code: str
    message: str


@dataclass(frozen=True)
class PlanBuildResult:
    """Result of building at most one SearchPlan from a candidate sequence."""

    plan: SearchPlan | None
    rejections: tuple[CandidateRejection, ...]
    error_code: str | None

    @property
    def success(self) -> bool:
        return self.plan is not None and self.error_code is None


def _url_issue(raw: str) -> str:
    if not isinstance(raw, str):
        return REJECTION_INVALID_URL
    try:
        scheme = urlsplit(raw).scheme.lower()
    except ValueError:
        return REJECTION_INVALID_URL
    if scheme and scheme not in ("http", "https"):
        return REJECTION_UNSAFE_URL
    return REJECTION_INVALID_URL


def _unsafe_host(host: str) -> bool:
    if is_ip_literal(host):
        safe, _ = classify_ip(host)
        return not safe
    return host == "localhost" or host.endswith(".localhost")


def _target_error(raw: str) -> str | None:
    if not isinstance(raw, str):
        return ERROR_UNSAFE_TARGET
    try:
        normalized = normalize_target_url(raw)
        host = normalized_origin(normalized)[1]
    except SiteNormalizationError:
        return ERROR_UNSAFE_TARGET
    if _unsafe_host(host):
        return ERROR_UNSAFE_TARGET
    return None


def _derive_html_shape(candidate: SearchCandidate) -> SearchRequestShape:
    method = candidate.method.strip().upper()
    keyword_path = (candidate.keyword_param.strip(),)
    if method == "POST":
        return SearchRequestShape(
            keyword_location=KEYWORD_LOCATION_FORM,
            keyword_path=keyword_path,
            form_fields=tuple(candidate.fixed_params),
        )
    return SearchRequestShape(
        keyword_location=KEYWORD_LOCATION_QUERY,
        keyword_path=keyword_path,
        fixed_query_params=tuple(candidate.fixed_params),
    )


class PlanBuilder:
    """Convert Analyzer candidates into the first valid SearchPlan v2."""

    def build(
        self,
        *,
        target_url: str,
        candidates: Sequence[SearchCandidate],
        selector_evidence: SelectorEvidence | None = None,
    ) -> PlanBuildResult:
        target_error = _target_error(target_url)
        if target_error is not None:
            return PlanBuildResult(None, (), target_error)

        normalized_target = normalize_target_url(target_url)
        target_domain = normalized_origin(normalized_target)[1]
        rejections: list[CandidateRejection] = []

        for index, candidate in enumerate(candidates):
            rejection = self._reject_candidate(
                index,
                candidate,
                normalized_target,
            )
            if rejection is not None:
                rejections.append(rejection)
                continue

            evidence_error = self._evidence_rejection(candidate, selector_evidence)
            if evidence_error is not None:
                rejections.append(
                    CandidateRejection(
                        index,
                        REJECTION_UNSUPPORTED_CANDIDATE,
                        evidence_error,
                    )
                )
                continue

            try:
                plan = self._build_plan(candidate, target_domain, selector_evidence)
                validate_search_plan(plan)
            except ProtocolError:
                rejections.append(
                    CandidateRejection(
                        index,
                        REJECTION_PLAN_VALIDATION_FAILED,
                        "candidate did not produce a valid SearchPlan",
                    )
                )
                continue

            return PlanBuildResult(plan, tuple(rejections), None)

        if not candidates:
            return PlanBuildResult(None, (), ERROR_NO_CANDIDATES)
        return PlanBuildResult(None, tuple(rejections), ERROR_NO_EXECUTABLE_PLAN)

    def _reject_candidate(
        self,
        index: int,
        candidate: SearchCandidate,
        normalized_target: str,
    ) -> CandidateRejection | None:
        if not isinstance(candidate, SearchCandidate):
            return CandidateRejection(
                candidate_index=index,
                code=REJECTION_UNSUPPORTED_CANDIDATE,
                message="candidate is not a SearchCandidate",
            )

        if not isinstance(candidate.method, str) or candidate.method.strip().upper() not in _ALLOWED_METHODS:
            return CandidateRejection(
                candidate_index=index,
                code=REJECTION_UNSUPPORTED_METHOD,
                message="candidate HTTP method must be GET or POST",
            )

        if not isinstance(candidate.endpoint, str):
            return CandidateRejection(
                candidate_index=index,
                code=REJECTION_INVALID_URL,
                message="candidate endpoint is required",
            )
        try:
            normalized_endpoint = normalize_target_url(candidate.endpoint)
        except SiteNormalizationError:
            code = _url_issue(candidate.endpoint)
            return CandidateRejection(
                candidate_index=index,
                code=code,
                message=(
                    "candidate endpoint is not a safe http(s) URL"
                    if code == REJECTION_UNSAFE_URL
                    else "candidate endpoint is not a valid URL"
                ),
            )

        if _unsafe_host(normalized_origin(normalized_endpoint)[1]):
            return CandidateRejection(
                candidate_index=index,
                code=REJECTION_UNSAFE_URL,
                message="candidate endpoint targets a blocked local or reserved address",
            )

        try:
            same_origin_ok = same_origin(normalized_target, normalized_endpoint)
        except SiteNormalizationError:
            same_origin_ok = False
        if not same_origin_ok:
            return CandidateRejection(
                candidate_index=index,
                code=REJECTION_CROSS_ORIGIN_URL,
                message="candidate endpoint is not on the target origin",
            )

        if not isinstance(candidate.keyword_param, str) or not candidate.keyword_param.strip():
            return CandidateRejection(
                candidate_index=index,
                code=REJECTION_MISSING_REQUIRED_FIELD,
                message="candidate keyword_param is required",
            )

        if candidate.scope != "same_origin":
            return CandidateRejection(
                candidate_index=index,
                code=REJECTION_UNSUPPORTED_CANDIDATE,
                message="candidate scope requires validation",
            )

        if candidate.status != "unverified":
            return CandidateRejection(
                candidate_index=index,
                code=REJECTION_UNSUPPORTED_CANDIDATE,
                message="candidate status is not unverified",
            )

        if not isinstance(candidate.fixed_params, (tuple, list)):
            return CandidateRejection(
                candidate_index=index,
                code=REJECTION_UNSUPPORTED_CANDIDATE,
                message="candidate fixed_params must be a sequence",
            )

        params: dict[str, str] = {}
        for pair in candidate.fixed_params:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                return CandidateRejection(
                    candidate_index=index,
                    code=REJECTION_UNSUPPORTED_CANDIDATE,
                    message="candidate fixed_params contain a malformed pair",
                )
            name, value = pair
            if (
                not isinstance(name, str)
                or not name.strip()
                or not isinstance(value, str)
                or name.strip() in params
            ):
                return CandidateRejection(
                    candidate_index=index,
                    code=REJECTION_UNSUPPORTED_CANDIDATE,
                    message="candidate fixed_params contain a duplicate or invalid name",
                )
            params[name.strip()] = value

        keyword_param = candidate.keyword_param.strip()
        if keyword_param in params:
            return CandidateRejection(
                candidate_index=index,
                code=REJECTION_UNSUPPORTED_CANDIDATE,
                message="candidate keyword_param conflicts with fixed_params",
            )

        if not isinstance(candidate.evidence, (tuple, list)):
            return CandidateRejection(
                candidate_index=index,
                code=REJECTION_UNSUPPORTED_CANDIDATE,
                message="candidate evidence must be a sequence",
            )

        source = candidate.source if isinstance(candidate.source, str) else ""
        if source not in _SOURCE_ADAPTER:
            return CandidateRejection(
                candidate_index=index,
                code=REJECTION_UNSUPPORTED_CANDIDATE,
                message="candidate source has no formal adapter",
            )
        if source in ("trs_signature", "jpaas_signature", "generic_json") and candidate.request_shape is None:
            return CandidateRejection(
                candidate_index=index,
                code=REJECTION_UNSUPPORTED_CANDIDATE,
                message="TRS/JPAAS candidate requires a request shape",
            )
        return None

    @staticmethod
    def _candidate_key(candidate: SearchCandidate) -> tuple[str, ...]:
        return (
            candidate.method,
            normalize_target_url(candidate.endpoint),
            candidate.keyword_param,
            tuple(sorted(candidate.fixed_params)),
        )

    def _evidence_rejection(
        self,
        candidate: SearchCandidate,
        evidence: SelectorEvidence | None,
    ) -> str | None:
        if evidence is None:
            return None
        if not isinstance(evidence, SelectorEvidence):
            return "selector evidence must be a SelectorEvidence object"
        if not evidence.validated:
            return "selector evidence is not validated"
        expected_kind = _SOURCE_STRATEGY.get(
            candidate.source if isinstance(candidate.source, str) else "",
            SEARCH_STRATEGY_JSON_API,
        )
        if evidence.candidate_kind != expected_kind:
            return "selector evidence kind does not match candidate strategy"
        if evidence.candidate_key != self._candidate_key(candidate):
            return "selector evidence does not match candidate identity"
        if not (evidence.result_item and evidence.title and evidence.url):
            return "selector evidence is incomplete"
        return None

    def _build_plan(
        self,
        candidate: SearchCandidate,
        target_domain: str,
        selector_evidence: SelectorEvidence | None = None,
    ) -> SearchPlan:
        method = candidate.method.strip().upper()
        source = candidate.source if isinstance(candidate.source, str) else ""
        adapter = _SOURCE_ADAPTER[source]
        strategy = _SOURCE_STRATEGY[source]

        clean_endpoint, endpoint_query = _split_endpoint_query(candidate.endpoint)
        clean_endpoint = normalize_target_url(clean_endpoint)

        if candidate.request_shape is not None:
            request_shape_data = candidate.request_shape
            fixed_query = request_shape_data.fixed_query_params
            form_fields = request_shape_data.form_fields
            json_template = request_shape_data.json_object_template
            keyword_location = request_shape_data.keyword_location
            keyword_path = (
                (candidate.keyword_param.strip(),)
                if keyword_location in (KEYWORD_LOCATION_QUERY, KEYWORD_LOCATION_FORM)
                else tuple(request_shape_data.keyword_path or ())
            )
        else:
            derived = _derive_html_shape(candidate)
            fixed_query = derived.fixed_query_params
            form_fields = derived.form_fields
            json_template = ()
            keyword_location = derived.keyword_location
            keyword_path = derived.keyword_path

        merged_query = _merge_pairs(endpoint_query, fixed_query)
        request_shape = SearchRequestShape(
            keyword_location=keyword_location,
            keyword_path=keyword_path,
            fixed_query_params=merged_query,
            form_fields=form_fields,
            json_object_template=json_template,
        )

        if adapter == ADAPTER_HTML:
            request_format = REQUEST_FORMAT_NONE if method == "GET" else REQUEST_FORMAT_FORM_URLENCODED
            response_format = RESPONSE_FORMAT_HTML
        elif adapter == ADAPTER_TRS:
            if method != "POST":
                raise ProtocolError("INVALID_PLAN", "TRS adapter requires POST")
            request_format = REQUEST_FORMAT_FORM_URLENCODED
            response_format = RESPONSE_FORMAT_JSON
        elif adapter == ADAPTER_JPAAS:
            if method != "GET":
                raise ProtocolError("INVALID_PLAN", "JPAAS adapter requires GET")
            request_format = REQUEST_FORMAT_NONE
            response_format = RESPONSE_FORMAT_JSON
        elif adapter == ADAPTER_GENERIC_JSON:
            if method == "GET":
                request_format = REQUEST_FORMAT_NONE
                response_format = RESPONSE_FORMAT_JSON
            elif method == "POST":
                request_format = REQUEST_FORMAT_JSON
                response_format = RESPONSE_FORMAT_JSON
            else:
                raise ProtocolError("INVALID_PLAN", "Generic JSON adapter requires GET or POST")
        else:
            raise ProtocolError("INVALID_PLAN", "adapter is not supported by PlanBuilder yet")

        evidence = [str(item) for item in candidate.evidence]
        selectors = (
            SearchSelectors(
                result_item=selector_evidence.result_item,
                title=selector_evidence.title,
                url=selector_evidence.url,
                snippet=selector_evidence.snippet,
                body=selector_evidence.body,
            )
            if selector_evidence is not None
            else SearchSelectors("", "", "", "", "")
        )
        status = PLAN_STATUS_READY if selector_evidence is not None else PLAN_STATUS_DRAFT
        base_plan = SearchPlan(
            plan_id="",
            endpoint=clean_endpoint,
            protocol_version=PROTOCOL_VERSION_V2,
            status=status,
            strategy=strategy,
            adapter=adapter,
            http_method=method,
            request_format=request_format,
            response_format=response_format,
            request_shape=request_shape,
            pagination=SearchPagination(),
            selectors=selectors,
            scope=SearchScope(domain=target_domain),
            discovery=SearchDiscovery(
                evidence=evidence,
                confidence=0,
                source=source,
            ),
            created_from="",
        )
        return SearchPlan(
            plan_id=compute_plan_id(base_plan),
            endpoint=base_plan.endpoint,
            plan_schema_version=base_plan.plan_schema_version,
            protocol_version=base_plan.protocol_version,
            status=base_plan.status,
            strategy=base_plan.strategy,
            adapter=base_plan.adapter,
            http_method=base_plan.http_method,
            request_format=base_plan.request_format,
            response_format=base_plan.response_format,
            request_shape=base_plan.request_shape,
            pagination=base_plan.pagination,
            selectors=base_plan.selectors,
            scope=base_plan.scope,
            discovery=base_plan.discovery,
            created_from=base_plan.created_from,
        )