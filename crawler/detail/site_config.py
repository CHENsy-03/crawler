"""Read-only site/parser/score configuration loading for detail v2."""

import copy
import json
import os


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_json(relative_path: str) -> dict:
    path = os.path.join(_project_root(), relative_path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_site_configs() -> dict:
    return _read_json(os.path.join("config", "site.json"))


def normalize_hostname(hostname: str) -> str:
    return (hostname or "").strip().lower().rstrip(".")


def find_site_by_hostname(hostname: str) -> tuple[str | None, dict | None]:
    host = normalize_hostname(hostname)
    for key, cfg in load_site_configs().items():
        domain = normalize_hostname(str(cfg.get("domain", "")))
        if domain == host:
            return key, copy.deepcopy(cfg)
    return None, None


def load_parser_global() -> dict:
    return copy.deepcopy(_read_json(os.path.join("config", "parser.json")).get("_global", {}))


def load_score_config(hostname: str) -> dict:
    scores = _read_json(os.path.join("config", "score.json"))
    site_key, _ = find_site_by_hostname(hostname)
    merged = copy.deepcopy(scores.get("_global", {}))
    if site_key is not None and site_key in scores:
        merged.update(copy.deepcopy(scores[site_key]))
    return merged