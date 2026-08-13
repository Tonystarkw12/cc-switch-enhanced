"""Prime adapter: a Claude-Code-family CLI whose config mirrors ~/.claude.

Prime keeps its settings in `~/.prime/agent/settings.json` with the exact same
env block keys as Claude Code (ANTHROPIC_MODEL, ANTHROPIC_BASE_URL, ...), so we
reuse ClaudeAdapter wholesale and only point it at Prime's path. Its model
name carries no `[1M]` aggregator marker, so the suffix is cleared.
"""
from __future__ import annotations

from . import config
from .claude import ClaudeAdapter
from .registry import register


@register
class PrimeAdapter(ClaudeAdapter):
    id = "prime"
    name = "Prime"
    primary = "prime.model"
    follow = ("prime.model", "prime.subagent")
    suffix = ""  # prime model names carry no [1M] marker (unlike claude)
    path = config.HOME / ".prime" / "agent" / "settings.json"
