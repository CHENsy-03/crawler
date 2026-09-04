import ast
import json
import os
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from crawler.security.dns_policy import DNSValidationError, resolve_and_validate
from crawler.security.ip_policy import classify_ip
from crawler.security.models import OutboundPolicy
from crawler.security.outbound_policy import decide
from crawler.security.url_normalizer import URLNormalizationError, normalize_outbound_url

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "outbound_request_security_contract.json")


def _load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _expand_url(case):
    raw = case["raw"]
    if "label_length" in case:
        raw = raw.replace("@label@", "a" * case["label_length"])
    if "host_length" in case:
        raw = raw.replace("@host@", "a" * case["host_length"])
    if "path_length" in case:
        raw = raw.replace("@path@", "a" * case["path_length"])
    return raw


class FakeResolver:
    def __init__(self, addresses, behavior=None):
        self.addresses = list(addresses)
        self.behavior = behavior
        self.calls = 0

    def resolve(self, host, timeout_seconds):
        self.calls += 1
        if self.behavior == "timeout":
            raise TimeoutError("timeout")
        if self.behavior == "error":
            raise RuntimeError("resolver error")
        return list(self.addresses)


def _make_policy(raw_policy):
    return OutboundPolicy(
        allowed_hosts=frozenset(raw_policy["allowed_hosts"]),
        allowed_http=raw_policy["allowed_http"],
        allowed_ports_by_scheme={
            scheme: frozenset(ports)
            for scheme, ports in raw_policy["allowed_ports_by_scheme"].items()
        },
        max_dns_addresses=raw_policy["max_dns_addresses"],
        allow_controlled_subdomains=raw_policy["allow_controlled_subdomains"],
    )


def test_fixture_count_and_unique_ids():
    fixture = _load_fixture()
    total = sum(len(fixture[key]) for key in ("url_cases", "ip_cases", "dns_cases", "policy_cases", "redirect_cases"))
    assert total >= 120
    ids = [case["id"] for group in fixture.values() for case in group]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("case", _load_fixture()["url_cases"], ids=lambda c: c["id"])
def test_url_cases(case):
    raw = _expand_url(case)
    if "expected_reason" in case:
        with pytest.raises(URLNormalizationError) as exc_info:
            normalize_outbound_url(raw)
        assert exc_info.value.reason_code == case["expected_reason"]
        return
    normalized = normalize_outbound_url(raw)
    assert normalized.scheme == case["expected_scheme"]
    assert normalized.host == case["expected_host"]
    assert normalized.port == case["expected_port"]
    assert normalized.explicit_port == case["expected_explicit_port"]
    assert normalized.authority == case["expected_authority"]
    assert normalized.normalized_url == case["expected_normalized_url"]
    assert normalized.is_ip_literal == case["expected_is_ip_literal"]


@pytest.mark.parametrize("case", _load_fixture()["ip_cases"], ids=lambda c: c["id"])
def test_ip_cases(case):
    classification = classify_ip(case["address"])
    assert classification.category == case["expected_category"]
    assert classification.allowed == case["expected_allowed"]


@pytest.mark.parametrize("case", _load_fixture()["dns_cases"], ids=lambda c: c["id"])
def test_dns_cases(case):
    resolver = FakeResolver(case["addresses"], case.get("resolver_behavior"))
    max_addresses = case.get("max_dns_addresses") or 16
    if case["expected_reason"]:
        try:
            result = resolve_and_validate(case["host"], resolver, max_addresses=max_addresses)
        except DNSValidationError as exc:
            assert exc.reason_code == case["expected_reason"]
        else:
            assert result.reason_code == case["expected_reason"]
        return
    result = resolve_and_validate(case["host"], resolver, max_addresses=max_addresses)
    assert result.allowed
    assert list(result.addresses) == case["expected_addresses"]


@pytest.mark.parametrize("case", _load_fixture()["policy_cases"], ids=lambda c: c["id"])
def test_policy_cases(case):
    resolver = FakeResolver(case["addresses"])
    decision = decide(case["raw"], _make_policy(case["policy"]), resolver=resolver)
    assert decision.reason_code == case["expected_reason"]
    assert list(decision.addresses) == case["expected_addresses"]


@pytest.mark.parametrize("case", _load_fixture()["redirect_cases"], ids=lambda c: c["id"])
def test_redirect_cases(case):
    resolver = FakeResolver(case["addresses"])
    decision = decide(case["raw"], _make_policy(case["policy"]), resolver=resolver, previous_raw=case["previous"])
    assert decision.reason_code == case["expected_reason"]
    assert list(decision.addresses) == case["expected_addresses"]


def test_normalized_url_immutable():
    normalized = normalize_outbound_url("https://example.com/")
    with pytest.raises(FrozenInstanceError):
        normalized.host = "changed.example"


def test_policy_input_not_modified():
    policy = _make_policy(
        {
            "allowed_hosts": ["example.com"],
            "allowed_http": False,
            "allowed_ports_by_scheme": {"http": [80], "https": [443]},
            "max_dns_addresses": 16,
            "allow_controlled_subdomains": False,
        }
    )
    before = (set(policy.allowed_hosts), dict(policy.allowed_ports_by_scheme))
    decision = decide("https://example.com/", policy, resolver=FakeResolver(["8.8.8.8"]))
    assert decision.allowed
    after = (set(policy.allowed_hosts), dict(policy.allowed_ports_by_scheme))
    assert before == after


def test_normalization_idempotent():
    first = normalize_outbound_url("HTTPS://Example.COM/a/./b/../c?q=%2b")
    second = normalize_outbound_url(first.normalized_url)
    assert first == second


def test_fake_resolver_called_once():
    resolver = FakeResolver(["8.8.8.8", "1.1.1.1"])
    result = resolve_and_validate("example.com", resolver)
    assert result.allowed
    assert resolver.calls == 1


def test_ip_literal_does_not_call_resolver():
    resolver = FakeResolver(["8.8.8.8"])
    result = resolve_and_validate("8.8.8.8", resolver)
    assert result.allowed
    assert resolver.calls == 0


def test_mixed_dns_rejected():
    resolver = FakeResolver(["8.8.8.8", "10.0.0.1"])
    result = resolve_and_validate("example.com", resolver)
    assert not result.allowed
    assert result.reason_code == "ip_not_allowed"
    assert list(result.addresses) == ["8.8.8.8", "10.0.0.1"]


def test_dns_stable_sort_and_dedupe():
    resolver = FakeResolver(["8.8.8.8", "1.1.1.1", "8.8.8.8"])
    result = resolve_and_validate("example.com", resolver)
    assert list(result.addresses) == ["1.1.1.1", "8.8.8.8"]


def test_security_package_no_http_imports():
    root = Path("crawler/security")
    forbidden = {"requests", "httpx", "aiohttp", "urllib3", "socket"}
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
                assert not (names & forbidden), f"{path} imports {names & forbidden}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    assert top not in forbidden, f"{path} imports {top}"


def test_no_production_module_imports_security_package():
    root = Path("crawler")
    for path in root.rglob("*.py"):
        parts = path.parts
        if "crawler" in parts and "security" in parts:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        assert "from crawler.security" not in source, path
        assert "import crawler.security" not in source, path

def test_policy_pre_dns_denials_do_not_call_resolver():
    denied_policy = _make_policy(
        {
            "allowed_hosts": ["example.com"],
            "allowed_http": False,
            "allowed_ports_by_scheme": {"http": [80], "https": [443]},
            "max_dns_addresses": 16,
            "allow_controlled_subdomains": False,
        }
    )
    http_policy = _make_policy(
        {
            "allowed_hosts": ["example.com"],
            "allowed_http": True,
            "allowed_ports_by_scheme": {"http": [80], "https": [443]},
            "max_dns_addresses": 16,
            "allow_controlled_subdomains": False,
        }
    )
    cases = [
        (denied_policy, "https://sub.example.com/", None, "host_not_allowed"),
        (denied_policy, "http://example.com/", None, "http_not_allowed"),
        (denied_policy, "https://example.com:8080/", None, "port_not_allowed"),
        (http_policy, "http://example.com/b", "https://example.com/a", "https_downgrade"),
        (denied_policy, "https://other.example/b", "https://example.com/a", "redirect_host_not_allowed"),
    ]
    for policy, raw, previous, expected in cases:
        resolver = FakeResolver(["8.8.8.8"])
        decision = decide(raw, policy, resolver=resolver, previous_raw=previous)
        assert decision.reason_code == expected
        assert resolver.calls == 0