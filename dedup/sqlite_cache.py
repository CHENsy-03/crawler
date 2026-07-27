import sqlite3, hashlib, os, logging
log = logging.getLogger('crawler.dedup')


class DedupDB:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output', 'crawler.db')
        self.db_path = os.path.abspath(db_path)
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute(('CREATE TABLE IF NOT EXISTS crawled ('
                          'url_hash TEXT PRIMARY KEY, url TEXT NOT NULL, title TEXT, '
                          'crawl_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, score INTEGER DEFAULT 0)'))
        self.conn.commit()

    def _url_hash(self, url):
        return hashlib.md5(url.encode('utf-8')).hexdigest()

    def is_duplicate(self, url):
        h = self._url_hash(url)
        return self.conn.execute('SELECT 1 FROM crawled WHERE url_hash = ?', (h,)).fetchone() is not None

    def mark_crawled(self, url, title='', score=0):
        self.conn.execute('INSERT OR IGNORE INTO crawled VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)',
                          (self._url_hash(url), url, title[:200], score))
        self.conn.commit()

    def dedup_list(self, articles):
        result = []
        for a in articles:
            url = a.get('url', '')
            if url and not self.is_duplicate(url):
                self.mark_crawled(url, a.get('title', ''), a.get('score', 0))
                result.append(a)
        return result

    def close(self):
        if hasattr(self, 'conn'):
            self.conn.close()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()
