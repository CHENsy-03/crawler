import pytest

from crawler.site.analyzer import SiteAnalyzer
import socket

from crawler.site.security import SecurityPolicyError, classify_ip, security_check


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


def test_gaierror_converted_to_security_policy_error(monkeypatch):
    def boom(*args, **kwargs):
        raise socket.gaierror("name or service not known")
    monkeypatch.setattr("crawler.site.security.socket.getaddrinfo", boom)
    with pytest.raises(SecurityPolicyError) as exc_info:
        security_check("http://example.com")
    assert str(exc_info.value) == "target hostname could not be resolved"
    assert "name or service not known" not in str(exc_info.value)


def test_timeout_error_converted_to_security_policy_error():
    def resolver(host):
        raise TimeoutError("dns timeout")
    with pytest.raises(SecurityPolicyError) as exc_info:
        security_check("http://example.com", resolver=resolver)
    assert "timeout" not in str(exc_info.value)


def test_os_error_converted_to_security_policy_error():
    def resolver(host):
        raise OSError("connection reset")
    with pytest.raises(SecurityPolicyError) as exc_info:
        security_check("http://example.com", resolver=resolver)
    assert "connection reset" not in str(exc_info.value)


def test_resolver_generic_exception_converted_to_security_policy_error():
    def resolver(host):
        raise RuntimeError("dns boom")
    with pytest.raises(SecurityPolicyError) as exc_info:
        security_check("http://example.com", resolver=resolver)
    assert "boom" not in str(exc_info.value)
    assert str(exc_info.value) == "target hostname could not be resolved"


def test_existing_security_policy_error_not_wrapped():
    original = SecurityPolicyError("already blocked")
    def resolver(host):
        raise original
    with pytest.raises(SecurityPolicyError) as exc_info:
        security_check("http://example.com", resolver=resolver)
    assert exc_info.value is original


def test_keyboard_interrupt_not_swallowed():
    def resolver(host):
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        security_check("http://example.com", resolver=resolver)


def test_security_check_public_resolver_passes():
    safe, ips, reason = security_check("http://example.com", resolver=lambda h: ["8.8.8.8"])
    assert safe
    assert reason == ""


def test_security_check_private_resolver_rejects():
    safe, ips, reason = security_check("http://example.com", resolver=lambda h: ["10.0.0.1"])
    assert not safe
    assert reason


def test_security_check_all_safe_addresses_pass():
    safe, ips, reason = security_check("http://example.com", resolver=lambda h: ["8.8.8.8", "9.9.9.9"])
    assert safe
    assert len(ips) == 2


def test_security_check_public_ipv6_passes():
    safe, ips, reason = security_check("http://[2606:4700:4700::1111]/", resolver=lambda h: ["2606:4700:4700::1111"])
    assert safe
    assert reason == ""


def test_security_check_ipv6_loopback_rejects():
    safe, ips, reason = security_check("http://[::1]/", resolver=lambda h: ["::1"])
    assert not safe
    assert reason


def test_security_check_ipv4_mapped_loopback_rejects():
    safe, ips, reason = security_check("http://[::ffff:127.0.0.1]/", resolver=lambda h: ["::ffff:127.0.0.1"])
    assert not safe
    assert reason
