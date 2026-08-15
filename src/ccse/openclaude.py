"""OpenClaude adapter: ~/.openclaude/settings.json env block.

OpenClaude (@gitlawb/openclaude, a Claude-Code-workflow harness for any LLM)
applies a settings.json ``env`` object into the process environment at
startup (``applyConfigEnvironmentVariables``), then resolves the model as
``modelOverride || $ANTHROPIC_MODEL || $CLAUDE_MODEL || settings.model ||
default``. Writing ``env.ANTHROPIC_MODEL`` therefore pins the model the same
way the Claude Code adapter does. Same for base_url ($ANTHROPIC_BASE_URL,
read by the Anthropic client constructor) and auth ($ANTHROPIC_AUTH_TOKEN).

No tier slots (haiku/sonnet/opus): openclaude's resolver only reads the main
model var; no ``[1M]`` suffix — that marker is Claude Code-specific.
"""
from __future__ import annotations

from . import config
from .registry import KIND_API_KEY, KIND_BASE_URL, Slot, register

ENV_SLOTS: dict[str, list[str]] = {
    "model": ["ANTHROPIC_MODEL"],
}

ENDPOINT_ENV = {
    KIND_BASE_URL: ("base_url", "ANTHROPIC_BASE_URL"),
    KIND_API_KEY: ("api_key", "ANTHROPIC_AUTH_TOKEN"),
}


@register
class OpenClaudeAdapter:
    id = "openclaude"
    name = "OpenClaude"
    primary = "openclaude.model"
    path = config.HOME / ".openclaude" / "settings.json"

    @property
    def available(self) -> bool:
        return self.path.exists()

    def _env(self) -> dict:
        d = config.load_json(self.path) or {}
        return d.setdefault("env", {})

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        env = self._env()
        out = []
        for slot, keys in ENV_SLOTS.items():
            vals = [env.get(k) for k in keys if env.get(k) is not None]
            out.append(Slot(key=f"{self.id}.{slot}", label="ANTHROPIC_MODEL (main)",
                            current=vals[0] if vals else None))
        for kind, (label, key) in ENDPOINT_ENV.items():
            cur = env.get(key)
            if cur == "":
                cur = None
            out.append(Slot(key=f"{self.id}.{label}", label=f"{label} ({key})",
                            current=cur, kind=kind))
        return out

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        relevant = {k[len(f"{self.id}."):]: v for k, v in assignments.items()
                    if k.startswith(f"{self.id}.")}
        if not relevant or not self.available:
            return []
        data = config.load_json(self.path) or {}
        env = data.setdefault("env", {})
        diffs: list[str] = []
        for slot, val in relevant.items():
            keys = ENV_SLOTS.get(slot)
            if keys:
                for k in keys:
                    old = env.get(k)
                    if old != val:
                        diffs.append(f"  env.{k}: {old!r} -> {val!r}")
                        if not dry:
                            env[k] = val
            elif slot in (KIND_BASE_URL, KIND_API_KEY):
                k = ENDPOINT_ENV[slot][1]
                old = env.get(k)
                if old != val:
                    diffs.append(f"  env.{k}: {old!r} -> {val!r}")
                    if not dry:
                        env[k] = val
        if diffs and not dry:
            config.keep_mode_write_json(self.path, data)
        return diffs
