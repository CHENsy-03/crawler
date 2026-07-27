import json
import logging
import os
import signal
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis as _redis

from parser.html_parser import extract_title, extract_date, extract_content
from extractor.scorer import score_article

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("parser_worker")


def _load_site_config(site_key: str) -> dict | None:
    """Load a single site config from config/site.json by top-level key."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "config", "site.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            sites = json.load(f)
        return sites.get(site_key)
    except Exception as e:
        log.error("Failed to load site config for %s: %s", site_key, e)
        return None


def _process_message(raw: dict) -> dict | None:
    """Parse a single HTML message, extract content, score, and return a v1 ResultMessage dict.
    
    Returns None if the message cannot be processed (unknown site, empty HTML, etc.).
    """
    task_id = raw.get("task_id", "")
    message_id = raw.get("message_id", "")
    site_key = raw.get("site", "")
    keyword = raw.get("keyword", "")
    level = raw.get("level", 1)
    url = raw.get("url", "")
    title_from_msg = raw.get("title", "")
    html = raw.get("html", "")

    if not url or not html or len(html) < 100:
        log.warning("[task=%s] Skipping: url=%s html_len=%d", task_id, url[:60], len(html))
        return None

    # Load site config for parser mode and scoring
    site_cfg = _load_site_config(site_key)
    if site_cfg is None:
        log.error("[task=%s] Unknown site: %s (url=%s)", task_id, site_key, url[:60])
        return None

    # Extract title, date, and content from raw HTML
    try:
        parsed_title = extract_title(html, site_cfg) or title_from_msg
    except Exception as e:
        log.error("[task=%s] extract_title error: %s (url=%s)", task_id, e, url[:60])
        parsed_title = title_from_msg

    try:
        parsed_date = extract_date(html, site_cfg)
    except Exception as e:
        log.error("[task=%s] extract_date error: %s (url=%s)", task_id, e, url[:60])
        parsed_date = ""

    try:
        parsed_content = extract_content(html, site_cfg)
    except Exception as e:
        log.error("[task=%s] extract_content error: %s (url=%s)", task_id, e, url[:60])
        parsed_content = ""

    # Score: build article dict and pass keywords
    keywords_tuple = (keyword,) if keyword else ()
    try:
        score_result = score_article(
            {"title": parsed_title, "content": parsed_content, "url": url},
            keywords_tuple,
            site_cfg=site_cfg,
        )
    except Exception as e:
        log.error("[task=%s] score_article error: %s (url=%s)", task_id, e, url[:60])
        score_result = {"score": 0, "matched_keywords": []}

    result_msg = {
        "protocol_version": "1.0",
        "task_id": task_id,
        "message_id": uuid.uuid4().hex[:8],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "type": "result",
        "site": site_key,
        "keyword": keyword,
        "level": level,
        "url": url,
        "title": parsed_title,
        "publish_date": parsed_date,
        "content": parsed_content,
        "summary": (parsed_content or "")[:300],
        "score": score_result.get("score", 0),
        "matched_keywords": score_result.get("matched_keywords", []),
    }

    log.info("[task=%s] PARSED -> result: %s (%d chars, score=%d)",
             task_id, parsed_title[:50], len(parsed_content or ""), result_msg["score"])
    return result_msg


def run_worker(redis_addr: str = "localhost:6379"):
    host = redis_addr.split(":")[0]
    port = int(redis_addr.split(":")[1]) if ":" in redis_addr else 6379
    r = _redis.Redis(host=host, port=port, decode_responses=True)

    running = True

    def shutdown(sig, frame):
        nonlocal running
        log.info("Received signal, shutting down...")
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    log.info("Parser Worker started: consuming crawler:html -> producing crawler:result")

    while running:
        try:
            result = r.brpop("crawler:html", timeout=3)
            if result is None:
                continue

            _, data = result
            raw = json.loads(data)

            result_msg = _process_message(raw)
            if result_msg is not None:
                r.lpush("crawler:result", json.dumps(result_msg, ensure_ascii=False))

        except Exception as e:
            log.error("Parser worker loop error: %s", e)
            time.sleep(2)

    log.info("Parser Worker stopped.")


if __name__ == "__main__":
    run_worker()
