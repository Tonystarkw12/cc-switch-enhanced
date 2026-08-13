"""OpenCode adapter: ~/.config/opencode/opencode.json."""
from __future__ import annotations

from . import config
from .registry import KIND_API_KEY, KIND_BASE_URL, Adapter, Slot, register


@register
class OpenCodeAdapter:
    id = "opencode"
    name = "OpenCode"
    primary = "opencode.model"
    path = config.HOME / ".config" / "opencode" / "opencode.json"

    @property
    def available(self) -> bool:
        return self.path.exists()

    def _provider(self, d) -> str | None:
        m = d.get("model")
        if isinstance(m, str) and "/" in m:
            return m.split("/", 1)[0]
        return None

    def _endpoint(self, d, kind):
        """provider.<active>.options.<baseURL|apiKey>"""
        prov = self._provider(d)
        if not prov:
            return None
        p = (d.get("provider") or {}).get(prov) or {}
        if kind == KIND_BASE_URL:
            return (p.get("options") or {}).get("baseURL")
        return (p.get("options") or {}).get("apiKey")

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        d = config.load_json(self.path) or {}
        out = [Slot(key=f"{self.id}.model", label="model",
                    current=d.get("model"))]
        for role, v in (d.get("agent") or {}).items():
            if isinstance(v, dict) and "model" in v:
                out.append(Slot(key=f"{self.id}.agent.{role}.model",
                                label=f"agent.{role}.model",
                                current=v.get("model")))
        prov = self._provider(d)
        if prov:
            out.append(Slot(key=f"{self.id}.base_url", label=f"provider.{prov}.baseURL",
                            current=self._endpoint(d, KIND_BASE_URL), kind=KIND_BASE_URL))
            out.append(Slot(key=f"{self.id}.api_key", label=f"provider.{prov}.apiKey",
                            current=self._endpoint(d, KIND_API_KEY), kind=KIND_API_KEY))
        return out

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        relevant = {k: v for k, v in assignments.items() if k.startswith(f"{self.id}.")}
        if not relevant or not self.available:
            return []
        d = config.load_json(self.path) or {}
        diffs: list[str] = []
        top = f"{self.id}.model"
        if top in relevant:
            old = d.get("model")
            if old != relevant[top]:
                diffs.append(f"  model: {old!r} -> {relevant[top]!r}")
                if not dry:
                    d["model"] = relevant[top]
        for key, val in relevant.items():
            prefix = f"{self.id}.agent."
            if key.startswith(prefix):
                rest = key[len(prefix):]  # e.g. build.model
                role, _, field = rest.partition(".")
                if role and field == "model":
                    agent = d.setdefault("agent", {}).setdefault(role, {})
                    old = agent.get("model")
                    if old != val:
                        diffs.append(f"  agent.{role}.model: {old!r} -> {val!r}")
                        if not dry:
                            agent["model"] = val
        # endpoint slots
        prov = self._provider(d)
        if prov:
            p = d.setdefault("provider", {}).setdefault(prov, {}).setdefault("options", {})
            for key, field in ((f"{self.id}.base_url", "baseURL"),
                               (f"{self.id}.api_key", "apiKey")):
                if key in relevant:
                    old = p.get(field)
                    if old != relevant[key]:
                        diffs.append(f"  provider.{prov}.options.{field}: {old!r} -> "
                                     f"{relevant[key]!r}")
                        if not dry:
                            p[field] = relevant[key]
        if diffs and not dry:
            config.keep_mode_write_json(self.path, d)
        return diffs