import json
import logging
import os
import signal
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis as _redis

from protocol.messages import (
    PROTOCOL_VERSION,
    PROTOCOL_VERSION_V2,
    ProtocolError,
    SearchRequestedMessage,
    decode_search_request,
    new_message_id,
)
from crawler.search.plan_builder import (
    ERROR_NO_CANDIDATES,
    ERROR_NO_EXECUTABLE_PLAN,
    ERROR_UNSAFE_TARGET,
    PlanBuilder,
    PlanBuildResult,
)
from crawler.search.plan_cache import (
    DEFAULT_PLAN_CACHE_TTL_SECONDS,
    PlanCacheReadResult,
    PlanCacheWriteResult,
    SearchPlanCache,
    build_plan_cache_key,
)
from crawler.search.search_plan import SearchPlan
from crawler.site.analyzer import SiteAnalyzer
from crawler.site.models import SearchCandidate, SiteAnalysisResult
from plugins import search as plugin_search

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("search_worker")


def _load_site_config(site_key: str) -> dict | None:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "config", "site.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            sites = json.load(f)
        return sites.get(site_key)
    except Exception as e:
        log.error("Failed to load site config for %s: %s", site_key, e)
        return None


def _load_plan_cache_ttl() -> int:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "config", "system.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        value = data.get("search_plan_cache_ttl_seconds", DEFAULT_PLAN_CACHE_TTL_SECONDS)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            log.warning("Invalid search_plan_cache_ttl_seconds, using default")
            return DEFAULT_PLAN_CACHE_TTL_SECONDS
        return value
    except Exception:
        log.warning("Failed to load plan cache TTL, using default")
        return DEFAULT_PLAN_CACHE_TTL_SECONDS


@dataclass(frozen=True)
class V2PlanGenerationResult:
    """Internal result of v2 SearchPlan generation."""

    task_id: str
    message_id: str
    plan: SearchPlan | None
    error_code: str | None

    @property
    def success(self) -> bool:
        return self.plan is not None and self.error_code is None


class AnalyzerProtocol(Protocol):
    def analyze(self, target_url: str) -> SiteAnalysisResult:
        ...


class PlanBuilderProtocol(Protocol):
    def build(
        self,
        *,
        target_url: str,
        candidates: Sequence[SearchCandidate],
    ) -> PlanBuildResult:
        ...


class PlanCacheProtocol(Protocol):
    def get(self, *, target_url: str) -> PlanCacheReadResult:
        ...

    def put(self, *, target_url: str, plan: SearchPlan) -> PlanCacheWriteResult:
        ...


def decode_v2_search_request(raw: str | bytes) -> SearchRequestedMessage:
    """Strictly decode a v2 SearchRequestedMessage."""
    decoded = decode_search_request(raw)
    if not isinstance(decoded, SearchRequestedMessage):
        raise ProtocolError("INVALID_TYPE", "v2 search type must be 'search_requested'")
    return decoded


def _generate_v2_plan(
    message: SearchRequestedMessage,
    *,
    analyzer: AnalyzerProtocol,
    plan_builder: PlanBuilderProtocol,
    plan_cache: PlanCacheProtocol,
) -> V2PlanGenerationResult:
    try:
        build_plan_cache_key(message.target_url)
    except ValueError:
        return V2PlanGenerationResult(
            message.task_id,
            message.message_id,
            None,
            ERROR_UNSAFE_TARGET,
        )

    read_result = plan_cache.get(target_url=message.target_url)
    if read_result.hit and read_result.plan is not None:
        return V2PlanGenerationResult(
            message.task_id,
            message.message_id,
            read_result.plan,
            None,
        )

    try:
        analysis = analyzer.analyze(message.target_url)
    except Exception:
        return V2PlanGenerationResult(
            message.task_id,
            message.message_id,
            None,
            "analysis_failed",
        )

    candidates = getattr(analysis, "candidates", ()) or ()
    if not candidates:
        return V2PlanGenerationResult(
            message.task_id,
            message.message_id,
            None,
            ERROR_NO_CANDIDATES,
        )

    build_result = plan_builder.build(
        target_url=message.target_url,
        candidates=candidates,
    )
    if build_result.plan is None or not build_result.success:
        error_code = build_result.error_code or ERROR_NO_EXECUTABLE_PLAN
        return V2PlanGenerationResult(
            message.task_id,
            message.message_id,
            None,
            error_code,
        )

    plan = build_result.plan
    plan_cache.put(target_url=message.target_url, plan=plan)
    return V2PlanGenerationResult(
        message.task_id,
        message.message_id,
        plan,
        None,
    )


def handle_v2_search_message(
    raw: str | bytes,
    *,
    analyzer: AnalyzerProtocol,
    plan_builder: PlanBuilderProtocol,
    plan_cache: PlanCacheProtocol,
) -> V2PlanGenerationResult:
    """Decode and process one v2 SearchRequestedMessage."""
    try:
        message = decode_v2_search_request(raw)
    except ProtocolError:
        return V2PlanGenerationResult("", "", None, "invalid_message")
    return _generate_v2_plan(
        message,
        analyzer=analyzer,
        plan_builder=plan_builder,
        plan_cache=plan_cache,
    )


def handle_search_message(
    raw: str | bytes,
    *,
    analyzer: AnalyzerProtocol,
    plan_builder: PlanBuilderProtocol,
    plan_cache: PlanCacheProtocol,
) -> V2PlanGenerationResult | None:
    """Return a v2 plan result or None when the message is v1."""
    decoded = decode_search_request(raw)
    if not isinstance(decoded, SearchRequestedMessage):
        return None
    return _generate_v2_plan(
        decoded,
        analyzer=analyzer,
        plan_builder=plan_builder,
        plan_cache=plan_cache,
    )


def run_worker(redis_addr: str = "localhost:6379"):
    host = redis_addr.split(":")[0]
    port = int(redis_addr.split(":")[1]) if ":" in redis_addr else 6379
    r = _redis.Redis(host=host, port=port, decode_responses=True)
    analyzer = SiteAnalyzer()
    plan_builder = PlanBuilder()
    plan_cache = SearchPlanCache(r, ttl_seconds=_load_plan_cache_ttl())

    running = True

    def shutdown(sig, frame):
        nonlocal running
        log.info("Received signal, shutting down...")
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    log.info("Search Worker started: consuming crawler:search -> producing crawler:url")
    while running:
        try:
            result = r.brpop("crawler:search", timeout=3)
            if result is None:
                continue

            _, data = result
            raw = json.loads(data)

            protocol_version = raw.get("protocol_version")
            if protocol_version not in (PROTOCOL_VERSION, PROTOCOL_VERSION_V2):
                log.error("[task=%s] unsupported protocol_version=%s", raw.get("task_id", ""), protocol_version)
                continue
            if protocol_version == PROTOCOL_VERSION_V2:
                v2_result = handle_v2_search_message(
                    data,
                    analyzer=analyzer,
                    plan_builder=plan_builder,
                    plan_cache=plan_cache,
                )
                if v2_result.plan is not None:
                    log.info("[task=%s] v2 SearchPlan ready: plan_id=%s", v2_result.task_id, v2_result.plan.plan_id)
                else:
                    log.error("[task=%s] v2 plan generation failed: code=%s", v2_result.task_id, v2_result.error_code)
                continue

            task_id = raw.get("task_id", "")
            message_id = raw.get("message_id", "")
            timestamp = raw.get("timestamp", "")
            site_key = raw.get("site", "")
            keyword = raw.get("keyword", "")
            level = raw.get("level", 1)
            max_pages = raw.get("max_pages", 0)
            if not isinstance(max_pages, int) or max_pages < 1:
                log.warning("[task=%s] invalid max_pages=%s, using default 1", task_id, max_pages)
                max_pages = 1

            log.info("[task=%s] Search: site=%s keyword=%s level=%d max_pages=%d",
                     task_id, site_key, keyword, level, max_pages)

            site_cfg = _load_site_config(site_key)
            if site_cfg is None:
                log.error("[task=%s] Site config not found: site=%s keyword=%s", task_id, site_key, keyword)
                continue

            try:
                articles = plugin_search(site_cfg, keyword, max_pages)
            except Exception as e:
                log.error("[task=%s] Search failed: site=%s keyword=%s error=%s", task_id, site_key, keyword, e)
                try:
                    err_msg = json.dumps({
                        "protocol_version": "1.0",
                        "task_id": task_id,
                        "message_id": new_message_id(),
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "type": "error",
                        "stage": "search",
                        "site": site_key,
                        "keyword": keyword,
                        "level": level,
                        "url": "",
                        "error_code": "SEARCH_FAILED",
                        "error": str(e)[:500],
                        "retryable": True,
                    }, ensure_ascii=False)
                    r.lpush("crawler:error", err_msg)
                except Exception:
                    log.error("[task=%s] Failed to push search error", task_id)
                continue
            log.info("[task=%s] Found %d articles for keyword=%s", task_id, len(articles), keyword)

            article_count = 0
            for article in articles:
                url = article.get("url", "")
                title = article.get("title", "")
                if not url:
                    continue
                payload = json.dumps({
                    "task_id": task_id,
                    "url": url,
                    "site": site_key,
                    "keyword": keyword,
                    "level": level,
                    "title": title,
                    "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                }, ensure_ascii=False)
                r.lpush("crawler:url", payload)
                article_count += 1
                log.info("[task=%s] -> crawler:url: %s [%s]", task_id, url[:80], title[:50] if title else "no title")
            # Send SearchDoneMessage after all URLs are enqueued
            sd_msg = {
                "protocol_version": "1.0",
                "task_id": task_id,
                "message_id": new_message_id(),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "type": "search_done",
                "site": site_key,
                "keyword": keyword,
                "url_count": article_count,
                "level": level,
            }
            r.lpush("crawler:event", json.dumps(sd_msg, ensure_ascii=False))
            log.info("[task=%s] SearchDone: %d URLs pushed", task_id, article_count)


            log.info("[task=%s] Search complete: %d URLs enqueued", task_id, len(articles))

        except Exception as e:
            log.error("Search worker error: %s", e)
            time.sleep(2)

    log.info("Search Worker stopped.")


if __name__ == "__main__":
    run_worker()

