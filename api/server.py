import json, os, logging, threading

try:
    from fastapi import FastAPI, Query, HTTPException
    from fastapi.responses import PlainTextResponse
    from pydantic import BaseModel
    FASTAPI_OK = True
except ImportError:
    FASTAPI_OK = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('api')

from parser.html_parser import extract_title, extract_date, extract_content
from extractor.scorer import score_article
from monitor.metrics import get_collector


def _load_sites():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, 'config', 'site.json'), 'r', encoding='utf-8') as f:
        return json.load(f)


if FASTAPI_OK:
    app = FastAPI(title='Crawler API v2.0', description='Parser Service')

    class ParseRequest(BaseModel):
        url: str = ''
        html: str = ''

    @app.post('/parse')
    async def parse_html(req: ParseRequest):
        if not req.html or len(req.html) < 100:
            raise HTTPException(400, 'HTML content required (min 100 chars)')
        title = extract_title(req.html)
        date = extract_date(req.html)
        content = extract_content(req.html)
        result = score_article({'title': title, 'content': content, 'url': req.url}, ('',))
        collector = get_collector()
        collector.inc('parse_total')
        collector.inc('parse_success')
        return {
            'url': req.url, 'title': title, 'publish_date': date,
            'content': content[:500], 'content_len': len(content), 'score': result['score'],
        }

    @app.get('/health')
    async def health():
        return {'status': 'ok'}

    @app.get('/ready')
    async def ready():
        return {'status': 'ready'}

    @app.get('/sites')
    async def list_sites():
        sites = _load_sites()
        return [{'key': k, 'name': v['name'], 'domain': v['domain']} for k, v in sites.items()]

    @app.get('/articles')
    async def query_articles(keyword: str = Query(None), site: str = Query(None), limit: int = Query(50)):
        from storage.manager import StorageManager
        store = StorageManager()
        result = store.query_articles(keyword=keyword, site=site, limit=limit)
        store.close()
        return {'count': len(result), 'articles': [{k: v for k, v in a.items() if k != 'content'} for a in result]}

    @app.get('/tasks')
    async def list_tasks(limit: int = Query(20)):
        from storage.manager import StorageManager
        store = StorageManager()
        if store.duck_conn:
            result = store.duck_conn.execute(
                'SELECT id, keyword, site, status, article_count, created_at FROM task ORDER BY created_at DESC LIMIT ?', [limit]
            ).fetchall()
            cols = ['id', 'keyword', 'site', 'status', 'article_count', 'created_at']
            tasks = [dict(zip(cols, [str(v) for v in row])) for row in result]
        else:
            tasks = []
        store.close()
        return {'count': len(tasks), 'tasks': tasks}

    @app.get('/statistics')
    async def get_statistics():
        from storage.manager import StorageManager
        store = StorageManager()
        stats = store.get_statistics()
        store.close()
        return stats

    @app.get('/metrics')
    async def metrics():
        collector = get_collector()
        return PlainTextResponse(collector.dump_prometheus(), media_type='text/plain')

    @app.on_event('startup')
    async def startup_parser_worker():
        if os.environ.get('PARSER_WORKER_ENABLED', '').lower() not in ('1', 'true'):
            log.info('Parser worker disabled (env PARSER_WORKER_ENABLED != true)')
            return
        threading.Thread(target=_run_parser_worker, daemon=True).start()
        log.info('Parser worker started (bg)')

else:
    app = None


def _run_parser_worker():
    import time
    try:
        import redis as _redis
    except ImportError:
        log.warning('redis-py not installed, parser worker disabled')
        return
    r = _redis.Redis(host='localhost', port=6379, decode_responses=True)
    log.info('Parser worker listening on crawler:html')
    while True:
        try:
            result = r.brpop('crawler:html', timeout=5)
            if result is None:
                continue
            _, data = result
            payload = json.loads(data)
            url = payload.get('url', '')
            html = payload.get('html', '')
            title = payload.get('title', '')
            if not html or len(html) < 100:
                continue
            parsed_title = extract_title(html) or title
            parsed_date = extract_date(html)
            parsed_content = extract_content(html)
            score_result = score_article({'title': parsed_title, 'content': parsed_content, 'url': url}, ('',))
            result_payload = json.dumps({
                'url': url, 'title': parsed_title, 'publish_date': parsed_date,
                'content': parsed_content, 'score': score_result['score'],
            }, ensure_ascii=False)
            r.lpush('crawler:result', result_payload)
            collector = get_collector()
            collector.inc('parse_total')
            collector.inc('parse_success')
            log.info('PARSED -> result_queue: %s (%d chars)', parsed_title[:50], len(parsed_content or ''))
        except Exception as e:
            log.error('Parser worker error: %s', e)
            time.sleep(2)


def create_app():
    return app
