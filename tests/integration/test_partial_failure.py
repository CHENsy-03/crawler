"""E2E: Partial failure -> completed_with_errors."""
import json, pytest, time
from .helpers import build_msg, URL_BASE, SEARCH_DONE_BASE, create_task
from .http_fixture import start_test_server
pytestmark = pytest.mark.e2e



class TestPartialFailure:
    def test_completed_with_errors(self, redis_client, mysql_client, task_id):
        svr = start_test_server()
        create_task(mysql_client, task_id)
        for url in ["http://127.0.0.1:18080/article/1","http://127.0.0.1:18080/article/error"]:
            u = build_msg(URL_BASE, task_id=task_id, url=url, keyword=task_id)
            redis_client.lpush("crawler:url", json.dumps(u, ensure_ascii=False))
        d = build_msg(SEARCH_DONE_BASE, task_id=task_id, keyword=task_id, url_count=2)
        redis_client.lpush("crawler:event", json.dumps(d, ensure_ascii=False))
        dl = time.time() + 30
        while time.time() < dl:
            cur = mysql_client.cursor()
            cur.execute("SELECT status,article_count FROM tasks WHERE id=%s", (task_id,))
            row = cur.fetchone()
            if row and row[0] in ("completed_with_errors","completed"):
                assert row[0] == "completed_with_errors", f"expected completed_with_errors, got {row[0]}"
                assert row[1] == 1, f"expected article_count=1, got {row[1]}"
                break
            time.sleep(0.5)
        else:
            svr.shutdown()
            pytest.fail("Task not done")
        svr.shutdown()
