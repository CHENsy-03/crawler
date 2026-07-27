import logging
from config.keywords import get_expand_keywords, get_min_results, LOW_ALT_KEYWORDS

log = logging.getLogger('search.expand')


def expand_keywords(user_keywords, current_results=0):
    """Expand user keywords with preset synonyms.
    If current_results >= min_results, return only user keywords (no expansion needed).
    Otherwise, merge user keywords with group expand list."""
    expanded = set(user_keywords)
    for kw in user_keywords:
        min_r = get_min_results(kw)
        if current_results > 0 and current_results >= min_r:
            log.debug('Keyword %s: %d results >= min_results=%d, skip expand', kw, current_results, min_r)
            continue
        group_expand = get_expand_keywords(kw)
        expanded.update(group_expand)
        log.info('Keyword %s expanded: %s (min_results=%d, current=%d)', kw, group_expand, min_r, current_results)
    expanded.update(LOW_ALT_KEYWORDS)
    result = tuple(expanded)
    return result
