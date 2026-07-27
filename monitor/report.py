import os
import json
import logging
from datetime import datetime

log = logging.getLogger('monitor.report')

try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False


def daily_report(db_path='output/crawler.duckdb', output_dir=None):
    if not HAS_DUCKDB:
        return {}
    conn = duckdb.connect(db_path)
    try:
        total = conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
        by_site = {r[0]: r[1] for r in conn.execute(
            'SELECT site, COUNT(*) FROM articles GROUP BY site ORDER BY COUNT(*) DESC').fetchall()}
        by_keyword = {r[0]: r[1] for r in conn.execute(
            'SELECT keyword, COUNT(*) FROM articles GROUP BY keyword ORDER BY COUNT(*) DESC').fetchall()}
        avg_score = conn.execute('SELECT AVG(score) FROM articles').fetchone()[0] or 0
        recent = conn.execute(
            'SELECT title, url, site, score FROM articles ORDER BY crawl_time DESC LIMIT 10').fetchall()

        report = {
            'generated': datetime.now().isoformat(),
            'total_articles': total,
            'by_site': by_site,
            'by_keyword': by_keyword,
            'avg_score': round(avg_score, 1),
            'recent_articles': [{'title': r[0], 'url': r[1], 'site': r[2], 'score': r[3]} for r in recent],
        }

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            path = os.path.join(output_dir, f'report_{datetime.now().strftime("%Y%m%d")}.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            log.info('Daily report saved: %s', path)

        return report
    finally:
        conn.close()


def trend_summary(db_path='output/crawler.duckdb'):
    if not HAS_DUCKDB:
        return {}
    conn = duckdb.connect(db_path)
    try:
        return {
            'keyword_trends': conn.execute(
                'SELECT keyword, COUNT(*) as cnt, AVG(score) as avg_score FROM articles GROUP BY keyword ORDER BY cnt DESC LIMIT 10'
            ).fetchall(),
            'province_ranking': conn.execute(
                'SELECT province, COUNT(*) as cnt FROM articles GROUP BY province ORDER BY cnt DESC'
            ).fetchall(),
            'daily_stats': conn.execute(
                'SELECT DATE(crawl_time) as day, COUNT(*) as cnt FROM articles GROUP BY day ORDER BY day DESC LIMIT 7'
            ).fetchall(),
        }
    finally:
        conn.close()
