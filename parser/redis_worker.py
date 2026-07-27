import json
import logging
import os
import sys
import signal
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parser.html_parser import extract_title, extract_date, extract_content
from extractor.scorer import filter_by_score
from dedup.sqlite_cache import DedupDB
from storage.json_store import save_results

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('redis_worker')

try:
    import redis
    REDIS_OK = True
except ImportError:
    REDIS_OK = False


def run_worker(redis_addr='localhost:6379', redis_queue='crawler:html', output_dir='output'):
    if not REDIS_OK:
        log.error('redis-py not installed. Run: pip install redis')
        return

    r = redis.Redis(host=redis_addr.split(':')[0],
                    port=int(redis_addr.split(':')[1]) if ':' in redis_addr else 6379,
                    decode_responses=True)

    running = True

    def shutdown(sig, frame):
        nonlocal running
        log.info('Received signal, shutting down...')
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    log.info('Redis Worker started: queue=%s output=%s', redis_queue, output_dir)

    while running:
        try:
            result = r.brpop(redis_queue, timeout=3)
            if result is None:
                continue

            _, data = result
            payload = json.loads(data)

            url = payload.get('url', '')
            site_name = payload.get('site', '')
            keyword = payload.get('keyword', '')
            level = payload.get('level', 1)

            log.info('[L%d] Fetching: %s (%s)', level, url[:80], site_name)

            html = payload.get('html', '')
            if not html or len(html) < 100:
                log.warning('[L%d] Empty HTML: %s', level, url[:80])
                continue

            parsed_title = extract_title(html) or title
            parsed_date = extract_date(html)
            parsed_content = extract_content(html)

            article = {
                'title': parsed_title,
                'url': url,
                'publish_date': parsed_date,
                'content': parsed_content,
                'summary': parsed_content[:300] if parsed_content else '',
                'source': site_name or 'go-spider',
                'source_keywords': [keyword] if keyword else [],
            }

            articles = [article]
            keywords_tuple = (keyword,) if keyword else ()
            scored = filter_by_score(articles, keywords_tuple, site_cfg=None)

            if scored:
                save_results(scored, output_dir, 'go-spider')
                log.info('[L%d] PARSED: %s (%d chars)', level, parsed_title[:50], len(parsed_content or ''))

        except Exception as e:
            log.error('[L%d] Worker error: %s', level, e)
            time.sleep(1)

    log.info('Worker stopped. queue=%s', redis_queue)


if __name__ == '__main__':
    run_worker()
