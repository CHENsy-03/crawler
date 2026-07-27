import json, os

DEFAULT_KEYWORDS = (
    '低空经济',
    '低空政策',
    '低空监管',
    '低空',
)

def _load_keywords_config():
    path = os.path.join(os.path.dirname(__file__), 'keywords.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

_kw_config = _load_keywords_config()

def get_expand_keywords(keyword):
    group = _kw_config.get(keyword, {})
    return group.get('expand', [keyword])

def get_min_results(keyword):
    group = _kw_config.get(keyword, {})
    return group.get('min_results', 0)

LOW_ALT_KEYWORDS = list(set(kw for g in _kw_config.values() for kw in g.get('expand', []))) or [
    '低空经济','低空','无人机','通用航空','航空产业','eVTOL','飞行器','低空产业园','低空招标',
]
