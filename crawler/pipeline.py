import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from httpx.fetch import fetch, reset_all_sessions
from parser.html_parser import extract_title, extract_date, extract_content
from extractor.scorer import filter_by_score
from dedup.url_hash import UrlHashCache
from storage.manager import StorageManager
from crawler.search.result import normalize_search_result
from crawler.search.planner import QueryPlanner
from search.keyword_expand import expand_keywords
from search.result_merge import search_hit_rate, content_hit_rate
from utils import RequestContext
from plugins import search as search_with_plugin
from crawler.detail_scheduler import need_fetch_detail, _fetch_one_detail

log = logging.getLogger('crawler.pipeline')


def process_url(url, site_cfg, keywords=()):
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


def run_pipeline(site_cfg, keywords, output_dir, max_pages=0, with_detail=False):
    ctx = RequestContext(site_cfg.get('name', ''))
    reset_all_sessions()
    planner = QueryPlanner()
    all_articles = []
    for kw in keywords:
        plan = planner.plan(kw)
        for level, q in plan:
            stype = site_cfg.get('search', {}).get('type', '').upper()
            log.info(ctx.fmt('[L%d] [%s] %s'), level, stype, q)
            with ctx.timed('search'):
                articles = search_with_plugin(site_cfg, q, max_pages)
            articles = [normalize_search_result(a) for a in articles]
            for a in articles:
                a['matched_keyword'] = q
            all_articles.extend(articles)
            planner.record_level(level, len(articles), q)
            if planner.is_enough(len(all_articles)):
                log.info(ctx.fmt('  enough: %d >= %d, stop'), len(all_articles), planner.stats['min_results'])
                break
        for a in all_articles:
            a.setdefault('site', site_cfg.get('name', ''))
            a.setdefault('province', site_cfg.get('province', site_cfg.get('name', '').replace('财政局','').replace('财政厅','')))

    if all_articles is None:
        log.warning('Search failed')
    elif len(all_articles) == 0:
        log.warning('No matching results after filtering')
    else:
        log.info(ctx.fmt('Collected %d articles before scoring'), len(all_articles))
    expanded = expand_keywords(keywords)
    with ctx.timed('dedup'):
        dedup = UrlHashCache()
        all_articles = dedup.dedup_list(all_articles)

    search_hit = search_hit_rate(all_articles, expanded)
    content_hit = content_hit_rate(all_articles, expanded)
    log.info(ctx.fmt('  search_hit: %d/%d (%.1f%%) | content_hit: %d/%d (%.1f%%)'),
             search_hit['search_hit'], search_hit['found'], search_hit['search_hit_rate'],
             content_hit['content_hit'], content_hit['found'], content_hit['content_hit_rate'])
    filtered = [a for a in all_articles if a.get('content_hit', True)]
    if len(filtered) < len(all_articles):
        log.info(ctx.fmt('  content_hit filter: %d -> %d articles'), len(all_articles), len(filtered))
    all_articles = filtered
    for a in all_articles[:10]:
        log.info(ctx.fmt('  SEARCH: %s | %s'), a.get('title','')[:70], a.get('url','')[:60])

    with ctx.timed('scoring'):
        scored = filter_by_score(all_articles, keywords, site_cfg=site_cfg)
    if with_detail and scored:
        workers = site_cfg.get('_system', {}).get('worker', 3)
        with ctx.timed('detail'):
            ctx.metrics.requests['total'] += 1
            to_fetch = [a for a in scored if need_fetch_detail(a)]
        skip = len(scored) - len(to_fetch)
        ctx.metrics.articles['detail_skipped'] = skip
        ctx.metrics.articles['detail_fetched'] = len(to_fetch)
        if skip > 0:
            log.info('Detail fetch: %d skip (content OK), %d to fetch', skip, len(to_fetch))
            if to_fetch:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    future_map = {executor.submit(_fetch_one_detail, a.get('url', ''), site_cfg): a for a in to_fetch}
                    for future in as_completed(future_map):
                        a = future_map[future]
                        try:
                            body = future.result(timeout=30)
                            if body:
                                a['content'] = body
                                a['summary'] = body[:300]
                        except Exception as e:
                            log.warning('Detail fetch failed %s: %s', a.get('url', '')[:50], e)

    ctx.metrics.articles['found'] = len(all_articles)
    ctx.metrics.articles['scored'] = len(scored)
    store = StorageManager(output_dir, site_cfg.get('name', 'result'))
    saved_count = store.save(scored)
    store.close()
    ctx.metrics.articles['saved'] = len(scored)
    log.info(ctx.fmt('Saved: DuckDB (%d)'), saved_count)
    log.info(ctx.summary())
    return scored
