import time
from httpx._token_bucket import RateLimiter


class RateLimiterManager:
    """Domain-keyed singleton RateLimiter pool. 每个域名共享一个限流器，防止限流失效。"""

    _pool = {}

    @classmethod
    def get(cls, domain, rate=1.0, per=1):
        if domain not in cls._pool:
            cls._pool[domain] = RateLimiter(rate=rate, per=per)
        return cls._pool[domain]

    @classmethod
    def reset(cls, domain=None):
        if domain:
            cls._pool.pop(domain, None)
        else:
            cls._pool.clear()

    @classmethod
    def stats(cls):
        return {d: {'allowance': rl.allowance, 'rate': rl.rate}
                for d, rl in cls._pool.items()}


rate_limiter_manager = RateLimiterManager()
