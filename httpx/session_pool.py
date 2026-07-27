import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from httpx.ua_pool import UAPool

_ua_pool = UAPool()
_session_pool = {}


def _build_adapter(max_retries=3, pool_conn=10, pool_size=20):
    retry_strategy = Retry(
        total=max_retries, backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    return HTTPAdapter(pool_connections=pool_conn, pool_maxsize=pool_size, max_retries=retry_strategy)


def get_session_for_domain(domain, max_retries=3):
    """Domain-bound Session with Connection Pool + KeepAlive + Cookie sharing"""
    if domain not in _session_pool:
        ua = _ua_pool.get_for_domain(domain)
        s = requests.Session()
        s.headers.update({
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
        })
        s.mount('http://', _build_adapter(max_retries))
        s.mount('https://', _build_adapter(max_retries))
        _session_pool[domain] = s
    return _session_pool[domain]


def clear_session(domain=None):
    if domain:
        _session_pool.pop(domain, None)
    else:
        _session_pool.clear()


def get_random_session():
    ua = _ua_pool.get_random()
    s = requests.Session()
    s.headers.update({'User-Agent': ua})
    return s


def get_pool_stats():
    """Debug: return session pool info"""
    return {d: {'headers': dict(s.headers), 'cookies': dict(s.cookies.get_dict())}
            for d, s in _session_pool.items()}
