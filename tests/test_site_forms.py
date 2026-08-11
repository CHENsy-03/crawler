from pathlib import Path

from crawler.site.forms import parse_forms
from crawler.site.models import DiscoveryLimits

FIX = Path(__file__).parent / "fixtures" / "site_discovery"


def test_get_form_with_hidden_param():
    html = (FIX / "get_form.html").read_text(encoding="utf-8")
    candidates, diags = parse_forms(html, "http://example.gov.cn/", DiscoveryLimits())
    assert len(candidates) == 1
    c = candidates[0]
    assert c.method == "GET"
    assert c.keyword_param == "q"
    assert ("siteCode", "abc123") in c.fixed_params
    assert c.status == "unverified"


def test_post_form_urlencoded_only_candidate():
    html = (FIX / "post_form.html").read_text(encoding="utf-8")
    candidates, diags = parse_forms(html, "http://example.gov.cn/", DiscoveryLimits())
    assert len(candidates) == 1
    c = candidates[0]
    assert c.method == "POST"
    assert c.request_encoding == "application/x-www-form-urlencoded"


def test_login_form_rejected():
    html = (FIX / "login.html").read_text(encoding="utf-8")
    candidates, diags = parse_forms(html, "http://example.gov.cn/", DiscoveryLimits())
    assert candidates == []
    assert any(d.code == "LOGIN_OR_CAPTCHA_REQUIRED" for d in diags)


def test_sensitive_hidden_rejected():
    html = '<form action="/search" method="get"><input name="q"><input type="hidden" name="csrf_token" value="x"></form>'
    candidates, diags = parse_forms(html, "http://example.gov.cn/", DiscoveryLimits())
    assert candidates == []
    assert any(d.code == "SENSITIVE_FORM_REJECTED" for d in diags)

def test_form_class_attribute_single():
    html = '<form class="search-form" action="/search" method="get"><input name="q"></form>'
    candidates, diags = parse_forms(html, "http://example.gov.cn/", DiscoveryLimits())
    assert len(candidates) == 1
    assert candidates[0].method == "GET"


def test_form_class_attribute_multiple():
    html = '<form class="site search-form primary" action="/search" method="get"><input name="q"></form>'
    candidates, diags = parse_forms(html, "http://example.gov.cn/", DiscoveryLimits())
    assert len(candidates) == 1
    assert candidates[0].keyword_param == "q"


def test_unknown_method_not_treated_as_get():
    for method in ["PUT", "DELETE", "PATCH"]:
        html = f'<form action="/search" method="{method}"><input name="q"></form>'
        candidates, diags = parse_forms(html, "http://example.gov.cn/", DiscoveryLimits())
        assert candidates == [], method


def test_post_method_case_insensitive():
    html = '<form action="/search" method="PoSt"><input name="q"></form>'
    candidates, diags = parse_forms(html, "http://example.gov.cn/", DiscoveryLimits())
    assert len(candidates) == 1
    assert candidates[0].method == "POST"


def test_missing_method_defaults_get():
    html = '<form action="/search"><input name="q"></form>'
    candidates, diags = parse_forms(html, "http://example.gov.cn/", DiscoveryLimits())
    assert len(candidates) == 1
    assert candidates[0].method == "GET"


def test_empty_method_defaults_get():
    html = '<form action="/search" method=""><input name="q"></form>'
    candidates, diags = parse_forms(html, "http://example.gov.cn/", DiscoveryLimits())
    assert len(candidates) == 1
    assert candidates[0].method == "GET"


def test_form_evidence_redacts_sensitive_action_query():
    html = '<form action="/search?token=SECRET&q=x" method="get"><input name="q"></form>'
    candidates, diags = parse_forms(html, "http://example.gov.cn/", DiscoveryLimits())
    assert len(candidates) == 1
    c = candidates[0]
    assert c.endpoint == "http://example.gov.cn/search?token=SECRET&q=x"
    assert "SECRET" not in str(c.evidence)
    assert "token=[REDACTED]" in c.evidence[0]
    assert "q=x" in c.evidence[0]


def test_form_evidence_redacts_code_and_keeps_plain_params():
    html = '<form action="/callback?code=real-secret&state=abc&q=x" method="get"><input name="q"></form>'
    candidates, diags = parse_forms(html, "http://example.gov.cn/", DiscoveryLimits())
    assert len(candidates) == 1
    c = candidates[0]
    assert "real-secret" not in str(c.evidence)
    assert "code=[REDACTED]" in c.evidence[0]
    assert "state=abc" in c.evidence[0]
    assert "q=x" in c.evidence[0]


def test_form_evidence_plain_query_unchanged():
    html = '<form action="/search?q=x&page=2" method="get"><input name="q"></form>'
    candidates, diags = parse_forms(html, "http://example.gov.cn/", DiscoveryLimits())
    assert len(candidates) == 1
    assert candidates[0].evidence[0] == "form method=get action=/search?q=x&page=2"
