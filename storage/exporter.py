import csv
import json
import logging
from pathlib import Path
from datetime import datetime

log = logging.getLogger('storage.exporter')

try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False


class DuckDBExporter:
    def __init__(self, db_path='output/crawler.duckdb'):
        if not HAS_DUCKDB:
            raise ImportError('duckdb not installed')
        self.conn = duckdb.connect(db_path)

    def to_csv(self, output_path=None, keyword=None, site=None, limit=10000):
        sql = 'SELECT * FROM articles WHERE 1=1'
        params = []
        if keyword:
            sql += ' AND (title LIKE ? OR keyword LIKE ?)'
            params.extend(['%' + keyword + '%', '%' + keyword + '%'])
        if site:
            sql += ' AND site = ?'
            params.append(site)
        sql += ' ORDER BY crawl_time DESC LIMIT ?'
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        cols = [d[0] for d in self.conn.execute(sql, params).description]

        if not output_path:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f'export_{ts}.csv'
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        log.info('Exported %d rows to CSV: %s', len(rows), output_path)
        return output_path

    def to_json(self, output_path=None, keyword=None, site=None, limit=10000):
        sql = 'SELECT * FROM articles WHERE 1=1'
        params = []
        if keyword:
            sql += ' AND (title LIKE ? OR keyword LIKE ?)'
            params.extend(['%' + keyword + '%', '%' + keyword + '%'])
        if site:
            sql += ' AND site = ?'
            params.append(site)
        sql += ' ORDER BY crawl_time DESC LIMIT ?'
        params.append(limit)

        result = self.conn.execute(sql, params)
        cols = [d[0] for d in result.description]
        rows = [dict(zip(cols, row)) for row in result.fetchall()]

        if not output_path:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f'export_{ts}.json'
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=2, default=str)
        log.info('Exported %d rows to JSON: %s', len(rows), output_path)
        return output_path

    def to_excel(self, output_path=None, keyword=None, site=None, limit=10000):
        try:
            from openpyxl import Workbook
        except ImportError:
            raise ImportError('openpyxl not installed. Run: pip install openpyxl')

        sql = 'SELECT * FROM articles WHERE 1=1'
        params = []
        if keyword:
            sql += ' AND (title LIKE ? OR keyword LIKE ?)'
            params.extend(['%' + keyword + '%', '%' + keyword + '%'])
        if site:
            sql += ' AND site = ?'
            params.append(site)
        sql += ' ORDER BY crawl_time DESC LIMIT ?'
        params.append(limit)

        result = self.conn.execute(sql, params)
        cols = [d[0] for d in result.description]
        rows = result.fetchall()

        if not output_path:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f'export_{ts}.xlsx'
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        wb = Workbook()
        ws = wb.active
        ws.title = 'articles'
        ws.append(cols)
        for row in rows:
            ws.append([str(v) if v is not None else '' for v in row])
        wb.save(output_path)
        log.info('Exported %d rows to Excel: %s', len(rows), output_path)
        return output_path

    def close(self):
        self.conn.close()
