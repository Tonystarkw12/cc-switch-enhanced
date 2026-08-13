"""Adapter base + registry."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

REGISTRY: dict[str, type] = {}

# slot kinds
KIND_MODEL = "model"
KIND_BASE_URL = "base_url"
KIND_API_KEY = "api_key"


@dataclass
class Slot:
    """A single mutable field within an adapter.

    key: dotted path as it appears in profiles.toml, e.g. "model", "claude.haiku"
    label: human label shown by `show`
    current: detected current value, None if unset/agent absent
    kind: model | base_url | api_key — which `--X` flag targets it
    follows: model slot that tracks the primary on a bare `--model NAME`
        (subagent/secondary fields). Tier slots leave this False.
    """

    key: str
    label: str
    current: str | None
    kind: str = KIND_MODEL
    follows: bool = False


class Adapter(Protocol):
    id: str
    name: str
    path: Path
    available: bool

    def slots(self) -> list[Slot]: ...
    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]: ...
    """Apply slot->value mappings. `dry` True => write nothing, return diff lines."""


def register(cls):
    REGISTRY[cls.id] = cls
    return cls


def all_adapters() -> list:
    return [cls() for cls in REGISTRY.values()]