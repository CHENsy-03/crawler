"""E2E: All URLs fail -> failed."""
import json, pytest, time
from .helpers import build_msg, URL_BASE, SEARCH_DONE_BASE, ERROR_BASE, create_task
from .http_fixture import start_test_server
pytestmark = pytest.mark.e2e



class TestAllFailed:
    def test_failed_status(self, redis_client, mysql_client, task_id):
        svr = start_test_server()
        create_task(mysql_client, task_id)
        for url in ["http://127.0.0.1:18080/article/error","http://127.0.0.1:18080/article/error2"]:
            u = build_msg(URL_BASE, task_id=task_id, url=url, keyword=task_id)
            redis_client.lpush("crawler:url", json.dumps(u, ensure_ascii=False))
        d = build_msg(SEARCH_DONE_BASE, task_id=task_id, keyword=task_id, url_count=2)
        redis_client.lpush("crawler:event", json.dumps(d, ensure_ascii=False))
        dl = time.time() + 30
        while time.time() < dl:
            cur = mysql_client.cursor()
            cur.execute("SELECT status FROM tasks WHERE id=%s", (task_id,))
            row = cur.fetchone()
            if row and row[0] == "failed":
                svr.shutdown()
                break
            time.sleep(0.5)
        else:
            svr.shutdown()
            pytest.fail("Task not failed")
    def test_duplicate_error_idempotent(self, redis_client, mysql_client, task_id):
        svr = start_test_server()
        create_task(mysql_client, task_id)
        u = build_msg(URL_BASE, task_id=task_id, url="http://127.0.0.1:18080/article/error")
        redis_client.lpush("crawler:url", json.dumps(u, ensure_ascii=False))
        e = build_msg(ERROR_BASE, task_id=task_id, keyword=task_id,
            url="http://127.0.0.1:18080/article/error")
        for _ in range(2):
            redis_client.lpush("crawler:error", json.dumps(e, ensure_ascii=False))
        d = build_msg(SEARCH_DONE_BASE, task_id=task_id, keyword=task_id, url_count=1)
        redis_client.lpush("crawler:event", json.dumps(d, ensure_ascii=False))
        dl = time.time() + 30
        while time.time() < dl:
            cur = mysql_client.cursor()
            cur.execute("SELECT status, article_count FROM tasks WHERE id=%s", (task_id,))
            row = cur.fetchone()
            if row and row[0]=="failed":
                assert row[1] == 0
                svr.shutdown()
                break
            time.sleep(0.5)
        else:
            svr.shutdown()
            pytest.fail("Task not failed")
