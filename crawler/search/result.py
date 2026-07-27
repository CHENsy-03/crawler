"""Standard SearchResult format for all plugins."""

REQUIRED_FIELDS = ['title', 'url', 'snippet', 'publish_time', 'source']


def normalize_search_result(raw):
    """Ensure a plugin result dict has all standard fields."""
    return {
        'title': raw.get('title', ''),
        'url': raw.get('url', ''),
        'snippet': raw.get('snippet', raw.get('summary', '')),
        'publish_time': raw.get('publish_time', raw.get('publish_date', '')),
        'source': raw.get('source', ''),
        # Extra fields preserved for pipeline use
        'content': raw.get('content', ''),
        'summary': raw.get('summary', raw.get('snippet', '')),
        'publish_date': raw.get('publish_date', raw.get('publish_time', '')),
        'source_keywords': raw.get('source_keywords', []),
    }
