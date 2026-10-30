"""DSH (DeepSeek Harness) adapter — ~/.dsh/cordis.patch.yml (0.2.0-rc.2).

dsh 0.2 dropped the old settings.yaml ``agentDefaultModel`` section: config
is now a cordis entry tree composed per profile as
bundle → profile patch → home patch → CLI patch, and the model for new
agents is the ``agent-default-model`` entry (@deepseek-ai/dsh-agent-default-model,
config: provider + model; a patch config replaces the whole config). The
home-layer patch file ~/.dsh/cordis.patch.yml applies to every profile and
after profile patches, so writing it there switches all profiles at once and
overrides per-profile patches (e.g. one pinning qwen3.8:27b).

Provider stays untouched when a home entry already exists; on a fresh entry
it is detected from the profile patches (profiles/*/cordis.patch.yml — all
that define the entry must agree) and falls back to deepseek-official.
Endpoint/api-key config lives in llm-* provider entries and stays out of
scope — dsh is a model-only adapter, like codebuddy/forge.
"""
from __future__ import annotations

import io

from . import config
from .registry import Slot, register

PATH = config.HOME / ".dsh" / "cordis.patch.yml"
ENTRY_ID = "agent-default-model"
ENTRY_NAME = "@deepseek-ai/dsh-agent-default-model"
DEFAULT_PROVIDER = "deepseek-official"


def _yaml():
    import ruamel.yaml as _y  # type: ignore
    y = _y.YAML()
    y.preserve_quotes = True
    y.width = 4096
    return y


def _entry(doc):
    """The agent-default-model patch entry, or None."""
    if not isinstance(doc, list):
        return None
    for e in doc:
        if isinstance(e, dict) and e.get("id") == ENTRY_ID:
            return e
    return None


def _profile_provider(home) -> str:
    """Provider from the profile patches when they agree; bundle default
    otherwise. dsh resolves per profile and ccse writes the home layer for
    all of them, so a split vote has no single right answer."""
    found: set[str] = set()
    prof_dir = config.HOME / ".dsh" / "profiles"
    if prof_dir.is_dir():
        for f in sorted(prof_dir.glob("*/cordis.patch.yml")):
            try:
                doc = _yaml().load(f.read_text("utf-8"))
            except Exception:  # noqa: BLE001 — unreadable profile patch
                continue
            e = _entry(doc)
            p = e.get("config", {}).get("provider") if isinstance(e, dict) else None
            if p:
                found.add(str(p))
    return found.pop() if len(found) == 1 else DEFAULT_PROVIDER


@register
class DshAdapter:
    id = "dsh"
    name = "DSH"
    primary = "dsh.model"
    path = PATH

    @property
    def available(self) -> bool:
        return (config.HOME / ".dsh").exists()

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        model = None
        if self.path.exists():
            try:
                doc = _yaml().load(self.path.read_text("utf-8"))
            except Exception:  # noqa: BLE001 — malformed patch file
                doc = None
            e = _entry(doc)
            if e is not None:
                cfg = e.get("config")
                if isinstance(cfg, dict) and cfg.get("model") not in (None, ""):
                    model = str(cfg["model"])
        return [Slot(key=f"{self.id}.model",
                     label="cordis.patch agent-default-model.model "
                           "(home layer, all profiles)",
                     current=model)]

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        val = assignments.get(f"{self.id}.model")
        if val is None or not self.available:
            return []
        y = _yaml()
        text = self.path.read_text("utf-8") if self.path.exists() else ""
        doc = y.load(text) if text.strip() else []
        if doc is None:
            doc = []
        if not isinstance(doc, list):
            return [f"  (skip: {self.path} is not a patch list)"]
        e = _entry(doc)
        if e is not None:
            cfg = e.get("config")
            if not isinstance(cfg, dict):
                cfg = e["config"] = {}
            old = cfg.get("model")
            if old is not None and str(old) == val:
                return []
            cfg["model"] = val
            if not dry:
                cfg.setdefault("provider",
                               _profile_provider(self.path))
        else:
            old = None
            cfg = {"provider": _profile_provider(self.path), "model": val}
            doc.append({"id": ENTRY_ID, "name": ENTRY_NAME, "config": cfg})
        if not dry:
            buf = io.StringIO()
            y.dump(doc, buf)
            config.write_text_atomic(self.path, buf.getvalue())
        return [f"  agent-default-model.model: {old!r} -> {val!r}"]
