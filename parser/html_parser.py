import re
from lxml.html import fromstring
from parser.multi_strategy import clean_text, normalize_date
from urllib.parse import urljoin
import json, os
from parser.ai_parser import parse_with_ai  # 2.4 AI Parser interface

_MODE_MAP = {'trs':'trs','jpaas':'jpaas','sichuan':'sichuan','shandong':'shandong','default':'government'}

_CS_GLOBAL = ['.TRS_Editor','.article-content','.content','#mainText','#UCAP-CONTENT']
_XP_GLOBAL = ['//div[@class="TRS_Editor"]','//div[@class="article-content"]','//div[@id="mainText"]','//article']


def _load_cms_rules(mode):
    cms_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cms_rules')
    mode = _MODE_MAP.get(mode, 'government')
    fp = os.path.join(cms_dir, mode + '.json')
    try:
        with open(fp, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        log.warning('_load_cms_rules failed for mode=%s', mode)
        return None


def _get_rules(site_cfg=None):
    if not site_cfg:
        return None
    ext = site_cfg.get('extract', {})
    mode = ext.get('mode', '')
    if ext.get('title_selector') or ext.get('content_selector'):
        return {
            'title': ext.get('title_selector', '').split(',') if ext.get('title_selector') else [],
            'content': ext.get('content_selector', '').split(',') if ext.get('content_selector') else [],
        }
    loaded = _load_cms_rules(mode)
    if loaded:
        return loaded
    return _load_cms_rules('trs')


# ===== 2.3 Density Parser: 正文密度算法 =====
BLOCK_TAGS = {'div', 'article', 'section', 'main', 'td', 'li'}
SKIP_TAGS = {'script', 'style', 'noscript', 'nav', 'header', 'footer', 'form', 'iframe', 'aside'}


def _calc_density(elem):
    """计算文本密度: clean_text_len / total_content_len"""
    raw = elem.text_content() if hasattr(elem, 'text_content') else ''
    cleaned = clean_text(raw)
    if len(cleaned) < 80:
        return 0.0
    # 链接密度惩罚：链接文字占比 > 30% → 非正文
    all_text = len(cleaned)
    link_text = 0
    try:
        for a in elem.xpath('.//a'):
            link_text += len(clean_text(a.text_content() if hasattr(a, 'text_content') else ''))
    except:
        pass
    if all_text > 0 and link_text / all_text > 0.3:
        return 0.0
    # 密度 = 干净文字长度 / 原始长度
    density = len(cleaned) / max(len(raw), 1)
    # 长文本加分
    score = density * (1 + min(len(cleaned) / 1000, 1))
    return score


def _density_extract(html, max_chars=3000):
    """2.3 Density Parser: 正文密度算法 -- 遍历块级元素，计算文本密度，无规则适配。"""
    try:
        doc = fromstring(html)
        candidates = []
        # 遍历所有块级元素
        for elem in doc.iter():
            if elem.tag in SKIP_TAGS:
                continue
            if elem.tag in BLOCK_TAGS:
                score = _calc_density(elem)
                if score > 0:
                    text = clean_text(elem.text_content() if hasattr(elem, 'text_content') else '')
                    candidates.append((score, len(text), text))
        # 按得分排序，取最高分
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            _, _, best = candidates[0]
            return best[:max_chars]
        # 回退到自由文本提取
        texts = []
        for p in doc.xpath('//p'):
            t = clean_text(p.text_content() if hasattr(p, 'text_content') else '')
            if len(t) >= 30:
                texts.append(t)
        if texts:
            return ' '.join(texts)[:max_chars]
    except Exception:
        log.debug('_density_extract fallback triggered')
    return None


def _css_to_xpath(sel):
    import re as _r
    sel = sel.strip()
    if _r.match('^[a-zA-Z][a-zA-Z0-9-]*$', sel): return '//' + sel
    if sel.startswith('.'): return '//*[contains(concat(" ", normalize-space(@class), " "), " ' + sel[1:] + ' ")]'
    if sel.startswith('#'): return '//*[@id="' + sel[1:] + '"]'
    return '//' + sel


def _extract_by_selectors(html, selectors, use_lxml=True):
    if not selectors:
        return None
    if use_lxml:
        try:
            doc = fromstring(html)
            for sel in selectors:
                for el in doc.xpath(_css_to_xpath(sel)):
                    t = clean_text(el.text_content() if hasattr(el, 'text_content') else '')
                    if len(t) >= 80:
                        return t
        except Exception:
            pass  # lxml selector failed, try regex fallback
    for sel in selectors:
        cname = sel.lstrip('.#')
        pat = re.compile(r'<div\b[^>]*\bclass\s*=\s*(["\'])' + re.escape(cname) + r'\1[^>]*>(.*?)</div>', re.I|re.S)
        m = pat.search(html)
        if m:
            t = clean_text(m.group(1))
            if len(t) >= 80:
                return t
    return None


def _extract_by_markers(html, markers, max_chars=3000):
    if not markers:
        return None
    for mkr in markers:
        end = mkr.replace('开始', '结束').replace('begin', 'end')
        pat = re.compile(re.escape(mkr) + r'(.*?)' + re.escape(end), re.I|re.S)
        m = pat.search(html)
        if m:
            t = clean_text(m.group(1))
            if len(t) >= 40:
                return t[:max_chars]
    return None


def _regex_fallback(html, max_chars=3000):
    texts = []
    for p in re.finditer(r'<p[^>]*>(.*?)</p>', html, re.I|re.S):
        t = clean_text(p.group(1))
        if len(t) >= 30:
            texts.append(t)
    return ' '.join(texts)[:max_chars] if texts else clean_text(html)[:max_chars]


def extract_title(html, site_cfg=None):
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.I|re.S)
    if m:
        return clean_text(m.group(1))
    rules = _get_rules(site_cfg)
    if rules:
        result = _extract_by_selectors(html, rules.get('title', []))
        if result:
            return clean_text(result)[:100]
    return ''


def extract_date(html, site_cfg=None):
    return normalize_date(html)


def extract_content(html, site_cfg=None, max_chars=3000):
    """四级解析：Site Parser -> CMS Parser -> AI Parser -> Density Parser"""
    rules = _get_rules(site_cfg)
    if rules:
        result = _extract_by_markers(html, rules.get('content_markers', []), max_chars)
        if result:
            return result
        result = _extract_by_selectors(html, rules.get('content', []))
        if result:
            return result[:max_chars]
    result = _extract_by_selectors(html, _CS_GLOBAL)
    if result:
        return result[:max_chars]
    # 2.4 AI Parser: 如果 site_cfg.ai_enabled, 调用 AI 提取
    if site_cfg and site_cfg.get('extract', {}).get('ai_enabled'):
        ai_result = parse_with_ai(html, site_cfg)
        if ai_result:
            content = ai_result.get('content', '')
            if content and len(content) >= 80:
                return content[:max_chars]
    
    result = _density_extract(html, max_chars)
    if result:
        return result
    return _regex_fallback(html, max_chars)


def extract_links(html, base_url, art_pattern=True):
    links = []
    for m in re.finditer(r'<a\b[^>]*\bhref\s*=\s*(["\'])([^"\']+?)\1[^>]*>(.*?)</a>', html, re.I|re.S):
        url = m.group(2)
        title = clean_text(m.group(3))
        if not url or url.startswith(('javascript:', 'mailto:', 'tel:', '#')):
            continue
        if art_pattern and 'art_' not in url:
            continue
        links.append({'title': title, 'url': urljoin(base_url, url)})
    return links

