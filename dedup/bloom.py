import logging

log = logging.getLogger('dedup.bloom')


class BloomFilter:
    """Placeholder for Redis Bloom filter. Currently delegates to in-memory set."""

    def __init__(self, capacity=100000, error_rate=0.01):
        self._seen = set()
        log.info('Bloom filter placeholder (memory set), capacity=%d', capacity)

    def add(self, url):
        self._seen.add(url)

    def contains(self, url):
        return url in self._seen

    def size(self):
        return len(self._seen)


class RedisBloomFilter:
    """Future: RedisBloom implementation. Replace BloomFilter when Redis is available."""

    def __init__(self, redis_client, key='crawler:bloom'):
        self.redis = redis_client
        self.key = key
        log.info('Redis Bloom filter: key=%s (stub - requires RedisBloom module)', key)

    def add(self, url):
        # Future: self.redis.execute_command('BF.ADD', self.key, url)
        pass

    def contains(self, url):
        # Future: return self.redis.execute_command('BF.EXISTS', self.key, url)
        return False
