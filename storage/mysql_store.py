import os
import logging
from datetime import datetime

log = logging.getLogger('storage.mysql')

try:
    import pymysql
    MYSQL_OK = True
except ImportError:
    MYSQL_OK = False


class MySQLStore:
    def __init__(self, host=None, port=3306, user='root', password='', database='crawler_db'):
        if not MYSQL_OK:
            raise ImportError('pymysql not installed. Run: pip install pymysql')
        self.host = host or os.environ.get('MYSQL_HOST', 'localhost')
        self.port = int(os.environ.get('MYSQL_PORT', port))
        self.user = os.environ.get('MYSQL_USER', user)
        self.password = os.environ.get('MYSQL_PASSWORD', password)
        self.database = os.environ.get('MYSQL_DATABASE', database)
        self.conn = None

    def connect(self):
        self.conn = pymysql.connect(
            host=self.host, port=self.port, user=self.user,
            password=self.password, database=self.database,
            charset='utf8mb4', autocommit=True
        )

    def close(self):
        if self.conn:
            self.conn.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    def insert_article(self, article):
        sql = '''INSERT INTO article (url, title, summary, content, province, site, keyword, publish_time, score, matched_keywords, detail_fetched, status)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                 ON DUPLICATE KEY UPDATE score=VALUES(score), crawl_time=CURRENT_TIMESTAMP'''
        pub_time = article.get('publish_date') or None
        if pub_time and len(pub_time) == 10:
            pub_time = pub_time + ' 00:00:00'
        with self.conn.cursor() as cur:
            cur.execute(sql, (
                article.get('url', ''),
                article.get('title', '')[:500],
                str(article.get('summary', ''))[:500],
                article.get('content', ''),
                article.get('source', ''),
                article.get('source', ''),
                (article.get('source_keywords') or [''])[0],
                pub_time,
                article.get('score', 0),
                ';'.join(article.get('matched_keywords', [])),
                bool(article.get('content', '')),
                0,
            ))

    def insert_task(self, task_id, keyword, site, status='created'):
        sql = '''INSERT INTO task (id, keyword, site, status)
                 VALUES (%s, %s, %s, %s)
                 ON DUPLICATE KEY UPDATE status=VALUES(status)'''
        with self.conn.cursor() as cur:
            cur.execute(sql, (task_id, keyword, site, status))

    def update_task(self, task_id, status, article_count=0):
        sql = 'UPDATE task SET status=%s, article_count=%s WHERE id=%s'
        with self.conn.cursor() as cur:
            cur.execute(sql, (status, article_count, task_id))

    def insert_crawl_log(self, url, status, cost_ms=0, error=None):
        sql = 'INSERT INTO crawl_log (url, status, cost_ms, error) VALUES (%s, %s, %s, %s)'
        with self.conn.cursor() as cur:
            cur.execute(sql, (url, status, cost_ms, error[:1000] if error else None))

    def insert_articles_batch(self, articles):
        if not articles:
            return 0
        sql = '''INSERT INTO article (url, title, summary, content, province, site, keyword, publish_time, score, matched_keywords, detail_fetched, status)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                 ON DUPLICATE KEY UPDATE score=VALUES(score), crawl_time=CURRENT_TIMESTAMP'''
        values = []
        for a in articles:
            pub_time = a.get('publish_date') or None
            if pub_time and len(pub_time) == 10:
                pub_time = pub_time + ' 00:00:00'
            values.append((
                a.get('url', ''), a.get('title', '')[:500],
                str(a.get('summary', ''))[:500], str(a.get('content', '')),
                a.get('source', ''), a.get('source', ''),
                (a.get('source_keywords') or [''])[0],
                pub_time, a.get('score', 0),
                ';'.join(a.get('matched_keywords', [])),
                bool(a.get('content', '')), 0,
            ))
        with self.conn.cursor() as cur:
            cur.executemany(sql, values)
        return len(values)

    def query_articles(self, keyword=None, limit=50):
        if keyword:
            sql = 'SELECT title, url, source, publish_time, score FROM article WHERE title LIKE %s ORDER BY score DESC LIMIT %s'
            with self.conn.cursor() as cur:
                cur.execute(sql, ('%' + keyword + '%', limit))
                return [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
        sql = 'SELECT title, url, source, publish_time, score FROM article ORDER BY created_at DESC LIMIT %s'
        with self.conn.cursor() as cur:
            cur.execute(sql, (limit,))
            return [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
