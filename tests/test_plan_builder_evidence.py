"""Offline tests for PlanBuilder selector evidence handoff."""

import pytest

from crawler.search.plan_builder import PlanBuilder
from crawler.site.models import CandidateRequestShape, SearchCandidate
from crawler.site.selector_evidence import SelectorEvidence

TARGET = "https://example.gov.cn/"


def _html_evidence():
    return SelectorEvidence(
        candidate_key=("GET", "https://example.gov.cn/search", "q", ()),
        candidate_kind="html_form",
        response_kind="html",
        result_item="div.result-item",
        title="a",
        url="a",
        final_origin=TARGET,
        match_count=2,
        validated=True,
        evidence_source="probe",
    )


def _json_evidence():
    return SelectorEvidence(
        candidate_key=("POST", "https://example.gov.cn/so/ss/query/s", "q", ()),
        candidate_kind="json_api",
        response_kind="json",
        result_item="/data/items",
        title="/title",
        url="/url",
        final_origin=TARGET,
        match_count=2,
        validated=True,
        evidence_source="probe",
    )


def _candidate(source="form", endpoint="https://example.gov.cn/search", method="GET", request_shape=None):
    return SearchCandidate(
        method=method,
        endpoint=endpoint,
        keyword_param="q",
        source=source,
        status="unverified",
        request_shape=request_shape,
    )


def test_html_evidence_builds_ready_plan_with_selectors():
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(),),
        selector_evidence=_html_evidence(),
    )
    assert result.success
    assert result.plan is not None
    assert result.plan.status == "ready"
    assert result.plan.selectors.result_item == "div.result-item"
    assert result.plan.selectors.title == "a"
    assert result.plan.selectors.url == "a"


def test_json_evidence_builds_ready_plan_with_pointers():
    shape = CandidateRequestShape(
        method="POST",
        endpoint="https://example.gov.cn/so/ss/query/s",
        keyword_location="form",
        keyword_param="q",
        form_fields=(("pageSize", "20"),),
        content_type="application/x-www-form-urlencoded",
        approved_origins=(TARGET, "https://example.gov.cn"),
    )
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(
            source="trs_signature",
            endpoint="https://example.gov.cn/so/ss/query/s",
            method="POST",
            request_shape=shape,
        ),),
        selector_evidence=_json_evidence(),
    )
    assert result.success
    assert result.plan is not None
    assert result.plan.status == "ready"
    assert result.plan.selectors.result_item == "/data/items"
    assert result.plan.selectors.title == "/title"
    assert result.plan.selectors.url == "/url"


def test_unvalidated_evidence_rejected():
    evidence = SelectorEvidence(
        candidate_key=("GET", "https://example.gov.cn/search", "q", ()),
        candidate_kind="html_form",
        response_kind="html",
        result_item="div.result-item",
        title="a",
        url="a",
        final_origin=TARGET,
        match_count=2,
        validated=False,
        evidence_source="probe",
    )
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(),),
        selector_evidence=evidence,
    )
    assert result.plan is None
    assert result.error_code == "no_executable_plan"
    assert result.rejections[0].code == "unsupported_candidate"


def test_evidence_kind_mismatch_rejected():
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(),),
        selector_evidence=_json_evidence(),
    )
    assert result.plan is None
    assert result.rejections[0].code == "unsupported_candidate"


def test_evidence_identity_mismatch_rejected():
    evidence = SelectorEvidence(
        candidate_key=("GET", "https://other.example/search", "q", ()),
        candidate_kind="html_form",
        response_kind="html",
        result_item="div.result-item",
        title="a",
        url="a",
        final_origin=TARGET,
        match_count=2,
        validated=True,
        evidence_source="probe",
    )
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(),),
        selector_evidence=evidence,
    )
    assert result.plan is None
    assert result.rejections[0].code == "unsupported_candidate"


def test_no_evidence_keeps_existing_draft_behavior():
    result = PlanBuilder().build(target_url=TARGET, candidates=(_candidate(),))
    assert result.success
    assert result.plan is not None
    assert result.plan.status == "draft"
    assert result.plan.selectors.result_item == ""


def test_raw_body_string_cannot_be_passed_as_evidence():
    result = PlanBuilder().build(
        target_url=TARGET,
        candidates=(_candidate(),),
        selector_evidence="<html>raw body</html>",  # type: ignore[arg-type]
    )
    assert result.plan is None
    assert result.rejections[0].code == "unsupported_candidate"
