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
from .registry import (KIND_API_KEY, KIND_BASE_URL, KIND_MODEL, Slot, register)

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
    endpoint_paths={"base_url": "llm.baseUrl", "api_key": "llm.apiKey"},
)

# OpenClaw: ~/.openclaw/openclaw.json — agents.defaults.model.primary +
# subagents.model; endpoint under models.providers.<active> (dict, not list)
make_adapter(
    "openclaw", "OpenClaw",
    HOME / ".openclaw" / "openclaw.json",
    {
        "primary": "agents.defaults.model.primary",
        "subagent": "agents.defaults.subagents.model",
    },
    endpoint_paths={
        "base_url": "models.providers.{provider}.baseUrl",
        "api_key": "models.providers.{provider}.apiKey",
    },
)

# KiloCode: ~/.kilocode/cli/config.json — providers[selected].apiModelId +
# openAiBaseUrl/openAiApiKey
make_adapter(
    "kilocode", "KiloCode",
    HOME / ".kilocode" / "cli" / "config.json",
    {"apiModelId": "providers[newapi].apiModelId"},
    endpoint_paths={
        "base_url": "providers[newapi].openAiBaseUrl",
        "api_key": "providers[newapi].openAiApiKey",
    },
)

# Snow: ~/.snow/config.json — snowcfg.advancedModel (main model; snow falls
# back to "gpt-5" when empty). basicModel is a secondary slot for --useBasicModel.
make_adapter(
    "snow", "Snow",
    HOME / ".snow" / "config.json",
    {"advancedModel": "snowcfg.advancedModel",
     "basicModel": "snowcfg.basicModel"},
    endpoint_paths={"base_url": "snowcfg.baseUrl", "api_key": "snowcfg.apiKey"},
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
        prov = None
        for p in d.get("providers", []) or []:
            if p.get("name") == def_model:
                prov = p
                cur = p.get("model")
                break
        out = [
            Slot(key="reasonix.model", label="active-provider model", current=cur),
            Slot(key="reasonix.default_model", label="default_model", current=def_model),
        ]
        if prov is not None:
            out.append(Slot(key="reasonix.base_url", label="active-provider base_url",
                            current=prov.get("base_url"), kind=KIND_BASE_URL))
            out.append(Slot(key="reasonix.api_key", label="active-provider api_key_env",
                            current=prov.get("api_key_env"), kind=KIND_API_KEY))
        return out

    def apply(self, assignments, dry=False):
        relevant = {k[len("reasonix.") + 0:]: v for k, v in assignments.items()
                    if k.startswith("reasonix.")}
        if not relevant or not self.available:
            return []
        d = self._doc()
        if d is None:
            return [f"  (skip: tomlkit unavailable)"]
        diffs: list[str] = []
        dmod = d.get("default_model")
        prov = None
        for p in (d.get("providers", None) or []):
            if p.get("name") == dmod:
                prov = p
                break
        if prov is not None:
            if "model" in relevant and prov.get("model") != relevant["model"]:
                diffs.append(f"  providers[{dmod}].model: {prov.get('model')!r} -> "
                             f"{relevant['model']!r}")
                if not dry:
                    prov["model"] = relevant["model"]
            if "base_url" in relevant and prov.get("base_url") != relevant["base_url"]:
                diffs.append(f"  providers[{dmod}].base_url: {prov.get('base_url')!r} -> "
                             f"{relevant['base_url']!r}")
                if not dry:
                    prov["base_url"] = relevant["base_url"]
            if "api_key" in relevant:
                var = prov.get("api_key_env") or "NEWAPI_API_KEY"
                import os
                old_key = os.environ.get(var)
                if old_key != relevant["api_key"]:
                    if not dry:
                        from .envrc import ensure_env_var
                        ensure_env_var(var, relevant["api_key"])
                    diffs.append(f"  env {var} (zshrc): {config.redact(old_key)!r} -> "
                                 f"{config.redact(relevant['api_key'])!r}")
        if "default_model" in relevant and d.get("default_model") != relevant["default_model"]:
            diffs.append(f"  default_model: {d.get('default_model')!r} -> "
                         f"{relevant['default_model']!r}")
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
        out = [Slot(key="grok.model", label="models.default", current=cur)]
        if cur:
            mtab = d.get("model") or {}
            blk = mtab.get(cur) if isinstance(mtab, dict) else None
            out.append(Slot(key="grok.base_url", label=f"model[{cur}].base_url",
                            current=blk.get("base_url") if blk else None,
                            kind=KIND_BASE_URL))
            out.append(Slot(key="grok.api_key", label=f"model[{cur}].env_key",
                            current=blk.get("env_key") if blk else None,
                            kind=KIND_API_KEY))
        return out

    def apply(self, assignments, dry=False):
        relevant = {k[len("grok."):]: v for k, v in assignments.items()
                    if k.startswith("grok.")}
        if not relevant or not self.available:
            return []
        d = self._doc()
        if d is None:
            return [f"  (skip: tomlkit unavailable)"]
        models = d.get("models")
        cur = models.get("default") if models is not None else None
        diffs: list[str] = []
        if "model" in relevant and cur != relevant["model"]:
            diffs.append(f"  models.default: {cur!r} -> {relevant['model']!r}")
            if not dry:
                if "models" not in d:
                    import tomlkit
                    d["models"] = tomlkit.table()
                d["models"]["default"] = relevant["model"]
                cur = relevant["model"]
        # ensure [model."<cur>"] table exists (model.apply ensures it too)
        if cur and "base_url" in relevant:
            mtab = d.get("model")
            blk = mtab.get(cur) if isinstance(mtab, dict) else None
            if blk is None:
                import tomlkit
                if mtab is None or not isinstance(mtab, dict):
                    mtab = tomlkit.table()
                    d["model"] = mtab
                blk = tomlkit.table()
                blk["model"] = cur
                mtab[cur] = blk
            if blk.get("base_url") != relevant["base_url"]:
                diffs.append(f"  model[{cur}].base_url: {blk.get('base_url')!r} -> "
                             f"{relevant['base_url']!r}")
                if not dry:
                    blk["base_url"] = relevant["base_url"]
        if cur and "api_key" in relevant:
            import os
            mtab = d.get("model")
            blk = mtab.get(cur) if isinstance(mtab, dict) else None
            if blk is None:
                import tomlkit
                if mtab is None or not isinstance(mtab, dict):
                    mtab = tomlkit.table()
                    d["model"] = mtab
                blk = tomlkit.table()
                blk["model"] = cur
                mtab[cur] = blk
            var = blk.get("env_key") or "NEWAPI_API_KEY"
            old_key = os.environ.get(var)
            if old_key != relevant["api_key"]:
                if not dry:
                    from .envrc import ensure_env_var
                    ensure_env_var(var, relevant["api_key"])
                diffs.append(f"  env {var} (zshrc): {config.redact(old_key)!r} -> "
                             f"{config.redact(relevant['api_key'])!r}")
        if diffs and not dry:
            text = tomlh.dump_toml(d)
            config.write_text_atomic(self.path, text)
        return diffs


@register
class ForgeAdapter:
    """Forge ~/.forge/.forge.toml [session] + ~/.forge/.credentials.json.

    Model = session.model_id; active provider = session.provider_id; its
    base_url/api_key live on the matching entry in credentials.json
    (url_params.OPENAI_URL / auth_details.api_key)."""
    id = "forge"
    name = "Forge"
    primary = "forge.model"
    path = HOME / ".forge" / ".forge.toml"
    _creds_path = HOME / ".forge" / ".credentials.json"

    @property
    def available(self):
        return self.path.exists()

    def _doc(self):
        return tomlh.load_toml_editable(self.path)

    def _creds(self):
        if not self._creds_path.exists():
            return None
        try:
            return config.load_json(self._creds_path)
        except Exception:
            return None

    def _active_provider(self):
        d = self._doc()
        if d is None:
            return None, None
        return (d.get("session") or {}).get("provider_id"), d

    def _provider_entry(self, pid):
        creds = self._creds()
        if not isinstance(creds, list):
            return None
        for c in creds:
            if isinstance(c, dict) and c.get("id") == pid:
                return c
        return None

    def slots(self):
        if not self.available:
            return []
        d = self._doc()
        if d is None:
            return []
        sess = d.get("session") or {}
        cur = sess.get("model_id")
        out = [Slot(key="forge.model", label="session.model_id", current=cur)]
        pid = sess.get("provider_id")
        if pid:
            entry = self._provider_entry(pid)
            url = (entry.get("url_params") or {}).get("OPENAI_URL") \
                if entry else None
            key = (entry.get("auth_details") or {}).get("api_key") \
                if entry else None
            out.append(Slot(key="forge.base_url", label=f"providers.{pid}.OPENAI_URL",
                            current=url, kind=KIND_BASE_URL))
            out.append(Slot(key="forge.api_key", label=f"providers.{pid}.api_key",
                            current=key, kind=KIND_API_KEY))
        return out

    def apply(self, assignments, dry=False):
        relevant = {k[len("forge."):]: v for k, v in assignments.items()
                    if k.startswith("forge.")}
        if not relevant or not self.available:
            return []
        d = self._doc()
        if d is None:
            return [f"  (skip: tomlkit unavailable)"]
        sess = d.get("session")
        if sess is None:
            return [f"  (skip: no [session] table)"]
        diffs: list[str] = []
        if "model" in relevant:
            old = sess.get("model_id")
            if old != relevant["model"]:
                diffs.append(f"  session.model_id: {old!r} -> {relevant['model']!r}")
                if not dry:
                    sess["model_id"] = relevant["model"]
        pid = sess.get("provider_id")
        creds = self._creds()
        entry = next((c for c in creds if isinstance(c, dict) and c.get("id") == pid),
                     None) if isinstance(creds, list) else None
        creds_dirty = False
        if pid and entry is not None:
            for key, section, field in (
                    ("base_url", "url_params", "OPENAI_URL"),
                    ("api_key", "auth_details", "api_key")):
                if key not in relevant:
                    continue
                sec = entry.setdefault(section, {})
                old = sec.get(field)
                if old != relevant[key]:
                    diffs.append(f"  providers.{pid}.{section}.{field}: "
                                 f"{config.redact(old)!r} -> "
                                 f"{config.redact(relevant[key])!r}")
                    if not dry:
                        sec[field] = relevant[key]
                        creds_dirty = True
        if not dry:
            if creds_dirty and isinstance(creds, list):
                config.keep_mode_write_json(self._creds_path, creds)
            if "model" in relevant:
                text = tomlh.dump_toml(d)
                config.write_text_atomic(self.path, text)
        return diffs


# ───────────────────────── YAML adapter — Hermes ────────────────────────

@register
class CrushAdapter:
    """Crush ~/.config/crush/crush.json (credentials) +
    ~/.local/share/crush/providers.json (model catalog).

    crush.json declares the providers in use (id + base_url + api_key);
    providers.json holds each provider's model list + default_large_model_id.
    Model slot = default_large_model_id of the first configured provider."""
    id = "crush"
    name = "Crush"
    primary = "crush.model"
    path = HOME / ".config" / "crush" / "crush.json"

    @property
    def available(self):
        return self.path.exists() and self._providers_path().exists()

    def _providers_path(self):
        return HOME / ".local" / "share" / "crush" / "providers.json"

    def _configured_provider(self):
        d = config.load_json(self.path) or {}
        provs = d.get("providers") or {}
        if isinstance(provs, dict):
            for pid, pconf in provs.items():
                if isinstance(pconf, dict):
                    return pid, pconf
        return None, None

    def _provider_entry(self, pid):
        c = config.load_json(self._providers_path())
        if not isinstance(c, list):
            return None
        for p in c:
            if isinstance(p, dict) and p.get("id") == pid:
                return p
        return None

    def slots(self):
        if not self.available:
            return []
        pid, pconf = self._configured_provider()
        if not pid:
            return []
        entry = self._provider_entry(pid)
        out = [Slot(key="crush.model",
                    label=f"providers[{pid}].default_large_model_id",
                    current=entry.get("default_large_model_id") if entry else None)]
        out.append(Slot(key="crush.base_url", label=f"providers.{pid}.base_url",
                        current=pconf.get("base_url"), kind=KIND_BASE_URL))
        out.append(Slot(key="crush.api_key", label=f"providers.{pid}.api_key",
                        current=pconf.get("api_key"), kind=KIND_API_KEY))
        return out

    def apply(self, assignments, dry=False):
        relevant = {k[len("crush."):]: v for k, v in assignments.items()
                    if k.startswith("crush.")}
        if not relevant or not self.available:
            return []
        pid, pconf = self._configured_provider()
        if not pid:
            return []
        diffs: list[str] = []
        model_written = False
        if "model" in relevant:
            cat = config.load_json(self._providers_path())
            entry = next((p for p in cat if isinstance(p, dict) and p.get("id") == pid),
                         None) if isinstance(cat, list) else None
            if entry is None:
                diffs.append(f"  (skip: provider {pid!r} not in providers.json)")
            else:
                old = entry.get("default_large_model_id")
                if old != relevant["model"]:
                    diffs.append(f"  providers[{pid}].default_large_model_id: {old!r} -> "
                                 f"{relevant['model']!r}")
                    if not dry:
                        entry["default_large_model_id"] = relevant["model"]
                        config.keep_mode_write_json(self._providers_path(), cat)
                        model_written = True
        d = config.load_json(self.path) or {}
        provs = d.setdefault("providers", {})
        p = provs.setdefault(pid, {})
        ep_dirty = False
        for key, field in (("base_url", "base_url"), ("api_key", "api_key")):
            if key in relevant:
                old = p.get(field)
                if old != relevant[key]:
                    diffs.append(f"  providers.{pid}.{field}: {old!r} -> {relevant[key]!r}")
                    if not dry:
                        p[field] = relevant[key]
                        ep_dirty = True
        if ep_dirty and not dry:
            config.keep_mode_write_json(self.path, d)
        return diffs


@register
class DroidAdapter:
    """Droid (Factory) ~/.factory/settings.json.

    sessionDefaultSettings.model = active model id (composite like
    custom:glm-4.7-...-0). base_url/api_key live on the matching customModels[]
    entry (the model id is not a bare model name — see show)."""
    id = "droid"
    name = "Droid"
    primary = "droid.model"
    path = HOME / ".factory" / "settings.json"

    @property
    def available(self):
        return self.path.exists()

    def _active_custom(self, d):
        m = (d.get("sessionDefaultSettings") or {}).get("model")
        for cm in d.get("customModels") or []:
            if isinstance(cm, dict) and cm.get("id") == m:
                return m, cm
        return m, None

    def slots(self):
        if not self.available:
            return []
        d = config.load_json(self.path) or {}
        m, cm = self._active_custom(d)
        out = [Slot(key="droid.model", label="sessionDefaultSettings.model",
                    current=m)]
        if cm is not None:
            out.append(Slot(key="droid.base_url", label="active customModel.baseUrl",
                            current=cm.get("baseUrl"), kind=KIND_BASE_URL))
            out.append(Slot(key="droid.api_key", label="active customModel.apiKey",
                            current=cm.get("apiKey"), kind=KIND_API_KEY))
        return out

    def apply(self, assignments, dry=False):
        relevant = {k[len("droid."):]: v for k, v in assignments.items()
                    if k.startswith("droid.")}
        if not relevant or not self.available:
            return []
        d = config.load_json(self.path) or {}
        sds = d.setdefault("sessionDefaultSettings", {})
        diffs: list[str] = []
        if "model" in relevant:
            old = sds.get("model")
            if old != relevant["model"]:
                diffs.append(f"  sessionDefaultSettings.model: {old!r} -> {relevant['model']!r}")
                if not dry:
                    sds["model"] = relevant["model"]
        m, cm = self._active_custom(d)
        if cm is not None:
            for key, field in (("base_url", "baseUrl"), ("api_key", "apiKey")):
                if key in relevant:
                    old = cm.get(field)
                    if old != relevant[key]:
                        diffs.append(f"  customModels[id={m}].{field}: {old!r} -> "
                                     f"{relevant[key]!r}")
                        if not dry:
                            cm[field] = relevant[key]
        if diffs and not dry:
            config.keep_mode_write_json(self.path, d)
        return diffs


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
        out = []
        if isinstance(m, dict):
            out.append(Slot(key="hermes.model", label="model.default",
                            current=m.get("default")))
            if m.get("base_url"):
                out.append(Slot(key="hermes.base_url", label="model.base_url",
                                current=m.get("base_url"), kind=KIND_BASE_URL))
            if m.get("api_key"):
                out.append(Slot(key="hermes.api_key", label="model.api_key",
                                current=m.get("api_key"), kind=KIND_API_KEY))
        return out

    def apply(self, assignments, dry=False):
        relevant = {k[len("hermes."):]: v for k, v in assignments.items()
                    if k.startswith("hermes.")}
        if not relevant or not self.available:
            return []
        doc, y = _load_yaml(self.path)
        if doc is None:
            return [f"  (skip: ruamel.yaml unavailable)"]
        if "model" not in doc or not isinstance(doc["model"], dict):
            return [f"  (skip: no model section)"]
        diffs: list[str] = []
        m = doc["model"]
        for label, field in (("model", "default"), ("base_url", "base_url"),
                             ("api_key", "api_key")):
            if label not in relevant:
                continue
            old = m.get(field)
            if old == relevant[label]:
                continue
            diffs.append(f"  model.{field}: {config.redact(old)!r} -> "
                         f"{config.redact(relevant[label])!r}")
            if not dry:
                m[field] = relevant[label]
        if not diffs:
            return []
        if not dry:
            from io import StringIO
            buf = StringIO()
            y.dump(doc, buf)
            config.write_text_atomic(self.path, buf.getvalue())
        return diffs