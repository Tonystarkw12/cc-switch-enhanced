"""Mimo (mimocode) adapter: ~/.config/mimocode/mimocode.jsonc.

opencode-shaped config: top-level ``"model": "<provider>/<id>"`` (composite;
the `mimo models` catalog shows ``custom/…``, ``xiaomi/…`` prefixes) plus
``provider.<id>.options.{baseURL,apiKey}`` and a ``models`` catalog per
provider. The file is JSONC and heavily comment-annotated, so apply() does
regex surgery on the literal key lines (comments preserved verbatim) and
validates the result by comment-stripped JSON parse. Active provider = the
``model`` prefix; bare ``--model NAME`` keeps it, and a provider catalog entry
is ensured for custom providers (``only_configured_models`` is on).
"""
from __future__ import annotations

import json
import re

from . import config
from .registry import KIND_API_KEY, KIND_BASE_URL, Slot, register

PATH = config.HOME / ".config" / "mimocode" / "mimocode.jsonc"


def _strip_comments(text: str) -> str:
    """Remove //… and /*…*/ comments and trailing commas — string-aware
    (a naive regex eats the `//` in baseURL values like https://…)."""
    out = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            i = text.find("\n", i)
            i = n if i < 0 else i
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    stripped = "".join(out)
    return re.sub(r",(\s*[}\]])", r"\1", stripped)  # trailing commas


def _parse(text: str) -> dict:
    return json.loads(_strip_comments(text)) or {}


def _provider_of(doc: dict) -> str | None:
    m = doc.get("model")
    if isinstance(m, str) and "/" in m:
        return m.split("/", 1)[0]
    return None


@register
class MimoAdapter:
    id = "mimo"
    name = "Mimo"
    primary = "mimo.model"
    path = PATH

    @property
    def available(self) -> bool:
        return self.path.exists()

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        doc = _parse(self.path.read_text("utf-8"))
        out = [Slot(key=f"{self.id}.model", label="model", current=doc.get("model"))]
        prov = _provider_of(doc)
        opts = ((doc.get("provider") or {}).get(prov) or {}).get("options") \
            if prov else None
        if isinstance(opts, dict):
            out.append(Slot(key=f"{self.id}.base_url", label=f"provider.{prov}.baseURL",
                            current=opts.get("baseURL"), kind=KIND_BASE_URL))
            out.append(Slot(key=f"{self.id}.api_key", label=f"provider.{prov}.apiKey",
                            current=opts.get("apiKey"), kind=KIND_API_KEY))
        return out

    @staticmethod
    def _swap(text: str, key: str, val: str, nth: int = 0) -> tuple[str, bool]:
        """Replace the value of the nth `"key": "…"` literal; keep everything
        else (comments included) byte-identical."""
        pat = re.compile(r'("' + re.escape(key) + r'"\s*:\s*")[^"]*(")')
        hits = list(pat.finditer(text))
        if len(hits) <= nth:
            return text, False
        m = hits[nth]
        new = text[:m.start()] + m.group(1) + val + m.group(2) + text[m.end():]
        return new, True

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        if not self.available:
            return []
        relevant = {k[len(f"{self.id}."):]: v for k, v in assignments.items()
                    if k.startswith(f"{self.id}.")}
        if not relevant:
            return []
        text = self.path.read_text("utf-8")
        doc = _parse(text)
        diffs: list[str] = []
        if "model" in relevant:
            val = relevant["model"]
            prov = _provider_of(doc)
            if prov and "/" not in val:
                val = f"{prov}/{val}"
            old = doc.get("model")
            if old != val:
                text, ok = self._swap(text, "model", val)
                if ok:
                    diffs.append(f"  model: {old!r} -> {val!r}")
            # custom provider catalog entry (only_configured_models gate)
            nprov, nmodel = val.split("/", 1) if "/" in val else (prov, val)
            entry = (doc.get("provider") or {}).get(nprov)
            if isinstance(entry, dict) and nmodel and \
                    nmodel not in (entry.get("models") or {}):
                text = re.sub(
                    r'("' + re.escape(nprov) + r'"\s*:\s*\{)',
                    r'\1', text, count=1)
                # insert a sibling inside provider.<nprov> — safest anchor:
                # right after its "models": { opener
                mm = re.search(r'("' + re.escape(nprov) + r'"\s*:\s*\{.*?"models"\s*:\s*\{)',
                               text, re.S)
                if mm:
                    text = text[:mm.end()] + \
                        f'\n        "{nmodel}": {{"name": "{nmodel}"}},' + \
                        text[mm.end():]
                    diffs.append(f"  provider.{nprov}.models: + {nmodel!r}")
        for label, key in (("base_url", "baseURL"), ("api_key", "apiKey")):
            if label in relevant:
                old = doc.get("provider", {}).get(
                    _provider_of(doc), {}).get("options", {}).get(key)
                if old != relevant[label]:
                    text, ok = self._swap(text, key, relevant[label])
                    if ok:
                        diffs.append(f"  options.{key}: "
                                     f"{config.redact(old) if key == 'apiKey' else old!r}"
                                     f" -> {config.redact(relevant[label]) if key == 'apiKey' else relevant[label]!r}")
        if diffs:
            _parse(text)  # validate still parses after surgery
            if not dry:
                config.write_text_atomic(self.path, text)
        return diffs
