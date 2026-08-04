import pytest

from crawler.site.analyzer import SiteAnalyzer
from crawler.site.security import classify_ip, security_check


class FakeResponse:
    def __init__(self, status_code=200, headers=None, text="", too_large=False, bytes_read=0, location=""):
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "text/html"}
        self.text = text
        self.too_large = too_large
        self.bytes_read = bytes_read
        self.location = location


@pytest.mark.parametrize("ip_text", [
    "127.0.0.1", "10.0.0.1", "192.168.1.1", "169.254.169.254",
    "::1", "fe80::1", "224.0.0.1", "0.0.0.0",
])
def test_unsafe_ips(ip_text):
    safe, reason = classify_ip(ip_text)
    assert not safe
    assert reason


def test_public_ip_safe():
    safe, reason = classify_ip("8.8.8.8")
    assert safe
    assert reason == ""


def test_security_check_rejects_mixed_resolver():
    safe, ips, reason = security_check("http://example.com", resolver=lambda h: ["8.8.8.8", "10.0.0.1"])
    assert not safe
    assert "10.0.0.1" in ips
    assert reason


def test_analyzer_blocks_before_fetch():
    calls = []
    def fetcher(url, limits):
        calls.append(url)
        return FakeResponse()
    result = SiteAnalyzer(
        resolver=lambda h: ["10.0.0.1"],
        fetcher=fetcher,
    ).analyze("http://example.com/")
    assert any(d.code == "TARGET_BLOCKED_BY_POLICY" for d in result.diagnostics)
    assert calls == []
