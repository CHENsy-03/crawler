import logging

log = logging.getLogger('crawler.plugins.html')


def search(site_cfg, keyword, max_pages=0):
    log.warning('HTML search plugin (stub) - not yet implemented for %s', site_cfg.get('name', '?'))
    return []
import logging
import re
from urllib.parse import urljoin, urlencode, urlparse

from bs4 import BeautifulSoup

log = logging.getLogger('crawler.plugins.html')

_SEARCH_PATHS = ['/search', '/s', '/so/s']


def _get_dl():
    from crawler.core.downloader import get_downloader
    return get_downloader()


def _resolve_url(base, href):
    if not href:
        return ''
    href = href.strip()
    if href.startswith('http://') or href.startswith('https://'):
        return href
    return urljoin(base, href)


def _discover_search_url(site_cfg):
    """Try to discover the search URL from site config or common paths."""
    search = site_cfg.get('search', {})
    api_url = search.get('api_url', '')
    if api_url:
        return api_url
    base_url = site_cfg.get('base_url', site_cfg.get('domain', ''))
    if not base_url:
        return ''
    if not base_url.startswith('http'):
        base_url = 'https://' + base_url
    return base_url


def _build_search_url(api_url, keyword, page=1, params=None):
    """Build the search URL with keyword and pagination."""
    sep = '&' if '?' in api_url else '?'
    url = f'{api_url}{sep}'

    if params:
        for k, v in params.items():
            url += f'{k}={v}&'

    url += f'q={urlencode({"": keyword})[1:]}'

    if page > 1:
        url += f'&page={page}'

    return url


def _extract_results(soup, base_url):
    """Extract search result items from HTML soup."""
    results = []
    seen_urls = set()

    candidates = soup.find_all(['a', 'h2', 'h3', 'div', 'li'])
    link_candidates = []

    for i, tag in enumerate(candidates):
        if tag.name in ('h2', 'h3'):
            a = tag.find('a')
            if a and a.get('href'):
                link_candidates.append(a)
        elif tag.name == 'a' and tag.get('href'):
            link_candidates.append(tag)

    if not link_candidates:
        for a in soup.find_all('a', href=True):
            link_candidates.append(a)

    for a in link_candidates:
        href = a.get('href', '')
        full_url = _resolve_url(base_url, href)
        if not full_url or full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        title = (a.get_text() or '').strip()
        if not title or len(title) < 4:
            continue

        snippet = ''
        parent = a.parent
        if parent:
            p_tag = parent.find('p')
            if p_tag:
                snippet = (p_tag.get_text() or '').strip()[:200]
            if not snippet:
                div = parent.find('div', class_=re.compile(r'(summary|desc|abstract)'))
                if div:
                    snippet = (div.get_text() or '').strip()[:200]

        results.append({
            'title': title,
            'url': full_url,
            'snippet': snippet,
        })

    return results


def search(site_cfg, keyword, max_pages=0):
    """Collect search results from a standard HTML search page."""
    dl = _get_dl()
    api_url = _discover_search_url(site_cfg)

    if not api_url:
        log.warning('HTML search plugin: no search endpoint for %s', site_cfg.get('name', '?'))
        return []

    search_cfg = site_cfg.get('search', {})
    params = search_cfg.get('params', {})
    page_size = search_cfg.get('page_size', 20)
    max_p = max_pages if max_pages > 0 else search_cfg.get('max_pages', 1)

    all_results = []
    seen_urls = set()

    for page in range(1, max_p + 1):
        try:
            url = _build_search_url(api_url, keyword, page, params)
            resp = dl.fetch(url, site_cfg=site_cfg, timeout=15)
            if not resp:
                log.warning('HTML search: no response for page %d (%s)', page, url[:80])
                break

            soup = BeautifulSoup(resp.text, 'html.parser')
            page_results = _extract_results(soup, url)

            if not page_results:
                log.info('HTML search: no results on page %d (%s)', page, url[:80])
                break

            for r in page_results:
                if r['url'] not in seen_urls:
                    seen_urls.add(r['url'])
                    all_results.append(r)

            if len(page_results) < page_size:
                break

        except Exception as e:
            log.error('HTML search: page %d error: %s', page, e)
            break

    log.info('HTML search: site=%s keyword=%s pages=%d results=%d',
             site_cfg.get('name', '?'), keyword, page, len(all_results))
    return all_results
