"""MCode (MiniMax Code) adapter: ~/.minimax/config.yaml.

Data dir is ``~/.minimax`` (strace-verified; MINIMAX_DATA_DIR overrides). The
active model is the composite ``defaultModel: <source>/<model-id>`` where
source is ``minimax`` (managed login, provider.minimax) or a BYO id under
``custom_provider.<id>`` (created by ``mcode provider add``; literal apiKey +
baseURL in its ``options``). Switching model repoints ``defaultModel`` and, for
a custom source, ensures a matching ``models.<id>`` catalog entry exists (the
resolver needs it — ``mcode provider test`` validates exactly this). Bare
``--model NAME`` keeps the current source prefix; a NAME with ``/`` overrides
source+model verbatim. Subagent overrides (``agents/*/config.yaml``) are `{}`
until configured in the TUI; schema unknown → not touched.
"""
from __future__ import annotations

import io

from . import config
from .registry import KIND_API_KEY, KIND_BASE_URL, Slot, register

PATH = config.HOME / ".minimax" / "config.yaml"


def _yaml():
    import ruamel.yaml as _y  # type: ignore
    y = _y.YAML()
    y.preserve_quotes = True
    y.width = 4096
    return y


def _split(default_model: str | None) -> tuple[str | None, str | None]:
    if not default_model or "/" not in default_model:
        return None, default_model
    src, _, model = default_model.partition("/")
    return src, model


def _cp_id(src: str) -> str:
    """custom_provider:<id> source form → the map key."""
    return src.removeprefix("custom_provider:")


@register
class McodeAdapter:
    id = "mcode"
    name = "MCode"
    primary = "mcode.model"
    model_raw = True  # bare names resolve via provider catalogs in apply()
    path = PATH

    @property
    def available(self) -> bool:
        return self.path.exists()

    def _doc(self):
        return _yaml().load(self.path.read_text("utf-8")) or {}

    def _provider_opts(self, doc: dict) -> dict | None:
        """options dict of the provider serving the active defaultModel."""
        src, _ = _split(doc.get("defaultModel"))
        if not src:
            return None
        if not src:
            return None
        cp = (doc.get("custom_provider") or {}).get(_cp_id(src))
        if isinstance(cp, dict):
            return cp.get("options")
        pm = (doc.get("provider") or {}).get(src)
        if isinstance(pm, dict):
            return pm.get("options")
        return None

    def _resolve_source(self, doc: dict, model: str) -> str:
        """Source for a bare model name: whichever provider catalog carries it
        (custom_provider first — BYO gateways hold aggregator names), else the
        current defaultModel source. Prefixes here are functional providers,
        not route ids, so blind keep-prefix would point at a wrong catalog."""
        cp = doc.get("custom_provider") or {}
        for sid, entry in cp.items():
            if isinstance(entry, dict) and model in (entry.get("models") or {}):
                return f"custom_provider:{sid}"  # route classifier needs the prefix
        pm = doc.get("provider") or {}
        for sid, entry in pm.items():
            if isinstance(entry, dict) and model in (entry.get("models") or {}):
                return sid
        src, _ = _split(doc.get("defaultModel"))
        return src or "minimax"

    def slots(self) -> list[Slot]:
        if not self.available:
            return []
        doc = self._doc()
        out = [Slot(key=f"{self.id}.model", label="defaultModel",
                    current=doc.get("defaultModel"))]
        opts = self._provider_opts(doc)
        if opts is not None:
            out.append(Slot(key=f"{self.id}.base_url", label="options.baseURL",
                            current=opts.get("baseURL"), kind=KIND_BASE_URL))
            cur = opts.get("apiKey")
            out.append(Slot(key=f"{self.id}.api_key", label="options.apiKey",
                            current=cur, kind=KIND_API_KEY))
        return out

    def apply(self, assignments: dict[str, str], dry: bool) -> list[str]:
        if not self.available:
            return []
        relevant = {k[len(f"{self.id}."):]: v for k, v in assignments.items()
                    if k.startswith(f"{self.id}.")}
        if not relevant:
            return []
        y = _yaml()
        doc = y.load(self.path.read_text("utf-8")) or {}
        diffs: list[str] = []
        if "model" in relevant:
            val = relevant["model"]
            if "/" not in val:
                val = f"{self._resolve_source(doc, val)}/{val}"
            else:  # explicit <src>/<model>: bare custom ids need the route prefix
                src, model = _split(val)
                if src and "custom_provider:" not in src and \
                        isinstance((doc.get("custom_provider") or {}).get(src), dict) and \
                        src not in (doc.get("provider") or {}):
                    val = f"custom_provider:{src}/{model}"
            old = doc.get("defaultModel")
            if old != val:
                diffs.append(f"  defaultModel: {old!r} -> {val!r}")
                if not dry:
                    doc["defaultModel"] = val
            # custom source: ensure catalog entry (resolver requires it)
            nsrc, nmodel = _split(val)
            cp = doc.get("custom_provider") or {}
            entry = cp.get(_cp_id(nsrc)) if isinstance(cp, dict) else None
            if isinstance(entry, dict) and nmodel and \
                    nmodel not in (entry.get("models") or {}):
                diffs.append(f"  custom_provider[{nsrc}].models: + {nmodel!r}")
                if not dry:
                    models = entry.setdefault("models", {})
                    models[nmodel] = {"reasoning": False}
        opts = self._provider_opts(doc)
        for label, field in (("base_url", "baseURL"), ("api_key", "apiKey")):
            if label in relevant and opts is not None:
                old = opts.get(field)
                if old != relevant[label]:
                    diffs.append(f"  options.{field}: "
                                 f"{config.redact(old) if field == 'apiKey' else old!r}"
                                 f" -> {config.redact(relevant[label]) if field == 'apiKey' else relevant[label]!r}")
                    if not dry:
                        opts[field] = relevant[label]
        if diffs and not dry:
            buf = io.StringIO()
            y.dump(doc, buf)
            config.write_text_atomic(self.path, buf.getvalue())
        return diffs
