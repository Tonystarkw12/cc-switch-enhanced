"""More adapters: codebuddy, copilot(best-effort), pi, openclaw, kilocode,
crush, continue, copaw, reasonix, grok, forge, hermes.

Declarative-driven (none hand-rolled) where the format + a single string field
suffices. Hand-rolled where multi-field or list/table indexing is needed.

Status legend:
  ✅ primary     — writable single model-name field, real config file
  🟡 best-effort — field exists but is DB/objc/CLI-managed; file write may be
                   overwritten on next agent start. We still write it.
  ❌ not-support — no plaintext model field, can't help
"""
from __future__ import annotations

from pathlib import Path

from . import config
from .jsonpath import make_adapter
from . import toml as tomlh
from .registry import Slot, register

HOME = config.HOME


def _load_yaml(path: Path):
    try:
        import ruamel.yaml as _y  # type: ignore
    except ImportError:
        return None, None
    if not path.exists():
        return None, None
    y = _y.YAML()
    y.preserve_quotes = True
    y.width = 4096
    doc = y.load(path.read_text("utf-8"))
    return doc, y


# ───────────────────────── JSON-path adapters ──────────────────────────

# CodeBuddy: ~/.codebuddy/settings.json top-level "model"
make_adapter(
    "codebuddy", "CodeBuddy",
    HOME / ".codebuddy" / "settings.json",
    {"model": "model"},
)

# PI (lazyypi): ~/.pi/agent/settings.json — llm.model + subagents overrides +
# defaultModel + provider model defs
make_adapter(
    "pi", "Pi",
    HOME / ".pi" / "agent" / "settings.json",
    {
        "model": "llm.model",
        "defaultModel": "defaultModel",
        "subagent.context-builder": "subagents.agentOverrides.context-builder.model",
        "subagent.planner": "subagents.agentOverrides.planner.model",
        "subagent.researcher": "subagents.agentOverrides.researcher.model",
        "subagent.reviewer": "subagents.agentOverrides.reviewer.model",
        "subagent.scout": "subagents.agentOverrides.scout.model",
        "subagent.worker": "subagents.agentOverrides.worker.model",
    },
)

# OpenClaw: ~/.openclaw/openclaw.json — agents.defaults.model.primary +
# subagents.model
make_adapter(
    "openclaw", "OpenClaw",
    HOME / ".openclaw" / "openclaw.json",
    {
        "primary": "agents.defaults.model.primary",
        "subagent": "agents.defaults.subagents.model",
    },
)

# KiloCode: ~/.kilocode/cli/config.json — providers[selected].apiModelId
make_adapter(
    "kilocode", "KiloCode",
    HOME / ".kilocode" / "cli" / "config.json",
    {"apiModelId": "providers[newapi].apiModelId"},
)

# Snow: ~/.snow/config.json — snowcfg.advancedModel (main model; snow falls
# back to "gpt-5" when empty). basicModel is a secondary slot for --useBasicModel.
make_adapter(
    "snow", "Snow",
    HOME / ".snow" / "config.json",
    {"advancedModel": "snowcfg.advancedModel",
     "basicModel": "snowcfg.basicModel"},
)


# ───────────────────────── TOML adapters ───────────────────────────────
# All use tomlkit to preserve comments/formatting where possible.


@register
class ReasonixAdapter:
    """Reasonix ~/.reasonix/config.toml: default_model + [[providers]] model.

    Slot `model` targets the active provider's `model` field (provider whose
    name == default_model). Slot `default_model` chooses which provider.
    """
    id = "reasonix"
    name = "Reasonix"
    primary = "reasonix.model"
    path = HOME / ".reasonix" / "config.toml"

    @property
    def available(self):
        return self.path.exists()

    def _doc(self):
        return tomlh.load_toml_editable(self.path)

    def slots(self):
        if not self.available:
            return []
        d = self._doc()
        if d is None:
            return []
        def_model = d.get("default_model")
        cur = None
        for prov in d.get("providers", []) or []:
            if prov.get("name") == def_model:
                cur = prov.get("model")
                break
        return [
            Slot(key="reasonix.model", label="active-provider model", current=cur),
            Slot(key="reasonix.default_model", label="default_model", current=def_model),
        ]

    def apply(self, assignments, dry=False):
        relevant = {k[len("reasonix.") + 0:]: v for k, v in assignments.items()
                    if k.startswith("reasonix.")}
        if not relevant or not self.available:
            return []
        d = self._doc()
        if d is None:
            return [f"  (skip: tomlkit unavailable)"]
        diffs: list[str] = []
        if "model" in relevant:
            dmod = d.get("default_model")
            for prov in (d.get("providers", None) or []):
                if prov.get("name") == dmod:
                    old = prov.get("model")
                    if old != relevant["model"]:
                        diffs.append(
                            f"  providers[{dmod}].model: {old!r} -> {relevant['model']!r}")
                        if not dry:
                            prov["model"] = relevant["model"]
                    break
        if "default_model" in relevant:
            old = d.get("default_model")
            if old != relevant["default_model"]:
                diffs.append(
                    f"  default_model: {old!r} -> {relevant['default_model']!r}")
                if not dry:
                    d["default_model"] = relevant["default_model"]
        if diffs and not dry:
            text = tomlh.dump_toml(d)
            config.write_text_atomic(self.path, text)
        return diffs


@register
class GrokAdapter:
    """Grok ~/.grok/config.toml: [models] default = "<name>" and
    [model."<name>"] model = "<name>". Slot `model` sets both: switches
    default to it and ensures/updates its [model."<name>"].model."""
    id = "grok"
    name = "Grok"
    primary = "grok.model"
    path = HOME / ".grok" / "config.toml"

    @property
    def available(self):
        return self.path.exists()

    def _doc(self):
        return tomlh.load_toml_editable(self.path)

    def slots(self):
        if not self.available:
            return []
        d = self._doc()
        if d is None:
            return []
        cur = d.get("models", {}).get("default") if "models" in d else None
        return [Slot(key="grok.model", label="models.default", current=cur)]

    def apply(self, assignments, dry=False):
        val = assignments.get("grok.model")
        if val is None or not self.available:
            return []
        d = self._doc()
        if d is None:
            return [f"  (skip: tomlkit unavailable)"]
        models = d.get("models")
        old = models.get("default") if models is not None else None
        if old == val:
            return []
        diffs = [f"  models.default: {old!r} -> {val!r}"]
        if not dry:
            if "models" not in d:
                import tomlkit
                d["models"] = tomlkit.table()
            d["models"]["default"] = val
            # ensure [model."<val>"] block with model=<val> if missing
            mtab = d.get("model", None)
            if mtab is None or val not in mtab:
                import tomlkit
                if mtab is None:
                    d["model"] = tomlkit.table()
                    mtab = d["model"]
                if val not in mtab:
                    sub = tomlkit.table()
                    sub["model"] = val
                    mtab[val] = sub
            text = tomlh.dump_toml(d)
            config.write_text_atomic(self.path, text)
        return diffs


@register
class ForgeAdapter:
    """Forge ~/.forge/.forge.toml: [session] model_id (and provider_id).
    Slot `model` sets session.model_id."""
    id = "forge"
    name = "Forge"
    primary = "forge.model"
    path = HOME / ".forge" / ".forge.toml"

    @property
    def available(self):
        return self.path.exists()

    def _doc(self):
        return tomlh.load_toml_editable(self.path)

    def slots(self):
        if not self.available:
            return []
        d = self._doc()
        if d is None:
            return []
        cur = d.get("session", {}).get("model_id") if "session" in d else None
        return [Slot(key="forge.model", label="session.model_id", current=cur)]

    def apply(self, assignments, dry=False):
        val = assignments.get("forge.model")
        if val is None or not self.available:
            return []
        d = self._doc()
        if d is None:
            return [f"  (skip: tomlkit unavailable)"]
        sess = d.get("session")
        if sess is None:
            return [f"  (skip: no [session] table)"]
        old = sess.get("model_id")
        if old == val:
            return []
        if not dry:
            sess["model_id"] = val
            text = tomlh.dump_toml(d)
            config.write_text_atomic(self.path, text)
        return [f"  session.model_id: {old!r} -> {val!r}"]


# ───────────────────────── YAML adapter — Hermes ────────────────────────

@register
class HermesAdapter:
    """Hermes ~/.hermes/config.yaml: model.default (string) + model.provider.
    Slot `model` sets model.default only (provider/base_url stay)."""
    id = "hermes"
    name = "Hermes"
    primary = "hermes.model"
    path = HOME / ".hermes" / "config.yaml"

    @property
    def available(self):
        return self.path.exists()

    def slots(self):
        if not self.available:
            return []
        doc, _y = _load_yaml(self.path)
        if doc is None:
            return []
        m = doc.get("model", {})
        cur = m.get("default") if isinstance(m, dict) else None
        return [Slot(key="hermes.model", label="model.default", current=cur)]

    def apply(self, assignments, dry=False):
        val = assignments.get("hermes.model")
        if val is None or not self.available:
            return []
        doc, y = _load_yaml(self.path)
        if doc is None:
            return [f"  (skip: ruamel.yaml unavailable)"]
        if "model" not in doc or not isinstance(doc["model"], dict):
            return [f"  (skip: no model section)"]
        old = doc["model"].get("default")
        if old == val:
            return []
        if not dry:
            doc["model"]["default"] = val
            from io import StringIO
            buf = StringIO()
            y.dump(doc, buf)
            config.write_text_atomic(self.path, buf.getvalue())
        return [f"  model.default: {old!r} -> {val!r}"]