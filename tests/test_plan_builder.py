"""Offline tests for the deterministic SearchPlan builder."""

from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest

from crawler.search.plan_builder import (
    ERROR_NO_CANDIDATES,
    ERROR_NO_EXECUTABLE_PLAN,
    ERROR_UNSAFE_TARGET,
    KEYWORD_PLACEHOLDER,
    PlanBuildResult,
    PlanBuilder,
    REJECTION_CROSS_ORIGIN_URL,
    REJECTION_INVALID_URL,
    REJECTION_MISSING_REQUIRED_FIELD,
    REJECTION_PLAN_VALIDATION_FAILED,
    REJECTION_UNSAFE_URL,
    REJECTION_UNSUPPORTED_CANDIDATE,
    REJECTION_UNSUPPORTED_METHOD,
)
from crawler.search.search_plan import (
    PLAN_STATUS_DRAFT,
    PROTOCOL_VERSION_V2,
    SEARCH_STRATEGY_HTML_FORM,
    SEARCH_STRATEGY_JSON_API,
    SEARCH_STRATEGY_UNKNOWN,
    ProtocolError,
    SearchPlan,
    SearchScope,
    compute_plan_id,
    validate_search_plan,
)
from crawler.site.models import SearchCandidate

TARGET = "https://example.gov.cn/"


def _candidate(**overrides):
    data = {
        "method": "GET",
        "endpoint": "https://example.gov.cn/search",
        "keyword_param": "q",
        "fixed_params": (),
        "request_encoding": "",
        "source": "form",
        "priority": 3,
        "scope": "same_origin",
        "evidence": ("form method=get action=/search",),
        "status": "unverified",
    }
    data.update(overrides)
    return SearchCandidate(**data)


def test_empty_candidates_return_no_candidates():
    result = PlanBuilder().build(target_url=TARGET, candidates=())
    assert result.plan is None
    assert result.rejections == ()
    assert result.error_code == ERROR_NO_CANDIDATES
    assert not result.success


def test_single_valid_candidate_creates_valid_plan():
    result = PlanBuilder().build(target_url=TARGET, candidates=(_candidate(),))
    assert result.success
    assert result.error_code is None
    assert result.plan is not None
    validate_search_plan(result.plan)
    assert result.plan.protocol_version == PROTOCOL_VERSION_V2
    assert result.plan.status == PLAN_STATUS_DRAFT
    assert result.plan.strategy == SEARCH_STRATEGY_HTML_FORM
    assert result.plan.http_method == "GET"
    assert result.plan.endpoint == "https://example.gov.cn/search"
    assert result.plan.scope.domain == "example.gov.cn"
    assert result.plan.query_params == {"q": KEYWORD_PLACEHOLDER}


def test_repeated_build_is_deterministic():
    builder = PlanBuilder()
    first = builder.build(target_url=TARGET, candidates=(_candidate(),))
    second = builder.build(target_url=TARGET, candidates=(_candidate(),))
    assert first.plan == second.plan
    assert first.plan is not None and second.plan is not None
    assert first.plan.plan_id == second.plan.plan_id
    assert first.plan.plan_id == compute_plan_id(first.plan)


def test_first_valid_candidate_wins():
    first = _candidate(endpoint="https://example.gov.cn/search")
    second = _candidate(endpoint="https://example.gov.cn/s")
    result = PlanBuilder().build(target_url=TARGET, candidates=(first, second))
    assert result.success
    assert result.rejections == ()
    assert result.plan is not None
    assert result.plan.endpoint == first.endpoint


def test_invalid_first_then_valid_second():
    invalid = _candidate(method="PATCH")
    valid = _candidate(endpoint="https://example.gov.cn/s")
    result = PlanBuilder().build(target_url=TARGET, candidates=(invalid, valid))
    assert result.success
    assert result.plan is not None
    assert result.plan.endpoint == valid.endpoint
    assert len(result.rejections) == 1
    assert result.rejections[0].candidate_index == 0
    assert result.rejections[0].code == REJECTION_UNSUPPORTED_METHOD


def test_all_invalid_returns_one_rejection_per_candidate():
    first = _candidate(method="PATCH")
    second = _candidate(keyword_param="")
    result = PlanBuilder().build(target_url=TARGET, candidates=(first, second))
    assert result.plan is None
    assert result.error_code == ERROR_NO_EXECUTABLE_PLAN
    assert [r.candidate_index for r in result.rejections] == [0, 1]
    assert len(result.rejections) == 2


def test_missing_keyword_param_is_rejected():
    result = PlanBuilder().build(target_url=TARGET, candidates=(_candidate(keyword_param=""),))
    assert result.plan is None
    assert result.error_code == ERROR_NO_EXECUTABLE_PLAN
    assert result.rejections[0].code == REJECTION_MISSING_REQUIRED_FIELD


def test_unsupported_method_is_rejected():
    result = PlanBuilder().build(target_url=TARGET, candidates=(_candidate(method="PATCH"),))
    assert result.rejections[0].code == REJECTION_UNSUPPORTED_METHOD


def test_invalid_url_is_rejected():
    result = PlanBuilder().build(target_url=TARGET, candidates=(_candidate(endpoint="not-a-url"),))
    assert result.rejections[0].code == REJECTION_INVALID_URL


def test_cross_origin_url_is_rejected():
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(endpoint="https://other.example/search"),),
    )
    assert result.rejections[0].code == REJECTION_CROSS_ORIGIN_URL


def test_dangerous_scheme_is_rejected():
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(endpoint="ftp://example.gov.cn/search"),),
    )
    assert result.rejections[0].code == REJECTION_UNSAFE_URL


def test_local_ip_endpoint_is_rejected():
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(endpoint="http://127.0.0.1/search"),),
    )
    assert result.rejections[0].code == REJECTION_UNSAFE_URL


def test_unsupported_candidate_type_is_rejected():
    result = PlanBuilder().build(target_url=TARGET, candidates=("not-a-candidate",))
    assert result.rejections[0].code == REJECTION_UNSUPPORTED_CANDIDATE


def test_scope_requiring_validation_is_rejected():
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(scope="requires_scope_validation"),),
    )
    assert result.rejections[0].code == REJECTION_UNSUPPORTED_CANDIDATE


def test_status_not_unverified_is_rejected():
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(status="ready"),),
    )
    assert result.rejections[0].code == REJECTION_UNSUPPORTED_CANDIDATE


def test_keyword_param_conflicting_with_fixed_param_is_rejected():
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(fixed_params=(("q", "fixed"),)),),
    )
    assert result.rejections[0].code == REJECTION_UNSUPPORTED_CANDIDATE


def test_fixed_params_are_mapped_without_invention():
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(fixed_params=(("siteCode", "abc"),)),),
    )
    assert result.plan is not None
    assert result.plan.query_params == {"q": KEYWORD_PLACEHOLDER, "siteCode": "abc"}


def test_unknown_source_uses_unknown_strategy():
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(source="common_path"),),
    )
    assert result.plan is not None
    assert result.plan.strategy == SEARCH_STRATEGY_UNKNOWN


def test_trs_signature_maps_to_json_api_strategy():
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(
            _candidate(
                source="trs_signature",
                endpoint="https://example.gov.cn/so/ss/query/s",
            ),
        ),
    )
    assert result.plan is not None
    assert result.plan.strategy == SEARCH_STRATEGY_JSON_API


def test_plan_validation_failure_is_controlled():
    def fail(_plan):
        raise ProtocolError("INVALID_PLAN_STRATEGY", "search_plan strategy is not allowed")

    with patch("crawler.search.plan_builder.validate_search_plan", side_effect=fail):
        result = PlanBuilder().build(target_url=TARGET, candidates=(_candidate(),))
    assert result.plan is None
    assert result.error_code == ERROR_NO_EXECUTABLE_PLAN
    assert result.rejections[0].code == REJECTION_PLAN_VALIDATION_FAILED
    assert "traceback" not in result.rejections[0].message.lower()


def test_invalid_target_returns_unsafe_target():
    result = PlanBuilder().build(target_url="not-a-url", candidates=(_candidate(),))
    assert result.plan is None
    assert result.rejections == ()
    assert result.error_code == ERROR_UNSAFE_TARGET


def test_localhost_target_returns_unsafe_target():
    result = PlanBuilder().build(target_url="http://localhost/", candidates=(_candidate(),))
    assert result.error_code == ERROR_UNSAFE_TARGET


def test_rejection_and_result_are_immutable():
    rejection = __import__("crawler.search.plan_builder", fromlist=["CandidateRejection"]).CandidateRejection(0, "code", "message")
    with pytest.raises(FrozenInstanceError):
        rejection.code = "changed"
    result = PlanBuildResult(None, (), None)
    with pytest.raises(FrozenInstanceError):
        result.error_code = ERROR_NO_CANDIDATES


def test_success_property_contract():
    failed = PlanBuildResult(None, (), ERROR_NO_EXECUTABLE_PLAN)
    assert not failed.success
    assert PlanBuildResult(None, (), None).success is False


def test_input_sequence_is_not_modified():
    candidates = [_candidate(), _candidate(method="PATCH")]
    before = tuple(candidates)
    PlanBuilder().build(target_url=TARGET, candidates=candidates)
    assert tuple(candidates) == before


def test_success_stops_before_later_candidate():
    valid = _candidate()
    invalid = _candidate(keyword_param="")
    result = PlanBuilder().build(target_url=TARGET, candidates=(valid, invalid))
    assert result.success
    assert result.rejections == ()
    assert result.plan is not None
    assert result.plan.endpoint == valid.endpoint


def test_failure_never_contains_half_plan():
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(method="PATCH"), _candidate(keyword_param="")),
    )
    assert result.plan is None


def test_rejection_message_does_not_contain_sensitive_values():
    secret = "SECRET-TOKEN-VALUE"
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(endpoint=f"https://other.example/search?token={secret}"),),
    )
    assert result.rejections[0].code == REJECTION_CROSS_ORIGIN_URL
    combined = " ".join((result.rejections[0].code, result.rejections[0].message))
    assert secret not in combined
    assert "other.example" not in result.rejections[0].message


def test_build_does_not_call_network_or_dns():
    def fail(*_args, **_kwargs):
        raise AssertionError("external lookup attempted")

    with patch("socket.getaddrinfo", side_effect=fail), patch("urllib.request.urlopen", side_effect=fail):
        result = PlanBuilder().build(target_url=TARGET, candidates=(_candidate(),))
    assert result.success


def test_default_pagination_and_selectors_are_not_invented():
    result = PlanBuilder().build(target_url=TARGET, candidates=(_candidate(),))
    default_plan = SearchPlan(
        plan_id="",
        endpoint=TARGET,
        scope=SearchScope(domain="example.gov.cn"),
    )
    assert result.plan is not None
    assert result.plan.pagination == default_plan.pagination
    assert result.plan.selectors == default_plan.selectors
