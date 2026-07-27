import logging
from urllib.parse import urlparse
from httpx.fetch import fetch, post_json, get_json, reset_all_sessions
from httpx.session_pool import get_session_for_domain
from httpx.rate_limiter import rate_limiter_manager
from httpx.circuit_breaker import breaker_manager
from httpx.jitter import jitter_sleep
from httpx.ua_pool import UAPool

log = logging.getLogger('crawler.downloader')
_ua_pool = UAPool()


class Downloader:
    """Unified HTTP client. ALL HTTP requests must go through this class.
    Features: Session Pool, Rate Limiting, Circuit Breaker, Retry, UA Rotation."""

    def __init__(self, default_timeout=15, max_retries=3):
        self.timeout = default_timeout
        self.max_retries = max_retries

    def fetch(self, url, site_cfg=None, timeout=None, headers=None):
        """GET request returning a requests.Response object."""
        return fetch(url, site_cfg, max_retries=self.max_retries, timeout=timeout or self.timeout)

    def post_json(self, url, data, site_cfg=None):
        """POST form-encoded, returns parsed JSON dict."""
        return post_json(url, data, site_cfg, max_retries=self.max_retries, timeout=self.timeout)

    def get_json(self, url, params=None, site_cfg=None):
        """GET with JSON response, returns parsed JSON dict."""
        return get_json(url, params, site_cfg, max_retries=self.max_retries, timeout=self.timeout)

    def reset_sessions(self):
        reset_all_sessions()

    def session_for(self, url):
        domain = urlparse(url).netloc
        return get_session_for_domain(domain)

    def stats(self):
        return {
            'rate_limiter': rate_limiter_manager.stats(),
            'circuit_breaker': breaker_manager.stats(),
        }


_default_downloader = Downloader()


def get_downloader():
    return _default_downloader
