import pytest
from urllib.parse import urlsplit

from crawler.site.normalizer import SiteNormalizationError, normalize_target_url, redact_evidence_url


@pytest.mark.parametrize("raw,want", [
    ("http://Example.COM:80/a#frag", "http://example.com/a"),
    ("https://Example.com:443/a?x=1", "https://example.com/a?x=1"),
    ("http://example.com:8080/p?q=1", "http://example.com:8080/p?q=1"),
    ("http://example.com", "http://example.com/"),
    ("http://example.com/a?x=1&x=2", "http://example.com/a?x=1&x=2"),
    ("HTTPS://EXAMPLE.COM:443/", "https://example.com/"),
])
def test_normalize_valid(raw, want):
    assert normalize_target_url(raw) == want


@pytest.mark.parametrize("raw", [
    "ftp://example.com/",
    " http://example.com",
    "http://example.com ",
    "http://exa mple.com/",
    "http://user:pass@example.com/",
    "http:///nohost",
    "http://example.com:abc",
    "http://example.com:99999",
    "http://example.com:",
    "https://[::1",
    "http://example.com/\n",
])
def test_normalize_invalid(raw):
    with pytest.raises(SiteNormalizationError):
        normalize_target_url(raw)


def test_redact_sensitive_query_values():
    raw = "https://example.com/callback?code=real-secret&q=x"
    out = redact_evidence_url(raw)
    assert "real-secret" not in out
    assert "code=[REDACTED]" in out
    assert "q=x" in out


def test_redact_query_name_case_and_encoding():
    raws = [
        "https://example.com/search?TOKEN=SECRET",
        "https://example.com/search?%74%6f%6b%65%6e=SECRET",
        "https://example.com/search?access_token=SECRET",
        "https://example.com/search?session_id=SECRET",
    ]
    for raw in raws:
        out = redact_evidence_url(raw)
        assert "SECRET" not in out
        assert "[REDACTED]" in out


def test_redact_duplicate_and_empty_sensitive_params():
    raw = "https://example.com/search?token=one&q=keep&token=two&token="
    out = redact_evidence_url(raw)
    assert "one" not in out
    assert "two" not in out
    assert out.count("token=[REDACTED]") == 3
    assert "q=keep" in out


def test_redact_preserves_plain_query():
    raw = "https://example.com/search?q=x&page=2"
    assert redact_evidence_url(raw) == raw


def test_redact_no_query_unchanged():
    raw = "https://example.com/search"
    assert redact_evidence_url(raw) == raw


def test_redact_relative_query():
    raw = "/search?token=SECRET&q=x"
    out = redact_evidence_url(raw)
    assert "SECRET" not in out
    assert "token=[REDACTED]" in out
    assert "q=x" in out


def test_redact_malformed_input_does_not_raise():
    for raw in [None, 123, "http://[::1?token=SECRET"]:
        try:
            out = redact_evidence_url(raw)
        except Exception as exc:
            pytest.fail(f"redact raised for {raw!r}: {exc}")
        assert "SECRET" not in str(out)


def test_normalize_ipv6_without_port():
    raw = "http://[2001:db8::1]/path"
    out = normalize_target_url(raw)
    assert out == "http://[2001:db8::1]/path"
    parts = urlsplit(out)
    assert parts.hostname == "2001:db8::1"
    assert parts.port is None
    assert "[[" not in out


def test_normalize_ipv6_with_port():
    raw = "http://[2001:db8::1]:8080/path?q=x#frag"
    out = normalize_target_url(raw)
    assert out == "http://[2001:db8::1]:8080/path?q=x"
    parts = urlsplit(out)
    assert parts.hostname == "2001:db8::1"
    assert parts.port == 8080
    assert parts.query == "q=x"
    assert parts.fragment == ""


def test_normalize_https_ipv6_with_port():
    raw = "https://[2606:4700:4700::1111]:8443/a"
    out = normalize_target_url(raw)
    assert out == "https://[2606:4700:4700::1111]:8443/a"
    parts = urlsplit(out)
    assert parts.hostname == "2606:4700:4700::1111"
    assert parts.port == 8443


def test_normalize_ipv6_default_port_removed():
    assert normalize_target_url("http://[::1]:80/") == "http://[::1]/"
    assert normalize_target_url("https://[::1]:443/") == "https://[::1]/"


def test_normalize_ipv4_address_unchanged():
    assert normalize_target_url("http://8.8.8.8:8080/") == "http://8.8.8.8:8080/"
    assert normalize_target_url("http://8.8.8.8/") == "http://8.8.8.8/"


def test_normalize_domain_unchanged_with_path_query():
    raw = "http://example.com/path?q=x&x=2"
    assert normalize_target_url(raw) == raw


def test_normalize_ipv6_roundtrip_host_and_port():
    for raw, expected_host, expected_port in [
        ("http://[2001:db8::1]/", "2001:db8::1", None),
        ("http://[2001:db8::1]:8080/", "2001:db8::1", 8080),
        ("http://[::ffff:127.0.0.1]/", "::ffff:127.0.0.1", None),
    ]:
        out = normalize_target_url(raw)
        parts = urlsplit(out)
        assert parts.hostname == expected_host
        assert parts.port == expected_port
