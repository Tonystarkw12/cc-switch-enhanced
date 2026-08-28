"""ZCode adapter: ~/.zcode global instructions only.

ZCode (a Claude-Code-workflow clone) loads ~/.zcode/AGENTS.md as its global
instructions file, so `ccse rules` targets it like every other agent.

Its endpoint/model, however, is managed by the harness's own builtin-plan
auth (bigmodel coding plan): the server bundle resolves
BIGMODEL_CODING_PLAN_ANTHROPIC_BASE_URL internally and never reads
process.env.ANTHROPIC_BASE_URL / ANTHROPIC_MODEL, and ~/.zcode/cli/config.json
carries no model slot. Writing a speculative settings.json would be ignored,
so slots() returns [] — this adapter is rules-only until the harness gains a
verified external override surface.
"""
from __future__ import annotations

from . import config
from .registry import Slot, register


@register
class ZCodeAdapter:
    id = "zcode"
    name = "ZCode"
    path = config.HOME / ".zcode" / "AGENTS.md"

    @property
    def available(self) -> bool:
        return self.path.exists()

    def slots(self) -> list[Slot]:
        return []

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        return []
