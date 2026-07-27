import logging

log = logging.getLogger('search.strategy')


class QueryStrategy:
    """Strategy for querying multiple sites with keyword expansion."""

    def __init__(self, site_cfg, keywords):
        from search.keyword_expand import expand_keywords
        self.site_cfg = site_cfg
        self.user_keywords = tuple(keywords) if keywords else ()
        self.expanded_keywords = expand_keywords(self.user_keywords)
        self.site_name = site_cfg.get('name', 'unknown')

    def search_type(self):
        return self.site_cfg.get('search', {}).get('type', '')

    def log_info(self):
        log.info('QueryStrategy: site=%s type=%s keywords=%d (expanded from %d)',
                 self.site_name, self.search_type(),
                 len(self.expanded_keywords), len(self.user_keywords))
