"""Mu adapter: the KYRN/MU CLI (a pi-family agent) — settings.json
``defaultModel``/``defaultProvider`` plus its own models.json provider catalog.

Mu resolves the startup model from the *pair* in ``~/.mu/agent/settings.json``:
``defaultProvider`` names an entry in ``~/.mu/agent/models.json`` and
``defaultModel`` is the bare model id inside that provider's ``models`` list.
Neither half is enough alone — a ``defaultModel`` whose provider is absent, or
a model missing from that provider's catalog, silently falls back to "the first
provider with usable credentials". ``--model`` therefore writes both halves and
repairs a dangling provider, the way prime does for the same pi-family shape.

Three mu-specific details the generic JSON-path adapter cannot express:

* ``apiKey`` in models.json holds the LITERAL key. The same ``$NAME`` /
  ``${NAME}`` interpolation that mu's docs describe is read *by mu itself* at
  request time, so a bare env-var name left in the field is a working config —
  but only if the variable is exported. A bare name that is set in the
  environment is inlined here so the config no longer depends on shell state.
* ``enabledModels`` (glob patterns, same syntax as ``--models``) gates which
  models exist at startup. When the user has narrowed it, a ``--model`` switch
  that ignored it would leave mu resolving nothing, so the new
  ``provider/model`` pattern is added to the list.
* ``defaultThinkingLevel`` is a per-tier preference, not part of the model
  identity, so it is deliberately left alone.

Credentials saved by ``mu setup``/``/login`` live in ``auth.json`` and are not
touched. Reuses no prime logic — different home, and mu has no recentModels.
"""
from __future__ import annotations

import os
import re

from . import config
from .registry import KIND_API_KEY, KIND_BASE_URL, Slot, register

MODELS_JSON = config.HOME / ".mu" / "agent" / "models.json"
_ENV_NAME_RE = re.compile(r"[A-Z][A-Z0-9_]*")


@register
class MuAdapter:
    id = "mu"
    name = "Mu"
    primary = "mu.default_model"
    follow = ()
    path = config.HOME / ".mu" / "agent" / "settings.json"
    # apply() also rewrites the provider catalog; snapshot it so `ccse undo`
    # restores the endpoint and key, not just the model selection.
    snapshot_paths = (MODELS_JSON,)

    @property
    def available(self) -> bool:
        return self.path.exists()

    def _settings(self) -> dict:
        return config.load_json(self.path) or {}

    def _models(self) -> dict:
        return config.load_json(MODELS_JSON) or {}

    def _provider(self, settings: dict, models: dict | None = None):
        """Active provider name + its models.json entry."""
        pname = settings.get("defaultProvider")
        provs = (models if models is not None else self._models()).get("providers") or {}
        prov = provs.get(pname) if isinstance(pname, str) else None
        if not isinstance(prov, dict):
            return pname, None
        return pname, prov

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        s = self._settings()
        pname, prov = self._provider(s)
        out = [Slot(key="mu.default_model", label="defaultModel",
                    current=s.get("defaultModel")),
               Slot(key="mu.default_provider", label="defaultProvider",
                    current=pname if isinstance(pname, str) else None)]
        if prov is not None:
            models = prov.get("models") or []
            cur = models[0].get("id") if models and isinstance(models[0], dict) else None
            out.append(Slot(key="mu.provider_model",
                            label="providers.<active>.models[0].id",
                            current=cur))
            out.append(Slot(key="mu.base_url",
                            label=f"providers.{pname}.baseUrl",
                            current=prov.get("baseUrl"), kind=KIND_BASE_URL))
            out.append(Slot(key="mu.api_key",
                            label=f"providers.{pname}.apiKey",
                            current=prov.get("apiKey"), kind=KIND_API_KEY))
        return out

    def _split_model(self, value: str, provs: dict) -> tuple[str | None, str]:
        """`--model newapi/glm-5.2` selects the provider when that name is
        configured; any other slash is part of the model id (many ids carry
        one, e.g. `qwen/qwen3-235b`)."""
        if "/" in value:
            head, _, tail = value.partition("/")
            if head in provs and tail:
                return head, tail
        return None, value

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        relevant = {k[len("mu."):]: v for k, v in assignments.items()
                    if k.startswith("mu.")}
        if not relevant or not self.available:
            return []
        s = self._settings()
        m = self._models()
        provs = m.get("providers") or {}
        pname, prov = self._provider(s, m)
        diffs: list[str] = []
        s_dirty = m_dirty = False

        new_model = relevant.get("default_model")
        if new_model is not None:
            want_provider, bare_model = self._split_model(new_model, provs)
        else:
            want_provider, bare_model = None, None

        # settings.defaultProvider dangling (absent from models.json): the model
        # never resolves and the catalog sync below would be skipped — repoint
        # to the sole configured provider.
        if prov is None and isinstance(pname, str):
            cand = next(iter(provs), None)
            if isinstance(cand, str):
                diffs.append(f"  defaultProvider: {pname!r} -> {cand!r} "
                             "(absent from models.json)")
                pname, prov = cand, provs[cand]
                if not dry:
                    s["defaultProvider"] = cand
                    s_dirty = True
        if want_provider and want_provider != pname:
            diffs.append(f"  defaultProvider: {pname!r} -> {want_provider!r}")
            if not dry:
                s["defaultProvider"] = want_provider
                s_dirty = True
            pname = want_provider
            prov = provs.get(want_provider)
        if "default_provider" in relevant and relevant["default_provider"] != pname:
            diffs.append(f"  defaultProvider: {pname!r} -> "
                         f"{relevant['default_provider']!r}")
            if not dry:
                s["defaultProvider"] = relevant["default_provider"]
                s_dirty = True
            pname = relevant["default_provider"]
            prov = provs.get(pname) if isinstance(pname, str) else None

        # 1. settings.json — defaultModel
        if bare_model is not None and bare_model != s.get("defaultModel"):
            diffs.append(f"  defaultModel: {s.get('defaultModel')!r} -> {bare_model!r}")
            if not dry:
                s["defaultModel"] = bare_model
                s_dirty = True

        # 2. enabledModels gates startup selection: keep the new pair visible
        enabled = s.get("enabledModels")
        if bare_model is not None and isinstance(enabled, list) and enabled:
            pattern = f"{pname or 'newapi'}/{bare_model}"
            if pattern not in enabled:
                diffs.append(f"  enabledModels: += {pattern!r}")
                if not dry:
                    enabled.insert(0, pattern)
                    s_dirty = True

        # 3. models.json — active provider: model catalog + endpoint
        if prov is not None:
            if bare_model is not None:  # run even when settings already in sync
                models_list = prov.setdefault("models", [])
                new_name = bare_model.replace("-", " ").title()
                first = models_list[0] if models_list and isinstance(models_list[0], dict) \
                    else None
                if first is None:
                    models_list.insert(0, {"id": bare_model, "name": new_name})
                    diffs.append(f"  providers[{pname}].models[0].id -> {bare_model!r}")
                    m_dirty = True
                elif first.get("id") != bare_model:
                    first["id"] = bare_model
                    # the picker shows `name`, not `id` — keep them in sync
                    first["name"] = new_name
                    diffs.append(f"  providers[{pname}].models[0].id/name -> {bare_model!r}")
                    m_dirty = True
                elif first.get("name") != new_name:
                    first["name"] = new_name
                    diffs.append(f"  providers[{pname}].models[0].name -> {new_name!r}")
                    m_dirty = True
            if "base_url" in relevant:
                base_url = config.ensure_openai_v1(relevant["base_url"])
                if prov.get("baseUrl") != base_url:
                    diffs.append(f"  providers[{pname}].baseUrl: "
                                 f"{prov.get('baseUrl')!r} -> {base_url!r}")
                    if not dry:
                        prov["baseUrl"] = base_url
                        m_dirty = True
            cur_key = prov.get("apiKey")
            if isinstance(cur_key, str) and _ENV_NAME_RE.fullmatch(cur_key):
                lit = os.environ.get(cur_key)
                if lit:
                    diffs.append(f"  providers[{pname}].apiKey: {cur_key!r} -> "
                                 f"{config.redact(lit)!r} (env inlined)")
                    if not dry:
                        prov["apiKey"] = lit
                        m_dirty = True
            if "api_key" in relevant and prov.get("apiKey") != relevant["api_key"]:
                diffs.append(f"  providers[{pname}].apiKey: "
                             f"{config.redact(prov.get('apiKey'))!r} -> "
                             f"{config.redact(relevant['api_key'])!r}")
                if not dry:
                    prov["apiKey"] = relevant["api_key"]
                    m_dirty = True

        if m_dirty and not dry:
            config.keep_mode_write_json(MODELS_JSON, m)
        if s_dirty and not dry:
            config.keep_mode_write_json(self.path, s)
        return diffs
