"""Qwen Code adapter: ~/.qwen/settings.json model.name."""
from __future__ import annotations

from . import config
from .registry import Adapter, Slot, register


@register
class QwenAdapter:
    id = "qwen"
    name = "Qwen Code"
    primary = "qwen.model"
    path = config.HOME / ".qwen" / "settings.json"

    @property
    def available(self) -> bool:
        return self.path.exists()

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        d = config.load_json(self.path) or {}
        m = d.get("model") or {}
        return [Slot(key=f"{self.id}.model", label="model.name",
                     current=m.get("name") if isinstance(m, dict) else None)]

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        val = assignments.get(f"{self.id}.model")
        if val is None or not self.available:
            return []
        d = config.load_json(self.path) or {}
        m = d.setdefault("model", {})
        old = m.get("name")
        if old == val:
            return []
        if not dry:
            m["name"] = val
            config.keep_mode_write_json(self.path, d)
        return [f"  model.name: {old!r} -> {val!r}"]