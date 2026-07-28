"""E2E: All URLs succeed -> completed."""
import json, pytest, time
from .helpers import build_msg, URL_BASE, SEARCH_DONE_BASE, create_task
from .http_fixture import start_test_server
pytestmark = pytest.mark.e2e



class TestSuccessPipeline:
    def test_all_articles_stored(self, redis_client, mysql_client, task_id):
        svr = start_test_server()
        create_task(mysql_client, task_id)
        for url in [
            "http://127.0.0.1:18080/article/1",
            "http://127.0.0.1:18080/article/2",
        ]:
            u = build_msg(URL_BASE, task_id=task_id, url=url, keyword=task_id)
            redis_client.lpush("crawler:url", json.dumps(u, ensure_ascii=False))
        d = build_msg(SEARCH_DONE_BASE, task_id=task_id, keyword=task_id, url_count=2)
        redis_client.lpush("crawler:event", json.dumps(d, ensure_ascii=False))
        dl = time.time() + 30
        while time.time() < dl:
            cur = mysql_client.cursor()
            cur.execute("SELECT status FROM tasks WHERE id=%s", (task_id,))
            row = cur.fetchone()
            if row and row[0] == "completed":
                break
            time.sleep(0.5)
        else:
            svr.shutdown()
            pytest.fail("Task not completed")
        with mysql_client.cursor() as cur:
            cur.execute("SELECT article_count FROM tasks WHERE id=%s", (task_id,))
            assert cur.fetchone()[0] == 2
        svr.shutdown()

