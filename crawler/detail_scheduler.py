import logging

def _get_dl():
    from crawler.core.downloader import get_downloader
    return get_downloader()

from crawler.extractor import extract as extract_content

log = logging.getLogger('crawler.detail')


def need_fetch_detail(article):
    content = article.get('content', '') or ''
    summary = article.get('summary', '') or ''
    text = content if len(content) > len(summary) else summary
    if not text or len(text.strip()) < 80:
        return True
    if text.count('<') > text.count('>') + 3:
        return True
    stripped = text.strip()
    if stripped.endswith('...') or stripped.endswith('\u2026'):
        return True
    if len(stripped) > 2000:
        return False
    if len(stripped) > 300 and stripped[-1] not in ',;\uff0c\uff1b':
        return False
    return len(stripped) < 200


def _fetch_one_detail(url, site_cfg):
    try:
        dl = _get_dl()
        resp = dl.fetch(url, site_cfg)
        if resp:
            return extract_content(resp.text, site_cfg)
    except Exception:
        log.warning('_fetch_one_detail failed: %s', url[:80])
    return None
