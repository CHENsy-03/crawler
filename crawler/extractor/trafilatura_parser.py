import logging

log = logging.getLogger('crawler.extractor.trafilatura')


def extract_by_trafilatura(html, max_chars=3000):
    """Trafilatura-based extraction. Falls back to empty string if not installed."""
    try:
        import trafilatura
        result = trafilatura.extract(html, include_comments=False, include_tables=False)
        if result:
            return result[:max_chars]
    except ImportError:
        log.debug('trafilatura not installed')
    except Exception as e:
        log.warning('Trafilatura extract error: %s', e)
    return ''
