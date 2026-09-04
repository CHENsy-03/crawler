"""Pure v2 detail extraction from an HTMLMessageV2 payload."""

from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from parser.ai_parser import parse_with_ai
from parser.html_parser import get_global_content_selectors, get_site_rules
from parser.multi_strategy import normalize_date
from crawler.site.normalizer import SiteNormalizationError, normalize_target_url


@dataclass(frozen=True)
class DetailExtractionResult:
    title: str
    title_source: str
    publish_date: str
    canonical_url: str
    content: str
    extraction_method: str


_NOISE_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "form", "iframe", "aside"}
_BLOCK_TAGS = {"div", "article", "section", "main", "td", "li"}


def _clean_text(value) -> str:
    return " ".join(unescape(value or "").split())


def _remove_noise(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(_NOISE_TAGS):
        tag.decompose()


def _rule_source(site_cfg: dict | None) -> str:
    extract = (site_cfg or {}).get("extract", {}) or {}
    if extract.get("title_selector") or extract.get("content_selector"):
        return "site_selector"
    if extract.get("mode"):
        return "cms_rule"
    return ""


def _extract_title(soup: BeautifulSoup, site_cfg: dict | None) -> tuple[str, str]:
    rule_source = _rule_source(site_cfg)
    rules = get_site_rules(site_cfg) if site_cfg else None
    if rules:
        for selector in rules.get("title", []):
            node = soup.select_one(selector)
            if node is not None:
                text = _clean_text(node.get_text(" ", strip=True))
                if text:
                    return text, rule_source
    node = soup.find("h1")
    if node is not None:
        text = _clean_text(node.get_text(" ", strip=True))
        if text:
            return text, "h1"
    node = soup.find("meta", attrs={"property": "og:title"})
    if node is not None and node.get("content"):
        return _clean_text(node.get("content")), "og_title"
    node = soup.find("title")
    if node is not None:
        return _clean_text(node.get_text(" ", strip=True)), "html_title"
    return "", "empty"


def _extract_date(soup: BeautifulSoup, site_cfg: dict | None) -> str:
    node = soup.find("meta", attrs={"property": "article:published_time"})
    if node is not None and node.get("content"):
        normalized = normalize_date(node.get("content"))
        if normalized:
            return normalized
    node = soup.find("time")
    if node is not None:
        candidate = node.get("datetime") or node.get_text(" ", strip=True)
        normalized = normalize_date(candidate)
        if normalized:
            return normalized
    rules = get_site_rules(site_cfg) if site_cfg else None
    for selector in (rules or {}).get("date", []):
        node = soup.select_one(selector)
        if node is not None:
            normalized = normalize_date(node.get_text(" ", strip=True))
            if normalized:
                return normalized
    return ""


def _extract_canonical(soup: BeautifulSoup, final_url: str) -> str:
    for node in soup.find_all("link", attrs={"href": True}):
        rel = node.get("rel", [])
        tokens = rel if isinstance(rel, list) else str(rel or "").split()
        if "canonical" not in {str(token).lower() for token in tokens}:
            continue
        raw = node.get("href", "")
        if not raw:
            continue
        try:
            return normalize_target_url(urljoin(final_url, raw))
        except (SiteNormalizationError, ValueError):
            continue
    return ""


def _content_method(site_cfg: dict | None) -> str:
    extract = (site_cfg or {}).get("extract", {}) or {}
    if extract.get("content_selector") or extract.get("title_selector"):
        return "site_selector"
    if extract.get("mode"):
        return "cms_rule"
    return "fallback"


def _content_from_selectors(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    for selector in selectors:
        for node in soup.select(selector):
            text = _clean_text(node.get_text(" ", strip=True))
            if len(text) >= 80:
                return text
    return None


def _density_v2(soup: BeautifulSoup) -> str | None:
    candidates = []
    for block in soup.find_all(_BLOCK_TAGS):
        text = _clean_text(block.get_text(" ", strip=True))
        if len(text) < 80:
            continue
        links = sum(len(_clean_text(a.get_text(" ", strip=True))) for a in block.find_all("a"))
        if len(text) > 0 and links / len(text) > 0.3:
            continue
        candidates.append((len(text), text))
    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]
    return None


def _fallback_v2(soup: BeautifulSoup) -> str | None:
    paragraphs = []
    for node in soup.find_all("p"):
        text = _clean_text(node.get_text(" ", strip=True))
        if len(text) >= 30:
            paragraphs.append(text)
    if paragraphs:
        return " ".join(paragraphs)
    body = soup.body or soup
    text = _clean_text(body.get_text(" ", strip=True))
    return text or None


def extract_detail_v2(
    html: str,
    *,
    site_cfg: dict | None = None,
    final_url: str = "",
    global_config: dict | None = None,
) -> DetailExtractionResult:
    soup = BeautifulSoup(html or "", "html.parser")
    _remove_noise(soup)
    title, title_source = _extract_title(soup, site_cfg)
    publish_date = _extract_date(soup, site_cfg)
    canonical_url = _extract_canonical(soup, final_url)

    method = _content_method(site_cfg)
    content = None
    if method in ("site_selector", "cms_rule"):
        rules = get_site_rules(site_cfg)
        content = _content_from_selectors(soup, (rules or {}).get("content", []))

    if content is None:
        content = _content_from_selectors(soup, get_global_content_selectors())
        if content is not None:
            method = "fallback"

    ai_enabled = bool((global_config or {}).get("ai_enabled")) or bool((site_cfg or {}).get("extract", {}).get("ai_enabled"))
    if content is None and ai_enabled:
        ai_result = parse_with_ai(html, site_cfg)
        if ai_result and ai_result.get("content"):
            content = _clean_text(ai_result.get("content"))
            method = "ai"

    if content is None:
        content = _density_v2(soup)
        if content is not None:
            method = "density"

    if content is None:
        content = _fallback_v2(soup)
        if content is not None:
            method = "fallback"

    if content is None:
        content = ""
        method = "none"

    return DetailExtractionResult(
        title=title,
        title_source=title_source,
        publish_date=publish_date,
        canonical_url=canonical_url,
        content=content,
        extraction_method=method,
    )