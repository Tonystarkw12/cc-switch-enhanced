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

import os
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

# CodeBuddy: ~/.codebuddy/settings.json "model" + models.json catalog.
# Hand-rolled — a bare model name alone silently fails (see CodeBuddyAdapter).


@register
class CodeBuddyAdapter:
    """CodeBuddy ~/.codebuddy/settings.json + ~/.codebuddy/models.json.

    settings.json "model" is either a bare built-in name or a
    ``custom-local:<id>`` reference resolving to a models.json ``models[]``
    entry (url/apiKey live there). CodeBuddy silently keeps the previous
    model when the ref doesn't resolve, so `--model NAME` must keep the
    ``custom-local:`` prefix AND have a catalog entry — like kilo, we append
    one (copying url/apiKey from an existing entry) when missing. A bare
    NAME is treated as a gateway model whenever a catalog exists; only a
    never-customized install (no models.json entries) keeps it bare."""
    id = "codebuddy"
    name = "CodeBuddy"
    primary = "codebuddy.model"
    path = HOME / ".codebuddy" / "settings.json"
    MODELS = HOME / ".codebuddy" / "models.json"
    PREFIX = "custom-local:"

    @property
    def available(self):
        return self.path.exists()

    def _catalog(self):
        d = config.load_json(self.MODELS) or {}
        lst = d.get("models")
        if not isinstance(lst, list):
            lst = d.setdefault("models", [])
        return d, lst

    def _entry(self, lst, mid):
        for e in lst:
            if isinstance(e, dict) and e.get("id") == mid:
                return e
        return None

    def slots(self):
        if not self.available:
            return []
        s = config.load_json(self.path) or {}
        return [Slot(key="codebuddy.model", label="model", current=s.get("model"))]

    def apply(self, assignments, dry=False):
        relevant = {k[len("codebuddy."):]: v for k, v in assignments.items()
                    if k.startswith("codebuddy.")}
        if not relevant or not self.available:
            return []
        name = relevant.get("model")
        if name is None:
            return []
        s = config.load_json(self.path) or {}
        mdoc, lst = self._catalog()
        diffs: list[str] = []
        s_dirty = m_dirty = False

        if name.startswith(self.PREFIX):
            target, bare = name, name[len(self.PREFIX):]
        else:
            bare = name
            target = self.PREFIX + name if lst else name

        if s.get("model") != target:
            diffs.append(f"  model: {s.get('model')!r} -> {target!r}")
            if not dry:
                s["model"] = target
                s_dirty = True

        if target.startswith(self.PREFIX) and self._entry(lst, bare) is None:
            src = next((e for e in lst if isinstance(e, dict)), None)
            entry = dict(src) if src else {
                "vendor": "NewAPI", "supportsToolCall": True,
                "supportsImages": False, "supportsReasoning": True,
            }
            entry["id"] = bare
            entry["name"] = bare
            diffs.append(f"  models[{bare!r}]: (created)"
                         + (f" copied from {src.get('id')!r}" if src else ""))
            if not dry:
                lst.append(entry)
                m_dirty = True
        if m_dirty and not dry:
            config.keep_mode_write_json(self.MODELS, mdoc)
        if s_dirty and not dry:
            config.keep_mode_write_json(self.path, s)
        return diffs

# PI (lazyypi): ~/.pi/agent/settings.json + models.json. Pi resolves the
# active model from defaultModel and requires that model in the active
# provider's models.json catalog; keep both files synchronized.
PI_MODELS_JSON = HOME / ".pi" / "agent" / "models.json"


@register
class PiAdapter:
    id = "pi"
    name = "Pi"
    primary = "pi.model"
    follow = ("pi.defaultModel",)
    path = HOME / ".pi" / "agent" / "settings.json"

    @property
    def available(self):
        return self.path.exists()

    def _settings(self):
        return config.load_json(self.path) or {}

    def _models(self):
        return config.load_json(PI_MODELS_JSON) or {}

    def slots(self):
        if not self.available:
            return []
        s = self._settings()
        out = [Slot(key="pi.model", label="model", current=(s.get("llm") or {}).get("model"))]
        out.append(Slot(key="pi.defaultModel", label="defaultModel",
                        current=s.get("defaultModel")))
        llm = s.get("llm") or {}
        out.append(Slot(key="pi.base_url", label="base_url",
                        current=llm.get("baseUrl"), kind=KIND_BASE_URL))
        out.append(Slot(key="pi.api_key", label="api_key",
                        current=llm.get("apiKey"), kind=KIND_API_KEY))
        return out

    def apply(self, assignments, dry=False):
        relevant = {k[3:]: v for k, v in assignments.items()
                    if k.startswith("pi.")}
        if not relevant or not self.available:
            return []
        s = self._settings()
        m = self._models()
        llm = s.setdefault("llm", {})
        diffs = []
        new_model = relevant.get("model") or relevant.get("defaultModel")
        if new_model is not None:
            for field in ("model", "defaultModel"):
                old = llm.get("model") if field == "model" else s.get(field)
                if old != new_model:
                    diffs.append(f"  {field}: {old!r} -> {new_model!r}")
                    if not dry:
                        if field == "model":
                            llm["model"] = new_model
                        else:
                            s[field] = new_model
            provider_name = s.get("defaultProvider")
            for source, label in ((s, "settings"), (m, "models")):
                provider = (source.get("providers") or {}).get(provider_name)
                catalog = provider.get("models") if isinstance(provider, dict) else None
                if isinstance(catalog, list) and catalog and isinstance(catalog[0], dict):
                    old = catalog[0].get("id")
                    if old != new_model:
                        diffs.append(f"  {label}[{provider_name}].models[0].id: "
                                     f"{old!r} -> {new_model!r}")
                        if not dry:
                            catalog[0]["id"] = new_model
                            catalog[0]["name"] = new_model.replace("-", " ").title()
            if not dry:
                config.keep_mode_write_json(PI_MODELS_JSON, m)
        if "base_url" in relevant:
            base_url = config.ensure_openai_v1(relevant["base_url"])
            old = llm.get("baseUrl")
            if old != base_url:
                diffs.append(f"  llm.baseUrl: {old!r} -> {base_url!r}")
                if not dry:
                    llm["baseUrl"] = base_url
        if "api_key" in relevant:
            var = llm.get("apiKey") or "OPENAI_API_KEY"
            old_key = os.environ.get(var)
            if old_key != relevant["api_key"]:
                if not dry:
                    from .envrc import ensure_env_var
                    ensure_env_var(var, relevant["api_key"])
                diffs.append(f"  env {var}: {config.redact(old_key)!r} -> "
                             f"{config.redact(relevant['api_key'])!r}")
        if diffs and not dry:
            config.keep_mode_write_json(self.path, s)
        return diffs


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
    follow=("subagent",),
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


@register
class KiloAdapter:
    """Kilo Code CLI ~/.config/kilo/kilo.json (distinct from the VS Code
    extension's ~/.kilocode, which `kilocode` above handles).

    The model is referenced by `newapi/<name>` strings in many fields: top-level
    `model`, `subagent_model`, `small_model`, `experimental.swe_pruner_model`,
    and every `agent.<name>.model`. Separately, the CLI validates a model
    *registry* at `provider.<provider>.models.<bare-name>` at startup — the
    entry must carry `modalities.output` or `kilo` refuses to start. So `--model`
    must both rewrite the strings AND (re)create the registry entry for the new
    bare name (copying schema from the previous model when present), or the
    switch silently breaks the CLI."""
    id = "kilo"
    name = "Kilo"
    primary = "kilo.model"
    path = HOME / ".config" / "kilo" / "kilo.json"

    @property
    def available(self):
        return self.path.exists()

    def _provider(self, d):
        model = d.get("model")
        if isinstance(model, str) and "/" in model:
            return model.split("/", 1)[0]
        return next(iter(d.get("provider", {})), None)

    def slots(self):
        if not self.available:
            return []
        d = config.load_json(self.path) or {}
        out = [Slot(key="kilo.model", label="model", current=d.get("model"))]
        prov = self._provider(d)
        provcfg = (d.get("provider") or {}).get(prov) if prov else None
        if isinstance(provcfg, dict):
            opts = provcfg.get("options") or {}
            if opts.get("baseURL"):
                out.append(Slot(key="kilo.base_url",
                                label=f"provider.{prov}.options.baseURL",
                                current=opts.get("baseURL"), kind=KIND_BASE_URL))
        return out

    def apply(self, assignments, dry=False):
        relevant = {k[len("kilo."):]: v for k, v in assignments.items()
                    if k.startswith("kilo.")}
        if not relevant or not self.available:
            return []
        d = config.load_json(self.path) or {}
        diffs: list[str] = []

        if "model" in relevant:
            new = relevant["model"]
            old = d.get("model")
            prov = new.split("/", 1)[0] if isinstance(new, str) and "/" in new \
                else self._provider(d)
            bare = new.split("/", 1)[1] if isinstance(new, str) and "/" in new else new
            bare_old = old.split("/", 1)[1] \
                if isinstance(old, str) and "/" in old else None

            if old != new:
                d["model"] = new
                diffs.append(f"  model: {old!r} -> {new!r}")
                for key in ("subagent_model", "small_model"):
                    if key in d and d[key] != new:
                        diffs.append(f"  {key}: {d[key]!r} -> {new!r}")
                        d[key] = new
                exp = d.get("experimental")
                if isinstance(exp, dict) and "swe_pruner_model" in exp \
                        and exp["swe_pruner_model"] != new:
                    diffs.append(f"  experimental.swe_pruner_model: "
                                 f"{exp['swe_pruner_model']!r} -> {new!r}")
                    exp["swe_pruner_model"] = new
                agents = d.get("agent")
                if isinstance(agents, dict):
                    for name, acfg in agents.items():
                        if isinstance(acfg, dict) and acfg.get("model") != new:
                            diffs.append(f"  agent.{name}.model: "
                                         f"{acfg.get('model')!r} -> {new!r}")
                            acfg["model"] = new
                sv = d.get("subagent_variant_overrides")
                if isinstance(sv, dict) and isinstance(old, str) \
                        and old in sv and new != old:
                    sv[new] = sv.pop(old)
                    diffs.append(f"  subagent_variant_overrides: {old!r} -> {new!r}")

            # ensure registry entry so `kilo` startup validation passes
            provs = d.get("provider")
            provcfg = provs.get(prov) if isinstance(provs, dict) and prov else None
            models = provcfg.get("models") if isinstance(provcfg, dict) else None
            if isinstance(models, dict) and bare not in models:
                src = models.get(bare_old) if bare_old else None
                entry = dict(src) if isinstance(src, dict) else {
                    "name": bare, "reasoning": True,
                    "modalities": {"input": ["text", "image"],
                                   "output": ["text"]},
                }
                entry["name"] = bare
                if not dry:
                    models[bare] = entry
                diffs.append(f"  provider.{prov}.models[{bare}]: (created)"
                             + (f" copied from {bare_old!r}" if bare_old else ""))

        if "base_url" in relevant:
            prov = self._provider(d)
            provs = d.get("provider")
            provcfg = provs.get(prov) if isinstance(provs, dict) and prov else None
            opts = provcfg.setdefault("options", {}) if isinstance(provcfg, dict) else None
            if opts is not None and opts.get("baseURL") != relevant["base_url"]:
                diffs.append(f"  provider.{prov}.options.baseURL: "
                             f"{opts.get('baseURL')!r} -> {relevant['base_url']!r}")
                if not dry:
                    opts["baseURL"] = relevant["base_url"]

        if diffs and not dry:
            config.keep_mode_write_json(self.path, d)
        return diffs

# Snow: ~/.snow/config.json — snowcfg.advancedModel (main model; snow falls
# back to "gpt-5" when empty). basicModel tracks the primary on `--model` so a
# switch repoints both tiers (set both explicitly only to diverge them).
make_adapter(
    "snow", "Snow",
    HOME / ".snow" / "config.json",
    {"advancedModel": "snowcfg.advancedModel",
     "basicModel": "snowcfg.basicModel"},
    endpoint_paths={"base_url": "snowcfg.baseUrl", "api_key": "snowcfg.apiKey"},
    follow=("basicModel",),
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
    (url_params.OPENAI_URL / auth_details.api_key). `--model` also forces
    merge_system_messages=true (see note in apply)."""
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
            # ollama/vLLM-backed gateways reject system messages after the
            # first turn ("system message must be at the beginning"); forge's
            # merge_system_messages=true folds all system messages into a
            # single leading one. Ensure it whenever ccse switches the model,
            # or such a gateway 500s on the first mid-conversation system
            # send. Runs even when model_id already matches (config resets).
            if d.get("merge_system_messages") is not True:
                diffs.append(f"  merge_system_messages: "
                             f"{d.get('merge_system_messages')!r} -> True")
                if not dry:
                    d["merge_system_messages"] = True
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


def _env_name(ref: str | None) -> str:
    """`${OPENAI_API_KEY}` -> OPENAI_API_KEY (fallback NEWAPI_API_KEY)."""
    if ref and ref.startswith("${") and ref.endswith("}"):
        return ref[2:-1]
    return ref or "NEWAPI_API_KEY"


@register
class OmpAdapter:
    """OMP ~/.omp/agent/config.yml: llm.model (primary) + defaultModel +
    modelRoles.default (`provider/model:level`) + llm.baseUrl/apiKey.
    apiKey is a `${ENV_VAR}` reference; `--api-key` persists the literal via
    ensure_env_var so the config keeps the var name."""
    id = "omp"
    name = "OMP"
    primary = "omp.model"
    # `--model` sets llm.model + defaultModel + modelRoles.default together
    follow = ("omp.model", "omp.defaultModel", "omp.modelRole")
    path = HOME / ".omp" / "agent" / "config.yml"

    def _catalog_paths(self):
        return (self.path, self.path.with_name("models.yml"))

    @property
    def available(self):
        return self.path.exists()

    def slots(self):
        if not self.available:
            return []
        doc, _y = _load_yaml(self.path)
        if doc is None:
            return []
        llm = doc.get("llm") or {}
        out = [Slot(key="omp.model", label="llm.model", current=llm.get("model"))]
        out.append(Slot(key="omp.defaultModel", label="defaultModel",
                        current=doc.get("defaultModel")))
        mr = doc.get("modelRoles") or {}
        out.append(Slot(key="omp.modelRole", label="modelRoles.default",
                        current=mr.get("default")))
        if llm.get("baseUrl"):
            out.append(Slot(key="omp.base_url", label="llm.baseUrl",
                            current=llm.get("baseUrl"), kind=KIND_BASE_URL))
        out.append(Slot(key="omp.api_key", label="llm.apiKey",
                        current=llm.get("apiKey"), kind=KIND_API_KEY))
        return out

    def _merge_model_role(self, new: str, old: str | None) -> str:
        """modelRoles.default is `provider/model:level`. A bare target keeps
        old provider prefix (cli already does) and old `:level` suffix."""
        if old and ":" in old and ":" not in new:
            new = new + old[old.index(":"):]
        return new

    def apply(self, assignments, dry=False):
        relevant = {k[len("omp."):]: v for k, v in assignments.items()
                    if k.startswith("omp.")}
        if not relevant or not self.available:
            return []
        doc, y = _load_yaml(self.path)
        if doc is None:
            return [f"  (skip: ruamel.yaml unavailable)"]
        llm = doc.setdefault("llm", {})
        diffs: list[str] = []
        if "model" in relevant:
            old = llm.get("model")
            if old != relevant["model"]:
                diffs.append(f"  llm.model: {old!r} -> {relevant['model']!r}")
                if not dry:
                    llm["model"] = relevant["model"]
        if "defaultModel" in relevant:
            old = doc.get("defaultModel")
            if old != relevant["defaultModel"]:
                diffs.append(f"  defaultModel: {old!r} -> {relevant['defaultModel']!r}")
                if not dry:
                    doc["defaultModel"] = relevant["defaultModel"]
        if "modelRole" in relevant:
            mr = doc.setdefault("modelRoles", {})
            old = mr.get("default")
            new = self._merge_model_role(relevant["modelRole"], old)
            if old != new:
                diffs.append(f"  modelRoles.default: {old!r} -> {new!r}")
                if not dry:
                    mr["default"] = new
        if "model" in relevant:
            provider_name = doc.get("defaultProvider")
            for catalog_path in self._catalog_paths():
                if catalog_path == self.path:
                    catalog_doc, catalog_yaml = doc, y
                else:
                    catalog_doc, catalog_yaml = _load_yaml(catalog_path)
                provider = ((catalog_doc or {}).get("providers") or {}).get(provider_name)
                models = provider.get("models") if isinstance(provider, dict) else None
                if not isinstance(models, list) or not models or not isinstance(models[0], dict):
                    continue
                old = models[0].get("id")
                if old == relevant["model"]:
                    continue
                diffs.append(f"  {catalog_path.name}[{provider_name}].models[0].id: "
                             f"{old!r} -> {relevant['model']!r}")
                if not dry:
                    models[0]["id"] = relevant["model"]
                    models[0]["name"] = relevant["model"].replace("-", " ").title()
                    if catalog_path != self.path:
                        from io import StringIO
                        buf = StringIO()
                        catalog_yaml.dump(catalog_doc, buf)
                        config.write_text_atomic(catalog_path, buf.getvalue())
        if "base_url" in relevant:
            base_url = config.ensure_openai_v1(relevant["base_url"])
            old = llm.get("baseUrl")
            if old != base_url:
                diffs.append(f"  llm.baseUrl: {old!r} -> {base_url!r}")
                if not dry:
                    llm["baseUrl"] = base_url
        if "api_key" in relevant:
            var = _env_name(llm.get("apiKey"))
            old_key = os.environ.get(var)
            if old_key != relevant["api_key"]:
                if not dry:
                    from .envrc import ensure_env_var
                    ensure_env_var(var, relevant["api_key"])
                diffs.append(f"  env {var}: {config.redact(old_key)!r} -> "
                             f"{config.redact(relevant['api_key'])!r}")
        if not diffs:
            return []
        if not dry:
            from io import StringIO
            buf = StringIO()
            y.dump(doc, buf)
            config.write_text_atomic(self.path, buf.getvalue())
        return diffs


@register
class MemmyAdapter:
    """Memmy ~/.memmy/config.yaml: agents.defaults.model + the active
    provider's apiBase/apiKey. apiKey is an `${ENV_VAR}` reference; a bare
    `--api-key K` persists the literal via ensure_env_var (shell rc / setx)
    so the config keeps pointing at the var name."""
    id = "memmy"
    name = "Memmy"
    primary = "memmy.model"
    path = HOME / ".memmy" / "config.yaml"

    @property
    def available(self):
        return self.path.exists()

    def _provider(self, doc):
        defaults = (doc.get("agents") or {}).get("defaults") or {}
        pname = defaults.get("provider")
        provs = doc.get("providers") or {}
        prov = provs.get(pname) if pname else None
        if not isinstance(prov, dict):
            return pname, None
        return pname, prov

    def slots(self):
        if not self.available:
            return []
        doc, _y = _load_yaml(self.path)
        if doc is None:
            return []
        defaults = (doc.get("agents") or {}).get("defaults") or {}
        out = [Slot(key="memmy.model", label="agents.defaults.model",
                    current=defaults.get("model"))]
        pname, prov = self._provider(doc)
        if prov is not None:
            out.append(Slot(key="memmy.base_url",
                            label=f"providers.{pname}.apiBase",
                            current=prov.get("apiBase"), kind=KIND_BASE_URL))
            out.append(Slot(key="memmy.api_key",
                            label=f"providers.{pname}.apiKey",
                            current=prov.get("apiKey"), kind=KIND_API_KEY))
        return out

    def apply(self, assignments, dry=False):
        relevant = {k[len("memmy."):]: v for k, v in assignments.items()
                    if k.startswith("memmy.")}
        if not relevant or not self.available:
            return []
        doc, y = _load_yaml(self.path)
        if doc is None:
            return [f"  (skip: ruamel.yaml unavailable)"]
        defaults = doc.setdefault("agents", {}).setdefault("defaults", {})
        diffs: list[str] = []
        if "model" in relevant:
            old = defaults.get("model")
            if old != relevant["model"]:
                diffs.append(f"  agents.defaults.model: {old!r} -> "
                             f"{relevant['model']!r}")
                if not dry:
                    defaults["model"] = relevant["model"]
        pname, prov = self._provider(doc)
        if prov is not None:
            if "base_url" in relevant:
                old = prov.get("apiBase")
                if old != relevant["base_url"]:
                    diffs.append(f"  providers[{pname}].apiBase: {old!r} -> "
                                 f"{relevant['base_url']!r}")
                    if not dry:
                        prov["apiBase"] = relevant["base_url"]
            if "api_key" in relevant:
                var = _env_name(prov.get("apiKey"))
                old_key = os.environ.get(var)
                if old_key != relevant["api_key"]:
                    if not dry:
                        from .envrc import ensure_env_var
                        ensure_env_var(var, relevant["api_key"])
                    diffs.append(f"  env {var}: {config.redact(old_key)!r} -> "
                                 f"{config.redact(relevant['api_key'])!r}")
        if not diffs:
            return []
        if not dry:
            from io import StringIO
            buf = StringIO()
            y.dump(doc, buf)
            config.write_text_atomic(self.path, buf.getvalue())
        return diffs
        return diffs