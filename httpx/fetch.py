import logging
import time
from urllib.parse import urlparse, urlencode
import requests as req
from httpx.session_pool import get_session_for_domain, clear_session
from httpx.jitter import jitter_sleep
from httpx.rate_limiter import rate_limiter_manager
from httpx.circuit_breaker import breaker_manager

log = logging.getLogger('crawler.http_client')

def _retry(session, domain, url, rate_cfg, max_retries, timeout, request_fn):
    """统一重试逻辑：RateLimiter -> Jitter -> CircuitBreaker -> HTTP"""
    delay = rate_cfg.get('delay', 1.5)
    jitter = rate_cfg.get('jitter', 0.8)
    max_r = rate_cfg.get('max_retry', max_retries)
    rl = rate_limiter_manager.get(domain, rate=rate_cfg.get('rate', max(0.5, 1.0 / (delay or 1.5))), per=1)
    cb = breaker_manager.get(domain)
    for attempt in range(1, max_r + 1):
        try:
            rl.acquire()
            def _do():
                jitter_sleep(delay, jitter)
                resp = request_fn(session)
                if resp.status_code >= 300:
                    raise Exception('HTTP ' + str(resp.status_code))
                return resp
            return cb.call(_do)
        except RuntimeError as e:
            if 'OPEN' in str(e):
                log.warning('Breaker open for %s, skip %s', domain, url[:50])
                return None
            raise
        except Exception as e:
            if attempt < max_r:
                log.warning('Retry %d/%d for %s: %s', attempt, max_r, url[:50], str(e)[:60])
                time.sleep(attempt)
            else:
                log.warning('Failed after %d retries: %s', max_r, url[:50])
    return None

from dataclasses import dataclass


@dataclass
class FetchOnceResult:
    url: str
    status_code: int
    headers: dict
    content: bytes
    bytes_read: int
    too_large: bool = False
    location: str = ""

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


def reset_all_sessions():
    clear_session()
    log.info('All HTTP sessions reset')


def fetch_once(url, site_cfg=None, timeout=15, max_bytes=None):
    """Single request that does not follow redirects and enforces a streaming byte limit."""
    domain = urlparse(url).netloc
    session = get_session_for_domain(domain)
    resp = session.get(url, timeout=timeout, allow_redirects=False, stream=True)
    status_code = resp.status_code
    headers = dict(resp.headers)
    location = headers.get("Location", "")

    content_length = resp.headers.get("Content-Length")
    if max_bytes is not None and content_length:
        try:
            if int(content_length) > max_bytes:
                resp.close()
                return FetchOnceResult(url, status_code, headers, b"", 0, True, location)
        except ValueError:
            pass

    chunks = []
    total = 0
    try:
        for chunk in resp.iter_content(chunk_size=8192):
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                return FetchOnceResult(url, status_code, headers, b"".join(chunks), total, True, location)
            chunks.append(chunk)
    finally:
        resp.close()
    return FetchOnceResult(url, status_code, headers, b"".join(chunks), total, False, location)


def fetch(url, site_cfg=None, max_retries=3, timeout=15):
    domain = urlparse(url).netloc
    session = get_session_for_domain(domain)
    rate_cfg = site_cfg.get('rate_limit', {}) if site_cfg else {}
    return _retry(session, domain, url, rate_cfg, max_retries, timeout,
                  lambda s: s.get(url, timeout=timeout))

def get_json(url, params=None, site_cfg=None, max_retries=3, timeout=15):
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    session = get_session_for_domain(domain)
    rate_cfg = site_cfg.get('rate_limit', {}) if site_cfg else {}
    def _do_get(s):
        headers = {'X-Requested-With': 'XMLHttpRequest','Accept': '*/*',
                   'Referer': site_cfg.get('search', {}).get('page_url', url) if site_cfg else url}
        return s.get(url, params=params, headers=headers, timeout=timeout)
    resp = _retry(session, domain, url, rate_cfg, max_retries, timeout, _do_get)
    if resp and resp.status_code == 200:
        return resp.json()
    return None

def post_json(url, data, site_cfg=None, max_retries=3, timeout=15):
    """POST请求（form-encoded），专为TRS API设计"""
    domain = urlparse(url).netloc
    session = get_session_for_domain(domain)
    rate_cfg = site_cfg.get('rate_limit', {}) if site_cfg else {}
    def _do_post(s):
        headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
        return s.post(url, data=urlencode(data), headers=headers, timeout=timeout)
    resp = _retry(session, domain, url, rate_cfg, max_retries, timeout, _do_post)
    if resp is None:
        return None
    try:
        return resp.json()
    except Exception:
        log.warning('post_json response parse failed')
        return None
