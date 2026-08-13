"""Claude Code adapter: ~/.claude/settings.json env block."""
from __future__ import annotations

from pathlib import Path

from . import config
from .registry import (KIND_API_KEY, KIND_BASE_URL, KIND_MODEL, Adapter, Slot,
                       register)

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

# endpoint slots: single env key each (no alias list needed)
ENDPOINT_ENV = {
    KIND_BASE_URL: ("base_url", "ANTHROPIC_BASE_URL"),
    KIND_API_KEY: ("api_key", "ANTHROPIC_AUTH_TOKEN"),
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
            text = config.keep_mode_write_json(self.path, data)
            _ = text
        return diffs

    def probe(self, timeout: int = 8) -> tuple[str, str]:
        """Claude Code speaks Anthropic Messages (/v1/messages), not OpenAI
        /models, so the default probe can't judge it. POST a 1-token request."""
        import json
        import socket
        import ssl
        import urllib.error
        import urllib.request

        env = self._env()
        base, model, key = env.get("ANTHROPIC_BASE_URL"), \
            env.get("ANTHROPIC_MODEL"), env.get("ANTHROPIC_AUTH_TOKEN")
        if not base or not model:
            return ("SKIP", "no ANTHROPIC_BASE_URL/model configured")
        # [1M] is a Claude Code context-window marker it strips before sending
        model = model.removesuffix("[1M]")
        url = base.rstrip("/") + "/v1/messages"
        payload = json.dumps({
            "model": model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("x-api-key", key) if key else None
        req.add_header("anthropic-version", "2023-06-01")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as ex:
            if ex.code in (401, 403):
                return ("FAIL", f"HTTP {ex.code} — api_key rejected")
            return ("FAIL", f"HTTP {ex.code} — not an Anthropic-compatible endpoint")
        except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError,
                OSError) as ex:
            return ("FAIL", f"endpoint unreachable: {getattr(ex, 'reason', ex)}")
        except Exception as ex:
            return ("FAIL", f"response parse error: {ex}")
        if body.get("type") == "error":
            return ("FAIL", f"endpoint rejected: {body['error'].get('message', body['error'])}")
        return ("PASS", "anthropic /v1/messages ok")