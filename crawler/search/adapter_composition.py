"""Deterministic production adapter registry composition."""

from crawler.search.adapter_registry import AdapterRegistry
from crawler.search.generic_json_adapter import GenericJSONSearchAdapter
from crawler.search.html_adapter import HTMLSearchAdapter
from crawler.search.jpaas_adapter import JPAASSearchAdapter
from crawler.search.trs_adapter import TRSSearchAdapter


def build_default_adapter_registry() -> AdapterRegistry:
    """Build a fresh registry containing exactly the four formal adapters."""
    registry = AdapterRegistry()
    registry.register(HTMLSearchAdapter())
    registry.register(TRSSearchAdapter())
    registry.register(JPAASSearchAdapter())
    registry.register(GenericJSONSearchAdapter())
    return registry