"""Static HTML form parsing for unverified search candidates."""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from crawler.site.models import Diagnostic, DiscoveryLimits, SearchCandidate
from crawler.site.normalizer import SiteNormalizationError, normalize_target_url, same_origin

SENSITIVE_RE = re.compile(
    r"(csrf|xsrf|token|session|auth|password|passwd|cookie|signature|secret|nonce|captcha|verify_code)",
    re.I,
)
NON_SEARCH_RE = re.compile(
    r"(login|register|signin|signup|subscribe|comment|upload|payment|pay|reset|password|captcha|登录|注册|订阅|留言|上传|支付|密码|验证码)",
    re.I,
)
KEYWORD_RE = re.compile(
    r"(^|[^a-z])(q|query|keyword|keywords|searchword|search_word|wd|key|searchkey)([^a-z]|$)",
    re.I,
)
ALLOWED_METHODS = {"get", "post"}


def _is_sensitive(name: str) -> bool:
    return bool(SENSITIVE_RE.search(name or ""))


def _attr_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value)
    return str(value)


def _looks_like_non_search(form, text: str) -> bool:
    combined = " ".join(
        [
            _attr_text(form.get("id", "")),
            _attr_text(form.get("name", "")),
            _attr_text(form.get("class", "")),
            _attr_text(form.get("action", "")),
            _attr_text(form.get("title", "")),
            text,
        ]
    )
    return bool(NON_SEARCH_RE.search(combined))


def _public_fixed_params(inputs) -> list[tuple[str, str]]:
    fixed = []
    for tag in inputs:
        name = tag.get("name", "")
        if not name or tag.get("type", "").lower() != "hidden" or _is_sensitive(name):
            continue
        fixed.append((name, tag.get("value", "")))
    return sorted(fixed)


def _scope_for(endpoint: str, base_url: str) -> str:
    try:
        return "same_origin" if same_origin(endpoint, base_url) else "requires_scope_validation"
    except SiteNormalizationError:
        return "requires_scope_validation"


def parse_forms(html: str, base_url: str, limits: DiscoveryLimits) -> tuple[list[SearchCandidate], list[Diagnostic]]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[SearchCandidate] = []
    diagnostics: list[Diagnostic] = []
    count = 0

    for form in soup.find_all("form"):
        if count >= limits.max_forms:
            diagnostics.append(Diagnostic("LIMIT_EXCEEDED", "forms", "max form count reached", severity="warning"))
            break
        count += 1
        inputs = form.find_all(["input", "select", "textarea"])[: limits.max_inputs_per_form]
        form_text = form.get_text(" ", strip=True)

        sensitive = [tag.get("name", "") for tag in inputs if _is_sensitive(tag.get("name", ""))]
        if sensitive:
            if any(re.search(r"password|passwd|captcha|verify_code", name, re.I) for name in sensitive) or re.search(
                r"登录|密码|验证码|login|captcha", form_text, re.I
            ):
                code = "LOGIN_OR_CAPTCHA_REQUIRED"
                message = "form requires login, password, or captcha"
            else:
                code = "SENSITIVE_FORM_REJECTED"
                message = "form contains sensitive fields"
            diagnostics.append(
                Diagnostic(
                    code,
                    "forms",
                    message,
                    details=tuple(sorted(set(sensitive))),
                )
            )
            continue
        if _looks_like_non_search(form, form_text):
            diagnostics.append(
                Diagnostic("LOGIN_OR_CAPTCHA_REQUIRED", "forms", "form looks like login, captcha, or non-search action")
            )
            continue

        keyword_param = ""
        for tag in inputs:
            name = tag.get("name", "")
            if name and KEYWORD_RE.search(name):
                keyword_param = name
                break
        if not keyword_param:
            continue

        raw_method = (form.get("method", "") or "").strip().lower() or "get"
        if raw_method not in ALLOWED_METHODS:
            continue

        action = form.get("action", "") or ""
        endpoint = urljoin(base_url, action) if action else base_url
        try:
            normalized_endpoint = normalize_target_url(endpoint)
        except SiteNormalizationError:
            continue
        scope = _scope_for(normalized_endpoint, base_url)

        fixed = _public_fixed_params(inputs)
        evidence = (f"form method={raw_method} action={action}",)
        if raw_method == "post":
            enctype = (form.get("enctype", "") or "").lower()
            if enctype and enctype != "application/x-www-form-urlencoded":
                diagnostics.append(
                    Diagnostic("SENSITIVE_FORM_REJECTED", "forms", "non-form-urlencoded POST form is not reusable")
                )
                continue
            candidates.append(
                SearchCandidate(
                    method="POST",
                    endpoint=normalized_endpoint,
                    keyword_param=keyword_param,
                    fixed_params=tuple(fixed),
                    request_encoding="application/x-www-form-urlencoded",
                    source="form",
                    priority=3,
                    scope=scope,
                    evidence=evidence,
                )
            )
        else:
            candidates.append(
                SearchCandidate(
                    method="GET",
                    endpoint=normalized_endpoint,
                    keyword_param=keyword_param,
                    fixed_params=tuple(fixed),
                    source="form",
                    priority=4 if fixed else 5,
                    scope=scope,
                    evidence=evidence,
                )
            )

    return candidates, diagnostics
