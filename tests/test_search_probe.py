"""Offline tests for controlled search probe safety foundation."""

import json
import re

import pytest

from crawler.site.forms import parse_forms
from crawler.site.models import CandidateRequestShape, DiscoveryLimits, SearchCandidate
from crawler.site.search_probe import (
    PinnedProbeFetcher,
    ProbeRequestBuildResult,
    RawTransportResponse,
    SearchProbePolicy,
    SearchProbeRequest,
    SearchProbeResponse,
    SearchProbeRejection,
    build_probe_request,
    probe_eligibility_rejection,
    _read_limited,
)
from crawler.site.signatures import detect_cms_signatures

POLICY = SearchProbePolicy()
TARGET = "https://example.gov.cn/"


def _shape(**overrides):
    data = {
        "method": "GET",
        "endpoint": "https://example.gov.cn/search",
        "keyword_location": "query",
        "keyword_param": "q",
        "fixed_query_params": (("siteCode", "abc"),),
        "form_fields": (),
        "json_object_template": (),
        "content_type": "",
        "evidence_source": "form",
        "approved_origins": (TARGET, "https://example.gov.cn/search"),
    }
    data.update(overrides)
    return CandidateRequestShape(**data)


def _html_response(url="https://example.gov.cn/search?q=x", status=200):
    return RawTransportResponse(
        status,
        (("Content-Type", "text/html; charset=utf-8"),),
        b"<html><body>ok</body></html>",
        url,
        0,
    )


def _json_response(url="https://example.gov.cn/api?q=x", status=200):
    return RawTransportResponse(
        status,
        (("Content-Type", "application/json"),),
        b'{"items": []}',
        url,
        0,
    )


class FakeTransport:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def request(self, request, *, resolved_ip, timeout_seconds, max_bytes):
        self.calls.append((resolved_ip, timeout_seconds, request.url, request.body, dict(request.headers)))
        if not self.responses:
            raise AssertionError("fake transport has no response")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class LoopTransport(FakeTransport):
    def request(self, request, *, resolved_ip, timeout_seconds, max_bytes):
        self.calls.append((resolved_ip, timeout_seconds, request.url, request.body, dict(request.headers)))
        return RawTransportResponse(302, (("Location", "/loop"),), b"", request.url, 0)


class FakeClock:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    def __call__(self):
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        return value


class FakeChunkResponse:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def read(self, amt=8192, decode_content=True):
        if not self.chunks:
            return b""
        return self.chunks.pop(0)


def _build_request(shape=None, keyword="低空经济"):
    return build_probe_request(shape or _shape(), keyword, POLICY)


def test_policy_defaults_match_contract():
    p = SearchProbePolicy()
    assert p.max_candidates == 3
    assert p.max_keywords_per_candidate == 2
    assert p.max_requests == 6
    assert p.max_redirects == 3
    assert p.max_decompressed_bytes == 2 * 1024 * 1024
    assert p.total_timeout_seconds == 10
    assert p.concurrency == 1
    assert p.retries == 0
    assert p.allowed_ports == (80, 443)


def test_policy_rejects_looser_budget():
    for kwargs in [
        {"max_candidates": 4},
        {"max_keywords_per_candidate": 3},
        {"max_requests": 7},
        {"max_redirects": 4},
        {"max_decompressed_bytes": 2 * 1024 * 1024 + 1},
        {"total_timeout_seconds": 11},
        {"concurrency": 2},
        {"retries": 1},
        {"allowed_ports": (443,)},
    ]:
        with pytest.raises(ValueError):
            SearchProbePolicy(**kwargs)


def test_get_form_request_construction():
    result = _build_request()
    assert result.rejection is None
    assert result.request is not None
    assert result.request.method == "GET"
    assert result.request.url.startswith("https://example.gov.cn/search?")
    assert "siteCode=abc" in result.request.url
    assert result.request.body is None


def test_post_form_request_construction():
    shape = _shape(
        method="POST",
        keyword_location="form",
        fixed_query_params=(),
        form_fields=(("siteCode", "abc"),),
        content_type="application/x-www-form-urlencoded",
    )
    result = _build_request(shape)
    assert result.request is not None
    body = result.request.body.decode("utf-8")
    assert body.startswith("siteCode=abc&q=")
    assert result.request.url == "https://example.gov.cn/search"


def test_unicode_keyword_encoded_once():
    result = _build_request(keyword="低空经济")
    assert result.request is not None
    assert result.request.url.count("%E4%BD%8E%E7%A9%BA%E7%BB%8F%E6%B5%8E") == 1


def test_fixed_params_order_is_deterministic():
    first = _build_request(keyword="a").request
    second = _build_request(keyword="a").request
    assert first is not None and second is not None
    assert first.url == second.url


def test_json_get_shape_manual():
    shape = _shape(
        endpoint="https://api.example.gov.cn/search",
        keyword_location="query",
        keyword_param="kw",
        content_type="application/json",
        approved_origins=("https://api.example.gov.cn/",),
    )
    result = _build_request(shape)
    assert result.request is not None
    assert result.request.body is None
    assert ("Accept", "application/json, application/*+json") in result.request.headers


def test_json_post_object_shape_manual():
    shape = _shape(
        method="POST",
        endpoint="https://api.example.gov.cn/search",
        keyword_location="json",
        keyword_param=None,
        keyword_path=("query", "kw"),
        json_object_template=((("siteId", "1"), "x"),),
        content_type="application/json",
        approved_origins=("https://api.example.gov.cn/",),
    )
    result = _build_request(shape)
    assert result.request is not None
    body = json.loads(result.request.body.decode("utf-8"))
    assert body["query"]["kw"] == "低空经济"
    assert ("Content-Type", "application/json") in result.request.headers


def test_json_missing_keyword_path_rejected():
    shape = _shape(keyword_location="json", keyword_path=None, content_type="application/json")
    result = _build_request(shape)
    assert result.request is None
    assert result.rejection is not None
    assert result.rejection.code == "missing_keyword_field"


def test_script_src_only_candidate_not_eligible():
    html = '<script src="/so/ss/query/s"></script>'
    candidates = detect_cms_signatures(html, TARGET, DiscoveryLimits())
    assert candidates
    assert all(c.request_shape is None for c in candidates)
    result = build_probe_request(candidates[0].request_shape, "k", POLICY)
    assert result.rejection is not None
    assert result.rejection.code == "not_eligible"


def test_missing_keyword_location_rejected():
    shape = _shape(keyword_location="", keyword_param=None)
    rejection = probe_eligibility_rejection(shape, POLICY)
    assert rejection is not None
    assert rejection.code == "missing_keyword_location"


def test_duplicate_keyword_field_rejected():
    shape = _shape(fixed_query_params=(("q", "fixed"),))
    rejection = probe_eligibility_rejection(shape, POLICY)
    assert rejection is not None
    assert rejection.code == "ambiguous_keyword_field"


@pytest.mark.parametrize(
    "name",
    [
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "session",
        "csrf",
        "xsrf",
        "signature",
        "api_key",
        "client_secret",
    ],
)
def test_sensitive_fields_rejected(name):
    shape = _shape(fixed_query_params=((name, "v"),))
    rejection = probe_eligibility_rejection(shape, POLICY)
    assert rejection is not None
    assert rejection.code == "sensitive_field"


def test_sensitive_name_case_and_separator_variants():
    for name in ["Csrf_Token", "API-KEY", "SESSIONID", "x-csrf-token"]:
        shape = _shape(fixed_query_params=((name, "v"),))
        rejection = probe_eligibility_rejection(shape, POLICY)
        assert rejection is not None, name
        assert rejection.code == "sensitive_field"


def test_multipart_rejected():
    shape = _shape(
        method="POST",
        keyword_location="form",
        content_type="multipart/form-data",
    )
    rejection = probe_eligibility_rejection(shape, POLICY)
    assert rejection is not None
    assert rejection.code == "unsupported_content_type"


def test_sensitive_field_not_removed_before_continue():
    shape = _shape(fixed_query_params=(("q", "x"), ("token", "secret")))
    rejection = probe_eligibility_rejection(shape, POLICY)
    assert rejection is not None
    assert rejection.code == "sensitive_field"


def test_repr_does_not_leak_body_or_keyword():
    result = _build_request(keyword="低空经济")
    assert result.request is not None
    assert "低空经济" not in repr(result.request)
    response = SearchProbeResponse(200, "text/html", b"<html>secret</html>", result.request.url, 0)
    assert "secret" not in repr(response)
    rejection = SearchProbeRejection("x", "secret message")
    assert "secret" not in repr(rejection)


def test_non_http_url_rejected():
    req = SearchProbeRequest("GET", "ftp://example.gov.cn/", (), None, (TARGET,))
    assert PinnedProbeFetcher(FakeTransport()).fetch(req, policy=POLICY, resolver=lambda h: ["8.8.8.8"]).rejection is not None


def test_userinfo_url_rejected():
    req = SearchProbeRequest("GET", "https://user:pass@example.gov.cn/", (), None, (TARGET,))
    assert PinnedProbeFetcher(FakeTransport()).fetch(req, policy=POLICY, resolver=lambda h: ["8.8.8.8"]).rejection is not None


def test_ip_literal_url_rejected():
    req = SearchProbeRequest("GET", "https://127.0.0.1/", (), None, (TARGET,))
    assert PinnedProbeFetcher(FakeTransport()).fetch(req, policy=POLICY, resolver=lambda h: ["8.8.8.8"]).rejection is not None


def test_localhost_url_rejected():
    req = SearchProbeRequest("GET", "https://localhost/", (), None, (TARGET,))
    assert PinnedProbeFetcher(FakeTransport()).fetch(req, policy=POLICY, resolver=lambda h: ["8.8.8.8"]).rejection is not None


def test_non_standard_port_rejected():
    req = SearchProbeRequest("GET", "https://example.gov.cn:8443/", (), None, (TARGET,))
    assert PinnedProbeFetcher(FakeTransport()).fetch(req, policy=POLICY, resolver=lambda h: ["8.8.8.8"]).rejection is not None


def test_private_dns_result_rejected():
    result = _build_request().request
    out = PinnedProbeFetcher(FakeTransport()).fetch(result, policy=POLICY, resolver=lambda h: ["127.0.0.1"])
    assert out.rejection is not None
    assert out.rejection.code == "unsafe_ip"


def test_mixed_public_and_private_dns_result_rejected():
    result = _build_request().request
    out = PinnedProbeFetcher(FakeTransport()).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8", "10.0.0.1"])
    assert out.rejection is not None
    assert out.rejection.code == "unsafe_ip"


def test_dns_failure_rejected():
    result = _build_request().request

    def fail(_host):
        raise RuntimeError("dns boom")

    out = PinnedProbeFetcher(FakeTransport()).fetch(result, policy=POLICY, resolver=fail)
    assert out.rejection is not None
    assert out.rejection.code == "dns_failed"


def test_empty_dns_result_rejected():
    result = _build_request().request
    out = PinnedProbeFetcher(FakeTransport()).fetch(result, policy=POLICY, resolver=lambda h: [])
    assert out.rejection is not None
    assert out.rejection.code == "dns_failed"


def test_https_downgrade_rejected():
    req = SearchProbeRequest("GET", "http://example.gov.cn/search", (), None, ("https://example.gov.cn/",))
    out = PinnedProbeFetcher(FakeTransport()).fetch(req, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.rejection is not None
    assert out.rejection.code == "cross_origin"


def test_cross_approved_origin_rejected():
    result = _build_request().request
    req = SearchProbeRequest("GET", "https://other.example/search", (), None, result.approved_origins)
    out = PinnedProbeFetcher(FakeTransport()).fetch(req, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.rejection is not None
    assert out.rejection.code == "cross_origin"


def test_dns_binding_uses_validated_ip():
    transport = FakeTransport([_html_response()])
    result = _build_request().request
    out = PinnedProbeFetcher(transport).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.response is not None
    assert transport.calls[0][0] == "8.8.8.8"


def test_relative_redirect_accepted():
    transport = FakeTransport([
        RawTransportResponse(302, (("Location", "/next"),), b"", "https://example.gov.cn/search", 0),
        _html_response("https://example.gov.cn/next"),
    ])
    result = _build_request().request
    out = PinnedProbeFetcher(transport).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.response is not None
    assert out.response.hop_count == 1
    assert len(transport.calls) == 2


def test_redirect_expanding_origin_rejected():
    transport = FakeTransport([
        RawTransportResponse(302, (("Location", "https://other.example/next"),), b"", "https://example.gov.cn/search", 0),
    ])
    result = _build_request().request
    out = PinnedProbeFetcher(transport).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.rejection is not None
    assert out.rejection.code == "cross_origin"
    assert len(transport.calls) == 1


def test_redirect_loop_rejected():
    result = _build_request().request
    out = PinnedProbeFetcher(LoopTransport()).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.rejection is not None
    assert out.rejection.code == "too_many_redirects"


def test_more_than_three_redirects_rejected():
    transport = FakeTransport([
        RawTransportResponse(302, (("Location", "/1"),), b"", "https://example.gov.cn/search", 0),
        RawTransportResponse(302, (("Location", "/2"),), b"", "https://example.gov.cn/1", 1),
        RawTransportResponse(302, (("Location", "/3"),), b"", "https://example.gov.cn/2", 2),
        RawTransportResponse(302, (("Location", "/4"),), b"", "https://example.gov.cn/3", 3),
    ])
    result = _build_request().request
    out = PinnedProbeFetcher(transport).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.rejection is not None
    assert out.rejection.code == "too_many_redirects"


def test_total_timeout_covers_redirect_chain():
    transport = FakeTransport([
        RawTransportResponse(302, (("Location", "/next"),), b"", "https://example.gov.cn/search", 0),
        _html_response(),
    ])
    result = _build_request().request
    clock = FakeClock([0.0, 0.0, 0.0, 11.0])
    out = PinnedProbeFetcher(transport).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8"], clock=clock)
    assert out.rejection is not None
    assert out.rejection.code == "timeout"
    assert len(transport.calls) == 1


def test_no_cookie_or_auth_headers_in_request():
    result = _build_request()
    assert result.request is not None
    headers = dict(result.request.headers)
    assert "Cookie" not in headers
    assert "Authorization" not in headers
    assert "Proxy-Authorization" not in headers


def test_set_cookie_not_forwarded_on_redirect():
    transport = FakeTransport([
        RawTransportResponse(
            302,
            (("Location", "/next"), ("Set-Cookie", "session=secret")),
            b"",
            "https://example.gov.cn/search",
            0,
        ),
        _html_response("https://example.gov.cn/next"),
    ])
    result = _build_request().request
    out = PinnedProbeFetcher(transport).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.response is not None
    second_headers = transport.calls[1][4]
    assert "Cookie" not in second_headers
    assert "session=secret" not in str(second_headers)


def test_html_content_type_accepted():
    result = _build_request().request
    out = PinnedProbeFetcher(FakeTransport([_html_response()])).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.response is not None


def test_json_content_type_accepted():
    shape = _shape(
        endpoint="https://api.example.gov.cn/search",
        keyword_location="query",
        keyword_param="kw",
        content_type="application/json",
        approved_origins=("https://api.example.gov.cn/",),
    )
    result = _build_request(shape).request
    transport = FakeTransport([RawTransportResponse(200, (("Content-Type", "application/problem+json"),), b"{}", result.url, 0)])
    out = PinnedProbeFetcher(transport).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.response is not None


def test_missing_content_type_rejected():
    result = _build_request().request
    transport = FakeTransport([RawTransportResponse(200, (), b"ok", result.url, 0)])
    out = PinnedProbeFetcher(transport).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.rejection is not None
    assert out.rejection.code == "content_type_rejected"


def test_wrong_content_type_rejected():
    result = _build_request().request
    transport = FakeTransport([RawTransportResponse(200, (("Content-Type", "text/plain"),), b"ok", result.url, 0)])
    out = PinnedProbeFetcher(transport).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.rejection is not None
    assert out.rejection.code == "content_type_rejected"


def test_non_2xx_rejected():
    result = _build_request().request
    transport = FakeTransport([RawTransportResponse(500, (("Content-Type", "text/html"),), b"error", result.url, 0)])
    out = PinnedProbeFetcher(transport).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.rejection is not None
    assert out.rejection.code == "http_error"


def test_exactly_2MiB_accepted_by_reader():
    body = b"a" * (2 * 1024 * 1024)
    assert _read_limited(FakeChunkResponse([body]), 2 * 1024 * 1024) == body


def test_over_2MiB_rejected_by_reader():
    with pytest.raises(Exception):
        _read_limited(FakeChunkResponse([b"a" * (2 * 1024 * 1024), b"b"]), 2 * 1024 * 1024)


def test_transport_failure_does_not_retry():
    result = _build_request().request
    transport = FakeTransport([RuntimeError("boom")])
    out = PinnedProbeFetcher(transport).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.rejection is not None
    assert out.rejection.code == "request_failed"
    assert len(transport.calls) == 1


def test_challenge_page_rejected():
    result = _build_request().request
    transport = FakeTransport([
        RawTransportResponse(200, (("Content-Type", "text/html"),), b"<html>captcha required</html>", result.url, 0)
    ])
    out = PinnedProbeFetcher(transport).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.rejection is not None
    assert out.rejection.code == "challenge_page"


def test_error_rejection_does_not_leak_sensitive_values():
    result = _build_request(keyword="低空经济").request
    transport = FakeTransport([RuntimeError("token=SECRET body=低空经济")])
    out = PinnedProbeFetcher(transport).fetch(result, policy=POLICY, resolver=lambda h: ["8.8.8.8"])
    assert out.rejection is not None
    assert "SECRET" not in out.rejection.message
    assert "低空经济" not in out.rejection.message


def test_forms_build_get_request_shape():
    html = '<form action="/search" method="get"><input name="q"><input type="hidden" name="siteCode" value="abc"></form>'
    candidates, _ = parse_forms(html, TARGET, DiscoveryLimits())
    assert candidates
    assert candidates[0].request_shape is not None
    assert candidates[0].request_shape.keyword_location == "query"
    assert ("siteCode", "abc") in candidates[0].request_shape.fixed_query_params


def test_forms_build_post_request_shape():
    html = '<form action="/search" method="post"><input name="keyword"><input type="hidden" name="websiteid" value="web1"></form>'
    candidates, _ = parse_forms(html, TARGET, DiscoveryLimits())
    assert candidates
    assert candidates[0].request_shape is not None
    assert candidates[0].request_shape.keyword_location == "form"
    assert candidates[0].request_shape.content_type == "application/x-www-form-urlencoded"
    assert ("websiteid", "web1") in candidates[0].request_shape.form_fields
