import logging
import json

def _get_dl():
    from crawler.core.downloader import get_downloader
    return get_downloader()

from parser.multi_strategy import clean_text, normalize_date

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
        expanded_docs = []
        for doc in docs:
            if 'mapSearchResult' in doc:
                items = doc.get('mapSearchResult', {}).get('items', [])
                for item in items:
                    expanded_docs.append(item.get('data', {}))
            else:
                expanded_docs.append(doc)
        docs = expanded_docs
        log.info('JPAAS raw result count=%d (after expand)', len(docs))
        if docs:
            log.info('JPAAS raw data sample:\n%s', json.dumps(docs[:1], ensure_ascii=False, indent=2)[:3000])
        if not docs:
            log.info('  JPAAS returned 0 results (site may not be indexed)')
            break
        for doc in docs:
            title = doc.get('title') or doc.get('title_str') or ''
            url = doc.get('url') or doc.get('zcywlj_617143') or ''
            if url and url.startswith('http://'):
                url = url.replace('http://', 'https://', 1)
            content = doc.get('content') or doc.get('content_556463') or doc.get('vc_content') or ''
            if not title:
                continue
            articles.append({
                'title': clean_text(title),
                'url': url,
                'content': content,
                'publish_date': normalize_date(doc.get('date', '')),
                'summary': clean_text(content),
                'source': site_cfg.get('name', ''),
                'site': site_cfg.get('name', ''),
                'province': site_cfg.get('name', '').replace('财政局','').replace('财政厅',''),
                'source_keywords': [keyword]
            })
        log.info('  Page %d: %d hits', page, len(docs))
        if len(docs) < int(params.get('pg', 10)):
            break
        if max_pages > 0 and page >= max_pages:
            break
        page += 1
    return articles
