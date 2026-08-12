"""Cline adapter: ~/.cline/data/settings/providers.json."""
from __future__ import annotations

from . import config
from .registry import Adapter, Slot, register


@register
class ClineAdapter:
    id = "cline"
    name = "Cline"
    primary = "cline.model"
    path = config.HOME / ".cline" / "data" / "settings" / "providers.json"

    @property
    def available(self) -> bool:
        return self.path.exists()

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        d = config.load_json(self.path) or {}
        last = d.get("lastUsedProvider")
        provs = d.get("providers") or {}
        if not last or not isinstance(provs, dict) or last not in provs:
            return [Slot(key=f"{self.id}.model", label=f"providers[{last}].settings.model",
                         current=None)]
        m = provs[last].get("settings", {}).get("model")
        return [Slot(key=f"{self.id}.model", label=f"providers[{last}].settings.model",
                     current=m)]

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        val = assignments.get(f"{self.id}.model")
        if val is None or not self.available:
            return []
        d = config.load_json(self.path) or {}
        last = d.get("lastUsedProvider")
        provs = d.get("providers")
        if not last or not isinstance(provs, dict) or last not in provs:
            return [f"  (skip: lastUsedProvider {last!r} not in providers)"]
        s = provs[last].setdefault("settings", {})
        old = s.get("model")
        if old == val:
            return []
        if not dry:
            s["model"] = val
            config.keep_mode_write_json(self.path, d)
        return [f"  providers[{last}].settings.model: {old!r} -> {val!r}"]