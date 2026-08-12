"""OpenCode adapter: ~/.config/opencode/opencode.json."""
from __future__ import annotations

from . import config
from .registry import Adapter, Slot, register


@register
class OpenCodeAdapter:
    id = "opencode"
    name = "OpenCode"
    primary = "opencode.model"
    path = config.HOME / ".config" / "opencode" / "opencode.json"

    @property
    def available(self) -> bool:
        return self.path.exists()

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        d = config.load_json(self.path) or {}
        out = [Slot(key=f"{self.id}.model", label="model",
                    current=d.get("model"))]
        for role, v in (d.get("agent") or {}).items():
            if isinstance(v, dict) and "model" in v:
                out.append(Slot(key=f"{self.id}.agent.{role}.model",
                                label=f"agent.{role}.model",
                                current=v.get("model")))
        return out

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        relevant = {k: v for k, v in assignments.items() if k.startswith(f"{self.id}.")}
        if not relevant or not self.available:
            return []
        d = config.load_json(self.path) or {}
        diffs: list[str] = []
        top = f"{self.id}.model"
        if top in relevant:
            old = d.get("model")
            if old != relevant[top]:
                diffs.append(f"  model: {old!r} -> {relevant[top]!r}")
                if not dry:
                    d["model"] = relevant[top]
        for key, val in relevant.items():
            prefix = f"{self.id}.agent."
            if key.startswith(prefix):
                rest = key[len(prefix):]  # e.g. build.model
                role, _, field = rest.partition(".")
                if role and field == "model":
                    agent = d.setdefault("agent", {}).setdefault(role, {})
                    old = agent.get("model")
                    if old != val:
                        diffs.append(f"  agent.{role}.model: {old!r} -> {val!r}")
                        if not dry:
                            agent["model"] = val
        if diffs and not dry:
            config.keep_mode_write_json(self.path, d)
        return diffs