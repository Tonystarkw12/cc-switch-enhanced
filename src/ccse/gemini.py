"""Gemini adapter: ~/.gemini/.env GEMINI_MODEL."""
from __future__ import annotations

from . import config
from .registry import Adapter, Slot, register


@register
class GeminiAdapter:
    id = "gemini"
    name = "Gemini CLI"
    primary = "gemini.model"
    path = config.HOME / ".gemini" / ".env"

    @property
    def available(self) -> bool:
        return self.path.exists()

    def _env(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for line in self.path.read_text("utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v
        return out

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        return [Slot(key=f"{self.id}.model", label="GEMINI_MODEL",
                     current=self._env().get("GEMINI_MODEL"))]

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        val = assignments.get(f"{self.id}.model")
        if val is None or not self.available:
            return []
        kv = self._env()
        old = kv.get("GEMINI_MODEL")
        if old == val:
            return []
        kv["GEMINI_MODEL"] = val
        lines = [f"{k}={v}" for k, v in kv.items()]
        text = "\n".join(lines) + "\n"
        if not dry:
            config.write_text_atomic(self.path, text)
        return [f"  GEMINI_MODEL: {old!r} -> {val!r}"]