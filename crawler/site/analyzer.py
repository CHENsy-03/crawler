"""Orchestrate safe entry fetch and unverified SearchCandidate discovery."""

from dataclasses import replace
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from crawler.core.downloader import get_downloader
from crawler.site.forms import parse_forms
from crawler.site.models import Diagnostic, DiscoveryLimits, SearchCandidate, SiteAnalysisResult
from crawler.site.normalizer import (
    SiteNormalizationError,
    normalize_target_url,
    normalized_origin,
    redact_evidence_url,
    redirect_allowed,
    same_origin,
)
from crawler.site.security import SecurityPolicyError, blocked_diagnostic, security_check
from crawler.site.signatures import detect_cms_signatures

_COMMON_PATHS = ("/search", "/s", "/so/s")
_ALLOWED_REDIRECTS = {301, 302, 303, 307, 308}


class SiteAnalyzer:
    def __init__(self, limits=None, resolver=None, fetcher=None, downloader=None):
        self.limits = limits or DiscoveryLimits()
        self.resolver = resolver
        self.fetcher = fetcher
        self.downloader = downloader

    def _fetch(self, url: str):
        if self.fetcher is not None:
            return self.fetcher(url, self.limits)
        dl = self.downloader or get_downloader()
        return dl.fetch_once(url, timeout=self.limits.timeout, max_bytes=self.limits.max_response_bytes)

    def _finish(self, normalized, final, diagnostics, fetch_summary, candidates=()):
        return SiteAnalysisResult(
            normalized_url=normalized,
            final_url=final,
            candidates=tuple(candidates),
            diagnostics=tuple(diagnostics),
            fetch_summary=fetch_summary,
            analyzer_version="0.1.0",
        )

    def analyze(self, target_url: str) -> SiteAnalysisResult:
        diagnostics: list[Diagnostic] = []
        fetch_summary: dict = {}
        try:
            normalized = normalize_target_url(target_url)
        except SiteNormalizationError as exc:
            return self._finish(
                target_url,
                target_url,
                [Diagnostic("INVALID_TARGET_URL", "normalize", str(exc))],
                {},
            )

        try:
            safe, ips, reason = security_check(normalized, self.resolver)
        except SecurityPolicyError as exc:
            return self._finish(normalized, normalized, [Diagnostic("TARGET_BLOCKED_BY_POLICY", "security", str(exc))], {"resolved_ips": []})
        if not safe:
            return self._finish(normalized, normalized, [blocked_diagnostic(normalized, reason)], {"resolved_ips": ips})

        current = normalized
        final = normalized
        response = None
        for hop in range(self.limits.max_redirects + 1):
            try:
                response = self._fetch(current)
            except Exception as exc:
                return self._finish(
                    normalized,
                    final,
                    [Diagnostic("FETCH_FAILED", "fetch", f"entry fetch failed: {exc}", retryable=True)],
                    fetch_summary,
                )
            if response is None:
                return self._finish(
                    normalized,
                    final,
                    [Diagnostic("FETCH_FAILED", "fetch", "entry fetch returned no response", retryable=True)],
                    fetch_summary,
                )
            fetch_summary.update({
                "status_code": response.status_code,
                "content_type": response.headers.get("Content-Type", ""),
                "bytes_read": getattr(response, "bytes_read", 0),
                "redirects": hop,
            })
            if response.status_code in _ALLOWED_REDIRECTS:
                location = response.headers.get("Location") or getattr(response, "location", "")
                if not location:
                    return self._finish(normalized, final, [Diagnostic("REDIRECT_BLOCKED", "redirect", "redirect response missing Location")], fetch_summary)
                next_url = urljoin(current, location)
                try:
                    next_normalized = normalize_target_url(next_url)
                except SiteNormalizationError:
                    return self._finish(normalized, final, [Diagnostic("REDIRECT_BLOCKED", "redirect", "redirect target failed URL normalization")], fetch_summary)
                try:
                    redirect_ok = redirect_allowed(current, next_normalized)
                except SiteNormalizationError:
                    return self._finish(normalized, final, [Diagnostic("REDIRECT_BLOCKED", "redirect", "redirect target has invalid origin")], fetch_summary)
                if not redirect_ok:
                    return self._finish(normalized, final, [Diagnostic("REDIRECT_BLOCKED", "redirect", "redirect target origin or scheme change is not allowed", details=(next_normalized,))], fetch_summary)
                try:
                    next_safe, next_ips, next_reason = security_check(next_normalized, self.resolver)
                except SecurityPolicyError as exc:
                    return self._finish(normalized, final, [Diagnostic("REDIRECT_BLOCKED", "redirect", str(exc))], fetch_summary)
                if not next_safe:
                    return self._finish(normalized, final, [Diagnostic("REDIRECT_BLOCKED", "redirect", f"redirect target blocked: {next_reason}", details=(next_normalized,))], fetch_summary)
                current = next_normalized
                final = next_normalized
                continue
            break
        else:
            return self._finish(normalized, final, [Diagnostic("REDIRECT_BLOCKED", "redirect", "max redirects exceeded")], fetch_summary)

        if getattr(response, "too_large", False):
            return self._finish(normalized, final, [Diagnostic("RESPONSE_TOO_LARGE", "fetch", "response exceeded streaming byte limit")], fetch_summary)
        if response.status_code < 200 or response.status_code >= 300:
            return self._finish(
                normalized,
                final,
                [Diagnostic("FETCH_FAILED", "fetch", f"entry fetch returned HTTP {response.status_code}", retryable=True)],
                fetch_summary,
            )
        content_type = (response.headers.get("Content-Type", "") or "").split(";")[0].strip().lower()
        if content_type not in self.limits.allowed_content_types:
            return self._finish(normalized, final, [Diagnostic("UNSUPPORTED_CONTENT_TYPE", "fetch", f"unsupported content type: {content_type}")], fetch_summary)

        candidates: list[SearchCandidate] = []
        try:
            html = response.text or ""
            candidates, form_diags = parse_forms(html, final, self.limits)
            diagnostics.extend(form_diags)
            signature_html = html[: self.limits.max_script_chars]
            candidates.extend(detect_cms_signatures(signature_html, final, self.limits))
            candidates.extend(self._static_clues(html, final))
        except Exception:
            diagnostics.append(Diagnostic("ANALYSIS_FAILED", "analysis", "static page analysis failed", severity="warning"))
            return self._finish(normalized, final, diagnostics, fetch_summary)

        strong = [c for c in candidates if c.source != "common_path"]
        page_diags = self._page_diagnostics(html, strong)
        diagnostics.extend(page_diags)

        if not strong and not any(d.code in ("UNSUPPORTED_JS_SEARCH", "LOGIN_OR_CAPTCHA_REQUIRED", "SENSITIVE_FORM_REJECTED") for d in diagnostics):
            diagnostics.append(Diagnostic("NO_SEARCH_CANDIDATE", "analysis", "no search candidate found"))

        candidates.extend(self._common_path_candidates(final))
        candidates = self._dedupe_and_sort(candidates)
        candidates = self._apply_limits(candidates)

        return self._finish(normalized, final, diagnostics, fetch_summary, candidates)

    def _static_clues(self, html: str, base_url: str) -> list[SearchCandidate]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[SearchCandidate] = []
        seen = set()
        for tag in soup.find_all(["a", "script", "link"]):
            href = tag.get("href") or tag.get("src") or ""
            if not href or len(seen) >= self.limits.max_links_meta:
                break
            if re_search(href):
                endpoint = urljoin(base_url, href)
                try:
                    normalized_endpoint = normalize_target_url(endpoint)
                except SiteNormalizationError:
                    continue
                key = normalized_endpoint
                if key not in seen:
                    seen.add(key)
                    source = "internal_link" if tag.name == "a" else "static_script"
                    scope = "same_origin" if same_origin(normalized_endpoint, base_url) else "requires_scope_validation"
                    out.append(
                        SearchCandidate(
                            method="GET",
                            endpoint=normalized_endpoint,
                            keyword_param="q",
                            source=source,
                            priority=2,
                            scope=scope,
                            evidence=(f"{source}:{redact_evidence_url(href)[:120]}",),
                        )
                    )
        return out

    def _common_path_candidates(self, base_url: str) -> list[SearchCandidate]:
        out = []
        for path in _COMMON_PATHS[: self.limits.max_common_paths]:
            endpoint = urljoin(base_url, path)
            try:
                normalized_endpoint = normalize_target_url(endpoint)
            except SiteNormalizationError:
                continue
            out.append(
                SearchCandidate(
                    method="GET",
                    endpoint=normalized_endpoint,
                    keyword_param="q",
                    source="common_path",
                    priority=1,
                    scope="same_origin",
                    evidence=("common_path",),
                )
            )
        return out

    def _page_diagnostics(self, html: str, strong_candidates: list[SearchCandidate]) -> list[Diagnostic]:
        diags: list[Diagnostic] = []
        soup = BeautifulSoup(html, "html.parser")
        has_script = bool(soup.find("script"))
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True).lower()
        if any(word in text for word in ("login", "log in", "captcha", "verify code", "登录", "密码", "验证码")):
            diags.append(Diagnostic("LOGIN_OR_CAPTCHA_REQUIRED", "analysis", "entry page requires login or captcha"))
        if not strong_candidates and has_script and "search" not in text and len(html) < 2000:
            diags.append(Diagnostic("UNSUPPORTED_JS_SEARCH", "analysis", "search entry appears to require JavaScript"))
        return diags

    def _apply_limits(self, candidates: list[SearchCandidate]) -> list[SearchCandidate]:
        bounded = []
        total_evidence_chars = 0
        for candidate in candidates:
            if self.limits.max_evidence_items <= 0 or self.limits.max_evidence_chars <= 0:
                bounded.append(replace(candidate, evidence=()))
                continue
            evidence = []
            for item in candidate.evidence:
                if len(evidence) >= self.limits.max_evidence_items:
                    break
                truncated = item[: self.limits.max_evidence_chars]
                if not truncated:
                    continue
                if total_evidence_chars + len(truncated) > self.limits.max_evidence_chars:
                    break
                total_evidence_chars += len(truncated)
                evidence.append(truncated)
            bounded.append(replace(candidate, evidence=tuple(evidence)))
        return bounded[: self.limits.max_candidates]

    @staticmethod
    def _dedupe_and_sort(candidates: list[SearchCandidate]) -> list[SearchCandidate]:
        best: dict[tuple, SearchCandidate] = {}
        merged_evidence: dict[tuple, list[str]] = {}
        seen_evidence: dict[tuple, set[str]] = {}
        for c in candidates:
            key = (
                c.method,
                c.endpoint,
                c.keyword_param,
                tuple(sorted(c.fixed_params)),
            )
            if key not in best or c.priority > best[key].priority:
                best[key] = c
            evidence = merged_evidence.setdefault(key, [])
            seen = seen_evidence.setdefault(key, set())
            for item in c.evidence:
                if item not in seen:
                    seen.add(item)
                    evidence.append(item)
        ordered = []
        for key, candidate in best.items():
            ordered.append(replace(candidate, evidence=tuple(merged_evidence[key])))
        ordered.sort(key=lambda c: (-c.priority, c.method, c.endpoint, c.keyword_param))
        return ordered


def re_search(text: str) -> bool:
    import re
    return bool(re.search(r"search|query|jsearch|so|ss", text, re.I))


def analyze_site(target_url: str, limits=None, resolver=None, fetcher=None, downloader=None) -> SiteAnalysisResult:
    return SiteAnalyzer(limits=limits, resolver=resolver, fetcher=fetcher, downloader=downloader).analyze(target_url)
