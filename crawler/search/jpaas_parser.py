"""Shared JPAAS response expansion and field mapping."""

from dataclasses import dataclass
from urllib.parse import urljoin

from parser.multi_strategy import clean_text, normalize_date

from crawler.search.execution_models import SearchResultItem
from crawler.search.json_utils import load_strict_json
from crawler.site.normalizer import SiteNormalizationError, normalize_target_url
from crawler.site.search_probe import SearchProbeResponse


class JPAASResponseError(ValueError):
    """Invalid JSON or non-success application code."""


class JPAASParseError(ValueError):
    """JPAAS response structure drifted from the frozen contract."""


class JPAASResultURLError(ValueError):
    """Result URL cannot be safely normalized."""


@dataclass(frozen=True)
class JPAASPageParseOutcome:
    items: tuple[SearchResultItem, ...]
    result_container_count: int


def expand_jpaas_documents(docs):
    expanded = []
    for doc in docs:
        if isinstance(doc, dict) and "mapSearchResult" in doc:
            container = doc.get("mapSearchResult", {})
            items = container.get("items", []) if isinstance(container, dict) else []
            for item in items:
                expanded.append(item.get("data", {}) if isinstance(item, dict) else item)
        else:
            expanded.append(doc)
    return expanded


def raw_jpaas_fields(doc):
    if not isinstance(doc, dict):
        raise JPAASParseError("JPAAS document must be an object")
    title = doc.get("title") or doc.get("title_str") or ""
    url = doc.get("url") or doc.get("zcywlj_617143") or ""
    content = doc.get("content") or doc.get("content_556463") or doc.get("vc_content") or ""
    publish_date = normalize_date(doc.get("date", ""))
    return {
        "title": clean_text(title),
        "url": url,
        "content": content,
        "publish_date": publish_date,
    }


def map_jpaas_legacy_article(doc, keyword, site_name):
    fields = raw_jpaas_fields(doc)
    if not fields["title"]:
        return None
    url = fields["url"]
    if url and url.startswith("http://"):
        url = url.replace("http://", "https://", 1)
    return {
        "title": fields["title"],
        "url": url,
        "content": fields["content"],
        "publish_date": fields["publish_date"],
        "summary": clean_text(fields["content"]),
        "source": site_name,
        "site": site_name,
        "province": site_name.replace("财政局", "").replace("财政厅", ""),
        "source_keywords": [keyword],
    }


def parse_jpaas_response(response: SearchProbeResponse, keyword: str) -> JPAASPageParseOutcome:
    try:
        data = load_strict_json(response.body)
    except Exception as exc:
        raise JPAASResponseError("JPAAS response is not strict JSON") from exc
    if not isinstance(data, dict):
        raise JPAASResponseError("JPAAS response root must be an object")
    if str(data.get("code", "")) != "200":
        raise JPAASResponseError("JPAAS application code is not 200")
    payload = data.get("data")
    if not isinstance(payload, dict):
        raise JPAASParseError("JPAAS data must be an object")
    docs = payload.get("appSearchResultBeanList")
    if not isinstance(docs, list):
        raise JPAASParseError("JPAAS appSearchResultBeanList must be a list")
    if not docs:
        return JPAASPageParseOutcome((), 0)

    for doc in docs:
        if not isinstance(doc, dict):
            raise JPAASParseError("JPAAS document must be an object")
        if "mapSearchResult" in doc:
            container = doc["mapSearchResult"]
            if not isinstance(container, dict):
                raise JPAASParseError("JPAAS mapSearchResult must be an object")
            items = container.get("items")
            if not isinstance(items, list):
                raise JPAASParseError("JPAAS mapSearchResult.items must be a list")

    items = []
    for doc in expand_jpaas_documents(docs):
        fields = raw_jpaas_fields(doc)
        if not fields["title"] or not fields["url"]:
            raise JPAASParseError("JPAAS document is missing title or url")
        try:
            normalized_url = normalize_target_url(urljoin(response.final_url, fields["url"]))
        except (SiteNormalizationError, ValueError) as exc:
            raise JPAASResultURLError("JPAAS result URL is invalid") from exc
        items.append(
            SearchResultItem(
                title=fields["title"],
                url=normalized_url,
                snippet=clean_text(fields["content"]),
                body=fields["content"],
            )
        )
    return JPAASPageParseOutcome(tuple(items), len(docs))