"""Adapter base + registry."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

REGISTRY: dict[str, type] = {}


@dataclass
class Slot:
    """A single mutable model-name field within an adapter."""

    key: str  # dotted path as it appears in profiles.toml, e.g. "model", "claude.haiku"
    label: str  # human label shown by `show`
    current: str | None  # detected current value, None if unset/agent absent


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