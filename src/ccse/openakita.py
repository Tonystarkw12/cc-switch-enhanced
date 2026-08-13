"""OpenAkita adapter: ~/.openakita/data/llm_endpoints.json.

OpenAkita resolves its relay endpoint from this file (see
``relay/resolver.py`` in the openakita package); ``DEFAULT_MODEL`` in ~/.env
is only a peripheral-feature fallback, NOT the main coding model, so it is
intentionally not touched here. The primary endpoint (``priority: 1``, else
``endpoints[0]``) carries the live ``model`` and ``base_url``. The API key
itself lives in ~/.env under the name given by ``api_key_env`` and is out of
scope for a model switch.
"""
from __future__ import annotations

from . import config
from .registry import KIND_BASE_URL, KIND_MODEL, Slot, register

PATH = config.HOME / ".openakita" / "data" / "llm_endpoints.json"


def _primary_endpoint(d: dict) -> dict | None:
    """Return the priority-1 endpoint, else the first endpoint, else None."""
    eps = d.get("endpoints")
    if not isinstance(eps, list) or not eps:
        return None
    for ep in eps:
        if isinstance(ep, dict) and ep.get("priority") == 1:
            return ep
    return eps[0] if isinstance(eps[0], dict) else None


@register
class OpenAkitaAdapter:
    id = "openakita"
    name = "OpenAkita"
    primary = "openakita.model"
    path = PATH

    @property
    def available(self) -> bool:
        return self.path.exists()

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        d = config.load_json(self.path) or {}
        ep = _primary_endpoint(d)
        if not ep:
            return [Slot(key=f"{self.id}.model", label="endpoints[0].model",
                         current=None)]
        return [
            Slot(key=f"{self.id}.model", label="endpoints[0].model",
                 current=ep.get("model"), kind=KIND_MODEL),
            Slot(key=f"{self.id}.base_url", label="endpoints[0].base_url",
                 current=ep.get("base_url"), kind=KIND_BASE_URL),
        ]

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        if not self.available:
            return []
        model = assignments.get(f"{self.id}.model")
        base = assignments.get(f"{self.id}.base_url")
        if model is None and base is None:
            return []
        d = config.load_json(self.path) or {}
        ep = _primary_endpoint(d)
        if not ep:
            return ["  (skip: no endpoints[] in llm_endpoints.json)"]
        diffs: list[str] = []
        if model is not None:
            old = ep.get("model")
            if old != model:
                diffs.append(f"  endpoints[0].model: {old!r} -> {model!r}")
                if not dry:
                    ep["model"] = model
        # base_url written verbatim (matches qwen/codex convention; do not
        # force /v1 — openakita's resolver expects whatever the user gives).
        if base is not None:
            old = ep.get("base_url")
            if old != base:
                diffs.append(f"  endpoints[0].base_url: {old!r} -> {base!r}")
                if not dry:
                    ep["base_url"] = base
        if diffs and not dry:
            config.keep_mode_write_json(self.path, d)
        return diffs
