"""Codex adapter: ~/.codex/config.toml top-level `model` + provider base_url/env_key."""
from __future__ import annotations

import os
import tomllib

from . import config
from .registry import KIND_API_KEY, KIND_BASE_URL, Adapter, Slot, register


@register
class CodexAdapter:
    id = "codex"
    name = "Codex"
    primary = "codex.model"
    path = config.HOME / ".codex" / "config.toml"

    @property
    def available(self) -> bool:
        return self.path.exists()

    def _load(self) -> dict:
        return tomllib.loads(self.path.read_text("utf-8"))

    def _provider(self, d: dict) -> tuple[str | None, dict | None]:
        name = d.get("model_provider")
        provs = d.get("model_providers") or {}
        if not name or name not in provs or not isinstance(provs[name], dict):
            return name, None
        return name, provs[name]

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        d = self._load()
        out = [Slot(key=f"{self.id}.model", label="model",
                    current=d.get("model"))]
        _, prov = self._provider(d)
        if prov is not None:
            out.append(Slot(key=f"{self.id}.base_url", label="provider base_url",
                            current=prov.get("base_url"), kind=KIND_BASE_URL))
            # api_key lives in an env var (env_key names it); expose the var NAME
            out.append(Slot(key=f"{self.id}.api_key", label="provider env_key",
                            current=prov.get("env_key"), kind=KIND_API_KEY))
        return out

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        if not self.available:
            return []
        relevant = {k[len("codex."):]: v for k, v in assignments.items()
                    if k.startswith("codex.")}
        if not relevant:
            return []
        d = self._load()
        prov_name, prov = self._provider(d)
        diffs: list[str] = []
        config_dirty = False
        if "model" in relevant:
            old = d.get("model")
            if old != relevant["model"]:
                diffs.append(f"  model: {old!r} -> {relevant['model']!r}")
                if not dry:
                    d["model"] = relevant["model"]
                    config_dirty = True
        if prov is not None:
            if "base_url" in relevant:
                old = prov.get("base_url")
                if old != relevant["base_url"]:
                    diffs.append(
                        f"  model_providers[{prov_name}].base_url: {old!r} -> "
                        f"{relevant['base_url']!r}")
                    if not dry:
                        prov["base_url"] = relevant["base_url"]
                        config_dirty = True
            if "api_key" in relevant:
                var = prov.get("env_key") or "NEWAPI_API_KEY"
                # codex reads the key from $var; persist the literal into ~/.zshrc
                old_key = os.environ.get(var)
                if old_key != relevant["api_key"]:
                    if not dry:
                        from .envrc import ensure_env_var
                        ensure_env_var(var, relevant["api_key"])
                    diffs.append(
                        f"  env {var} (zshrc): {config.redact(old_key)!r} -> "
                        f"{config.redact(relevant['api_key'])!r}")
        if config_dirty and not dry:
            if not config.detect_tomli_w():
                config.die("tomli_w not installed; run `uv pip install tomli-w` to write Codex TOML")
            import tomli_w  # type: ignore
            text = tomli_w.dumps(d)
            config.write_text_atomic(self.path, text)
        return diffs