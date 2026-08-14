"""Deterministic SearchHit construction for the v2 search pipeline."""

import hashlib
import json

from crawler.search.execution_models import SearchResultItem
from crawler.search.search_plan import SearchHit, SearchPlan


def compute_hit_id(
    *,
    protocol_version: str,
    task_id: str,
    plan_id: str,
    original_query: str,
    query_term: str,
    url: str,
) -> str:
    """Return a deterministic SHA-256 hit_id from stable execution inputs."""
    content = {
        "protocol_version": protocol_version,
        "task_id": task_id,
        "plan_id": plan_id,
        "original_query": original_query,
        "query_term": query_term,
        "url": url,
    }
    canonical = json.dumps(
        content,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_search_hit(
    *,
    task_id: str,
    plan: SearchPlan,
    original_query: str,
    query_term: str,
    item: SearchResultItem,
    discovered_at: str,
) -> SearchHit:
    """Build one logical SearchHit without scoring or keyword evidence."""
    source = item.source.strip() or plan.scope.domain
    return SearchHit(
        hit_id=compute_hit_id(
            protocol_version=plan.protocol_version,
            task_id=task_id,
            plan_id=plan.plan_id,
            original_query=original_query,
            query_term=query_term,
            url=item.url,
        ),
        plan_id=plan.plan_id,
        url=item.url,
        title=item.title,
        snippet=item.snippet or item.body,
        published_at=item.published_at,
        score=0,
        matched_keywords=[],
        source=source,
        discovered_at=discovered_at,
    )
