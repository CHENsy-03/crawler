"""Tests for the HTML search plugin using mocked HTTP responses."""

from unittest.mock import Mock, patch

from plugins.html import search, _resolve_url, _build_search_url

import pytest

SAMPLE_HTML = """<!DOCTYPE html>
<html><body>
<div class="search-results">
  <div class="result">
    <h3><a href="/article/1.html">政策文件一：低空经济管理办法</a></h3>
    <p class="summary">北京市发布低空经济管理新政策</p>
  </div>
  <div class="result">
    <h3><a href="https://example.com/art/2">政策文件二：低空经济扶持措施</a></h3>
    <p class="summary">杭州市出台低空经济扶持政策</p>
  </div>
  <div class="result">
    <h3><a href="/article/3.html">标题三</a></h3>
  </div>
</div>
</body></html>"""

EMPTY_HTML = "<html><body><p>没有找到相关结果</p></body></html>"


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


@pytest.fixture(autouse=True)
def mock_downloader():
    dl = Mock()
    dl.fetch.return_value = None
    with patch("plugins.html._get_dl", return_value=dl):
        yield dl


def test_resolve_url_absolute():
    assert _resolve_url("http://example.com", "/a/b") == "http://example.com/a/b"


def test_resolve_url_already_absolute():
    assert _resolve_url("http://example.com", "http://other.com/x") == "http://other.com/x"


def test_resolve_url_empty():
    assert _resolve_url("http://example.com", "") == ""


def test_build_search_url_simple():
    url = _build_search_url("http://test.gov/search", "低空经济")
    assert "q=%E4%BD%8E%E7%A9%BA" in url or "低空" in url


def test_search_returns_results(mock_downloader):
    mock_downloader.fetch.return_value = FakeResponse(SAMPLE_HTML)
    cfg = {
        "name": "测试站点",
        "search": {"api_url": "http://test.gov/search", "page_size": 10},
    }
    results = search(cfg, "低空经济", max_pages=1)
    assert len(results) >= 2
    assert results[0]["title"] == "政策文件一：低空经济管理办法"
    assert "article/1" in results[0]["url"]


def test_search_empty_results(mock_downloader):
    mock_downloader.fetch.return_value = FakeResponse(EMPTY_HTML)
    cfg = {
        "name": "测试站点",
        "search": {"api_url": "http://test.gov/search"},
    }
    results = search(cfg, "无结果关键词", max_pages=1)
    assert results == []


def test_search_no_response(mock_downloader):
    mock_downloader.fetch.return_value = None
    cfg = {
        "name": "测试站点",
        "search": {"api_url": "http://test.gov/search"},
    }
    results = search(cfg, "关键词", max_pages=1)
    assert results == []


def test_search_no_api_url():
    cfg = {"name": "测试站点", "search": {}}
    results = search(cfg, "关键词")
    assert results == []


def test_search_dedup(mock_downloader):
    dup_html = SAMPLE_HTML.replace("href=\"/article/1.html\"", "href=\"http://test.gov/article/1.html\"")
    mock_downloader.fetch.return_value = FakeResponse(dup_html)
    cfg = {
        "name": "测试站点",
        "search": {"api_url": "http://test.gov/search"},
    }
    results = search(cfg, "低空经济", max_pages=1)
    urls = [r["url"] for r in results]
    assert len(urls) == len(set(urls))
