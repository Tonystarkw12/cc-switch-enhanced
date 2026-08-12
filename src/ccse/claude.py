"""Claude Code adapter: ~/.claude/settings.json env block."""
from __future__ import annotations

from pathlib import Path

from . import config
from .registry import Adapter, Slot, register

ENV_SLOTS: dict[str, list[str]] = {
    "model":    ["ANTHROPIC_MODEL"],
    "haiku":    ["ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME"],
    "sonnet":   ["ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME"],
    "opus":     ["ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME"],
    "subagent": ["CLAUDE_CODE_SUBAGENT_MODEL"],
}

LABELS: dict[str, str] = {
    "model": "ANTHROPIC_MODEL (main)",
    "haiku": "Haiku tier",
    "sonnet": "Sonnet tier",
    "opus": "Opus tier",
    "subagent": "CLAUDE_CODE_SUBAGENT_MODEL",
}


@register
class ClaudeAdapter:
    id = "claude"
    name = "Claude Code"
    primary = "claude.model"
    # slots `ccse --model X` also sets, in addition to primary: the subagent
    # model should follow the main model. Tier overrides (haiku/sonnet/opus)
    # are deliberately excluded — users may run different models per tier
    # (e.g. sonnet=qwen3.8-max while main=glm-5.2); switch those via profile.
    follow = ("claude.model", "claude.subagent")
    suffix = "[1M]"  # Claude Code model names carry a context-window marker the
    #                aggregator needs (e.g. "glm-5.2[1M]"); other agents don't.
    path = config.HOME / ".claude" / "settings.json"

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
            cur = vals[0] if vals else None
            out.append(Slot(key=f"{self.id}.{slot}", label=LABELS[slot], current=cur))
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
            if not keys:
                continue
            for k in keys:
                old = env.get(k)
                if old != val:
                    diffs.append(f"  env.{k}: {old!r} -> {val!r}")
                    if not dry:
                        env[k] = val
        if diffs and not dry:
            text = config.keep_mode_write_json(self.path, data)
            _ = text
        return diffs