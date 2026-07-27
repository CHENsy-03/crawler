import logging

log = logging.getLogger('search.merge')


def semantic_hit_rate(articles, keywords):
    """Placeholder: AI-based semantic relevance check (future OpenAI/DeepSeek integration).
    For now, delegates to content_hit_rate."""
    return content_hit_rate(articles, keywords)


def merge_results(article_lists, dedup_by='url'):
    seen = set()
    merged = []
    for articles in article_lists:
        for a in articles:
            key = a.get(dedup_by, '')
            if key and key not in seen:
                seen.add(key)
                merged.append(a)
    log.info('Merge: %d lists -> %d unique articles', len(article_lists), len(merged))
    return merged


def search_hit_rate(articles, keywords):
    if not articles:
        return {'found': 0, 'search_hit': 0, 'search_hit_rate': 0.0}
    search_hit = 0
    for a in articles:
        found = False
        for k, v in a.items():
            if isinstance(v, str):
                for kw in keywords:
                    if kw in v:
                        search_hit += 1
                        found = True
                        break
            if found:
                break
    rate = (search_hit / len(articles) * 100) if articles else 0
    log.info('SearchHit: %d/%d (%.1f%%)', search_hit, len(articles), rate)
    return {'found': len(articles), 'search_hit': search_hit, 'search_hit_rate': round(rate, 1)}


def content_hit_rate(articles, keywords):
    if not articles:
        return {'found': 0, 'content_hit': 0, 'content_hit_rate': 0.0}
    content_hit = 0
    for a in articles:
        title = str(a.get('title', ''))
        body = str(a.get('content', '') or a.get('summary', ''))
        for kw in keywords:
            if kw in title or kw in body:
                content_hit += 1
                a['content_hit'] = True
                break
        else:
            a['content_hit'] = False
    rate = (content_hit / len(articles) * 100) if articles else 0
    log.info('ContentHit: %d/%d (%.1f%%)', content_hit, len(articles), rate)
    return {'found': len(articles), 'content_hit': content_hit, 'content_hit_rate': round(rate, 1)}
