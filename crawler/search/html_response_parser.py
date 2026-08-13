"""Pure HTML response parser shared by HTML adapter and transition executor."""

from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from crawler.search.execution_models import SearchResultItem
from crawler.search.search_plan import SearchPlan
from crawler.site.normalizer import SiteNormalizationError, normalize_target_url
from crawler.site.search_probe import SearchProbeResponse


class HTMLParseError(ValueError):
    """Structured HTML selector or result structure failure."""


class HTMLResultURLError(ValueError):
    """Raised when a result URL cannot be safely normalized."""


@dataclass(frozen=True)
class HTMLPageParseOutcome:
    items: tuple[SearchResultItem, ...]
    result_item_count: int


def parse_html_response(response: SearchProbeResponse, plan: SearchPlan) -> HTMLPageParseOutcome:
    soup = BeautifulSoup(response.body.decode("utf-8", errors="ignore"), "html.parser")
    try:
        containers = soup.select(plan.selectors.result_item)
    except Exception as exc:
        raise HTMLParseError(str(exc)) from exc
    if not containers:
        return HTMLPageParseOutcome((), 0)

    items: list[SearchResultItem] = []
    for container in containers:
        links = container.select(plan.selectors.url)
        titles = container.select(plan.selectors.title)
        if len(links) != 1 or len(titles) != 1:
            raise HTMLParseError("result item selector structure changed")
        href = links[0].get("href", "")
        title = titles[0].get_text(" ", strip=True)
        if not href or not title:
            raise HTMLParseError("result item is missing title or url")
        try:
            normalized = normalize_target_url(urljoin(response.final_url, href))
        except (SiteNormalizationError, ValueError) as exc:
            raise HTMLResultURLError("result URL is invalid") from exc
        snippet = ""
        body = ""
        if plan.selectors.snippet:
            node = container.select_one(plan.selectors.snippet)
            snippet = node.get_text(" ", strip=True) if node else ""
        if plan.selectors.body:
            node = container.select_one(plan.selectors.body)
            body = node.get_text(" ", strip=True) if node else ""
        items.append(SearchResultItem(title=title, url=normalized, snippet=snippet, body=body))
    return HTMLPageParseOutcome(tuple(items), len(containers))