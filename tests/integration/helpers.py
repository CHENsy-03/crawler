import json, time, uuid

def build_msg(base, **overrides):
    m = dict(base)
    m["message_id"] = uuid.uuid4().hex[:8]
    m["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    m.update(overrides)
    return m

SEARCH_DONE_BASE = {"protocol_version": "1.0", "type": "search_done", "site": "czj_beijing", "keyword": "低空经济", "url_count": 0, "level": 1}
URL_BASE = {"protocol_version": "1.0", "type": "url", "url": "http://127.0.0.1:18080/article/1", "site": "czj_beijing", "keyword": "低空经济", "level": 1, "title": ""}
HTML_BASE = {"protocol_version": "1.0", "type": "html", "url": "http://127.0.0.1:18080/article/1", "site": "czj_beijing", "keyword": "低空经济", "level": 1, "title": "", "html": ""}
ERROR_BASE = {"protocol_version": "1.0", "type": "error", "stage": "download", "site": "czj_beijing", "keyword": "低空经济", "level": 1, "url": "", "error_code": "", "error": "", "retryable": True}



def create_task(mysql_client, task_id, keyword=chr(0x4f4e)+chr(0x7a7a)+chr(0x7ecf)+chr(0x6d4e), site="czj_beijing"):
    with mysql_client.cursor() as cur:
        cur.execute(
            "INSERT INTO tasks (id,keyword,site,status,article_count) VALUES (%s,%s,%s,%s,%s)",
            (task_id, keyword, site, "created", 0))
    mysql_client.commit()
