"""Offline tests for strict JSON Pointer resolution."""

import pytest

from crawler.search.json_pointer import JSONPointerError, resolve_json_pointer


def test_pointer_escape_roundtrip():
    data = {"a/b": {"m~n": {"key": 1}}}
    assert resolve_json_pointer(data, "/a~1b/m~0n/key") == 1


def test_root_pointer_returns_data():
    data = [1, 2]
    assert resolve_json_pointer(data, "") is data


def test_array_index():
    data = [{"a": 1}, {"a": 2}]
    assert resolve_json_pointer(data, "/1/a") == 2


def test_invalid_escape_rejected():
    with pytest.raises(JSONPointerError):
        resolve_json_pointer({"a": 1}, "/a~2")


def test_invalid_array_index_rejected():
    with pytest.raises(JSONPointerError):
        resolve_json_pointer([1], "/01")
    with pytest.raises(JSONPointerError):
        resolve_json_pointer([1], "/1")
    with pytest.raises(JSONPointerError):
        resolve_json_pointer([1], "/-")


def test_missing_key_rejected():
    with pytest.raises(JSONPointerError):
        resolve_json_pointer({"a": 1}, "/b")
