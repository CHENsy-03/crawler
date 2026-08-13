"""Offline tests for selector evidence extraction and validation."""

import pytest

from crawler.site.selector_evidence import (
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    SelectorEvidence,
    extract_html_selector_evidence,
    extract_json_selector_evidence,
)

KEY = ("GET", "https://example.gov.cn/search", "q", ())
ORIGIN = "https://example.gov.cn/"

HTML_OK = """
<div class="results">
  <div class="result-item"><h3><a href="https://example.gov.cn/a">Title A</a></h3></div>
  <div class="result-item"><h3><a href="https://example.gov.cn/b">Title B</a></h3></div>
</div>
"""


def test_html_two_consistent_items_success():
    result = extract_html_selector_evidence(HTML_OK, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "success"
    assert result.evidence is not None
    assert result.evidence.result_item == "div.result-item"
    assert result.evidence.title == "a"
    assert result.evidence.url == "a"
    assert result.evidence.match_count == 2
    assert result.evidence.validated is True


def test_html_single_item_rejected():
    html = '<div class="result-item"><a href="https://example.gov.cn/a">A</a></div>'
    result = extract_html_selector_evidence(html, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "no_evidence"


def test_html_missing_title_rejected():
    html = """
    <div class="results">
      <div class="result-item"><a href="https://example.gov.cn/a"></a></div>
      <div class="result-item"><a href="https://example.gov.cn/b"></a></div>
    </div>
    """
    result = extract_html_selector_evidence(html, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "no_evidence"


def test_html_missing_url_rejected():
    html = """
    <div class="results">
      <div class="result-item"><h3>Title A</h3></div>
      <div class="result-item"><h3>Title B</h3></div>
    </div>
    """
    result = extract_html_selector_evidence(html, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "no_evidence"


def test_html_all_links_rejected():
    html = '<a href="https://example.gov.cn/a">A</a><a href="https://example.gov.cn/b">B</a>'
    result = extract_html_selector_evidence(html, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "no_evidence"


def test_html_body_selector_rejected():
    html = "<div><div>a</div><div>b</div></div>"
    result = extract_html_selector_evidence(html, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "no_evidence"


def test_html_dynamic_class_rejected():
    html = """
    <div class="results">
      <div class="a1b2c3d4e5"><a href="https://example.gov.cn/a">A</a></div>
      <div class="a1b2c3d4e5"><a href="https://example.gov.cn/b">B</a></div>
    </div>
    """
    result = extract_html_selector_evidence(html, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "no_evidence"


def test_html_unsafe_href_rejected():
    html = """
    <div class="results">
      <div class="result-item"><a href="javascript:alert(1)">A</a></div>
      <div class="result-item"><a href="data:text/html,x">B</a></div>
    </div>
    """
    result = extract_html_selector_evidence(html, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "no_evidence"


def test_html_ambiguous_two_groups_rejected():
    html = """
    <div class="news">
      <div class="news-item"><a href="https://example.gov.cn/a">A</a></div>
      <div class="news-item"><a href="https://example.gov.cn/b">B</a></div>
    </div>
    <div class="files">
      <div class="file-item"><a href="https://example.gov.cn/c">C</a></div>
      <div class="file-item"><a href="https://example.gov.cn/d">D</a></div>
    </div>
    """
    result = extract_html_selector_evidence(html, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "ambiguous"


def test_html_parse_is_deterministic():
    first = extract_html_selector_evidence(HTML_OK, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    second = extract_html_selector_evidence(HTML_OK, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert first == second


JSON_OK = b'{"data":{"items":[{"title":"A","url":"https://example.gov.cn/a"},{"title":"B","url":"https://example.gov.cn/b"}]}}'


def test_json_two_consistent_items_success():
    result = extract_json_selector_evidence(JSON_OK, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "success"
    assert result.evidence is not None
    assert result.evidence.result_item == "/data/items"
    assert result.evidence.title == "/title"
    assert result.evidence.url == "/url"
    assert result.evidence.match_count == 2


def test_json_less_than_two_items_rejected():
    body = b'{"data":{"items":[{"title":"A","url":"https://example.gov.cn/a"}]}}'
    result = extract_json_selector_evidence(body, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "no_evidence"


def test_json_non_array_result_rejected():
    body = b'{"data":{"items":{"title":"A"}}}'
    result = extract_json_selector_evidence(body, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "no_evidence"


def test_json_inconsistent_structure_rejected():
    body = b'{"data":{"items":[{"title":"A"},{"url":"https://example.gov.cn/b"}]}}'
    result = extract_json_selector_evidence(body, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "no_evidence"


def test_json_multiple_arrays_ambiguous():
    body = b'{"a":[{"t":"A","u":"https://example.gov.cn/a"},{"t":"B","u":"https://example.gov.cn/b"}],"b":[{"t":"C","u":"https://example.gov.cn/c"},{"t":"D","u":"https://example.gov.cn/d"}]}'
    result = extract_json_selector_evidence(body, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "ambiguous"


def test_json_duplicate_object_key_rejected():
    body = b'{"data":{"items":[{"title":"A","title":"B","url":"https://example.gov.cn/a"},{"title":"C","url":"https://example.gov.cn/b"}]}}'
    result = extract_json_selector_evidence(body, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "rejected"


def test_json_pointer_escapes_slash_and_tilde():
    body = b'{"rows":[{"a/b":{"t":"A"},"c~d":"https://example.gov.cn/a"},{"a/b":{"t":"B"},"c~d":"https://example.gov.cn/b"}]}'
    result = extract_json_selector_evidence(body, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "success"
    assert result.evidence is not None
    assert result.evidence.result_item == "/rows"
    assert result.evidence.title == "/a~1b/t"
    assert result.evidence.url == "/c~0d"


def test_json_depth_budget_rejected(monkeypatch):
    monkeypatch.setattr("crawler.site.selector_evidence.MAX_JSON_DEPTH", 3)
    body = b'{"a":{"b":{"c":{"d":[{"t":"A","u":"https://example.gov.cn/a"},{"t":"B","u":"https://example.gov.cn/b"}]}}}}'
    result = extract_json_selector_evidence(body, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "rejected"


def test_json_node_budget_rejected(monkeypatch):
    monkeypatch.setattr("crawler.site.selector_evidence.MAX_JSON_NODES", 3)
    body = b'{"data":{"items":[{"title":"A","url":"https://example.gov.cn/a"},{"title":"B","url":"https://example.gov.cn/b"}]}}'
    result = extract_json_selector_evidence(body, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert result.code == "rejected"


def test_json_parse_deterministic():
    first = extract_json_selector_evidence(JSON_OK, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    second = extract_json_selector_evidence(JSON_OK, final_origin=ORIGIN, candidate_key=KEY, evidence_source="probe")
    assert first == second


def test_evidence_repr_does_not_contain_body_or_keyword():
    evidence = SelectorEvidence(
        candidate_key=KEY,
        candidate_kind="html_form",
        response_kind="html",
        result_item="div.result-item",
        title="a",
        url="a",
        final_origin=ORIGIN,
        match_count=2,
        validated=True,
        evidence_source="probe",
    )
    assert "body" not in repr(evidence).lower()
    assert "keyword" not in repr(evidence).lower()
