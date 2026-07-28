import json
import logging
import os
import re
import threading
import time
import uuid

import pytest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("e2e")

# Skips all tests when E2E_ENABLED is not set
@pytest.fixture(autouse=True, scope="session")
def _skip_if_not_e2e():
    if os.getenv("E2E_ENABLED") != "1":
        pytest.skip("Set E2E_ENABLED=1 to run integration tests")

E2E_TIMEOUT = int(os.getenv("E2E_TIMEOUT", "30"))
E2E_REDIS_URL = os.getenv("E2E_REDIS_URL", "redis://localhost:6379/0")
E2E_MYSQL_DSN = os.getenv("E2E_MYSQL_DSN", "root:@tcp(localhost:3306)/crawler_db")
E2E_API_URL = os.getenv("E2E_API_URL", "http://localhost:8080")

TEST_QUEUES = ["crawler:search","crawler:url","crawler:html","crawler:result","crawler:event","crawler:error"]

def _parse_mysql_dsn(dsn):
    m = re.match(r"(?P<user>[^:]+):(?P<password>[^@]*)@tcp\((?P<host>[^:]+):(?P<port>\d+)\)/(?P<database>.+)",dsn)
    if not m: m = re.match(r"(?P<user>[^:]+):(?P<password>[^@]*)@(?P<host>[^:]+):(?P<port>\d+)/(?P<database>.+)",dsn)
    if not m: raise ValueError("Cannot parse MYSQL_DSN: "+dsn)
    return m.groupdict()

@pytest.fixture(scope="session")
def redis_client():
    import redis
    try:
        r = redis.from_url(E2E_REDIS_URL,decode_responses=True)
        r.ping()
        log.info("Redis: "+E2E_REDIS_URL)
        return r
    except Exception as e:
        pytest.fail("Redis: "+str(e))

@pytest.fixture(scope="session")
def mysql_client():
    import pymysql
    cfg = _parse_mysql_dsn(E2E_MYSQL_DSN)
    try:
        conn = pymysql.connect(host=cfg["host"],port=int(cfg["port"]),user=cfg["user"],password=cfg["password"],database=cfg["database"],charset="utf8mb4",connect_timeout=5,autocommit=True)
        log.info("MySQL: "+cfg["host"]+":"+cfg["port"]+"/"+cfg["database"])
        return conn
    except Exception as e:
        pytest.fail("MySQL: "+str(e))

@pytest.fixture
def task_id():
    return "e2e-"+uuid.uuid4().hex[:12]

@pytest.fixture(autouse=True)
def clean_queues():
    import redis
    r = redis.from_url(E2E_REDIS_URL,decode_responses=True)
    for q in TEST_QUEUES: r.delete(q)
    yield
    for q in TEST_QUEUES: r.delete(q)

def push_message(r,queue,msg):
    r.lpush(queue,json.dumps(msg,ensure_ascii=False))

def pop_message(r,queue,timeout=3):
    result = r.brpop(queue,timeout=timeout)
    return json.loads(result[1]) if result else None

def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: e2e integration test")
