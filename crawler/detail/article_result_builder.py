"""Build ArticleResultV2 from HTMLMessageV2 and detail extraction."""

import hashlib
import time

from protocol.messages import (
    ARTICLE_RESULT_STATUS_EXTRACT_FAILED,
    EXTRACTION_METHOD_NONE,
    HTMLMessageV2,
    ArticleResultV2,
    new_message_id,
)

from crawler.detail.extraction_v2 import DetailExtractionResult
from crawler.detail.relevance_v2 import RelevanceResult

from parser.multi_strategy import clean_text, normalize_date


def build_summary(snippet: str, content: str) -> tuple[str, bool]:
    snippet_text = clean_text(snippet or "")
    if snippet_text:
        return snippet_text[:500], True
    return (content or "")[:500], False


def build_article_result_v2(
    html_msg: HTMLMessageV2,
    detail: DetailExtractionResult,
    relevance: RelevanceResult,
    *,
    summary: str,
    summary_from_snippet: bool,
    message_id: str | None = None,
    timestamp: str | None = None,
) -> ArticleResultV2:
    content = detail.content or ""
    if content:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        status = relevance.status
        evidence = relevance.evidence
        score = relevance.score
        extraction_method = detail.extraction_method
    else:
        content_hash = ""
        status = ARTICLE_RESULT_STATUS_EXTRACT_FAILED
        evidence = ()
        score = 0
        extraction_method = EXTRACTION_METHOD_NONE

    publish_date = detail.publish_date or normalize_date(html_msg.published_at)

    return ArticleResultV2(
        protocol_version=html_msg.protocol_version,
        task_id=html_msg.task_id,
        message_id=message_id or new_message_id(),
        timestamp=timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        hit_id=html_msg.hit_id,
        plan_id=html_msg.plan_id,
        original_query=html_msg.original_query,
        query_term=html_msg.query_term,
        requested_url=html_msg.requested_url,
        final_url=html_msg.final_url,
        canonical_url=detail.canonical_url or "",
        title=detail.title or html_msg.title,
        publish_date=publish_date,
        source=html_msg.source,
        summary=summary or "",
        content=content,
        content_hash=content_hash,
        score=score,
        matched_evidence=evidence,
        status=status,
        extraction_method=extraction_method,
    )