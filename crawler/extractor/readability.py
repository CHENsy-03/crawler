import re
import logging
from lxml.html import fromstring

log = logging.getLogger('crawler.extractor.readability')

SKIP_TAGS = {'script', 'style', 'noscript', 'nav', 'header', 'footer', 'aside', 'form', 'iframe', 'select', 'button'}
BLOCK_TAGS = {'div', 'article', 'section', 'main', 'p', 'td', 'li', 'pre', 'blockquote'}


def extract_by_readability(html, max_chars=3000):
    """Readability-style extraction: score blocks by text density, select best."""
    try:
        doc = fromstring(html)
        candidates = []
        for elem in doc.iter():
            if elem.tag in SKIP_TAGS:
                continue
            if elem.tag not in BLOCK_TAGS:
                continue
            text = elem.text_content()
            cleaned = _clean(text)
            text_len = len(cleaned)
            if text_len < 100:
                continue
            link_len = sum(len(a.text_content().strip()) for a in elem.findall('.//a'))
            link_ratio = link_len / max(text_len, 1)
            if link_ratio > 0.4:
                continue
            density = text_len / max(len(text), 1)
            score = density * text_len * (1 - link_ratio)
            candidates.append((score, cleaned))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1][:max_chars]
    except Exception as e:
        log.warning('Readability extract failed: %s', e)
    return ''


def _clean(text):
    text = re.sub(r'\s+', ' ', text)
    return text.strip()
