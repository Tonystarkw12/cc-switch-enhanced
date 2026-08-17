"""Command Code adapter: ~/.commandcode/settings.json — model + featureModels.

Command Code (command-code, cloud-first coding agent) persists its configured
model as the top-level ``model`` string in the user settings.json; per-feature
models live under ``featureModels`` (keys: titleGeneration, compaction,
toolDescription, tasteOnboarding, tasteLearning, branchSummarization, vision —
picked via `getFeatureModel`, falling back to the main model when absent).
Model ids come from the cloud catalog or a BYO custom-provider id (passed
through verbatim, may contain ``/`` — keep-prefix preserves it).

Auth is cloud (auth.json, user_* key) or BYO credentials.json; neither user
has BYO providers instantiated, so there is no local base_url/api_key surface
to switch — model-only adapter, like dsh/codebuddy.
"""
from __future__ import annotations

from . import config
from .registry import Slot, register

PATH = config.HOME / ".commandcode" / "settings.json"


@register
class CommandCodeAdapter:
    id = "commandcode"
    name = "Command Code"
    primary = "commandcode.model"
    path = PATH

    @property
    def available(self) -> bool:
        return self.path.exists()

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        d = config.load_json(self.path) or {}
        out = [Slot(key=f"{self.id}.model", label="model",
                    current=d.get("model") or None)]
        fm = d.get("featureModels") or {}
        if isinstance(fm, dict):
            for feat, val in fm.items():
                out.append(Slot(key=f"{self.id}.feature.{feat}",
                                label=f"featureModels.{feat}",
                                current=val, follows=True))
        return out

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        if not self.available:
            return []
        relevant = {k[len(f"{self.id}."):]: v for k, v in assignments.items()
                    if k.startswith(f"{self.id}.")}
        if not relevant:
            return []
        data = config.load_json(self.path) or {}
        diffs: list[str] = []
        if "model" in relevant:
            old = data.get("model")
            if old != relevant["model"]:
                diffs.append(f"  model: {old!r} -> {relevant['model']!r}")
                if not dry:
                    data["model"] = relevant["model"]
        prefix = "feature."
        for key, val in relevant.items():
            if not key.startswith(prefix):
                continue
            feat = key[len(prefix):]
            if not feat:
                continue
            fm = data.setdefault("featureModels", {})
            old = fm.get(feat)
            if old != val:
                diffs.append(f"  featureModels.{feat}: {old!r} -> {val!r}")
                if not dry:
                    fm[feat] = val
        if diffs and not dry:
            config.keep_mode_write_json(self.path, data)
        return diffs
