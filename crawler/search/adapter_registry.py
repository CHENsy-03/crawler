"""Explicit, injected AdapterRegistry without fallback or guessing."""

from dataclasses import dataclass

from crawler.search.adapter import SearchAdapter
from crawler.search.search_plan import ADAPTERS, SearchPlan


@dataclass(frozen=True)
class AdapterResolution:
    found: bool
    adapter: SearchAdapter | None = None
    error: str | None = None


class AdapterRegistry:
    """Registry that resolves only by the formal plan.adapter field."""

    def __init__(self) -> None:
        self._adapters: dict[str, SearchAdapter] = {}

    def register(self, adapter: SearchAdapter) -> None:
        name = adapter.adapter_name
        if not isinstance(name, str) or name not in ADAPTERS:
            raise ValueError(f"adapter name {name!r} is not in the controlled set")
        if name in self._adapters:
            raise ValueError(f"adapter {name!r} is already registered")
        self._adapters[name] = adapter

    def get(self, name: str) -> SearchAdapter | None:
        return self._adapters.get(name)

    def resolve_plan(self, plan: SearchPlan) -> AdapterResolution:
        if plan.adapter not in ADAPTERS:
            return AdapterResolution(False, None, "unknown adapter")
        adapter = self._adapters.get(plan.adapter)
        if adapter is None:
            return AdapterResolution(False, None, "adapter not registered")
        return AdapterResolution(True, adapter, None)