"""OpenHands adapter: ~/.openhands/agent_settings.json — llm.{model,base_url,api_key}.

OpenHands SDK v1.x persists the default agent spec (a serialized Agent model,
``save()`` writes ``model_dump_json(context={"expose_secrets": True})``) to
``~/.openhands/agent_settings.json``; ``load_or_create`` reads it back and the
comment there says it "respects user choices persisted in agent_settings.json".
The ``llm`` field is an LLM model with flat ``model`` / ``base_url`` /
``api_key`` keys — api_key lands as a plain string (SecretStr coerces on load).

Model names follow litellm provider routing (``openai/<name>``,
``anthropic/<name>``, ``litellm_proxy/...``); ccse's keep-prefix keeps whatever
prefix the current value carries. The file only exists after the first
``openhands`` run picks a model — until then the adapter reports missing.
"""
from __future__ import annotations

from . import config
from .registry import KIND_API_KEY, KIND_BASE_URL, KIND_MODEL, Slot, register

PATH = config.HOME / ".openhands" / "agent_settings.json"

FIELDS = {
    "model": (KIND_MODEL, "llm.model"),
    "base_url": (KIND_BASE_URL, "llm.base_url"),
    "api_key": (KIND_API_KEY, "llm.api_key"),
}


@register
class OpenHandsAdapter:
    id = "openhands"
    name = "OpenHands"
    primary = "openhands.model"
    path = PATH

    @property
    def available(self) -> bool:
        return self.path.exists()

    def _llm(self) -> dict:
        d = config.load_json(self.path) or {}
        return d.setdefault("llm", {})

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        llm = self._llm()
        out = []
        for label, (kind, path_label) in FIELDS.items():
            cur = llm.get(label)
            if cur == "":
                cur = None
            out.append(Slot(key=f"{self.id}.{label}", label=path_label,
                            current=cur, kind=kind))
        return out

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        if not self.available:
            return []
        relevant = {k[len(f"{self.id}."):]: v for k, v in assignments.items()
                    if k.startswith(f"{self.id}.")}
        if not relevant:
            return []
        data = config.load_json(self.path) or {}
        llm = data.setdefault("llm", {})
        diffs: list[str] = []
        for label, val in relevant.items():
            if label not in FIELDS:
                continue
            old = llm.get(label)
            if old != val:
                diffs.append(f"  llm.{label}: {old!r} -> {val!r}")
                if not dry:
                    llm[label] = val
        if diffs and not dry:
            config.keep_mode_write_json(self.path, data)
        return diffs
