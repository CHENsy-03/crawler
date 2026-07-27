import re
from html import unescape

TAG_RE = re.compile(r'(?is)<(script|style|noscript).*?</\1>|<[^>]+>')
SPACE_RE = re.compile(r'\s+')

DATE_PATTERNS = (
    re.compile(r'(?:发布日期|发布时间|日期)[：:]\s*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)'),
    re.compile(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?'),
    re.compile(r'(\d{4}年\d{1,2}月\d{1,2}日)'),
)


def clean_text(value):
    if value is None:
        return ''
    text = TAG_RE.sub(' ', str(value))
    text = unescape(text)
    text = text.replace('\xa0', ' ').replace('\u3000', ' ')
    return SPACE_RE.sub(' ', text).strip()


def normalize_date(value):
    text = clean_text(value)
    if not text:
        return ''
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        parts = re.findall(r'\d+', m.group(1))
        if len(parts) >= 3:
            return f'{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}'
    return ''
