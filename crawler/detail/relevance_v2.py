"""Deterministic detail-level relevance scoring for ArticleResultV2."""

from dataclasses import dataclass

from protocol.messages import MatchedEvidence

from crawler.detail.site_config import load_score_config


@dataclass(frozen=True)
class RelevanceResult:
    score: int
    original_score: int
    evidence: tuple[MatchedEvidence, ...]
    status: str


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _effective_weights(score_config: dict) -> dict:
    config = dict(score_config or {})
    nested = config.get("_global")
    if isinstance(nested, dict) and any(key in nested for key in ("title_weight", "body_weight", "url_weight", "threshold")):
        return dict(nested)
    return config


def _field_weight(field: str, weights: dict) -> int:
    if field == "title":
        return int(weights.get("title_weight", 5))
    if field in ("summary", "content"):
        return int(weights.get("body_weight", 1))
    if field == "url":
        return int(weights.get("url_weight", 0))
    return 0


def score_detail(
    *,
    original_query: str,
    query_term: str,
    title: str,
    summary: str,
    content: str,
    url: str,
    score_config: dict,
    summary_from_snippet: bool,
    title_is_detail: bool = False,
) -> RelevanceResult:
    weights = _effective_weights(score_config)
    threshold = int(weights.get("threshold", 2))
    terms = [(original_query, "original")]
    if _normalize(query_term) != _normalize(original_query):
        terms.append((query_term, "expanded"))

    candidates = [
        ("title", title or ""),
        ("summary", summary or ""),
        ("content", content or ""),
        ("url", url or ""),
    ]

    evidence = []
    score = 0
    original_score = 0
    has_detail_original_evidence = False
    for term, origin in terms:
        normalized_term = _normalize(term)
        for field, value in candidates:
            if field == "summary" and not summary_from_snippet:
                continue
            if normalized_term and normalized_term in _normalize(value):
                weight = _field_weight(field, weights)
                evidence.append(
                    MatchedEvidence(
                        term=term,
                        origin=origin,
                        field=field,
                        weight=weight,
                    )
                )
                score += weight
                if origin == "original":
                    original_score += weight
                    if field == "content":
                        has_detail_original_evidence = True
                    if field == "title" and title_is_detail:
                        has_detail_original_evidence = True

    if has_detail_original_evidence and original_score >= threshold:
        status = "accepted"
    elif evidence:
        status = "review_required"
    else:
        status = "irrelevant"

    return RelevanceResult(
        score=score,
        original_score=original_score,
        evidence=tuple(evidence),
        status=status,
    )


def load_v2_score_config(hostname: str) -> dict:
    return load_score_config(hostname)