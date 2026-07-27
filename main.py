#!/usr/bin/env python3
import sys, os, logging, argparse

base = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, base)

os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
os.environ.setdefault('PYTHONUTF8', '1')
if os.name == 'nt':
    try: os.system('chcp 65001 > nul 2>nul')
    except: pass

from scheduler.dispatcher import crawl_url, run_search
from httpx.fetch import fetch, post_json
from parser.multi_strategy import clean_text, normalize_date
from config.keywords import DEFAULT_KEYWORDS
import json

logging.basicConfig(level=logging.DEBUG if os.environ.get('CRAWLER_ENV','')=='dev' else logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('main')


def load_config(site_key=None):
    config_dir = os.path.join(base, 'config')
    def _load(name):
        with open(os.path.join(config_dir, name), 'r', encoding='utf-8') as f:
            return json.load(f)
    site_data = _load('site.json')
    http_data = _load('http.json')
    score_data = _load('score.json')
    system_data = _load('system.json')
    parser_data = _load('parser.json')
    if site_key:
        site = site_data.get(site_key)
        if not site:
            raise ValueError('Site not found: ' + site_key)
        site['rate_limit'] = http_data.get(site_key, http_data.get('_global', {}))
        site['score'] = score_data.get(site_key, score_data.get('_global', {}))
        global_parser = parser_data.get('_global', {})
        if global_parser:
            site.setdefault('extract', {}).update(global_parser)
        site['_system'] = system_data
        return site
    return {'sites': site_data, 'http': http_data, 'score': score_data, 'parser': parser_data}


def read_url_list(path):
    if not os.path.exists(path):
        log.error('File not found: %s', path)
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return [l.strip() for l in f if l.strip() and not l.startswith('#')]


def parse_args():
    p = argparse.ArgumentParser(description='\u653f\u5e9c\u7f51\u7ad9\u653f\u7b56\u722c\u866b')
    p.add_argument('--site', default='', help='\u7ad9\u70b9\u914d\u7f6e\u540d')
    p.add_argument('--keywords', nargs='+', default=None, help='\u641c\u7d22\u5173\u952e\u8bcd')
    p.add_argument('--urls', metavar='FILE', help='\u4ece\u6587\u4ef6\u8bfb\u53d6URL\u5217\u8868')
    p.add_argument('--output', default='output', help='\u8f93\u51fa\u76ee\u5f55')
    p.add_argument('--with-detail', action='store_true', help='\u6293\u53d6\u6587\u7ae0\u6b63\u6587')
    p.add_argument('--max-pages', type=int, default=0, help='\u6700\u5927\u7ffb\u9875\u6570')
    p.add_argument('--discover', metavar='URL', help='\u81ea\u52a8\u53d1\u73b0\u7ad9\u70b9\u914d\u7f6e')
    p.add_argument('--self-test', action='store_true', help='\u8fd0\u884c\u81ea\u68c0')
    p.add_argument('--serve', type=int, nargs='?', const=8000, default=None, metavar='PORT', help='Start FastAPI server')
    p.add_argument('--no-dedup', action='store_true', help='\u7981\u7528SQLite\u53bb\u91cd')
    return p.parse_args()


def run_self_test():
    log.info('-- Self tests --')
    assert clean_text('<em>\u4f4e\u7a7a</em>&nbsp;\u7ecf\u6d4e') == '\u4f4e\u7a7a \u7ecf\u6d4e'
    assert normalize_date('\u65e5\u671f\uff1a2025\u5e746\u67087\u65e5') == '2025-06-07'
    log.info('  clean_text/normalize_date: OK')
    html = '<div class=\'TRS_Editor\'><p>\u4f4e\u7a7a\u7ecf\u6d4e\u653f\u7b56\u6b63\u6587\u5185\u5bb9\u3002</p></div>'
    content = extract_content(html)
    assert '\u4f4e\u7a7a\u7ecf\u6d4e' in content
    log.info('  Content extraction: OK')
    log.info('All self-tests passed!')
    return True


def discover_site(url):
    import re, json
    from crawler.core.downloader import get_downloader
    from urllib.parse import urljoin, urlparse
    log = logging.getLogger('discover')
    log.info('-- Site discovery: %s --', url)
    dl = get_downloader()
    session = dl.session_for(url)
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    for path in ('/so/s', '/search/s', '/site/s', '/search', '/s'):
        try:
            resp = session.get(url.rstrip('/') + path + '?q=test', timeout=10)
            if resp.status_code == 200 and len(resp.text) > 500:
                log.info('  Found search page: %s', url.rstrip('/') + path)
                sc = re.search('siteCode\\s*[=:]\\s*(\\d+)', resp.text)
                site_code = sc.group(0).split('=')[-1].strip('"').strip("'") if sc else ''
                search_url = urljoin(url, 'so/ss/query/s')
                cfg = {'name': 'Auto-' + urlparse(url).netloc,
                       'domain': urlparse(url).netloc,
                       'base_url': url,
                       'search_page_url': url.rstrip('/') + path,
                       'search_api_url': search_url,
                       'site_code': site_code or 'unknown',
                       'api_type': 'trs_json'}
                log.info('  siteCode=%s', site_code or '?')
                print(); print('-- Generated config (add to sites_config.json) --')
                print(json.dumps(cfg, ensure_ascii=False, indent=2))
                return
        except:
            continue
    log.warning('  No search page found')
def main():
    args = parse_args()
    if args.discover:
        discover_site(args.discover)
        return
    if args.self_test:
        run_self_test()
        return

    if args.serve is not None:
        try:
            import uvicorn
            from api.server import create_app
            app = create_app()
            if app is None:
                log.error('FastAPI not installed. Run: pip install fastapi uvicorn')
                return
            log.info('Starting API server on port %d ...', args.serve)
            uvicorn.run(app, host='0.0.0.0', port=args.serve)
        except ImportError:
            log.error('FastAPI/uvicorn not installed. Run: pip install fastapi uvicorn')
        return

    keywords = tuple(args.keywords) if args.keywords else DEFAULT_KEYWORDS
    if not keywords and not args.urls:
        log.warning('\u8bf7\u6307\u5b9a--keywords\u6216--urls')
        return

    output_dir = os.path.join(base, args.output)
    site_cfg = load_config(args.site) if args.site else None

    if args.urls:
        urls = read_url_list(args.urls)
        if not urls:
            log.warning('No URLs found in: %s', args.urls); return
        log.info('=== URL Fetch Mode ===')
        log.info('Total URLs: %d', len(urls))
        articles = []
        for idx, url in enumerate(urls, 1):
            log.info('  [%d/%d] %s', idx, len(urls), url[:70])
            article = crawl_url(url, site_cfg or load_config('czj_beijing'), keywords)
            if article:
                articles.append(article)
        if not articles:
            log.warning('No articles fetched'); return
        from storage.json_store import save_results
        scored = filter_by_score(articles, keywords) if keywords else articles
        jp, cp = save_results(scored, output_dir, 'urls')
        print('  [OK]', len(scored), 'articles saved ->', jp)
        return

    if not site_cfg:
        log.warning('\u8bf7\u6307\u5b9a--site\u7ad9\u70b9\u540d'); return

    log.info('=' * 60)
    log.info('  Site: %s (%s)', site_cfg.get('name', args.site), site_cfg.get('domain', ''))
    log.info('  Keywords: %s', ', '.join(keywords))
    log.info('=' * 60)

    run_search(site_cfg, keywords, output_dir, args.max_pages, args.with_detail)


if __name__ == '__main__':
    main()
