"""Legacy JPAAS plugin behavior tests after shared parser extraction."""

from unittest.mock import patch

from plugins import jpaas


class FakeDownloader:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def get_json(self, url, params, site_cfg):
        self.calls.append((url, params))
        return self.result


def test_legacy_jpaas_plugin_output_is_preserved():
    result = {
        "code": "200",
        "data": {
            "appSearchResultBeanList": [
                {
                    "mapSearchResult": {
                        "items": [{"data": {"title": "标题", "url": "http://example.gov.cn/a", "content": "正文"}}]
                    }
                },
                {"title": "第二", "url": "/b", "content_556463": "第二正文", "date": "2026-01-01"},
            ]
        },
    }
    dl = FakeDownloader(result)
    with patch("plugins.jpaas._get_dl", return_value=dl):
        articles = jpaas.search(
            {"name": "测试财政局", "search": {"api_url": "https://api.example", "params": {"webId": "3217"}}},
            "低空经济",
            max_pages=1,
        )
    assert len(articles) == 2
    assert articles[0]["title"] == "标题"
    assert articles[0]["url"] == "https://example.gov.cn/a"
    assert articles[0]["summary"] == "正文"
    assert articles[0]["source_keywords"] == ["低空经济"]
    assert articles[1]["province"] == "测试"
    assert articles[1]["publish_date"] == "2026-01-01"
    assert dl.calls[0][1]["_cus_eq_webid"] == "3217"
