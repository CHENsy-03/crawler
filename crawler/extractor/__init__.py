from crawler.extractor.readability import extract_by_readability
from crawler.extractor.trafilatura_parser import extract_by_trafilatura
from parser.html_parser import extract_content as extract_by_xpath
from parser.ai_parser import parse_with_ai


def extract(html, site_cfg=None, max_chars=3000):
    """Multi-strategy extraction: XPath → Readability → Trafilatura → AI → fallback."""
    content = extract_by_xpath(html, site_cfg, max_chars)
    if content and len(content) > 200:
        return content
    content = extract_by_readability(html, max_chars)
    if content and len(content) > 200:
        return content
    content = extract_by_trafilatura(html, max_chars)
    if content and len(content) > 200:
        return content
    if site_cfg and site_cfg.get('extract', {}).get('ai_enabled'):
        ai = parse_with_ai(html, site_cfg)
        if ai and len(ai.get('content', '')) > 200:
            return ai['content'][:max_chars]
    from parser.html_parser import _regex_fallback
    return _regex_fallback(html, max_chars)
