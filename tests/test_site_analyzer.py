import pytest

from pathlib import Path

from crawler.site.analyzer import SiteAnalyzer
from crawler.site.models import DiscoveryLimits

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
