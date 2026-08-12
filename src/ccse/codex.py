"""Codex adapter: ~/.codex/config.toml top-level `model`."""
from __future__ import annotations

import tomllib

from . import config
from .registry import Adapter, Slot, register


@register
class CodexAdapter:
    id = "codex"
    name = "Codex"
    primary = "codex.model"
    path = config.HOME / ".codex" / "config.toml"

    @property
    def available(self) -> bool:
        return self.path.exists()

    def _load(self) -> dict:
        return tomllib.loads(self.path.read_text("utf-8"))

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        d = self._load()
        return [Slot(key=f"{self.id}.model", label="model",
                     current=d.get("model"))]

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        val = assignments.get(f"{self.id}.model")
        if val is None or not self.available:
            return []
        d = self._load()
        old = d.get("model")
        if old == val:
            return []
        if not config.detect_tomli_w():
            config.die("tomli_w not installed; run `uv pip install tomli-w` to write Codex TOML")
        d["model"] = val
        if not dry:
            import tomli_w  # type: ignore
            text = tomli_w.dumps(d)
            config.write_text_atomic(self.path, text)
        return [f"  model: {old!r} -> {val!r}"]