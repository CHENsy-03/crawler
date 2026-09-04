import json
import os

import pytest

from crawler.security.models import OutboundPolicy
from crawler.security.redirect_policy import (
    RedirectPolicyError,
    plan_redirect_hop,
    plan_redirects,
)
from crawler.security.transport_budget import (
    BudgetError,
    TransportBudget,
    budget_for,
    capped_stage_timeout,
    check_request_body_size,
    check_response_body_size,
    check_response_headers_size,
    remaining_deadline,
    validate_proxy,
)

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "outbound_transport_policy_contract.json")


def _load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_policy(raw):
    return OutboundPolicy(
        allowed_hosts=frozenset(raw["allowed_hosts"]),
        allowed_http=raw["allowed_http"],
        allowed_ports_by_scheme={k: frozenset(v) for k, v in raw["allowed_ports_by_scheme"].items()},
        max_dns_addresses=raw["max_dns_addresses"],
        allow_controlled_subdomains=raw["allow_controlled_subdomains"],
    )


class FakeResolver:
    def __init__(self, addresses_by_host):
        self.addresses_by_host = dict(addresses_by_host)
        self.calls = 0

    def resolve(self, host, timeout_seconds):
        self.calls += 1
        return list(self.addresses_by_host.get(host, []))


def test_budget_cases():
    fixture = _load_fixture()
    executed = set()
    expected = {case["id"] for case in fixture["budget_cases"]}
    for case in fixture["budget_cases"]:
        action = case["action"]
        if action == "profile_value":
            profile = budget_for(case["profile"])
            assert getattr(profile, case["field"]) == case["expected"], case["id"]
        elif action == "unknown_profile":
            with pytest.raises(BudgetError) as exc_info:
                budget_for(case["profile"])
            assert exc_info.value.reason_code == case["expected_reason"], case["id"]
        elif action == "limit":
            kind = case["kind"]
            if kind == "request_body":
                fn = lambda value: check_request_body_size(value)
            elif kind == "response_headers":
                fn = lambda value: check_response_headers_size(value)
            else:
                fn = lambda value: check_response_body_size(case["profile"], value)
            if case["allowed"]:
                fn(case["value"])
            else:
                with pytest.raises(BudgetError) as exc_info:
                    fn(case["value"])
                assert exc_info.value.reason_code == case["expected_reason"], case["id"]
        elif action == "remaining":
            if "expected_reason" in case:
                with pytest.raises(BudgetError) as exc_info:
                    remaining_deadline(case["profile"], case["elapsed_ms"])
                assert exc_info.value.reason_code == case["expected_reason"], case["id"]
            else:
                assert remaining_deadline(case["profile"], case["elapsed_ms"]) == case["expected_remaining"], case["id"]
        elif action == "stage_zero":
            with pytest.raises(BudgetError) as exc_info:
                capped_stage_timeout(case["profile"], case["stage_timeout_ms"], case["elapsed_ms"])
            assert exc_info.value.reason_code == case["expected_reason"], case["id"]
        elif action == "capped_stage":
            assert capped_stage_timeout(case["profile"], case["stage_timeout_ms"], case["elapsed_ms"]) == case["expected"], case["id"]
        elif action == "common":
            budget = TransportBudget()
            for field, expected_value in case["expected"].items():
                assert getattr(budget, field) == expected_value, f'{case["id"]}:{field}'
        elif action == "negative":
            with pytest.raises(BudgetError) as exc_info:
                check_request_body_size(case["value"])
            assert exc_info.value.reason_code == case["expected_reason"], case["id"]
        elif action == "bool":
            with pytest.raises(BudgetError) as exc_info:
                check_request_body_size(case["value"])
            assert exc_info.value.reason_code == case["expected_reason"], case["id"]
        elif action == "remaining_capped_zero":
            with pytest.raises(BudgetError) as exc_info:
                capped_stage_timeout(case["profile"], case["stage_timeout_ms"], case["elapsed_ms"])
            assert exc_info.value.reason_code == case["expected_reason"], case["id"]
        elif action == "remaining_one":
            assert capped_stage_timeout(case["profile"], case["stage_timeout_ms"], case["elapsed_ms"]) == case["expected"], case["id"]
        elif action == "stage_equals_remaining":
            assert capped_stage_timeout(case["profile"], case["stage_timeout_ms"], case["elapsed_ms"]) == case["expected"], case["id"]
        elif action == "bool_remaining":
            with pytest.raises(BudgetError) as exc_info:
                remaining_deadline(case["profile"], case["elapsed_ms"])
            assert exc_info.value.reason_code == case["expected_reason"], case["id"]
        elif action == "negative_remaining":
            with pytest.raises(BudgetError) as exc_info:
                remaining_deadline(case["profile"], case["elapsed_ms"])
            assert exc_info.value.reason_code == case["expected_reason"], case["id"]
        else:
            raise AssertionError(f"unknown budget action {action!r} for {case['id']}")
        executed.add(case["id"])
    assert executed == expected


def test_redirect_cases():
    fixture = _load_fixture()
    executed = set()
    expected = {case["id"] for case in fixture["redirect_cases"]}
    for case in fixture["redirect_cases"]:
        policy = _make_policy(case["policy"])
        resolver = FakeResolver(case["addresses"])
        action = case["action"]
        if action == "multi_hop":
            if case.get("expected_reason"):
                with pytest.raises(RedirectPolicyError) as exc_info:
                    plan_redirects(case["current"], case["locations"], policy, resolver=resolver)
                assert exc_info.value.reason_code == case["expected_reason"], case["id"]
            else:
                plan = plan_redirects(case["current"], case["locations"], policy, resolver=resolver)
                assert plan.final_hop is not None, case["id"]
                assert plan.final_hop.url == case["expected_final_url"], case["id"]
                assert resolver.calls == case["expected_resolver_calls"], case["id"]
                assert len(plan.hops) == len(case["locations"]), case["id"]
                assert len({id(hop.pinned_target) for hop in plan.hops}) == len(plan.hops), case["id"]
        elif action in {"absolute", "relative", "upgrade", "fragment", "scheme_relative_allowed"}:
            hop = plan_redirect_hop(case["current"], case["location"], policy, resolver=resolver, hop_count=case["hop"])
            assert hop.url == case["expected_url"], case["id"]
            assert list(hop.addresses) == case["expected_addresses"], case["id"]
            assert resolver.calls == case["expected_resolver_calls"], case["id"]
            assert hop.decision.allowed is True, case["id"]
            assert hop.pinned_target is not None, case["id"]
        elif action in {"downgrade", "host_denied", "subdomain_denied", "port_denied", "loopback_dns", "private_dns", "mixed_dns", "userinfo", "malformed", "hop_four", "scheme_relative_blocked_host", "scheme_relative_blocked_port", "location_none", "whitespace", "whitespace_multiline", "leading_space", "location_int", "location_bool", "location_list", "location_dict"}:
            with pytest.raises(RedirectPolicyError) as exc_info:
                plan_redirect_hop(case["current"], case["location"], policy, resolver=resolver, hop_count=case["hop"])
            assert exc_info.value.reason_code == case["expected_reason"], case["id"]
            assert resolver.calls == case["expected_resolver_calls"], case["id"]
        elif action == "missing":
            with pytest.raises(RedirectPolicyError) as exc_info:
                plan_redirect_hop(case["current"], case["location"], policy, resolver=resolver, hop_count=case["hop"])
            assert exc_info.value.reason_code == case["expected_reason"], case["id"]
            assert resolver.calls == case["expected_resolver_calls"], case["id"]
        elif action == "hop_three":
            hop = plan_redirect_hop(case["current"], case["location"], policy, resolver=resolver, hop_count=case["hop"])
            assert hop.url == case["expected_url"], case["id"]
            assert list(hop.addresses) == case["expected_addresses"], case["id"]
            assert resolver.calls == case["expected_resolver_calls"], case["id"]
        else:
            raise AssertionError(f"unknown redirect action {action!r} for {case['id']}")
        executed.add(case["id"])
    assert executed == expected


def test_proxy_cases():
    fixture = _load_fixture()
    executed = set()
    expected = {case["id"] for case in fixture["proxy_cases"]}
    for case in fixture["proxy_cases"]:
        if case["allowed"]:
            validate_proxy(case["proxy"])
        else:
            with pytest.raises(BudgetError) as exc_info:
                validate_proxy(case["proxy"])
            assert exc_info.value.reason_code == case["expected_reason"], case["id"]
        executed.add(case["id"])
    assert executed == expected


def test_redirect_bytes_location_rejected():
    fixture = _load_fixture()
    case = next(c for c in fixture["redirect_cases"] if c["id"] == "redirect-001")
    policy = _make_policy(case["policy"])
    for location in (b"", b"https://example.com/"):
        resolver = FakeResolver(case["addresses"])
        with pytest.raises(RedirectPolicyError) as exc_info:
            plan_redirect_hop(case["current"], location, policy, resolver=resolver, hop_count=1)
        assert exc_info.value.reason_code == "redirect_location_invalid", location
        assert resolver.calls == 0


def test_redirect_repeated_call_is_deterministic():
    fixture = _load_fixture()
    case = next(c for c in fixture["redirect_cases"] if c["id"] == "redirect-001")
    policy = _make_policy(case["policy"])
    first = plan_redirect_hop(case["current"], case["location"], policy, resolver=FakeResolver(case["addresses"]), hop_count=1)
    second = plan_redirect_hop(case["current"], case["location"], policy, resolver=FakeResolver(case["addresses"]), hop_count=1)
    assert first.url == second.url
    assert first.addresses == second.addresses
    assert list(first.pinned_target.validated_addresses) == list(second.pinned_target.validated_addresses)
