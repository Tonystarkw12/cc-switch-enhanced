"""Qwen Code adapter: ~/.qwen/settings.json model.name / baseUrl / env key."""
from __future__ import annotations

from . import config
from .registry import KIND_API_KEY, KIND_BASE_URL, Adapter, Slot, register

FALLBACK_ENV_KEY = "NEWAPI_API_KEY"


def _env_var_for_base(d: dict, base_url: str | None) -> str:
    """Env var name qwen uses for a base_url: the modelProviders entry whose
    baseUrl matches, else NEWAPI_API_KEY."""
    for p in (d.get("modelProviders") or {}).get("openai", []) or []:
        if isinstance(p, dict) and p.get("baseUrl") == base_url and p.get("envKey"):
            return p["envKey"]
    return FALLBACK_ENV_KEY


@register
class QwenAdapter:
    id = "qwen"
    name = "Qwen Code"
    primary = "qwen.model"
    path = config.HOME / ".qwen" / "settings.json"

    @property
    def available(self) -> bool:
        return self.path.exists()

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        import os
        d = config.load_json(self.path) or {}
        m = d.get("model") or {}
        base = m.get("baseUrl") if isinstance(m, dict) else None
        out = [Slot(key=f"{self.id}.model", label="model.name",
                    current=m.get("name") if isinstance(m, dict) else None)]
        if base:
            var = _env_var_for_base(d, base)
            out.append(Slot(key=f"{self.id}.base_url", label="model.baseUrl",
                            current=base, kind=KIND_BASE_URL))
            key = (d.get("env") or {}).get(var) or os.environ.get(var)
            out.append(Slot(key=f"{self.id}.api_key", label=f"env.{var}",
                            current=key if key else None, kind=KIND_API_KEY))
        return out

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        relevant = {k[len("qwen."):]: v for k, v in assignments.items()
                    if k.startswith("qwen.")}
        if not relevant or not self.available:
            return []
        d = config.load_json(self.path) or {}
        m = d.setdefault("model", {})
        diffs: list[str] = []
        if "model" in relevant:
            old = m.get("name")
            if old != relevant["model"]:
                diffs.append(f"  model.name: {old!r} -> {relevant['model']!r}")
                if not dry:
                    m["name"] = relevant["model"]
        if "base_url" in relevant:
            old = m.get("baseUrl")
            if old != relevant["base_url"]:
                diffs.append(f"  model.baseUrl: {old!r} -> {relevant['base_url']!r}")
                if not dry:
                    m["baseUrl"] = relevant["base_url"]
        if "api_key" in relevant:
            var = _env_var_for_base(d, m.get("baseUrl"))
            env = d.setdefault("env", {})
            old = env.get(var)
            if old != relevant["api_key"]:
                diffs.append(f"  env.{var}: {config.redact(old)!r} -> "
                             f"{config.redact(relevant['api_key'])!r}")
                if not dry:
                    env[var] = relevant["api_key"]
        if diffs and not dry:
            config.keep_mode_write_json(self.path, d)
        return diffs