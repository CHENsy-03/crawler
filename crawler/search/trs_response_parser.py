"""TRS JSON response parser reusing the existing legacy TRS mapping."""

from dataclasses import dataclass
from urllib.parse import urljoin

from parser.api_parser import parse_trs_doc

from crawler.search.execution_models import SearchResultItem
from crawler.search.json_utils import load_strict_json
from crawler.site.normalizer import SiteNormalizationError, normalize_target_url
from crawler.site.search_probe import SearchProbeResponse


class TRSJSONError(ValueError):
    """Invalid or unsafe JSON payload."""


class TRSResultURLError(ValueError):
    """Result URL cannot be safely normalized."""


class TRSParseError(ValueError):
    """TRS response structure drifted from the frozen contract."""


@dataclass(frozen=True)
class TRSPageParseOutcome:
    items: tuple[SearchResultItem, ...]
    result_doc_count: int


def parse_trs_response(response: SearchProbeResponse, keyword: str) -> TRSPageParseOutcome:
    try:
        data = load_strict_json(response.body)
    except Exception as exc:
        raise TRSJSONError("TRS response is not strict JSON") from exc
    if not isinstance(data, dict):
        raise TRSParseError("TRS response root must be an object")
    if "resultDocs" not in data:
        raise TRSParseError("TRS response is missing resultDocs")
    docs = data["resultDocs"]
    if not isinstance(docs, list):
        raise TRSParseError("TRS resultDocs must be a list")
    if not docs:
        return TRSPageParseOutcome((), 0)

    items: list[SearchResultItem] = []
    for doc in docs:
        if not isinstance(doc, dict):
            raise TRSParseError("TRS resultDocs element must be an object")
        parsed = parse_trs_doc(doc, keyword)
        if parsed is None:
            raise TRSParseError("TRS document is missing title or url")
        try:
            normalized_url = normalize_target_url(urljoin(response.final_url, parsed.get("url", "")))
        except (SiteNormalizationError, ValueError) as exc:
            raise TRSResultURLError("TRS result URL is invalid") from exc
        items.append(
            SearchResultItem(
                title=parsed.get("title", ""),
                url=normalized_url,
                snippet=parsed.get("summary", ""),
                body=parsed.get("content", ""),
                published_at=parsed.get("publish_date", ""),
            )
        )
    return TRSPageParseOutcome(tuple(items), len(docs))
