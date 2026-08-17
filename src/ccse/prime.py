"""Prime adapter: a pi-family CLI that keeps Claude-Code-style settings + its
own provider catalog.

Prime resolves the active model from ``settings.json``'s ``defaultModel``
(paired with ``defaultProvider``), NOT from the ``env.ANTHROPIC_MODEL`` block —
that env block is inert here. The model must exist in ``models.json`` under the
active provider (``providers.<defaultProvider>.models``), where base_url and the
apiKey env-var name also live. ``--model`` writes all three: settings
defaultModel, the provider's model catalog entry, and the recentModels list.

Reuses no ClaudeAdapter logic — the config semantics are different.
"""
from __future__ import annotations

import json

from . import config
from .registry import KIND_API_KEY, KIND_BASE_URL, KIND_MODEL, Adapter, Slot, register

MODELS_JSON = config.HOME / ".prime" / "agent" / "models.json"
ENV_NAME = "OPENAI_API_KEY"  # models.json apiKey is a bare env-var name


@register
class PrimeAdapter:
    id = "prime"
    name = "Prime"
    primary = "prime.default_model"
    # recentModels is updated as a side effect of defaultModel in apply()
    follow = ()
    path = config.HOME / ".prime" / "agent" / "settings.json"

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
        prov = provs.get(pname) if pname else None
        if not isinstance(prov, dict):
            return pname, None
        return pname, prov

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        s = self._settings()
        out = [Slot(key="prime.default_model", label="defaultModel",
                    current=s.get("defaultModel"))]
        rm = s.get("recentModels")
        if isinstance(rm, list):
            out.append(Slot(key="prime.recent_models", label="recentModels",
                            current=", ".join(rm)))
        _, prov = self._provider(s)
        if prov is not None:
            models = prov.get("models") or []
            cur = None
            if models and isinstance(models[0], dict):
                cur = models[0].get("id")
            out.append(Slot(key="prime.provider_model",
                            label=f"providers.<active>.models[0].id",
                            current=cur))
            out.append(Slot(key="prime.base_url",
                            label=f"providers.<active>.baseUrl",
                            current=prov.get("baseUrl"), kind=KIND_BASE_URL))
            out.append(Slot(key="prime.api_key",
                            label=f"providers.<active>.apiKey",
                            current=prov.get("apiKey"), kind=KIND_API_KEY))
        return out

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        import os
        relevant = {k[len("prime."):]: v for k, v in assignments.items()
                    if k.startswith("prime.")}
        if not relevant or not self.available:
            return []
        s = self._settings()
        m = self._models()
        pname, prov = self._provider(s, m)
        new_model = relevant.get("default_model")
        old_model = s.get("defaultModel")
        diffs: list[str] = []
        s_dirty = m_dirty = False
        # settings.defaultProvider dangling (absent from models.json) — the
        # model never resolves and the catalog sync below would be skipped;
        # repoint to the sole configured provider
        if prov is None:
            cand = next(iter(m.get("providers") or {}), None)
            if isinstance(cand, str):
                diffs.append(f"  defaultProvider: {pname!r} -> {cand!r} "
                             "(absent from models.json)")
                pname, prov = cand, m["providers"][cand]
                if not dry:
                    s["defaultProvider"] = cand
                    s_dirty = True

        # 1. settings.json — defaultModel (+ recentModels follow)
        if new_model is not None and new_model != old_model:
            diffs.append(f"  defaultModel: {old_model!r} -> {new_model!r}")
            if not dry:
                s["defaultModel"] = new_model
                s_dirty = True
                rm = s.get("recentModels")
                if isinstance(rm, list):
                    for i, item in enumerate(rm):
                        if isinstance(item, str) and item.split("/")[-1] == old_model:
                            rm[i] = f"{pname or 'newapi'}/{new_model}"
                    if not any(isinstance(i, str) and i.split("/")[-1] == new_model
                               for i in rm):
                        rm.insert(0, f"{pname or 'newapi'}/{new_model}")
                    diffs.append(f"  recentModels: -> {pname or 'newapi'}/{new_model}")

        # 2. models.json — active provider: model catalog + endpoint
        if prov is not None:
            if new_model is not None:  # run even when settings already in sync
                models_list = prov.setdefault("models", [])
                new_name = new_model.replace("-", " ").title()
                if models_list and isinstance(models_list[0], dict) \
                        and models_list[0].get("id") != new_model:
                    models_list[0]["id"] = new_model  # first entry = default
                    # status bar shows `name`, not `id` — keep them in sync
                    models_list[0]["name"] = new_name
                    diffs.append(f"  providers[{pname}].models[0].id/name -> {new_model!r}")
                    m_dirty = True
                elif models_list and isinstance(models_list[0], dict) \
                        and models_list[0].get("name") != new_name:
                    models_list[0]["name"] = new_name  # id already current, name stale
                    diffs.append(f"  providers[{pname}].models[0].name -> {new_name!r}")
                    m_dirty = True
                elif not models_list:
                    models_list.insert(0, {"id": new_model, "name": new_model})
                    diffs.append(f"  providers[{pname}].models[0].id -> {new_model!r}")
                    m_dirty = True
            if "base_url" in relevant:
                base_url = config.ensure_openai_v1(relevant["base_url"])
                if prov.get("baseUrl") != base_url:
                    diffs.append(f"  providers[{pname}].baseUrl: "
                                 f"{prov.get('baseUrl')!r} -> {base_url!r}")
                    if not dry:
                        prov["baseUrl"] = base_url
                        m_dirty = True
            if "api_key" in relevant:
                var = prov.get("apiKey") or ENV_NAME
                old_key = os.environ.get(var)
                if old_key != relevant["api_key"]:
                    if not dry:
                        from .envrc import ensure_env_var
                        ensure_env_var(var, relevant["api_key"])
                    diffs.append(f"  env {var}: {config.redact(old_key)!r} -> "
                                 f"{config.redact(relevant['api_key'])!r}")
        if m_dirty and not dry:
            config.keep_mode_write_json(MODELS_JSON, m)
        if s_dirty and not dry:
            config.keep_mode_write_json(self.path, s)
        return diffs
