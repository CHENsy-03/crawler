"""E2E: Empty search returns completed with Expected=0."""
import json, pytest, time
from .helpers import build_msg, SEARCH_DONE_BASE, create_task

pytestmark = pytest.mark.e2e


class TestEmptySearch:
    def test_returns_completed(self, redis_client, mysql_client, task_id):
        """SearchDone(url_count=0) -> completed, Expected=0."""
        create_task(mysql_client, task_id)
        msg = build_msg(SEARCH_DONE_BASE, task_id=task_id, url_count=0)
        redis_client.lpush("crawler:event", json.dumps(msg, ensure_ascii=False))
        deadline = time.time() + 30
        while time.time() < deadline:
            with mysql_client.cursor() as cur:
                cur.execute("SELECT status,article_count FROM tasks WHERE id=%s", (task_id,))
                row = cur.fetchone()
            if row and row[0] == "completed":
                assert row[1] == 0
                return
            time.sleep(0.5)
        pytest.fail("Task not completed within 30s")

    def test_no_articles(self, redis_client, mysql_client, task_id):
        """Empty search creates no articles."""
        create_task(mysql_client, task_id)
        msg = build_msg(SEARCH_DONE_BASE, task_id=task_id, url_count=0)
        redis_client.lpush("crawler:event", json.dumps(msg, ensure_ascii=False))
        deadline = time.time() + 30
        while time.time() < deadline:
            with mysql_client.cursor() as cur:
                cur.execute("SELECT status FROM tasks WHERE id=%s", (task_id,))
                row = cur.fetchone()
            if row and row[0] == "completed":
                # articles table has no task_id column; article_count=0 from task record confirms empty
                with mysql_client.cursor() as cur:
                    cur.execute("SELECT article_count FROM tasks WHERE id=%s", (task_id,))
                    assert cur.fetchone()[0] == 0
                return
            time.sleep(0.5)
        pytest.fail("Task not completed within 30s")

    def test_no_errors(self, redis_client, mysql_client, task_id):
        """Empty search creates no error messages."""
        create_task(mysql_client, task_id)
        msg = build_msg(SEARCH_DONE_BASE, task_id=task_id, url_count=0)
        redis_client.lpush("crawler:event", json.dumps(msg, ensure_ascii=False))
        deadline = time.time() + 30
        while time.time() < deadline:
            with mysql_client.cursor() as cur:
                cur.execute("SELECT status FROM tasks WHERE id=%s", (task_id,))
                row = cur.fetchone()
            if row and row[0] == "completed":
                assert redis_client.llen("crawler:error") == 0
                return
            time.sleep(0.5)
        pytest.fail("Task not completed within 30s")
