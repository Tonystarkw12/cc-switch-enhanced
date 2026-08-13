"""JCode adapter: ~/.jcode/config.toml.

Active model = ``[provider].default_model`` (global). The active provider block
``providers.<default_provider>`` carries ``base_url`` + ``api_key_env`` (an env
var NAME — the key itself lives in ~/.zshrc, like codex/grok/reasonix). Model
writes mirror into the provider block's ``default_model`` and ensure a matching
``[[providers.<name>.models]]`` registry entry exists (jcode validates against
it at startup). ``default_provider`` can name a missing block (stale type ref),
so we fall back to the first ``providers.*`` block when it does.
"""
from __future__ import annotations

import os
import tomllib

from . import config
from .registry import KIND_API_KEY, KIND_BASE_URL, Slot, register


@register
class JCodeAdapter:
    id = "jcode"
    name = "JCode"
    primary = "jcode.model"
    path = config.HOME / ".jcode" / "config.toml"

    @property
    def available(self) -> bool:
        return self.path.exists()

    def _load(self) -> dict:
        return tomllib.loads(self.path.read_text("utf-8"))

    def _provider(self, d: dict) -> tuple[str | None, dict | None]:
        """Resolve the active provider block. Falls back to the first
        ``providers.*`` block when default_provider names none (stale ref)."""
        name = (d.get("provider") or {}).get("default_provider")
        provs = d.get("providers") or {}
        if isinstance(provs, dict):
            if name and isinstance(provs.get(name), dict):
                return name, provs[name]
            for k, v in provs.items():
                if isinstance(v, dict):
                    return k, v
        return name, None

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        d = self._load()
        out = [Slot(key=f"{self.id}.model", label="provider.default_model",
                    current=(d.get("provider") or {}).get("default_model"))]
        _, prov = self._provider(d)
        if prov is not None:
            out.append(Slot(key=f"{self.id}.base_url", label="provider base_url",
                            current=prov.get("base_url"), kind=KIND_BASE_URL))
            env_var = prov.get("api_key_env")
            if env_var:
                out.append(Slot(key=f"{self.id}.api_key", label="provider api_key_env",
                                current=env_var, kind=KIND_API_KEY))
            elif "api_key" in prov:
                out.append(Slot(key=f"{self.id}.api_key", label="provider api_key",
                                current=prov.get("api_key"), kind=KIND_API_KEY))
        return out

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        if not self.available:
            return []
        relevant = {k[len("jcode."):]: v for k, v in assignments.items()
                    if k.startswith("jcode.")}
        if not relevant:
            return []
        d = self._load()
        prov_name, prov = self._provider(d)
        diffs: list[str] = []
        config_dirty = False
        if "model" in relevant:
            val = relevant["model"]
            # global active model
            prov_sec = d.setdefault("provider", {})
            old = prov_sec.get("default_model")
            if old != val:
                diffs.append(f"  provider.default_model: {old!r} -> {val!r}")
                if not dry:
                    prov_sec["default_model"] = val
                    config_dirty = True
            # mirror into the provider block + ensure registry entry
            if prov is not None:
                old2 = prov.get("default_model")
                if old2 != val:
                    diffs.append(
                        f"  providers[{prov_name}].default_model: {old2!r} -> {val!r}")
                    if not dry:
                        prov["default_model"] = val
                        config_dirty = True
                models = prov.get("models") or []
                if not any(isinstance(m, dict) and m.get("id") == val
                           for m in models):
                    diffs.append(f"  providers[{prov_name}].models: + {{id = {val!r}}}")
                    if not dry:
                        prov.setdefault("models", []).append({"id": val})
                        config_dirty = True
        if prov is not None:
            if "base_url" in relevant:
                old = prov.get("base_url")
                if old != relevant["base_url"]:
                    diffs.append(
                        f"  providers[{prov_name}].base_url: {old!r} -> "
                        f"{relevant['base_url']!r}")
                    if not dry:
                        prov["base_url"] = relevant["base_url"]
                        config_dirty = True
            if "api_key" in relevant:
                kval = relevant["api_key"]
                env_var = prov.get("api_key_env")
                if env_var:
                    old_key = os.environ.get(env_var)
                    if old_key != kval:
                        if not dry:
                            from .envrc import ensure_env_var
                            ensure_env_var(env_var, kval)
                        diffs.append(
                            f"  env {env_var} (zshrc): {config.redact(old_key)!r} -> "
                            f"{config.redact(kval)!r}")
                elif "api_key" in prov:
                    old = prov.get("api_key")
                    if old != kval:
                        diffs.append(
                            f"  providers[{prov_name}].api_key: "
                            f"{config.redact(old)!r} -> {config.redact(kval)!r}")
                        if not dry:
                            prov["api_key"] = kval
                            config_dirty = True
        if config_dirty and not dry:
            if not config.detect_tomli_w():
                config.die("tomli_w not installed; run `uv pip install tomli-w` to write JCode TOML")
            import tomli_w  # type: ignore
            config.write_text_atomic(self.path, tomli_w.dumps(d))
        return diffs
