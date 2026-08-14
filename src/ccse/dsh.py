"""DSH (deepseek harness) adapter: ~/.dsh/settings.yaml — agentDefaultModel.

DSH resolves the default model for new agents from the ``agentDefaultModel``
settings section (a ModelSelection: provider + model), hot-reloaded from
settings.yaml — this is what the web Models page writes. Absent => the bundle
default (deepseek-official / deepseek-v4-flash) applies. We switch ``.model``
and keep the provider (defaulting to deepseek-official on a fresh section).

Provider base_url / api_key live in provider profiles (``llm-<provider>:``,
resolved per request via apiKeyEnv refs) and are out of scope for a model
switch — dsh is a model-only adapter, like codebuddy/forge.
"""
from __future__ import annotations

import io

from . import config
from .registry import Slot, register

PATH = config.HOME / ".dsh" / "settings.yaml"
DEFAULT_PROVIDER = "deepseek-official"


def _yaml():
    import ruamel.yaml as _y  # type: ignore
    y = _y.YAML()
    y.preserve_quotes = True
    y.width = 4096
    return y


@register
class DshAdapter:
    id = "dsh"
    name = "DSH"
    primary = "dsh.model"
    path = PATH

    @property
    def available(self) -> bool:
        return self.path.exists()

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        y = _yaml()
        doc = y.load(self.path.read_text("utf-8")) or {}
        sel = doc.get("agentDefaultModel") if isinstance(doc, dict) else None
        model = sel.get("model") if isinstance(sel, dict) else None
        cur = None if model in (None, "") else str(model)
        return [Slot(key=f"{self.id}.model", label="agentDefaultModel.model",
                     current=cur)]

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        val = assignments.get(f"{self.id}.model")
        if val is None or not self.available:
            return []
        y = _yaml()
        text = self.path.read_text("utf-8")
        doc = y.load(text) if text.strip() else {}
        if doc is None:
            doc = {}
        sel = doc.get("agentDefaultModel")
        if not isinstance(sel, dict):
            sel = {}
            doc["agentDefaultModel"] = sel
        old = sel.get("model")
        if old == val:
            return []
        sel["model"] = val
        if not sel.get("provider"):
            sel["provider"] = DEFAULT_PROVIDER
        if not dry:
            buf = io.StringIO()
            y.dump(doc, buf)
            config.write_text_atomic(self.path, buf.getvalue())
        return [f"  agentDefaultModel.model: {old!r} -> {val!r}"]
