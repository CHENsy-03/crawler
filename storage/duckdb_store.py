# DuckDB optional storage module
try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False


def init_db(db_path='crawler_analytics.duckdb'):
    if not HAS_DUCKDB:
        return None
    conn = duckdb.connect(db_path)
    conn.execute('CREATE TABLE IF NOT EXISTS articles ('
                 'id INTEGER PRIMARY KEY, title VARCHAR, url VARCHAR UNIQUE, '
                 'content TEXT, province VARCHAR, publish_time VARCHAR, score INTEGER)')
    return conn


def save_to_duckdb(conn, articles, province=''):
    if not HAS_DUCKDB or conn is None:
        return 0
    count = 0
    for a in articles:
        try:
            conn.execute(
                'INSERT OR IGNORE INTO articles (title,url,content,province,publish_time,score) '
                'VALUES (?,?,?,?,?,?)',
                [a.get('title', ''), a.get('url', ''),
                 str(a.get('content', ''))[:1000],
                 province, a.get('publish_date', ''), a.get('score', 0)])
            count += 1
        except Exception:
            log.debug('save_to_duckdb: skip duplicate url=%s', a.get('url','')[:60])
    conn.commit()
    return count
