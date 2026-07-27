from parser.multi_strategy import clean_text, normalize_date


def parse_trs_doc(doc, keyword):
    """解析TRS API返回的文档"""
    data = doc.get('data') if isinstance(doc.get('data'), dict) else doc
    title = clean_text(data.get('titleO') or data.get('title') or '')
    url = clean_text(data.get('url') or data.get('URL') or '')
    if not title or not url:
        return None
    return {
        'title': title,
        'url': url,
        'publish_date': normalize_date(data.get('docDate') or data.get('publishTime') or ''),
        'summary': clean_text(data.get('summary', '')),
        'content': clean_text(data.get('summary', '')),  # TRS summary serves as initial content
        'source': '',
        'source_keywords': [keyword],
    }
# Unified article schema — all plugins must return these fields:
#   title, url, content, summary, publish_date, source, source_keywords
