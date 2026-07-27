import logging

log = logging.getLogger('crawler.plugins.html')


def search(site_cfg, keyword, max_pages=0):
    log.warning('HTML search plugin (stub) - not yet implemented for %s', site_cfg.get('name', '?'))
    return []
