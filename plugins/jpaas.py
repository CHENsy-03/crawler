import logging
import json

def _get_dl():
    from crawler.core.downloader import get_downloader
    return get_downloader()

from crawler.search.jpaas_parser import expand_jpaas_documents, map_jpaas_legacy_article

log = logging.getLogger('crawler.plugins.jpaas')


def search(site_cfg, keyword, max_pages=0):
    search = site_cfg.get('search', {})
    api_url = search.get('api_url')
    if not api_url:
        log.warning('JPAAS plugin: no api_url configured for %s', site_cfg.get('name'))
        return []
    params = search.get('params', {}).copy()
    params['q'] = keyword
    params['p'] = '1'
    params['pg'] = '10'
    params['sortType'] = '1'
    if 'webId' in params:
        params['_cus_eq_webid'] = params.pop('webId')

    articles = []
    page = 1
    while True:
        params['p'] = str(page)
        dl = _get_dl()
        result = dl.get_json(api_url, params, site_cfg)
        if not result:
            break
        if str(result.get('code', '')) != '200':
            log.warning('JPAAS search error: %s', result)
            break
        data = result.get('data', {})
        docs = data.get('appSearchResultBeanList', [])
        docs = expand_jpaas_documents(docs)
        log.info('JPAAS raw result count=%d (after expand)', len(docs))
        if docs:
            log.info('JPAAS raw data sample:\n%s', json.dumps(docs[:1], ensure_ascii=False, indent=2)[:3000])
        if not docs:
            log.info('  JPAAS returned 0 results (site may not be indexed)')
            break
        for doc in docs:
            article = map_jpaas_legacy_article(doc, keyword, site_cfg.get('name', ''))
            if article is not None:
                articles.append(article)
        log.info('  Page %d: %d hits', page, len(docs))
        if len(docs) < int(params.get('pg', 10)):
            break
        if max_pages > 0 and page >= max_pages:
            break
        page += 1
    return articles
