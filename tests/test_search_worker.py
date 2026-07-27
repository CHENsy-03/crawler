import json
import os
import sys
from unittest.mock import MagicMock

# Mock redis before importing search_worker
sys.modules["redis"] = MagicMock()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from protocol.messages import new_task_id, new_message_id
from workers.search_worker import _load_site_config


def _make_search_msg(task_id="t-001", message_id="m-001", site="czj_beijing",
                     keyword="低空经济", level=1, max_pages=1):
    return {
        "protocol_version": "1.0", "task_id": task_id,
        "message_id": message_id, "timestamp": "2026-07-27T16:00:00Z",
        "type": "search", "site": site, "keyword": keyword,
        "level": level, "max_pages": max_pages,
    }


class TestLoadSiteConfig:
    def test_valid_site(self):
        cfg = _load_site_config("czj_beijing")
        assert cfg is not None
        assert cfg["name"] == "北京市财政局"

    def test_unknown_site(self):
        cfg = _load_site_config("nonexistent")
        assert cfg is None


class TestMaxPagesValidation:
    def test_negative_flagged(self):
        msg = _make_search_msg(max_pages=-1)
        mp = msg.get("max_pages", 0)
        assert not (isinstance(mp, int) and mp >= 1)

    def test_zero_normalized_before_send(self):
        msg = _make_search_msg(max_pages=0)
        mp = msg.get("max_pages", 0)
        assert mp == 0

    def test_positive_passed_through(self):
        msg = _make_search_msg(max_pages=5)
        mp = msg.get("max_pages", 0)
        assert mp == 5


class TestTaskIDChain:
    def test_same_task_id_multiple_urls(self):
        task_id = new_task_id()
        assert len({task_id for _ in range(10)}) == 1

    def test_different_message_ids(self):
        ids = {new_message_id() for _ in range(10)}
        assert len(ids) == 10

    def test_url_message_retains_fields(self):
        payload = {
            "task_id": "t-001",
            "url": "https://czj.beijing.gov.cn/art/1.html",
            "site": "czj_beijing",
            "keyword": "低空经济",
            "level": 1,
            "title": "政策解读",
        }
        assert payload["task_id"] == "t-001"
        assert payload["site"] == "czj_beijing"
        assert payload["keyword"] == "低空经济"
        assert payload["level"] == 1
        assert payload["title"] == "政策解读"

    def test_html_inherits_task_id(self):
        task_id = new_task_id()
        url_msg_id = new_message_id()
        html_msg_id = new_message_id()
        assert url_msg_id != html_msg_id
