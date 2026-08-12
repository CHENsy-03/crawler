"""Offline test for JSON selector evidence through the formal probe entry."""

from crawler.site.models import CandidateRequestShape, SearchCandidate
from crawler.site.search_probe import (
    ProbeOutcome,
    SearchProbePolicy,
    SearchProbeResponse,
    probe_search_candidate,
)

POLICY = SearchProbePolicy()
JSON_BODY = (
    b'{"data":{"items":['
    b'{"title":"A","url":"https://api.example.gov.cn/a"},'
    b'{"title":"B","url":"https://api.example.gov.cn/b"}'
    b']}}'
)


class FakeFetcher:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def fetch(self, request, *, policy):
        self.calls.append(request)
        return self.outcome


def test_json_success_returns_evidence():
    shape = CandidateRequestShape(
        method="POST",
        endpoint="https://api.example.gov.cn/search",
        keyword_location="json",
        keyword_param=None,
        keyword_path=("query", "kw"),
        json_object_template=(),
        content_type="application/json",
        approved_origins=("https://api.example.gov.cn/",),
        evidence_source="probe",
    )
    candidate = SearchCandidate(
        method="POST",
        endpoint="https://api.example.gov.cn/search",
        keyword_param="kw",
        source="trs_signature",
        request_shape=shape,
        status="unverified",
    )
    outcome = ProbeOutcome(
        SearchProbeResponse(200, "application/json", JSON_BODY, "https://api.example.gov.cn/search", 0),
        None,
    )
    result = probe_search_candidate(candidate, ("k",), fetcher=FakeFetcher(outcome), policy=POLICY)
    assert result.status == "success"
    assert result.selector_evidence is not None
    assert result.selector_evidence.candidate_kind == "json_api"
    assert result.selector_evidence.result_item == "/data/items"
