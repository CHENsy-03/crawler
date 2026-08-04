"""Static CMS signature and resource clue extraction."""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from crawler.site.models import DiscoveryLimits, SearchCandidate
from crawler.site.normalizer import SiteNormalizationError, normalize_target_url, same_origin

_TRS_RE = re.compile(r"/so/s|/so/ss/query/s|siteCode|TRS", re.I)
_JPAAS_RE = re.compile(r"jpaas-jsearch|search\.zj\.gov\.cn|websiteid|serviceId", re.I)


def _scope(endpoint: str, base_url: str) -> str:
    return "same_origin" if same_origin(endpoint, base_url) else "requires_scope_validation"


def _make_candidate(method, endpoint, keyword_param, source, priority, base_url, evidence):
    try:
        normalized = normalize_target_url(endpoint)
    except SiteNormalizationError:
        return None
    return SearchCandidate(
        method=method,
        endpoint=normalized,
        keyword_param=keyword_param,
        source=source,
        priority=priority,
        scope=_scope(normalized, base_url),
        evidence=tuple(evidence),
    )


def detect_cms_signatures(html: str, base_url: str, limits: DiscoveryLimits) -> list[SearchCandidate]:
    candidates: list[SearchCandidate] = []
    soup = BeautifulSoup(html, "html.parser")

    if _TRS_RE.search(html):
        candidate = _make_candidate("GET", urljoin(base_url, "/so/ss/query/s"), "q", "trs_signature", 4, base_url, ("trs_signature",))
        if candidate:
            candidates.append(candidate)
    if _JPAAS_RE.search(html):
        jpaas_endpoint = None
        for script in soup.find_all("script", src=True):
            src = script.get("src", "")
            if "jpaas" in src.lower() or "search" in src.lower():
                jpaas_endpoint = urljoin(base_url, src)
                break
        if jpaas_endpoint:
            candidate = _make_candidate("GET", jpaas_endpoint, "q", "jpaas_signature", 4, base_url, ("jpaas_signature:script",))
            if candidate:
                candidates.append(candidate)

    for script in soup.find_all("script", src=True):
        src = script.get("src", "")
        if re.search(r"search|query|so|ss", src, re.I) and len(candidates) < limits.max_candidates:
            endpoint = urljoin(base_url, src)
            candidate = _make_candidate("GET", endpoint, "q", "static_script", 2, base_url, ("static_script",))
            if candidate:
                candidates.append(candidate)

    return candidates
