"""Offline tests for the SearchPlan Redis cache component."""

import json
import re
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest

from crawler.search.plan_cache import (
    CACHE_KEY_PREFIX,
    CACHE_SCHEMA_VERSION,
    DEFAULT_PLAN_CACHE_TTL_SECONDS,
    ERROR_PLAN_CACHE_READ_FAILED,
    ERROR_PLAN_CACHE_WRITE_FAILED,
    ERROR_PLAN_VALIDATION_FAILED,
    ERROR_UNSAFE_TARGET,
    PlanCacheReadResult,
    PlanCacheWriteResult,
    SearchPlanCache,
    build_plan_cache_key,
    compute_target_fingerprint,
)
from crawler.search.search_plan import (
    PLAN_STATUS_DRAFT,
    PROTOCOL_VERSION_V2,
    SEARCH_STRATEGY_HTML_FORM,
    SearchPlan,
    SearchScope,
    compute_plan_id,
    validate_search_plan,
)

TARGET = "https://example.gov.cn/"
ENDPOINT = "https://example.gov.cn/search"


def _valid_plan(endpoint=ENDPOINT, plan_id=None):
    base = SearchPlan(
        plan_id="",
        endpoint=endpoint,
        protocol_version=PROTOCOL_VERSION_V2,
        status=PLAN_STATUS_DRAFT,
        strategy=SEARCH_STRATEGY_HTML_FORM,
        http_method="GET",
        query_params={"q": "{keyword}"},
        scope=SearchScope(domain="example.gov.cn"),
    )
    pid = plan_id if plan_id is not None else compute_plan_id(base)
    return SearchPlan(
        plan_id=pid,
        endpoint=base.endpoint,
        protocol_version=base.protocol_version,
        status=base.status,
        strategy=base.strategy,
        http_method=base.http_method,
        query_params=base.query_params,
        request_body_template=base.request_body_template,
        pagination=base.pagination,
        selectors=base.selectors,
        scope=base.scope,
        discovery=base.discovery,
        created_from=base.created_from,
    )


def _envelope(plan, fingerprint):
    return json.dumps(
        {
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "target_fingerprint": fingerprint,
            "plan": plan.to_dict(),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.calls = []
        self.last_key = None
        self.last_value = None
        self.last_ex = None

    def get(self, name):
        self.calls.append(("get", name))
        return self.values.get(name)

    def set(self, name, value, *, ex=None):
        self.calls.append(("set", name, ex))
        self.values[name] = value
        self.last_key = name
        self.last_value = value
        self.last_ex = ex
        return True


class RaisingGetRedis(FakeRedis):
    def get(self, name):
        raise RuntimeError("redis get failed")


class RaisingSetRedis(FakeRedis):
    def set(self, name, value, *, ex=None):
        raise RuntimeError("redis set failed")


def test_same_normalized_url_has_same_fingerprint():
    first = compute_target_fingerprint("https://Example.gov.cn:443/")
    second = compute_target_fingerprint("https://example.gov.cn/")
    assert first == second


def test_fingerprint_is_64_lowercase_sha256():
    fingerprint = compute_target_fingerprint(TARGET)
    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)


def test_different_targets_have_different_fingerprints():
    first = compute_target_fingerprint("https://example.gov.cn/")
    second = compute_target_fingerprint("https://example.gov.cn/search")
    assert first != second


def test_cache_key_uses_fixed_prefix():
    key = build_plan_cache_key(TARGET)
    assert key.startswith(CACHE_KEY_PREFIX)
    assert key == CACHE_KEY_PREFIX + compute_target_fingerprint(TARGET)


def test_cache_key_does_not_contain_raw_url():
    key = build_plan_cache_key("https://example.gov.cn/search?q=secret")
    assert "example.gov.cn" not in key
    assert "/search" not in key
    assert "secret" not in key


def test_missing_key_returns_miss():
    cache = SearchPlanCache(FakeRedis())
    result = cache.get(target_url=TARGET)
    assert result.status == "miss"
    assert result.plan is None
    assert result.error_code is None
    assert not result.hit


def test_str_payload_hit():
    redis = FakeRedis()
    plan = _valid_plan()
    key = build_plan_cache_key(TARGET)
    redis.values[key] = _envelope(plan, compute_target_fingerprint(TARGET))
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.status == "hit"
    assert result.plan is not None
    assert result.error_code is None
    assert result.hit


def test_bytes_payload_hit():
    redis = FakeRedis()
    plan = _valid_plan()
    key = build_plan_cache_key(TARGET)
    redis.values[key] = _envelope(plan, compute_target_fingerprint(TARGET)).encode("utf-8")
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.status == "hit"
    assert result.plan == plan


def test_hit_returns_strictly_validated_plan():
    redis = FakeRedis()
    plan = _valid_plan()
    key = build_plan_cache_key(TARGET)
    redis.values[key] = _envelope(plan, compute_target_fingerprint(TARGET))
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.plan is not None
    validate_search_plan(result.plan)


def test_hit_plan_id_matches_recomputed_value():
    redis = FakeRedis()
    plan = _valid_plan()
    key = build_plan_cache_key(TARGET)
    redis.values[key] = _envelope(plan, compute_target_fingerprint(TARGET))
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.plan is not None
    assert result.plan.plan_id == compute_plan_id(result.plan)


def test_malformed_json_is_corrupt():
    redis = FakeRedis()
    key = build_plan_cache_key(TARGET)
    redis.values[key] = "{not json"
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.status == "corrupt"
    assert result.plan is None
    assert result.error_code is None


def test_non_utf8_bytes_is_corrupt():
    redis = FakeRedis()
    key = build_plan_cache_key(TARGET)
    redis.values[key] = b"\xff\xfe\x00"
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.status == "corrupt"


def test_json_non_object_is_corrupt():
    redis = FakeRedis()
    key = build_plan_cache_key(TARGET)
    redis.values[key] = "[]"
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.status == "corrupt"


def test_missing_envelope_field_is_corrupt():
    redis = FakeRedis()
    key = build_plan_cache_key(TARGET)
    redis.values[key] = json.dumps(
        {"cache_schema_version": 1, "target_fingerprint": compute_target_fingerprint(TARGET)}
    )
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.status == "corrupt"


def test_unknown_schema_version_is_corrupt():
    redis = FakeRedis()
    key = build_plan_cache_key(TARGET)
    payload = {
        "cache_schema_version": 2,
        "target_fingerprint": compute_target_fingerprint(TARGET),
        "plan": _valid_plan().to_dict(),
    }
    redis.values[key] = json.dumps(payload)
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.status == "corrupt"


def test_fingerprint_mismatch_is_corrupt():
    redis = FakeRedis()
    key = build_plan_cache_key(TARGET)
    payload = {
        "cache_schema_version": 1,
        "target_fingerprint": "0" * 64,
        "plan": _valid_plan().to_dict(),
    }
    redis.values[key] = json.dumps(payload)
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.status == "corrupt"


def test_plan_deserialization_failure_is_corrupt():
    redis = FakeRedis()
    key = build_plan_cache_key(TARGET)
    payload = {
        "cache_schema_version": 1,
        "target_fingerprint": compute_target_fingerprint(TARGET),
        "plan": {"plan_id": "x"},
    }
    redis.values[key] = json.dumps(payload)
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.status == "corrupt"


def test_plan_validation_failure_is_corrupt():
    redis = FakeRedis()
    plan = _valid_plan()
    bad = SearchPlan(
        plan_id=plan.plan_id,
        endpoint=plan.endpoint,
        protocol_version=plan.protocol_version,
        status=plan.status,
        strategy=plan.strategy,
        http_method="PATCH",
        query_params=plan.query_params,
        scope=plan.scope,
    )
    key = build_plan_cache_key(TARGET)
    redis.values[key] = _envelope(bad, compute_target_fingerprint(TARGET))
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.status == "corrupt"


def test_plan_id_tampering_is_corrupt():
    redis = FakeRedis()
    plan = _valid_plan()
    tampered = SearchPlan(
        plan_id="tampered",
        endpoint=plan.endpoint,
        protocol_version=plan.protocol_version,
        status=plan.status,
        strategy=plan.strategy,
        http_method=plan.http_method,
        query_params=plan.query_params,
        scope=plan.scope,
    )
    key = build_plan_cache_key(TARGET)
    redis.values[key] = _envelope(tampered, compute_target_fingerprint(TARGET))
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.status == "corrupt"


def test_cross_origin_endpoint_is_corrupt():
    redis = FakeRedis()
    plan = _valid_plan(endpoint="https://other.example/search")
    key = build_plan_cache_key(TARGET)
    redis.values[key] = _envelope(plan, compute_target_fingerprint(TARGET))
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.status == "corrupt"


def test_dangerous_endpoint_scheme_is_corrupt():
    redis = FakeRedis()
    plan = _valid_plan(endpoint="ftp://example.gov.cn/search")
    key = build_plan_cache_key(TARGET)
    redis.values[key] = _envelope(plan, compute_target_fingerprint(TARGET))
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.status == "corrupt"


def test_local_ip_endpoint_is_corrupt():
    redis = FakeRedis()
    plan = _valid_plan(endpoint="http://127.0.0.1/search")
    key = build_plan_cache_key(TARGET)
    redis.values[key] = _envelope(plan, compute_target_fingerprint(TARGET))
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.status == "corrupt"


def test_redis_read_exception_returns_read_failed():
    result = SearchPlanCache(RaisingGetRedis()).get(target_url=TARGET)
    assert result.status == "read_failed"
    assert result.plan is None
    assert result.error_code == ERROR_PLAN_CACHE_READ_FAILED
    assert not result.hit


def test_read_failed_has_expected_error_code():
    result = SearchPlanCache(RaisingGetRedis()).get(target_url=TARGET)
    assert result.error_code == ERROR_PLAN_CACHE_READ_FAILED


def test_corrupt_never_returns_half_plan():
    redis = FakeRedis()
    key = build_plan_cache_key(TARGET)
    redis.values[key] = "{bad"
    result = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.plan is None
    assert result.status == "corrupt"


def test_corrupt_cache_is_not_deleted():
    redis = FakeRedis()
    key = build_plan_cache_key(TARGET)
    redis.values[key] = "{bad"
    SearchPlanCache(redis).get(target_url=TARGET)
    assert key in redis.values


def test_valid_plan_can_be_written():
    redis = FakeRedis()
    result = SearchPlanCache(redis).put(target_url=TARGET, plan=_valid_plan())
    assert result.stored is True
    assert result.error_code is None


def test_write_envelope_schema_is_correct():
    redis = FakeRedis()
    plan = _valid_plan()
    SearchPlanCache(redis).put(target_url=TARGET, plan=plan)
    envelope = json.loads(redis.last_value.decode("utf-8"))
    assert envelope["cache_schema_version"] == 1
    assert envelope["target_fingerprint"] == compute_target_fingerprint(TARGET)
    assert envelope["plan"] == plan.to_dict()


def test_write_envelope_does_not_contain_original_target_url():
    redis = FakeRedis()
    plan = _valid_plan()
    target = "https://example.gov.cn/base?x=secret"
    SearchPlanCache(redis).put(target_url=target, plan=plan)
    payload = redis.last_value.decode("utf-8")
    envelope = json.loads(payload)
    assert "target_url" not in envelope
    assert "x=secret" not in payload
    assert "base" not in payload


def test_write_uses_exact_cache_key():
    redis = FakeRedis()
    SearchPlanCache(redis).put(target_url=TARGET, plan=_valid_plan())
    assert redis.last_key == build_plan_cache_key(TARGET)


def test_write_uses_single_command_with_ttl():
    redis = FakeRedis()
    SearchPlanCache(redis).put(target_url=TARGET, plan=_valid_plan())
    assert [call[0] for call in redis.calls] == ["set"]
    assert redis.last_ex == DEFAULT_PLAN_CACHE_TTL_SECONDS


def test_default_ttl_is_86400():
    assert DEFAULT_PLAN_CACHE_TTL_SECONDS == 86400
    redis = FakeRedis()
    SearchPlanCache(redis).put(target_url=TARGET, plan=_valid_plan())
    assert redis.last_ex == 86400


def test_custom_positive_ttl_is_used():
    redis = FakeRedis()
    SearchPlanCache(redis, ttl_seconds=120).put(target_url=TARGET, plan=_valid_plan())
    assert redis.last_ex == 120


def test_invalid_ttl_is_rejected():
    for value in (0, -1, 1.5, "86400", True, None):
        with pytest.raises((TypeError, ValueError)):
            SearchPlanCache(FakeRedis(), ttl_seconds=value)


def test_invalid_plan_does_not_call_redis():
    redis = FakeRedis()
    result = SearchPlanCache(redis).put(target_url=TARGET, plan="not-a-plan")
    assert result.stored is False
    assert result.error_code == ERROR_PLAN_VALIDATION_FAILED
    assert redis.calls == []


def test_plan_id_mismatch_does_not_write():
    redis = FakeRedis()
    plan = _valid_plan(plan_id="wrong-id")
    result = SearchPlanCache(redis).put(target_url=TARGET, plan=plan)
    assert result.stored is False
    assert result.error_code == ERROR_PLAN_VALIDATION_FAILED
    assert redis.calls == []


def test_cross_origin_plan_does_not_write():
    redis = FakeRedis()
    plan = _valid_plan(endpoint="https://other.example/search")
    result = SearchPlanCache(redis).put(target_url=TARGET, plan=plan)
    assert result.stored is False
    assert result.error_code == ERROR_PLAN_VALIDATION_FAILED
    assert redis.calls == []


def test_invalid_target_does_not_call_redis():
    redis = FakeRedis()
    result = SearchPlanCache(redis).put(
        target_url="ftp://example.gov.cn/",
        plan=_valid_plan(),
    )
    assert result.stored is False
    assert result.error_code == ERROR_UNSAFE_TARGET
    assert redis.calls == []
    read = SearchPlanCache(redis).get(target_url="http://localhost/")
    assert read.status == "corrupt"
    assert redis.calls == []


def test_redis_write_exception_returns_write_failed():
    result = SearchPlanCache(RaisingSetRedis()).put(target_url=TARGET, plan=_valid_plan())
    assert result.stored is False
    assert result.error_code == ERROR_PLAN_CACHE_WRITE_FAILED


def test_write_failure_does_not_modify_plan():
    redis = RaisingSetRedis()
    plan = _valid_plan()
    before = plan.to_dict()
    SearchPlanCache(redis).put(target_url=TARGET, plan=plan)
    assert plan.to_dict() == before


def test_serialized_payload_is_deterministic():
    first = FakeRedis()
    second = FakeRedis()
    SearchPlanCache(first).put(target_url=TARGET, plan=_valid_plan())
    SearchPlanCache(second).put(target_url=TARGET, plan=_valid_plan())
    assert first.last_value == second.last_value


def test_result_dataclasses_are_immutable():
    read = PlanCacheReadResult(None, "miss", None)
    with pytest.raises(FrozenInstanceError):
        read.status = "hit"
    write = PlanCacheWriteResult(True, None)
    with pytest.raises(FrozenInstanceError):
        write.stored = False


def test_hit_property_semantics():
    plan = _valid_plan()
    assert PlanCacheReadResult(plan, "hit", None).hit is True
    assert PlanCacheReadResult(None, "hit", None).hit is False
    assert PlanCacheReadResult(plan, "hit", ERROR_PLAN_CACHE_READ_FAILED).hit is False
    assert PlanCacheReadResult(None, "miss", None).hit is False


def test_cache_does_not_call_analyzer():
    redis = FakeRedis()
    with patch("crawler.site.analyzer.SiteAnalyzer.analyze", side_effect=AssertionError("analyzer called")):
        result = SearchPlanCache(redis).put(target_url=TARGET, plan=_valid_plan())
    assert result.stored is True
    with patch("crawler.site.analyzer.SiteAnalyzer.analyze", side_effect=AssertionError("analyzer called")):
        read = SearchPlanCache(redis).get(target_url=TARGET)
    assert read.status == "hit"


def test_cache_does_not_call_plan_builder():
    redis = FakeRedis()
    with patch("crawler.search.plan_builder.PlanBuilder.build", side_effect=AssertionError("plan builder called")):
        result = SearchPlanCache(redis).put(target_url=TARGET, plan=_valid_plan())
    assert result.stored is True
    with patch("crawler.search.plan_builder.PlanBuilder.build", side_effect=AssertionError("plan builder called")):
        read = SearchPlanCache(redis).get(target_url=TARGET)
    assert read.status == "hit"


def test_no_network_dns_or_time_access():
    redis = FakeRedis()
    with patch("socket.getaddrinfo", side_effect=AssertionError("dns called")), patch(
        "urllib.request.urlopen", side_effect=AssertionError("network called")
    ), patch("time.time", side_effect=AssertionError("time called")):
        result = SearchPlanCache(redis).put(target_url=TARGET, plan=_valid_plan())
        read = SearchPlanCache(redis).get(target_url=TARGET)
    assert result.stored is True
    assert read.status == "hit"


def test_errors_do_not_leak_sensitive_payload():
    class SecretRedis(FakeRedis):
        def get(self, name):
            raise RuntimeError("secret-value-and-payload")

    result = SearchPlanCache(SecretRedis()).get(target_url=TARGET)
    assert "secret-value-and-payload" not in (result.status or "")
    assert "secret-value-and-payload" not in (result.error_code or "")


def test_search_plan_roundtrip_preserves_fields():
    plan = _valid_plan()
    restored = SearchPlan.from_dict(plan.to_dict())
    assert restored == plan
    validate_search_plan(restored)
