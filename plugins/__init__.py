import logging

log = logging.getLogger('crawler.plugins')

_plugins = {}


def register(search_type, search_fn):
    _plugins[search_type] = search_fn


def get(search_type):
    return _plugins.get(search_type)


def search(site_cfg, keyword, max_pages=0):
    search_type = site_cfg.get('search', {}).get('type', '')
    fn = get(search_type)
    if fn:
        return fn(site_cfg, keyword, max_pages)
    log.warning('No plugin for search type: %s (site=%s)', search_type, site_cfg.get('name', '?'))
    return []


# Auto-register bundled plugins
from plugins import trs as _trs
from plugins import jpaas as _jpaas
from plugins import html as _html

register('trs_json', _trs.search)
register('jpaas_jsearch', _jpaas.search)
register('html', _html.search)
