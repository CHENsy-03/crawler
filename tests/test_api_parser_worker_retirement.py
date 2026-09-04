"""Regression tests for retirement of api/server.py inline Redis parser."""

import asyncio
import importlib
from pathlib import Path

import pytest

pytest.importorskip("fastapi")


ROOT = Path(__file__).resolve().parents[1]
API_SOURCE = (ROOT / "api" / "server.py").read_text(encoding="utf-8")


def _production_consumer_hits():
    hits = []
    for directory in ("api", "workers", "parser", "crawler"):
        for path in (ROOT / directory).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "brpop" in text and "crawler:html" in text:
                hits.append(path.relative_to(ROOT).as_posix())
    return hits


def test_api_server_has_no_parser_worker_switch():
    assert "PARSER_WORKER_ENABLED" not in API_SOURCE
    assert "startup_parser_worker" not in API_SOURCE
    assert "_run_parser_worker" not in API_SOURCE


def test_api_server_has_no_redis_consumer():
    assert "brpop" not in API_SOURCE
    assert "crawler:html" not in API_SOURCE
    assert "import redis" not in API_SOURCE
    assert "from redis" not in API_SOURCE


def test_api_server_starts_no_background_thread():
    assert "threading" not in API_SOURCE
    assert "Thread(" not in API_SOURCE


def test_api_server_imports_and_create_app():
    module = importlib.import_module("api.server")
    assert module.FASTAPI_OK is True
    app = module.create_app()
    assert app is not None


def test_http_routes_remain():
    module = importlib.import_module("api.server")
    app = module.create_app()
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/health" in paths
    assert "/ready" in paths
    assert "/parse" in paths


def test_parse_route_offline():
    module = importlib.import_module("api.server")
    html = "<html><body><div class=\"article-content\"><p>" + ("正文内容" * 40) + "</p></div></body></html>"
    request = module.ParseRequest(url="https://example.gov.cn/a.html", html=html)
    result = asyncio.run(module.parse_html(request))
    assert result["content_len"] > 0


def test_only_formal_consumer_scans_all_production_dirs():
    assert _production_consumer_hits() == ["workers/parser_worker.py"]


def test_old_parser_worker_still_removed():
    assert not (ROOT / "parser" / "redis_worker.py").exists()