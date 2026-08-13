"""Controlled, safe search probe request construction and HTTP retrieval."""

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import HTTPError
from urllib3.poolmanager import PoolManager
from urllib3.util.connection import create_connection

from crawler.site.models import CandidateRequestShape, SearchCandidate
from crawler.site.normalizer import (
    SiteNormalizationError,
    normalize_target_url,
    same_origin,
)
from crawler.site.security import classify_ip, is_ip_literal, resolve_host
from crawler.site.selector_evidence import (
    extract_html_selector_evidence,
    extract_json_selector_evidence,
    SelectorEvidence,
)

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_SENSITIVE_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "session",
    "csrf",
    "xsrf",
    "signature",
    "apikey",
)
_CHALLENGE_MARKERS = (
    "captcha",
    "验证码",
    "waf",
    "access denied",
    "security verification",
)


class ProbeResponseTooLarge(ValueError):
    """Raised when a decompressed response exceeds the probe byte limit."""


@dataclass(frozen=True)
class SearchProbePolicy:
    """Immutable probe safety and request budget policy."""

    max_candidates: int = 3
    max_keywords_per_candidate: int = 2
    max_requests: int = 6
    max_redirects: int = 3
    max_decompressed_bytes: int = 2 * 1024 * 1024
    total_timeout_seconds: float = 10.0
    concurrency: int = 1
    retries: int = 0
    allowed_ports: tuple[int, ...] = (80, 443)
    max_field_name_length: int = 128
    max_field_value_length: int = 1024

    def __post_init__(self) -> None:
        for name, value in {
            "max_candidates": self.max_candidates,
            "max_keywords_per_candidate": self.max_keywords_per_candidate,
            "max_requests": self.max_requests,
            "max_redirects": self.max_redirects,
            "max_decompressed_bytes": self.max_decompressed_bytes,
        }.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if isinstance(self.total_timeout_seconds, bool) or not isinstance(
            self.total_timeout_seconds, (int, float)
        ):
            raise ValueError("total_timeout_seconds must be a positive number")
        if self.total_timeout_seconds <= 0:
            raise ValueError("total_timeout_seconds must be positive")
        if self.max_candidates > 3:
            raise ValueError("max_candidates cannot exceed 3")
        if self.max_keywords_per_candidate > 2:
            raise ValueError("max_keywords_per_candidate cannot exceed 2")
        if self.max_requests > 6:
            raise ValueError("max_requests cannot exceed 6")
        if self.max_redirects > 3:
            raise ValueError("max_redirects cannot exceed 3")
        if self.max_decompressed_bytes > 2 * 1024 * 1024:
            raise ValueError("max_decompressed_bytes cannot exceed 2 MiB")
        if self.total_timeout_seconds > 10.0:
            raise ValueError("total_timeout_seconds cannot exceed 10 seconds")
        if self.concurrency != 1:
            raise ValueError("probe concurrency must be 1")
        if self.retries != 0:
            raise ValueError("probe retries must be 0")
        if tuple(self.allowed_ports) != (80, 443):
            raise ValueError("allowed_ports must be exactly (80, 443)")


@dataclass(frozen=True)
class SearchProbeRejection:
    """Structured, safe rejection for one probe step."""

    code: str
    message: str

    def __repr__(self) -> str:
        return f"SearchProbeRejection(code={self.code!r})"


@dataclass(frozen=True)
class SearchProbeRequest:
    """One concrete probe HTTP request."""

    method: str
    url: str
    headers: tuple[tuple[str, str], ...]
    body: bytes | None
    approved_origins: tuple[str, ...]

    def __repr__(self) -> str:
        host = urlsplit(self.url).hostname or ""
        return f"SearchProbeRequest(method={self.method!r}, host={host!r})"


@dataclass(frozen=True)
class RawTransportResponse:
    """Low-level transport response without content-type processing."""

    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    final_url: str
    hop_count: int


@dataclass(frozen=True)
class SearchProbeResponse:
    """Accepted probe response kept only for in-memory structure analysis."""

    status: int
    content_type: str
    body: bytes
    final_url: str
    hop_count: int

    def __repr__(self) -> str:
        return (
            f"SearchProbeResponse(status={self.status}, "
            f"content_type={self.content_type!r}, bytes={len(self.body)})"
        )


@dataclass(frozen=True)
class ProbeRequestBuildResult:
    request: SearchProbeRequest | None
    rejection: SearchProbeRejection | None




@dataclass(frozen=True)
class SearchProbeResult:
    """Formal probe outcome with selector evidence or a safe rejection."""

    candidate_key: tuple[str, ...]
    selector_evidence: SelectorEvidence | None
    status: str
    rejection: SearchProbeRejection | None = None

    def __repr__(self) -> str:
        return f"SearchProbeResult(status={self.status!r})"

@dataclass(frozen=True)
class ProbeOutcome:
    response: SearchProbeResponse | None
    rejection: SearchProbeRejection | None


class ProbeTransport(Protocol):
    def request(
        self,
        request: SearchProbeRequest,
        *,
        resolved_ip: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> RawTransportResponse:
        ...


class SearchProbeFetcher(Protocol):
    def fetch(
        self,
        request: SearchProbeRequest,
        *,
        policy: SearchProbePolicy,
        resolver=None,
        clock=None,
    ) -> ProbeOutcome:
        ...


def _sensitive_name(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", name.lower())
    return any(part in normalized for part in _SENSITIVE_PARTS)


def _reject(code: str, message: str) -> ProbeOutcome:
    return ProbeOutcome(None, SearchProbeRejection(code, message))


def _build_url(endpoint: str, query_pairs: list[tuple[str, str]]) -> str:
    parts = urlsplit(endpoint)
    existing = parse_qsl(parts.query, keep_blank_values=True)
    query = urlencode(existing + query_pairs, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def _json_template_to_dict(leaves: tuple[tuple[tuple[str, ...], Any], ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for path, value in leaves:
        node = result
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = value
    return result


def _apply_keyword_to_json(shape: CandidateRequestShape, keyword: str) -> dict[str, Any]:
    if not shape.keyword_path:
        raise ValueError("json keyword_path is required")
    body = _json_template_to_dict(shape.json_object_template)
    node = body
    for part in shape.keyword_path[:-1]:
        node = node.setdefault(part, {})
    node[shape.keyword_path[-1]] = keyword
    return body


def probe_eligibility_rejection(
    shape: CandidateRequestShape,
    policy: SearchProbePolicy,
) -> SearchProbeRejection | None:
    if shape.method not in ("GET", "POST"):
        return SearchProbeRejection("unsupported_method", "probe method must be GET or POST")
    try:
        normalized = normalize_target_url(shape.endpoint)
    except SiteNormalizationError:
        return SearchProbeRejection("invalid_endpoint", "probe endpoint is not a safe URL")
    parts = urlsplit(normalized)
    if parts.username is not None or parts.password is not None:
        return SearchProbeRejection("unsafe_endpoint", "probe endpoint contains userinfo")
    if is_ip_literal(parts.hostname or ""):
        return SearchProbeRejection("unsafe_endpoint", "probe endpoint uses an IP literal")
    if parts.port not in (None, 80, 443):
        return SearchProbeRejection("unsafe_endpoint", "probe endpoint uses a non-standard port")
    if not shape.approved_origins:
        return SearchProbeRejection("missing_origin", "probe shape has no approved origins")

    if shape.keyword_location not in ("query", "form", "json"):
        return SearchProbeRejection("missing_keyword_location", "probe keyword location is missing")
    if shape.keyword_location in ("query", "form"):
        if not shape.keyword_param or shape.keyword_path:
            return SearchProbeRejection(
                "missing_keyword_field", "probe keyword_param is required for query/form"
            )
    else:
        if not shape.keyword_path or shape.keyword_param:
            return SearchProbeRejection(
                "missing_keyword_field", "probe keyword_path is required for json"
            )

    if shape.keyword_location == "form" and shape.content_type != "application/x-www-form-urlencoded":
        return SearchProbeRejection("unsupported_content_type", "probe form content type is invalid")
    if shape.keyword_location == "json" and shape.content_type != "application/json":
        return SearchProbeRejection("unsupported_content_type", "probe json content type is invalid")

    names = [name for name, _ in shape.fixed_query_params]
    names += [name for name, _ in shape.form_fields]
    for name, value in [*shape.fixed_query_params, *shape.form_fields]:
        if _sensitive_name(name):
            return SearchProbeRejection("sensitive_field", "probe shape contains a sensitive field")
        if not isinstance(name, str) or len(name) > policy.max_field_name_length:
            return SearchProbeRejection("invalid_field", "probe field name is invalid")
        if not isinstance(value, str) or len(value) > policy.max_field_value_length:
            return SearchProbeRejection("invalid_field", "probe field value is invalid")
    if shape.keyword_param and shape.keyword_param in names:
        return SearchProbeRejection(
            "ambiguous_keyword_field", "probe keyword_param conflicts with fixed params"
        )
    for path, value in shape.json_object_template:
        if any(_sensitive_name(part) for part in path):
            return SearchProbeRejection("sensitive_field", "probe json shape contains a sensitive field")
        if not isinstance(value, (str, int, float, bool)) or (
            isinstance(value, str) and len(value) > policy.max_field_value_length
        ):
            return SearchProbeRejection("invalid_field", "probe json value is invalid")
    return None


def build_probe_request(
    shape: CandidateRequestShape | None,
    keyword: str,
    policy: SearchProbePolicy,
) -> ProbeRequestBuildResult:
    if not isinstance(shape, CandidateRequestShape):
        return ProbeRequestBuildResult(
            None,
            SearchProbeRejection("not_eligible", "candidate has no probe request shape"),
        )
    rejection = probe_eligibility_rejection(shape, policy)
    if rejection is not None:
        return ProbeRequestBuildResult(None, rejection)

    method = shape.method
    body: bytes | None = None
    content_type = shape.content_type or "text/html"
    if shape.keyword_location == "query":
        query_pairs = list(shape.fixed_query_params)
        query_pairs.append((shape.keyword_param or "", keyword))
        url = _build_url(shape.endpoint, query_pairs)
    elif shape.keyword_location == "form":
        url = _build_url(shape.endpoint, list(shape.fixed_query_params))
        form_pairs = list(shape.form_fields)
        form_pairs.append((shape.keyword_param or "", keyword))
        body = urlencode(form_pairs, doseq=True).encode("utf-8")
    else:
        url = _build_url(shape.endpoint, list(shape.fixed_query_params))
        body = json.dumps(
            _apply_keyword_to_json(shape, keyword),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        content_type = "application/json"

    headers: list[tuple[str, str]] = [("User-Agent", "crawler-platform-probe/1.0")]
    if content_type.startswith("application/json") or content_type == "application/json":
        headers.append(("Accept", "application/json, application/*+json"))
    else:
        headers.append(("Accept", "text/html, application/xhtml+xml"))
    if body is not None:
        headers.append(("Content-Type", content_type))

    return ProbeRequestBuildResult(
        SearchProbeRequest(
            method=method,
            url=url,
            headers=tuple(headers),
            body=body,
            approved_origins=shape.approved_origins,
        ),
        None,
    )


def _parse_content_type(raw: str) -> str:
    return raw.split(";", 1)[0].strip().lower()


def _content_type_matches(expected: str, actual: str) -> bool:
    if expected.startswith("application/json"):
        return actual == "application/json" or (
            actual.startswith("application/") and actual.endswith("+json")
        )
    return actual in ("text/html", "application/xhtml+xml")


def _looks_like_challenge(content_type: str, body: bytes) -> bool:
    if not content_type.startswith("text/html"):
        return False
    text = body[:8192].decode("utf-8", errors="ignore").lower()
    return any(marker in text for marker in _CHALLENGE_MARKERS)


def _validate_probe_url(url: str, approved_origins: tuple[str, ...]) -> SearchProbeRejection | None:
    try:
        normalized = normalize_target_url(url)
    except SiteNormalizationError:
        return SearchProbeRejection("invalid_url", "probe URL is invalid")
    parts = urlsplit(normalized)
    if parts.scheme not in ("http", "https"):
        return SearchProbeRejection("unsafe_url", "probe URL scheme is unsafe")
    if parts.username is not None or parts.password is not None:
        return SearchProbeRejection("unsafe_url", "probe URL contains userinfo")
    if not parts.hostname:
        return SearchProbeRejection("unsafe_url", "probe URL has no host")
    if is_ip_literal(parts.hostname):
        return SearchProbeRejection("unsafe_url", "probe URL uses an IP literal")
    if parts.hostname == "localhost" or parts.hostname.endswith(".localhost"):
        return SearchProbeRejection("unsafe_url", "probe URL uses a local hostname")
    if parts.port not in (None, 80, 443):
        return SearchProbeRejection("unsafe_url", "probe URL uses a non-standard port")
    if not any(same_origin(normalized, origin) for origin in approved_origins):
        return SearchProbeRejection("cross_origin", "probe URL is outside approved origins")
    return None


class _PinnedMixin:
    def __init__(self, *args: Any, resolved_ip: str | None = None, **kwargs: Any) -> None:
        self._resolved_ip = resolved_ip
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        target = self._resolved_ip or self._dns_host
        sock = create_connection(
            (target, self.port),
            self.timeout,
            source_address=self.source_address,
            socket_options=self.socket_options,
        )
        return sock


class PinnedHTTPConnection(_PinnedMixin, HTTPConnection):
    pass


class PinnedHTTPSConnection(_PinnedMixin, HTTPSConnection):
    pass


class _PinnedPoolMixin:
    def __init__(self, *args: Any, resolved_ip: str | None = None, **kwargs: Any) -> None:
        self._resolved_ip = resolved_ip
        super().__init__(*args, **kwargs)
        self.conn_kw["resolved_ip"] = resolved_ip


class PinnedHTTPConnectionPool(_PinnedPoolMixin, HTTPConnectionPool):
    ConnectionCls = PinnedHTTPConnection


class PinnedHTTPSConnectionPool(_PinnedPoolMixin, HTTPSConnectionPool):
    ConnectionCls = PinnedHTTPSConnection


class PinnedPoolManager(PoolManager):
    pool_classes_by_scheme = {
        "http": PinnedHTTPConnectionPool,
        "https": PinnedHTTPSConnectionPool,
    }

    def __init__(self, resolved_ip: str, *args: Any, **kwargs: Any) -> None:
        self._resolved_ip = resolved_ip
        super().__init__(*args, **kwargs)

    def _new_pool(self, scheme: str, host: str, port: int, request_context=None):
        pool_cls = self.pool_classes_by_scheme[scheme]
        return pool_cls(host, port, resolved_ip=self._resolved_ip, **request_context)


def _read_limited(response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(amt=8192, decode_content=True)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ProbeResponseTooLarge("probe response exceeded byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


class PinnedPoolTransport:
    """Probe transport that connects only to a pre-validated IP."""

    def request(
        self,
        request: SearchProbeRequest,
        *,
        resolved_ip: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> RawTransportResponse:
        pool = PinnedPoolManager(
            resolved_ip,
            retries=False,
            timeout=timeout_seconds,
        )
        response = None
        try:
            response = pool.urlopen(
                request.method,
                request.url,
                body=request.body,
                headers=dict(request.headers),
                redirect=False,
                preload_content=False,
                decode_content=True,
            )
            body = _read_limited(response, max_bytes)
        except HTTPError as exc:
            raise ProbeRequestTransportError(str(exc)) from exc
        finally:
            if response is not None:
                response.close()
        return RawTransportResponse(
            status=response.status,
            headers=tuple(response.headers.items()),
            body=body,
            final_url=response.geturl(),
            hop_count=0,
        )


class ProbeRequestTransportError(RuntimeError):
    pass


class PinnedProbeFetcher:
    """High-level safe probe fetch with DNS binding, redirects and limits."""

    def __init__(self, transport: ProbeTransport | None = None) -> None:
        self._transport = transport or PinnedPoolTransport()

    def fetch(
        self,
        request: SearchProbeRequest,
        *,
        policy: SearchProbePolicy,
        resolver=None,
        clock=None,
    ) -> ProbeOutcome:
        clock_fn = clock or time.monotonic
        start = clock_fn()
        deadline = start + policy.total_timeout_seconds
        current_url = request.url
        hops = 0

        while True:
            if clock_fn() > deadline:
                return _reject("timeout", "probe request exceeded total time budget")
            if hops > policy.max_redirects:
                return _reject("too_many_redirects", "probe redirect limit exceeded")

            url_rejection = _validate_probe_url(current_url, request.approved_origins)
            if url_rejection is not None:
                return ProbeOutcome(None, url_rejection)

            host = urlsplit(current_url).hostname or ""
            try:
                ips = list(resolve_host(host, resolver))
            except Exception:
                return _reject("dns_failed", "probe hostname could not be resolved safely")
            if not ips:
                return _reject("dns_failed", "probe hostname resolved to no addresses")
            for ip in ips:
                safe, _ = classify_ip(ip)
                if not safe:
                    return _reject("unsafe_ip", "probe target resolved to a blocked address")

            chosen_ip = ips[0]
            remaining = max(0.0, deadline - clock_fn())
            hop_request = SearchProbeRequest(
                method=request.method,
                url=current_url,
                headers=request.headers,
                body=request.body,
                approved_origins=request.approved_origins,
            )
            try:
                raw = self._transport.request(
                    hop_request,
                    resolved_ip=chosen_ip,
                    timeout_seconds=remaining,
                    max_bytes=policy.max_decompressed_bytes,
                )
            except ProbeResponseTooLarge:
                return _reject("response_too_large", "probe response exceeded byte limit")
            except Exception:
                return _reject("request_failed", "probe request failed")

            if raw.status in REDIRECT_STATUSES:
                location = dict(raw.headers).get("Location", "")
                if not location:
                    return _reject("redirect_missing_location", "probe redirect has no Location")
                hops += 1
                try:
                    current_url = normalize_target_url(urljoin(current_url, location))
                except SiteNormalizationError:
                    return _reject("invalid_redirect", "probe redirect target is invalid")
                continue

            if raw.status < 200 or raw.status >= 300:
                return _reject("http_error", "probe response status is not 2xx")

            content_type = _parse_content_type(dict(raw.headers).get("Content-Type", ""))
            expected = next(
                (value for key, value in request.headers if key.lower() == "accept"),
                "text/html",
            )
            if not content_type or not _content_type_matches(expected, content_type):
                return _reject("content_type_rejected", "probe response content type is rejected")
            if _looks_like_challenge(content_type, raw.body):
                return _reject("challenge_page", "probe response looks like a challenge page")

            return ProbeOutcome(
                SearchProbeResponse(
                    status=raw.status,
                    content_type=content_type,
                    body=raw.body,
                    final_url=raw.final_url,
                    hop_count=hops,
                ),
                None,
            )

def _candidate_key(candidate: SearchCandidate) -> tuple[str, ...]:
    return (
        candidate.method,
        normalize_target_url(candidate.endpoint),
        candidate.keyword_param,
        tuple(sorted(candidate.fixed_params)),
    )


def probe_search_candidate(
    candidate: SearchCandidate,
    keywords: tuple[str, ...],
    *,
    fetcher: SearchProbeFetcher,
    policy: SearchProbePolicy,
) -> SearchProbeResult:
    """Probe one candidate and return the first complete selector evidence."""
    key = _candidate_key(candidate)
    if candidate.request_shape is None:
        return SearchProbeResult(
            key,
            None,
            "not_eligible",
            SearchProbeRejection("not_eligible", "candidate has no probe request shape"),
        )

    for keyword in keywords[: policy.max_keywords_per_candidate]:
        built = build_probe_request(candidate.request_shape, keyword, policy)
        if built.rejection is not None or built.request is None:
            return SearchProbeResult(key, None, "rejected", built.rejection)
        outcome = fetcher.fetch(built.request, policy=policy)
        if outcome.rejection is not None or outcome.response is None:
            return SearchProbeResult(key, None, "rejected", outcome.rejection)

        response = outcome.response
        if response.content_type.startswith("text/html") or response.content_type == "application/xhtml+xml":
            extraction = extract_html_selector_evidence(
                response.body.decode("utf-8", errors="ignore"),
                final_origin=response.final_url,
                candidate_key=key,
                evidence_source=candidate.request_shape.evidence_source,
            )
        else:
            extraction = extract_json_selector_evidence(
                response.body,
                final_origin=response.final_url,
                candidate_key=key,
                evidence_source=candidate.request_shape.evidence_source,
            )

        if extraction.code == "success" and extraction.evidence is not None:
            return SearchProbeResult(key, extraction.evidence, "success", None)
        if extraction.code == "ambiguous":
            return SearchProbeResult(
                key,
                None,
                "ambiguous",
                SearchProbeRejection("ambiguous_evidence", "selector evidence is ambiguous"),
            )

    return SearchProbeResult(
        key,
        None,
        "no_evidence",
        SearchProbeRejection("no_evidence", "no complete selector evidence found"),
    )
