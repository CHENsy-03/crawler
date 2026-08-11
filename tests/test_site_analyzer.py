import pytest

from pathlib import Path

from crawler.site.analyzer import SiteAnalyzer
from crawler.site.models import DiscoveryLimits, SearchCandidate

FIX = Path(__file__).parent / "fixtures" / "site_discovery"


class FakeResponse:
    def __init__(self, status_code=200, headers=None, text="", too_large=False, bytes_read=0, location=""):
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
        self.text = text
        self.too_large = too_large
        self.bytes_read = bytes_read
        self.location = location


def _fixture(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_analyzer_generates_form_candidate():
    calls = []
    def fetcher(url, limits):
        calls.append(url)
        return FakeResponse(text=_fixture("get_form.html"))
    result = SiteAnalyzer(resolver=lambda h: ['8.8.8.8'], fetcher=fetcher).analyze("http://example.gov.cn/")
    assert calls == ["http://example.gov.cn/"]
    assert any(c.source == "form" and c.method == "GET" for c in result.candidates)


def test_analyzer_redirect_to_private_blocked_before_second_request():
    calls = []
    def fetcher(url, limits):
        calls.append(url)
        if len(calls) == 1:
            return FakeResponse(status_code=302, headers={"Location": "http://10.0.0.1/next", "Content-Type": "text/html"}, location="http://10.0.0.1/next")
        return FakeResponse(text=_fixture("no_search.html"))
    result = SiteAnalyzer(resolver=lambda h: ['8.8.8.8'], fetcher=fetcher).analyze("http://example.gov.cn/")
    assert len(calls) == 1
    assert any(d.code == "REDIRECT_BLOCKED" for d in result.diagnostics)


def test_analyzer_reports_too_large():
    def fetcher(url, limits):
        return FakeResponse(too_large=True, bytes_read=999999)
    result = SiteAnalyzer(resolver=lambda h: ['8.8.8.8'], fetcher=fetcher).analyze("http://example.gov.cn/")
    assert any(d.code == "RESPONSE_TOO_LARGE" for d in result.diagnostics)


def test_analyzer_reports_unsupported_content_type():
    def fetcher(url, limits):
        return FakeResponse(headers={"Content-Type": "application/pdf"}, text="%PDF")
    result = SiteAnalyzer(resolver=lambda h: ['8.8.8.8'], fetcher=fetcher).analyze("http://example.gov.cn/")
    assert any(d.code == "UNSUPPORTED_CONTENT_TYPE" for d in result.diagnostics)


def test_analyzer_no_search_candidate():
    def fetcher(url, limits):
        return FakeResponse(text=_fixture("no_search.html"))
    result = SiteAnalyzer(resolver=lambda h: ['8.8.8.8'], fetcher=fetcher).analyze("http://example.gov.cn/")
    assert any(d.code == "NO_SEARCH_CANDIDATE" for d in result.diagnostics)


def test_analyzer_login_diagnostic():
    def fetcher(url, limits):
        return FakeResponse(text=_fixture("login.html"))
    result = SiteAnalyzer(resolver=lambda h: ['8.8.8.8'], fetcher=fetcher).analyze("http://example.gov.cn/")
    assert any(d.code == "LOGIN_OR_CAPTCHA_REQUIRED" for d in result.diagnostics)

def test_analyzer_trs_signature_candidate():
    def fetcher(url, limits):
        return FakeResponse(text=_fixture("trs.html"))
    result = SiteAnalyzer(resolver=lambda h: ['8.8.8.8'], fetcher=fetcher).analyze("http://example.gov.cn/")
    assert any(c.source == "trs_signature" for c in result.candidates)


def test_analyzer_jpaas_signature_candidate():
    def fetcher(url, limits):
        return FakeResponse(text=_fixture("jpaas.html"))
    result = SiteAnalyzer(resolver=lambda h: ['8.8.8.8'], fetcher=fetcher).analyze("http://example.gov.cn/")
    assert any(c.source == "jpaas_signature" for c in result.candidates)


def test_analyzer_static_link_candidate():
    def fetcher(url, limits):
        return FakeResponse(text=_fixture("search_links.html"))
    result = SiteAnalyzer(resolver=lambda h: ['8.8.8.8'], fetcher=fetcher).analyze("http://example.gov.cn/")
    assert any(c.source in ("internal_link", "static_script") for c in result.candidates)


def test_analyzer_dedup_and_order():
    html = (FIX / "get_form.html").read_text(encoding="utf-8") * 2
    def fetcher(url, limits):
        return FakeResponse(text=html)
    result = SiteAnalyzer(resolver=lambda h: ['8.8.8.8'], fetcher=fetcher).analyze("http://example.gov.cn/")
    form_candidates = [c for c in result.candidates if c.source == "form"]
    assert len(form_candidates) == 1
    assert result.candidates[0].priority >= form_candidates[0].priority


def test_analyzer_post_candidate_not_submitted():
    calls = []
    def fetcher(url, limits):
        calls.append(url)
        return FakeResponse(text=_fixture("post_form.html"))
    result = SiteAnalyzer(resolver=lambda h: ['8.8.8.8'], fetcher=fetcher).analyze("http://example.gov.cn/")
    assert len(calls) == 1
    assert any(c.method == "POST" for c in result.candidates)

def _fake_safe_resolver(host):
    return ["8.8.8.8"]


def test_redirect_same_origin_allowed():
    calls = []
    def fetcher(url, limits):
        calls.append(url)
        if len(calls) == 1:
            return FakeResponse(status_code=302, headers={"Location": "/next", "Content-Type": "text/html"}, location="/next")
        return FakeResponse(text=_fixture("get_form.html"))
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    assert len(calls) == 2
    assert not any(d.code == "REDIRECT_BLOCKED" for d in result.diagnostics)


def test_redirect_http_to_https_same_host_allowed():
    calls = []
    def fetcher(url, limits):
        calls.append(url)
        if len(calls) == 1:
            return FakeResponse(status_code=302, headers={"Location": "https://example.gov.cn/next", "Content-Type": "text/html"}, location="https://example.gov.cn/next")
        return FakeResponse(text=_fixture("get_form.html"))
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    assert len(calls) == 2
    assert not any(d.code == "REDIRECT_BLOCKED" for d in result.diagnostics)


def test_redirect_https_to_http_rejected():
    calls = []
    def fetcher(url, limits):
        calls.append(url)
        return FakeResponse(status_code=302, headers={"Location": "http://example.gov.cn/next", "Content-Type": "text/html"}, location="http://example.gov.cn/next")
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("https://example.gov.cn/")
    assert len(calls) == 1
    assert any(d.code == "REDIRECT_BLOCKED" for d in result.diagnostics)


def test_redirect_cross_host_rejected():
    calls = []
    def fetcher(url, limits):
        calls.append(url)
        return FakeResponse(status_code=302, headers={"Location": "http://other.example/next", "Content-Type": "text/html"}, location="http://other.example/next")
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    assert len(calls) == 1
    assert any(d.code == "REDIRECT_BLOCKED" for d in result.diagnostics)


def test_redirect_port_change_rejected():
    calls = []
    def fetcher(url, limits):
        calls.append(url)
        return FakeResponse(status_code=302, headers={"Location": "http://example.gov.cn:8080/next", "Content-Type": "text/html"}, location="http://example.gov.cn:8080/next")
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    assert len(calls) == 1
    assert any(d.code == "REDIRECT_BLOCKED" for d in result.diagnostics)


def test_redirect_invalid_location_rejected():
    calls = []
    def fetcher(url, limits):
        calls.append(url)
        return FakeResponse(status_code=302, headers={"Location": "javascript:alert(1)", "Content-Type": "text/html"}, location="javascript:alert(1)")
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    assert len(calls) == 1
    assert any(d.code == "REDIRECT_BLOCKED" for d in result.diagnostics)


def test_redirect_missing_location_returns_only_redirect_diagnostic():
    calls = []
    def fetcher(url, limits):
        calls.append(url)
        return FakeResponse(status_code=302, headers={"Content-Type": "text/html"})
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    assert len(calls) == 1
    assert [d.code for d in result.diagnostics] == ["REDIRECT_BLOCKED"]
    assert result.candidates == ()


@pytest.mark.parametrize("status", [403, 404, 500])
def test_http_error_status_does_not_parse_page(status):
    calls = []
    def fetcher(url, limits):
        calls.append(url)
        return FakeResponse(status_code=status, text=_fixture("get_form.html"))
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    assert any(d.code == "FETCH_FAILED" for d in result.diagnostics)
    assert result.candidates == ()
    assert not any(d.code == "NO_SEARCH_CANDIDATE" for d in result.diagnostics)


def test_js_only_returns_unsupported_js_search(monkeypatch):
    from crawler.site import analyzer as analyzer_module
    def fetcher(url, limits):
        return FakeResponse(text=_fixture("js_only.html"))
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    assert any(d.code == "UNSUPPORTED_JS_SEARCH" for d in result.diagnostics)


def test_cross_origin_candidates_marked_requires_scope_validation():
    html = (
        '<form action="https://other.example/search" method="get"><input name="q"></form>'
        '<a href="https://other.example/so">search</a>'
        '<script src="https://other.example/so.js"></script>'
    )
    def fetcher(url, limits):
        return FakeResponse(text=html)
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    cross = [c for c in result.candidates if "other.example" in c.endpoint]
    assert cross
    assert all(c.scope == "requires_scope_validation" for c in cross)


def test_same_origin_relative_candidate_scope():
    html = '<a href="/search">search</a>'
    def fetcher(url, limits):
        return FakeResponse(text=html)
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    same = [c for c in result.candidates if c.source == "internal_link"]
    assert same
    assert all(c.scope == "same_origin" for c in same)


def test_redirect_loop_returns_redirect_blocked():
    calls = []
    def fetcher(url, limits):
        calls.append(url)
        return FakeResponse(status_code=302, headers={"Location": "/loop", "Content-Type": "text/html"}, location="/loop")
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    assert len(calls) == 6
    assert any(d.code == "REDIRECT_BLOCKED" for d in result.diagnostics)
    assert not any(d.code == "NO_SEARCH_CANDIDATE" for d in result.diagnostics)


def test_candidate_limit_enforced():
    html = "".join(
        f'<form action="/search{i}" method="get"><input name="q"></form>' for i in range(5)
    )
    def fetcher(url, limits):
        return FakeResponse(text=html)
    limits = DiscoveryLimits(max_candidates=2)
    result = SiteAnalyzer(limits=limits, resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    assert len(result.candidates) <= 2


def test_evidence_limits_enforced():
    html = '<form action="/very/long/search/path" method="get"><input name="q"></form>'
    def fetcher(url, limits):
        return FakeResponse(text=html)
    limits = DiscoveryLimits(max_evidence_items=1, max_evidence_chars=20)
    result = SiteAnalyzer(limits=limits, resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    for c in result.candidates:
        assert len(c.evidence) <= 1
        assert all(len(e) <= 20 for e in c.evidence)


def test_script_chars_limit_applied():
    def fetcher(url, limits):
        return FakeResponse(text=_fixture("trs.html"))
    limits = DiscoveryLimits(max_script_chars=5)
    result = SiteAnalyzer(limits=limits, resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    assert not any(c.source == "trs_signature" for c in result.candidates)

def test_parser_exception_does_not_crash(monkeypatch):
    import crawler.site.analyzer as analyzer_module
    def broken_parse(html, base_url, limits):
        raise RuntimeError("boom")
    monkeypatch.setattr(analyzer_module, "parse_forms", broken_parse)
    def fetcher(url, limits):
        return FakeResponse(text=_fixture("get_form.html"))
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    assert any(d.code == "ANALYSIS_FAILED" for d in result.diagnostics)
    assert "boom" not in str(result.to_dict())


def test_zero_max_evidence_chars_produces_no_evidence():
    def fetcher(url, limits):
        return FakeResponse(text=_fixture("get_form.html"))
    limits = DiscoveryLimits(max_evidence_items=5, max_evidence_chars=0)
    result = SiteAnalyzer(limits=limits, resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    form_candidates = [c for c in result.candidates if c.source == "form"]
    assert form_candidates
    assert all(c.evidence == () for c in form_candidates)
    assert all("" not in c.evidence for c in result.candidates)


def test_zero_max_evidence_items_produces_no_evidence():
    def fetcher(url, limits):
        return FakeResponse(text=_fixture("get_form.html"))
    limits = DiscoveryLimits(max_evidence_items=0, max_evidence_chars=100)
    result = SiteAnalyzer(limits=limits, resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    form_candidates = [c for c in result.candidates if c.source == "form"]
    assert form_candidates
    assert all(c.evidence == () for c in form_candidates)


def test_link_evidence_redacts_sensitive_href_query():
    html = '<a href="/search?token=SECRET&q=x">search</a>'
    def fetcher(url, limits):
        return FakeResponse(text=html)
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    links = [c for c in result.candidates if c.source == "internal_link"]
    assert links
    c = links[0]
    assert c.endpoint == "http://example.gov.cn/search?token=SECRET&q=x"
    assert "SECRET" not in str(c.evidence)
    assert "token=[REDACTED]" in c.evidence[0]
    assert "q=x" in c.evidence[0]


def test_analyzer_form_evidence_redacted_but_endpoint_unchanged():
    html = '<form action="/search?access_token=SECRET&q=x" method="get"><input name="q"></form>'
    def fetcher(url, limits):
        return FakeResponse(text=html)
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    forms = [c for c in result.candidates if c.source == "form"]
    assert forms
    c = forms[0]
    assert c.endpoint == "http://example.gov.cn/search?access_token=SECRET&q=x"
    assert "SECRET" not in str(c.evidence)
    assert "access_token=[REDACTED]" in c.evidence[0]
    assert "q=x" in c.evidence[0]


def test_evidence_plain_query_unchanged_through_analyzer():
    html = '<a href="/search?q=x&page=2">search</a>'
    def fetcher(url, limits):
        return FakeResponse(text=html)
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    links = [c for c in result.candidates if c.source == "internal_link"]
    assert links
    assert "/search?q=x&page=2" in links[0].evidence[0]
    assert "SECRET" not in str(links[0].evidence)


def test_no_sensitive_raw_value_in_any_evidence():
    html = (
        '<form action="/callback?code=real-secret&token=abc&q=x" method="get"><input name="q"></form>'
        '<a href="/search?access_token=xyz&q=x">search</a>'
    )
    def fetcher(url, limits):
        return FakeResponse(text=html)
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    assert result.candidates
    for c in result.candidates:
        for item in c.evidence:
            assert "real-secret" not in item
            assert "abc" not in item
            assert "xyz" not in item


def test_analyzer_initial_resolver_failure_returns_diagnostic():
    calls = []
    def resolver(host):
        raise RuntimeError("dns boom")
    def fetcher(url, limits):
        calls.append(url)
        return FakeResponse()
    result = SiteAnalyzer(resolver=resolver, fetcher=fetcher).analyze("http://example.com/")
    assert calls == []
    assert any(d.code == "TARGET_BLOCKED_BY_POLICY" for d in result.diagnostics)
    assert "dns boom" not in str(result.to_dict())


def test_analyzer_redirect_resolver_failure_blocks_second_request():
    calls = []
    state = {"count": 0}
    def resolver(host):
        state["count"] += 1
        if state["count"] == 1:
            return ["8.8.8.8"]
        raise RuntimeError("dns boom")
    def fetcher(url, limits):
        calls.append(url)
        return FakeResponse(
            status_code=302,
            headers={"Location": "/next", "Content-Type": "text/html"},
            location="/next",
        )
    result = SiteAnalyzer(resolver=resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    assert len(calls) == 1
    assert any(d.code == "REDIRECT_BLOCKED" for d in result.diagnostics)
    assert "dns boom" not in str(result.to_dict())


def test_analyzer_fetches_public_ipv6_with_brackets():
    calls = []
    def fetcher(url, limits):
        calls.append(url)
        return FakeResponse(text=_fixture("no_search.html"))
    result = SiteAnalyzer(
        resolver=lambda h: ["2606:4700:4700::1111"],
        fetcher=fetcher,
    ).analyze("http://[2606:4700:4700::1111]/")
    assert calls == ["http://[2606:4700:4700::1111]/"]
    assert result.normalized_url == "http://[2606:4700:4700::1111]/"


def _candidate(method="GET", endpoint="http://example.gov.cn/search", keyword="q", fixed=(), priority=0, source="", evidence=()):
    return SearchCandidate(
        method=method,
        endpoint=endpoint,
        keyword_param=keyword,
        fixed_params=tuple(fixed),
        priority=priority,
        source=source,
        evidence=tuple(evidence),
    )


def test_dedupe_merges_different_evidence_same_key():
    a = _candidate(evidence=("link-evidence",))
    b = _candidate(evidence=("form-evidence",))
    out = SiteAnalyzer._dedupe_and_sort([a, b])
    assert len(out) == 1
    assert out[0].evidence == ("link-evidence", "form-evidence")


def test_dedupe_deduplicates_repeated_evidence():
    a = _candidate(evidence=("same", "first"))
    b = _candidate(evidence=("same", "second"))
    out = SiteAnalyzer._dedupe_and_sort([a, b])
    assert len(out) == 1
    assert out[0].evidence == ("same", "first", "second")


def test_dedupe_merges_three_candidates():
    out = SiteAnalyzer._dedupe_and_sort([
        _candidate(evidence=("e1",)),
        _candidate(evidence=("e2",)),
        _candidate(evidence=("e3",)),
    ])
    assert len(out) == 1
    assert out[0].evidence == ("e1", "e2", "e3")


def test_dedupe_keeps_existing_multiple_evidence():
    a = _candidate(evidence=("e1", "e2"))
    b = _candidate(evidence=("e3",))
    out = SiteAnalyzer._dedupe_and_sort([a, b])
    assert out[0].evidence == ("e1", "e2", "e3")


def test_dedupe_empty_evidence_does_not_hide_other():
    a = _candidate(evidence=())
    b = _candidate(evidence=("form-evidence",))
    out = SiteAnalyzer._dedupe_and_sort([a, b])
    assert len(out) == 1
    assert out[0].evidence == ("form-evidence",)


def test_dedupe_identical_candidate_once():
    a = _candidate(evidence=("same",))
    out = SiteAnalyzer._dedupe_and_sort([a, _candidate(evidence=("same",))])
    assert len(out) == 1
    assert out[0].evidence == ("same",)


def test_dedupe_different_keys_not_merged():
    a = _candidate(endpoint="http://example.gov.cn/search", evidence=("a",))
    b = _candidate(endpoint="http://example.gov.cn/s", evidence=("b",))
    out = SiteAnalyzer._dedupe_and_sort([a, b])
    assert len(out) == 2
    assert {c.evidence[0] for c in out} == {"a", "b"}
    assert [c.endpoint for c in out] == [
        "http://example.gov.cn/s",
        "http://example.gov.cn/search",
    ]


def test_dedupe_different_method_not_merged():
    a = _candidate(method="GET", evidence=("get",))
    b = _candidate(method="POST", evidence=("post",))
    out = SiteAnalyzer._dedupe_and_sort([a, b])
    assert len(out) == 2


def test_dedupe_winner_fields_preserved_but_evidence_merged():
    low = _candidate(priority=1, source="common_path", evidence=("low",))
    high = _candidate(priority=5, source="form", evidence=("high",))
    out = SiteAnalyzer._dedupe_and_sort([low, high])
    assert len(out) == 1
    assert out[0].source == "form"
    assert out[0].priority == 5
    assert out[0].evidence == ("low", "high")


def test_dedupe_order_stable():
    candidates = [
        _candidate(endpoint="http://example.gov.cn/search", evidence=("a",)),
        _candidate(endpoint="http://example.gov.cn/search", evidence=("b",)),
        _candidate(endpoint="http://example.gov.cn/s", evidence=("c",)),
    ]
    first = SiteAnalyzer._dedupe_and_sort(candidates)
    second = SiteAnalyzer._dedupe_and_sort(candidates)
    assert [c.to_dict() for c in first] == [c.to_dict() for c in second]


def test_dedupe_empty_input_returns_empty():
    assert SiteAnalyzer._dedupe_and_sort([]) == []


def test_analyzer_form_and_link_same_key_merge_evidence():
    html = (
        '<form action="/search" method="get"><input name="q"></form>'
        '<a href="/search">search</a>'
    )
    def fetcher(url, limits):
        return FakeResponse(text=html)
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    same = [c for c in result.candidates if c.endpoint == "http://example.gov.cn/search"]
    assert len(same) == 1
    joined = " ".join(same[0].evidence)
    assert "form method=get action=/search" in joined
    assert "internal_link:/search" in joined


def test_analyzer_merged_evidence_stays_redacted():
    html = (
        '<form action="/search?token=SECRET" method="get"><input name="q"></form>'
        '<a href="/search?token=SECRET">search</a>'
    )
    def fetcher(url, limits):
        return FakeResponse(text=html)
    result = SiteAnalyzer(resolver=_fake_safe_resolver, fetcher=fetcher).analyze("http://example.gov.cn/")
    same = [c for c in result.candidates if c.endpoint == "http://example.gov.cn/search?token=SECRET"]
    assert len(same) == 1
    assert "SECRET" not in " ".join(same[0].evidence)
    assert "token=[REDACTED]" in " ".join(same[0].evidence)
