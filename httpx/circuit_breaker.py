from httpx._breaker import CircuitBreaker


class BreakerManager:
    """Domain-keyed CircuitBreaker pool. 每个域名共享一个熔断器，有历史记忆。"""

    _pool = {}

    @classmethod
    def get(cls, domain, failure_threshold=3, recovery_timeout=60):
        if domain not in cls._pool:
            cls._pool[domain] = CircuitBreaker(
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                name=domain
            )
        return cls._pool[domain]

    @classmethod
    def reset(cls, domain=None):
        if domain:
            cls._pool.pop(domain, None)
        else:
            cls._pool.clear()

    @classmethod
    def stats(cls):
        return {d: {'state': b.state, 'failures': b.failure_count}
                for d, b in cls._pool.items()}


breaker_manager = BreakerManager()
