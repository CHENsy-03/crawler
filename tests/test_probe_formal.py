"""Offline tests for the formal probe_search_candidate entry."""

from crawler.site.models import CandidateRequestShape, SearchCandidate
from crawler.site.search_probe import (
    ProbeOutcome,
    SearchProbePolicy,
    SearchProbeRejection,
    SearchProbeResponse,
    probe_search_candidate,
)

POLICY = SearchProbePolicy()
TARGET = "https://example.gov.cn/"

HTML_OK = (
    b'<div class="results">'
    b'<div class="result-item"><a href="https://example.gov.cn/a">A</a></div>'
    b'<div class="result-item"><a href="https://example.gov.cn/b">B</a></div>'
    b'</div>'
)
EMPTY_HTML = b'<html><body>no results</body></html>'


def _shape():
    return CandidateRequestShape(
        method="GET",
        endpoint="https://example.gov.cn/search",
        keyword_location="query",
        keyword_param="q",
        approved_origins=(TARGET, "https://example.gov.cn/search"),
        evidence_source="form",
    )


def _candidate():
    return SearchCandidate(
        method="GET",
        endpoint="https://example.gov.cn/search",
        keyword_param="q",
        request_shape=_shape(),
        status="unverified",
    )


class FakeFetcher:
    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.calls = []

    def fetch(self, request, *, policy):
        self.calls.append(request)
        if not self.outcomes:
            return ProbeOutcome(None, SearchProbeRejection("no_evidence", "no response"))
        return self.outcomes.pop(0)


def _html_outcome(body=HTML_OK):
    return ProbeOutcome(
        SearchProbeResponse(200, "text/html", body, "https://example.gov.cn/search", 0),
        None,
    )


def test_not_eligible_candidate_makes_zero_requests():
    candidate = SearchCandidate(
        method="GET",
        endpoint="https://example.gov.cn/search",
        keyword_param="q",
    )
    fetcher = FakeFetcher()
    result = probe_search_candidate(candidate, ("k",), fetcher=fetcher, policy=POLICY)
    assert result.status == "not_eligible"
    assert fetcher.calls == []


def test_html_success_returns_evidence():
    fetcher = FakeFetcher([_html_outcome()])
    result = probe_search_candidate(_candidate(), ("低空经济",), fetcher=fetcher, policy=POLICY)
    assert result.status == "success"
    assert result.selector_evidence is not None
    assert result.selector_evidence.candidate_kind == "html_form"


def test_stops_after_first_complete_evidence():
    fetcher = FakeFetcher([_html_outcome(), _html_outcome()])
    result = probe_search_candidate(_candidate(), ("k1", "k2"), fetcher=fetcher, policy=POLICY)
    assert result.status == "success"
    assert len(fetcher.calls) == 1


def test_tries_second_keyword_when_first_has_no_evidence():
    empty = ProbeOutcome(
        SearchProbeResponse(200, "text/html", EMPTY_HTML, "https://example.gov.cn/search", 0),
        None,
    )
    fetcher = FakeFetcher([empty, _html_outcome()])
    result = probe_search_candidate(_candidate(), ("k1", "k2"), fetcher=fetcher, policy=POLICY)
    assert result.status == "success"
    assert len(fetcher.calls) == 2


def test_rejected_outcome_does_not_generate_evidence():
    fetcher = FakeFetcher([ProbeOutcome(None, SearchProbeRejection("request_failed", "failed"))])
    result = probe_search_candidate(_candidate(), ("k",), fetcher=fetcher, policy=POLICY)
    assert result.status == "rejected"
    assert result.selector_evidence is None


def test_no_evidence_fails_closed():
    empty = ProbeOutcome(
        SearchProbeResponse(200, "text/html", EMPTY_HTML, "https://example.gov.cn/search", 0),
        None,
    )
    fetcher = FakeFetcher([empty, empty])
    result = probe_search_candidate(_candidate(), ("k1", "k2"), fetcher=fetcher, policy=POLICY)
    assert result.status == "no_evidence"
    assert result.selector_evidence is None


def test_keyword_order_is_preserved():
    empty = ProbeOutcome(
        SearchProbeResponse(200, "text/html", EMPTY_HTML, "https://example.gov.cn/search", 0),
        None,
    )
    fetcher = FakeFetcher([empty, _html_outcome()])
    probe_search_candidate(_candidate(), ("first", "second"), fetcher=fetcher, policy=POLICY)
    assert "first" in fetcher.calls[0].url
    assert "second" in fetcher.calls[1].url


def test_result_repr_does_not_leak_keyword_or_body():
    fetcher = FakeFetcher([_html_outcome()])
    result = probe_search_candidate(_candidate(), ("低空经济",), fetcher=fetcher, policy=POLICY)
    assert "低空经济" not in repr(result)
    assert "no results" not in repr(result)
