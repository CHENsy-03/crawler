import logging
from plugins.trs import search as search_trs
from plugins.jpaas import search as search_jpaas
from plugins import search as search_with_plugin

log = logging.getLogger('crawler.search')
