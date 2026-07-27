import logging
import hashlib
from pathlib import Path
from datetime import datetime
import json, csv

log = logging.getLogger('storage.manager')

try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False

try:
    from storage.mysql_store import MySQLStore, MYSQL_OK
except ImportError:
    MYSQL_OK = False


class StorageManager:
    """Unified storage: DuckDB(primary). Pipeline only calls save()/query()."""

    def __init__(self, output_dir='output', prefix='result', use_mysql=False):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.prefix = prefix
        self.ts = datetime.now().strftime('%Y%m%d_%H%M%S')

        self.duck_conn = None
        if HAS_DUCKDB:
            try:
                db_path = str(self.output_dir / 'crawler.duckdb')
                self.duck_conn = duckdb.connect(db_path)
                self.duck_conn.execute('''CREATE TABLE IF NOT EXISTS articles (
                    url TEXT PRIMARY KEY,
                    title TEXT,
                    summary TEXT,
                    content TEXT,
                    province TEXT,
                    publish_time VARCHAR,
                    site VARCHAR,
                    keyword VARCHAR,
                    crawl_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    score INTEGER DEFAULT 0,
                    matched_keywords VARCHAR,
                    detail_fetched BOOLEAN DEFAULT FALSE,
                    status INTEGER DEFAULT 0
                )''')
                self.duck_conn.execute('ALTER TABLE articles ADD COLUMN IF NOT EXISTS url_hash VARCHAR(32)')
                self.duck_conn.execute('ALTER TABLE articles ADD COLUMN IF NOT EXISTS matched_keyword VARCHAR(200)')
                self.duck_conn.execute('''CREATE TABLE IF NOT EXISTS crawl_log (
                    url TEXT,
                    status INTEGER,
                    cost_ms INTEGER DEFAULT 0,
                    retry INTEGER DEFAULT 0,
                    error TEXT,
                    crawl_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
                self.duck_conn.execute('ALTER TABLE crawl_log ADD COLUMN IF NOT EXISTS error_type VARCHAR(20)')
                self.duck_conn.execute('''CREATE TABLE IF NOT EXISTS statistics (
                    id INTEGER PRIMARY KEY,
                    date DATE UNIQUE,
                    total_articles INTEGER DEFAULT 0,
                    total_requests INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    avg_latency_ms REAL DEFAULT 0,
                    top_keyword VARCHAR,
                    top_site VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
                self.duck_conn.execute('''CREATE TABLE IF NOT EXISTS task (
                    id TEXT PRIMARY KEY,
                    keyword TEXT,
                    site TEXT,
                    status TEXT DEFAULT 'created',
                    article_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
                self.duck_conn.execute('CREATE INDEX IF NOT EXISTS idx_publish_time ON articles(publish_time)')
                self.duck_conn.execute('CREATE INDEX IF NOT EXISTS idx_keyword ON articles(keyword)')
                self.duck_conn.execute('CREATE INDEX IF NOT EXISTS idx_score ON articles(score)')
                log.info('DuckDB connected: %s', db_path)
            except Exception as e:
                log.warning('DuckDB init failed: %s', e)
                self.duck_conn = None

        self.mysql = None
        if use_mysql and MYSQL_OK:
            try:
                self.mysql = MySQLStore()
                self.mysql.connect()
                log.info('MySQL connected')
            except Exception as e:
                log.warning('MySQL init failed: %s', e)

    def save(self, articles):
        """Primary save: DuckDB (unique source of truth)."""
        count = len(articles) if articles else 0
        if self.duck_conn and articles:
            try:
                before = self.duck_conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
                sql = 'INSERT OR IGNORE INTO articles (url,url_hash,title,summary,content,publish_time,site,keyword,score,matched_keywords,matched_keyword,detail_fetched,source_type) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)'
                values = [[a.get('url', ''),
                           hashlib.md5(a.get('url','').encode()).hexdigest(),
                           a.get('title', ''),
                           str(a.get('summary', ''))[:500],
                           str(a.get('content', ''))[:10000],
                           a.get('publish_date', ''), a.get('site', a.get('source', '')),
                           (a.get('source_keywords') or [''])[0],
                           a.get('score', 0),
                           ';'.join(a.get('matched_keywords', [])),
                           a.get('matched_keyword', ''),
                           bool(a.get('content', '')),
                           a.get('search_type', '')] for a in articles]
                self.duck_conn.executemany(sql, values)
                self.duck_conn.commit()
                after = self.duck_conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
                count = after - before
                log.info('DuckDB: saved %d/%d articles', count, len(articles))
            except Exception as e:
                log.warning('DuckDB save error: %s', e)
                count = 0

        if self.mysql and articles:
            try:
                self.mysql.insert_articles_batch(articles)
                log.info('MySQL: saved %d articles', count)
            except Exception as e:
                log.warning('MySQL save error: %s', e)

        return count

    def export_json(self, articles=None):
        """On-demand JSON export."""
        return self._save_json(articles) if articles else None

    def export_csv(self, articles=None):
        """On-demand CSV export."""
        return self._save_csv(articles) if articles else None

    def log_crawl(self, url, http_status, cost_ms=0, retry=0, error=None):
        error_type = _classify_error(http_status, error)
        if self.duck_conn:
            try:
                self.duck_conn.execute(
                    'INSERT INTO crawl_log (url,status,cost_ms,retry,error,error_type) VALUES (?,?,?,?,?,?)',
                    [url, http_status, cost_ms, retry, str(error)[:500] if error else None, error_type])
            except Exception as e:
                log.debug('log_crawl: %s', e)

    def save_task(self, task_id, keyword, site, status='created'):
        if self.duck_conn:
            try:
                self.duck_conn.execute(
                    'INSERT OR REPLACE INTO task (id,keyword,site,status) VALUES (?,?,?,?)',
                    [task_id, keyword, site, status])
            except Exception as e:
                log.warning('save_task: %s', e)

    def query(self, keyword=None, site=None, min_score=0, limit=50):
        """Query articles from DuckDB."""
        if not self.duck_conn:
            return []
        sql = 'SELECT * FROM articles WHERE score >= ?'
        params = [min_score]
        if keyword:
            sql += ' AND (title LIKE ? OR keyword LIKE ?)'
            params.extend(['%' + keyword + '%', '%' + keyword + '%'])
        if site:
            sql += ' AND site = ?'
            params.append(site)
        sql += ' ORDER BY score DESC, crawl_time DESC LIMIT ?'
        params.append(limit)
        try:
            result = self.duck_conn.execute(sql, params)
            cols = [d[0] for d in result.description]
            return [dict(zip(cols, row)) for row in result.fetchall()]
        except Exception as e:
            log.warning('Query error: %s', e)
            return []

    def statistics(self):
        if not self.duck_conn:
            return {}
        try:
            total = self.duck_conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
            by_site = {r[0]: r[1] for r in self.duck_conn.execute('SELECT site, COUNT(*) FROM articles GROUP BY site ORDER BY COUNT(*) DESC').fetchall()}
            avg_score = self.duck_conn.execute('SELECT AVG(score) FROM articles').fetchone()[0] or 0
            date_range = self.duck_conn.execute('SELECT MIN(publish_time), MAX(publish_time) FROM articles').fetchone()
            return {'total_articles': total, 'by_site': by_site, 'avg_score': round(avg_score,1),
                    'date_range': {'from': date_range[0], 'to': date_range[1]} if date_range else {}}
        except Exception as e:
            log.warning('Statistics error: %s', e)
            return {}

    def query_articles(self, keyword=None, site=None, min_score=0, limit=50):
        return self.query(keyword=keyword, site=site, min_score=min_score, limit=limit)

    def get_statistics(self):
        return self.statistics()

    def search_keyword(self, keyword, limit=50):
        if not self.duck_conn:
            return []
        try:
            result = self.duck_conn.execute(
                'SELECT url, title, site, keyword, score, publish_time FROM articles WHERE title LIKE ? OR keyword LIKE ? ORDER BY score DESC LIMIT ?',
                ['%' + keyword + '%', '%' + keyword + '%', limit])
            cols = [d[0] for d in result.description]
            return [dict(zip(cols, row)) for row in result.fetchall()]
        except Exception as e:
            log.warning('search_keyword error: %s', e)
            return []

    def statistics(self):
        """Get storage statistics."""
        if not self.duck_conn:
            return {}
        try:
            total = self.duck_conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
            by_site = {r[0]: r[1] for r in self.duck_conn.execute(
                'SELECT site, COUNT(*) FROM articles GROUP BY site ORDER BY COUNT(*) DESC').fetchall()}
            avg_score = self.duck_conn.execute('SELECT AVG(score) FROM articles').fetchone()[0] or 0
            date_range = self.duck_conn.execute(
                'SELECT MIN(publish_time), MAX(publish_time) FROM articles').fetchone()
            return {
                'total_articles': total,
                'by_site': by_site,
                'avg_score': round(avg_score, 1),
                'date_range': {'from': date_range[0], 'to': date_range[1]} if date_range else {},
            }
        except Exception as e:
            log.warning('Statistics error: %s', e)
            return {}

    def _save_json(self, articles):
        fp = self.output_dir / f'{self.prefix}_{self.ts}.json'
        log.info('Export JSON: %s', fp)
        with open(fp, 'w', encoding='utf-8') as f:
            json.dump(articles or [], f, ensure_ascii=False, indent=2)
        return fp

    def _save_csv(self, articles):
        fp = self.output_dir / f'{self.prefix}_{self.ts}.csv'
        log.info('Export CSV: %s', fp)
        fields = ['title', 'url', 'publish_date', 'source', 'score', 'matched_keywords', 'summary', 'content']
        with open(fp, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            w.writeheader()
            for a in (articles or []):
                row = {k: a.get(k, '') for k in fields}
                if isinstance(row.get('matched_keywords'), list):
                    row['matched_keywords'] = ';'.join(row['matched_keywords'])
                w.writerow(row)
        return fp

    def close(self):
        if self.duck_conn:
            self.duck_conn.close()
        if self.mysql:
            self.mysql.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
def _classify_error(http_status, error):
    if http_status == 429 or (error and 'rate' in str(error).lower()):
        return 'rate_limit'
    if http_status in (0, -1) or (error and any(k in str(error).lower() for k in ('timeout','connection','dns','refused'))):
        return 'network'
    if http_status == 403:
        return 'forbidden'
    if http_status >= 500:
        return 'server_error'
    if http_status >= 400:
        return 'client_error'
    return 'unknown'
