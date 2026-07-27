import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from httpx.fetch import fetch, reset_all_sessions
from parser.html_parser import extract_title, extract_date, extract_content
from extractor.scorer import filter_by_score
from dedup.sqlite_cache import DedupDB
from storage.json_store import save_results
from scheduler.search_scheduler import search_with_plugin
from utils import RequestContext

from crawler.detail_scheduler import need_fetch_detail, _fetch_one_detail

log = logging.getLogger('crawler.orchestrator')


def crawl_url(url, site_cfg, keywords=()):
    resp = fetch(url, site_cfg)
    if not resp:
        return None
    return {
        'title': extract_title(resp.text),
        'url': url,
        'publish_date': extract_date(resp.text),
        'summary': '',
        'content': extract_content(resp.text, site_cfg),
        'source': site_cfg.get('name', '') if site_cfg else '',
        'source_keywords': list(keywords),
    }
