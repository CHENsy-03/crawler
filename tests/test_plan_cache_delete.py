"""Offline tests for SearchPlanCache.delete()."""

from crawler.search.plan_cache import SearchPlanCache, build_plan_cache_key

TARGET = "https://example.gov.cn/"


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.calls = []

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value, *, ex=None):
        self.values[name] = value
        return True

    def delete(self, name):
        self.calls.append(name)
        return self.values.pop(name, None) is not None


def test_delete_uses_exact_cache_key():
    redis = FakeRedis()
    cache = SearchPlanCache(redis)
    assert cache.delete(target_url=TARGET) is False
    assert redis.calls == [build_plan_cache_key(TARGET)]


def test_delete_removes_only_target_cache():
    redis = FakeRedis()
    other_key = build_plan_cache_key("https://other.example/")
    key = build_plan_cache_key(TARGET)
    redis.values[other_key] = b"other"
    redis.values[key] = b"plan"
    cache = SearchPlanCache(redis)
    assert cache.delete(target_url=TARGET) is True
    assert key not in redis.values
    assert other_key in redis.values


def test_delete_missing_key_is_safe():
    redis = FakeRedis()
    assert SearchPlanCache(redis).delete(target_url=TARGET) is False
