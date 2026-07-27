import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.modules["redis"] = MagicMock()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workers.parser_worker import _load_site_config, _process_message


class TestLoadSiteConfig:
    def test_valid_site(self):
        cfg = _load_site_config("czj_beijing")
        assert cfg is not None
        assert cfg["name"] == "北京市财政局"
        assert "search" in cfg
        assert "extract" in cfg

    def test_unknown_site(self):
        cfg = _load_site_config("nonexistent")
        assert cfg is None


class TestProcessMessage:
    def _make_html_msg(self, **overrides):
        msg = {
            "protocol_version": "1.0",
            "task_id": "t-001",
            "message_id": "m-001",
            "timestamp": "2026-07-27T16:00:00Z",
            "type": "html",
            "url": "https://czj.beijing.gov.cn/art/1.html",
            "site": "czj_beijing",
            "keyword": "低空经济",
            "level": 1,
            "title": "原始标题",
            "html": "<html><body><h1>政策解读标题</h1><p>正文内容正文内容正文内容正文内容正文内容正文内容正文内容正文内容正文内容正文内容正文内容正文内容正文内容正文内容正文内容正文内容正文内容正文内容正文内容正文内容</p></body></html>",
        }
        msg.update(overrides)
        return msg

    def test_task_id_preserved(self):
        msg = self._make_html_msg()
        result = _process_message(msg)
        assert result is not None
        assert result["task_id"] == "t-001"
        assert result["type"] == "result"
        assert result["message_id"] != "m-001"

    def test_site_keyword_level_preserved(self):
        msg = self._make_html_msg()
        result = _process_message(msg)
        assert result is not None
        assert result["site"] == "czj_beijing"
        assert result["keyword"] == "低空经济"
        assert result["level"] == 1
        assert result["url"] == "https://czj.beijing.gov.cn/art/1.html"

    def test_title_prefers_parsed(self):
        msg = self._make_html_msg(title="回退标题")
        result = _process_message(msg)
        assert result is not None
        assert result["title"] is not None and result["title"] != ""

    def test_title_fallback_to_msg(self):
        """When extract_title returns empty/falsy, fall back to message title."""
        with patch("workers.parser_worker.extract_title", return_value=""):
            msg = self._make_html_msg(title="回退标题")
            result = _process_message(msg)
            assert result is not None
            assert result["title"] == "回退标题"

    def test_result_has_all_v1_fields(self):
        msg = self._make_html_msg()
        result = _process_message(msg)
        assert result is not None
        required = [
            "protocol_version", "task_id", "message_id", "timestamp",
            "type", "site", "keyword", "level",
            "url", "title", "publish_date", "content", "summary",
            "score", "matched_keywords",
        ]
        for field in required:
            assert field in result, f"missing field: {field}"
        assert result["protocol_version"] == "1.0"
        assert result["type"] == "result"
        assert isinstance(result["score"], int)
        assert isinstance(result["matched_keywords"], list)

    def test_unknown_site_returns_none(self):
        msg = self._make_html_msg(site="nonexistent")
        result = _process_message(msg)
        assert result is None

    def test_empty_html_returns_none(self):
        msg = self._make_html_msg(html="")
        result = _process_message(msg)
        assert result is None

    def test_short_html_returns_none(self):
        msg = self._make_html_msg(html="<html>short</html>")
        result = _process_message(msg)
        assert result is None

    def test_parse_exception_does_not_crash(self):
        """process_message should catch extract exceptions and still return a result."""
        msg = self._make_html_msg()
        with patch("workers.parser_worker.extract_date", side_effect=Exception("parse error")):
            result = _process_message(msg)
            assert result is not None
            assert result["url"] == "https://czj.beijing.gov.cn/art/1.html"

    def test_score_exception_does_not_crash(self):
        msg = self._make_html_msg()
        with patch("workers.parser_worker.score_article", side_effect=Exception("score error")):
            result = _process_message(msg)
            assert result is not None
            assert result["score"] == 0
            assert result["matched_keywords"] == []


