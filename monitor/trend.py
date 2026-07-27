import logging

log = logging.getLogger('monitor.trend')

try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False


def _connect(db_path='output/crawler.duckdb'):
    if not HAS_DUCKDB:
        return None
    return duckdb.connect(db_path)


def keyword_trend(keyword, db_path='output/crawler.duckdb'):
    conn = _connect(db_path)
    if not conn:
        return []
    try:
        return conn.execute(
            'SELECT keyword, COUNT(*) as cnt, AVG(score) as avg_score FROM articles WHERE keyword LIKE ? GROUP BY keyword ORDER BY cnt DESC',
            ['%' + keyword + '%']).fetchall()
    finally:
        conn.close()


def province_ranking(db_path='output/crawler.duckdb'):
    conn = _connect(db_path)
    if not conn:
        return []
    try:
        return conn.execute(
            'SELECT province, COUNT(*) as cnt, AVG(score) as avg_score FROM articles GROUP BY province ORDER BY cnt DESC'
        ).fetchall()
    finally:
        conn.close()


def site_summary(db_path='output/crawler.duckdb'):
    conn = _connect(db_path)
    if not conn:
        return []
    try:
        return conn.execute(
            'SELECT site, COUNT(*) as total, SUM(CASE WHEN detail_fetched THEN 1 ELSE 0 END) as with_detail, AVG(score) as avg_score FROM articles GROUP BY site ORDER BY total DESC'
        ).fetchall()
    finally:
        conn.close()


def daily_summary(db_path='output/crawler.duckdb'):
    conn = _connect(db_path)
    if not conn:
        return []
    try:
        return conn.execute(
            'SELECT DATE(crawl_time) as day, COUNT(*) as cnt, AVG(score) as avg_score FROM articles GROUP BY day ORDER BY day DESC LIMIT 30'
        ).fetchall()
    finally:
        conn.close()
