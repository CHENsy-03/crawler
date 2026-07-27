import json
import logging
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis as _redis

from protocol.messages import new_message_id, SearchMessage
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

    log.info("Search Worker started: consuming crawler:search -> producing crawler:url")
    while running:
        try:
            result = r.brpop("crawler:search", timeout=3)
            if result is None:
                continue

            _, data = result
            raw = json.loads(data)

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

