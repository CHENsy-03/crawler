"""Manifest V2 generation, validation, and cross-runtime tests."""

import copy
import hashlib
import json
import os

import pytest

from crawler.security.osec_manifest_v2 import (
    build_envelope_v2,
    build_manifest_v2,
    decode_envelope_v2,
    envelope_to_bytes,
    load_fixture_and_legacy,
    manifest_hash_v2,
    validate_manifest_v2,
)

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
CONTRACT_PATH = os.path.join(FIXTURE_DIR, "outbound_security_config_contract.json")
LEGACY_PATH = os.path.join(FIXTURE_DIR, "outbound_security_config_legacy_digests.json")
MANIFEST_PATH = os.path.join(FIXTURE_DIR, "outbound_security_config_manifest_v2.json")
CONTRACT_SHA = "8D8B12F5F030DEA6FACE5E2B25795F667657873BD4DD89A178659E0DAABDCB45"
LEGACY_SHA = "37A6EA15C1E7E7D80089AE0872992E2B405125EDD68C272739C2C09EF5001E81"
MANIFEST_FIXTURE_SHA = "E62084230C5F3BFD9383F40598ADA4C6BCE8FCAA6AEC167AFDE0353FD44E7DE1"
MANIFEST_HASH = "01535055051b6e2d4ef7c25aa2ea6c84b26cd01917d35c9f4c3251c5f3828069"
ALL125 = "75336a374cd9ee82a8c811f380fd9ce6893364d65eaf0fbed76424307b2baa5b"
BASE104 = "bc38711ddf559eb5319eac9b080eeec611e3742d9cf0bbdb09072317cfc975b8"
AMENDMENT21 = "dfda4174b62f27b4132cf157e96b89be2982f9268724dc12f47ebc97c7df8850"


def _sha256_hex(data):
    return hashlib.sha256(data).hexdigest().upper()


def _read_normalized(path):
    raw = open(path, "rb").read()
    return raw, raw.replace(b"\r\n", b"\n")


def _load_inputs():
    contract_raw, contract_norm = _read_normalized(CONTRACT_PATH)
    legacy_raw, legacy_norm = _read_normalized(LEGACY_PATH)
    assert _sha256_hex(contract_norm) == CONTRACT_SHA
    assert _sha256_hex(legacy_norm) == LEGACY_SHA
    return load_fixture_and_legacy(contract_raw, legacy_raw)


def _load_manifest_bytes():
    raw = open(MANIFEST_PATH, "rb").read()
    assert _sha256_hex(raw) == MANIFEST_FIXTURE_SHA
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw.replace(b"\r\n", b"")
    return raw


def _flip_first_hex(value):
    return ("0" if value[0] != "0" else "1") + value[1:]


def test_manifest_v2_generate_and_validate():
    fixture, legacy = _load_inputs()
    manifest = build_manifest_v2(fixture, legacy)
    validate_manifest_v2(manifest, fixture, legacy)
    assert manifest["case_count"] == 125
    assert len(manifest["case_digests"]) == 125
    assert len(manifest["category_names"]) == 12
    assert set(manifest["category_names"]) == set(fixture["categories"])
    cohorts = {c["name"]: c for c in manifest["cohorts"]}
    assert cohorts["all125"]["aggregate_v1"] == ALL125
    assert cohorts["base104"]["aggregate_v1"] == BASE104
    assert cohorts["amendment21"]["aggregate_v1"] == AMENDMENT21
    assert manifest["whole_set_aggregate_v1"] == ALL125
    assert [c["name"] for c in manifest["cohorts"]] == ["all125", "amendment21", "base104"]
    by_id = {d["id"]: d for d in manifest["case_digests"]}
    assert by_id["p-004"]["sha256"] == "4ed0c899258ba53fe64eaf92b2b243281f9dbd0cfe8fae4b5c6ba76bcc38fd50"
    assert by_id["ver-003"]["sha256"] == "5ff23879522951099e3d6d44f8f74884905f23e29ebb64b17ed63efea5066806"


def test_manifest_v2_envelope_and_hash():
    fixture, legacy = _load_inputs()
    manifest = build_manifest_v2(fixture, legacy)
    envelope = build_envelope_v2(manifest)
    assert envelope["manifest_hash_v2"] == MANIFEST_HASH
    raw = _load_manifest_bytes()
    assert envelope_to_bytes(envelope) == raw
    parsed = decode_envelope_v2(raw, fixture, legacy)
    assert parsed["manifest_hash_v2"] == MANIFEST_HASH
    assert parsed["manifest_v2"] == manifest
    # regeneration is byte-stable
    assert envelope_to_bytes(build_envelope_v2(build_manifest_v2(fixture, legacy))) == raw


def test_manifest_v2_negative():
    fixture, legacy = _load_inputs()
    manifest = build_manifest_v2(fixture, legacy)
    raw = _load_manifest_bytes()

    def expect_fail(mutate_manifest=None, mutate_bytes=None):
        candidate = copy.deepcopy(manifest)
        data = raw
        if mutate_manifest:
            mutate_manifest(candidate)
        elif mutate_bytes:
            data = mutate_bytes(data)
        if mutate_manifest:
            with pytest.raises(Exception):
                validate_manifest_v2(candidate, fixture, legacy)
        else:
            with pytest.raises(Exception):
                decode_envelope_v2(data, fixture, legacy)

    expect_fail(mutate_manifest=lambda m: m["case_digests"].pop())
    expect_fail(mutate_manifest=lambda m: m["case_digests"][0].__setitem__("sha256", _flip_first_hex(m["case_digests"][0]["sha256"])))
    expect_fail(mutate_manifest=lambda m: m["case_digests"][0].__setitem__("category", "wrong"))
    expect_fail(mutate_manifest=lambda m: m["case_digests"].__setitem__(0, dict(m["case_digests"][0], unknown=True)))
    expect_fail(mutate_manifest=lambda m: m["cohorts"].reverse())
    expect_fail(mutate_manifest=lambda m: m["category_names"].append("unknown"))
    expect_fail(mutate_manifest=lambda m: m["category_aggregates"].pop(next(iter(m["category_aggregates"]))))
    # unknown envelope field
    env = json.loads(raw.decode("utf-8"))
    env["extra"] = True
    data = json.dumps(env, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with pytest.raises(Exception):
        decode_envelope_v2(data, fixture, legacy)
    # tampered hash
    env2 = json.loads(raw.decode("utf-8"))
    env2["manifest_hash_v2"] = _flip_first_hex(env2["manifest_hash_v2"])
    data2 = json.dumps(env2, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with pytest.raises(Exception):
        decode_envelope_v2(data2, fixture, legacy)