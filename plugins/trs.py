import logging

def _get_dl():
    from crawler.core.downloader import get_downloader
    return get_downloader()

from parser.api_parser import parse_trs_doc

log = logging.getLogger('crawler.plugins.trs')


def search(site_cfg, keyword, max_pages=0):
    search = site_cfg.get('search', {})
    api_url = search.get('api_url')
    if not api_url:
        log.warning('TRS plugin: no api_url configured for %s', site_cfg.get('name'))
        return []
    params = search.get('params', {}).copy()
    params['qt'] = keyword
    params['pageSize'] = params.get('pageSize', 20)
    articles = []
    page = 1
    while True:
        params['page'] = page
        dl = _get_dl()
        result = dl.post_json(api_url, params, site_cfg)
        if not result:
            break
        docs = result.get('resultDocs', [])
        for doc in docs:
            a = parse_trs_doc(doc, keyword)
            if a:
                articles.append(a)
        log.info('  Page %d: %d hits', page, len(docs))
        if len(docs) < params['pageSize'] or (max_pages > 0 and page >= max_pages):
            break
        page += 1
    return articles
