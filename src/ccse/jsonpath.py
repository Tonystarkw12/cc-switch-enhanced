"""Generic JSON-path adapter: adapters declare the dotted paths to mutate.

A "path" uses dot for object keys and [i] for list indices, e.g.
  env.ANTHROPIC_MODEL  or  model.name  or  providers[default].settings.model
List indices may also be a string key meaning "find list item whose key `id`/
`provider`/`name` matches, else ordinal"; handled via set_in_path/get_in_path.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import config
from .registry import KIND_API_KEY, KIND_BASE_URL, KIND_MODEL, Slot, register

_TOKEN = re.compile(r"([^.\[\]]+)|\[([^\]]*)\]")


def _tokenize(path: str) -> list[tuple[str, str | None]]:
    """Returns list of (key, None) for object keys or ('', selector) for
    list steps. selector is: digits (positional), '' (default=0), 'key=val'
    (match), or 'bare' (match id/provider/name/key)."""
    toks: list[tuple[str, str | None]] = []
    for m in _TOKEN.finditer(path):
        if m.group(1) is not None:
            toks.append((m.group(1), None))
        else:
            sel = m.group(2) or ""
            if sel == "":
                sel = "0"
            toks.append(("", sel))
    return toks


def get_in_path(obj, path: str):
    cur = obj
    for key, sel in _tokenize(path):
        if sel is None:
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
        elif sel.isdigit():
            if not isinstance(cur, list):
                return None
            try:
                cur = cur[int(sel)]
            except (ValueError, IndexError):
                return None
        else:
            if not isinstance(cur, list):
                return None
            idx = _match_index(cur, sel)
            if idx is None:
                return None
            cur = cur[idx]
    return cur


def set_in_path(obj, path: str, value):
    toks = _tokenize(path)
    cur = obj
    for i, (key, sel) in enumerate(toks):
        last = i == len(toks) - 1
        if sel is None:
            if last:
                old = cur.get(key)
                cur[key] = value
                return old != value
            if key not in cur or not isinstance(cur.get(key), (dict, list)):
                cur[key] = {}
            cur = cur[key]
        elif sel.isdigit():
            if not isinstance(cur, list):
                return False
            pos_i = int(sel)
            if last:
                old = cur[pos_i]
                cur[pos_i] = value
                return old != value
            cur = cur[pos_i]
        else:
            if not isinstance(cur, list):
                return False
            idx = _match_index(cur, sel) or 0
            if idx >= len(cur):
                return False
            if last:
                old = cur[idx]
                cur[idx] = value
                return old != value
            cur = cur[idx]
    return False


_BRACKET = re.compile(r"\[([^\]]*)\]")
_KV = re.compile(r"^([^=]+)=(.*)$")


def _match_index(lst: list, sel: str) -> int | None:
    sel = sel.strip()
    m = _KV.match(sel)
    if m:
        key, want = m.group(1), m.group(2)
        for j, item in enumerate(lst):
            if isinstance(item, dict) and str(item.get(key)) == want:
                return j
    else:
        for j, item in enumerate(lst):
            if isinstance(item, dict) and any(
                str(v) == sel for v in (
                    item.get("id"), item.get("provider"),
                    item.get("name"), item.get("key"), item.get("envKey"),
                ) if v is not None
            ):
                return j
    return None


def resolve_list_path(obj, path: str) -> str:
    """Rewrite bare/key=val bracket selectors to concrete [index]."""
    parts = re.split(r"(\[[^\]]*\])", path)
    cur = obj
    res = ""
    for part in parts:
        m = _BRACKET.fullmatch(part) if part else None
        if m:
            sel = (m.group(1) or "").strip() or "0"
            if sel.isdigit():
                res += f"[{sel}]"
                if isinstance(cur, list):
                    try:
                        cur = cur[int(sel)]
                    except IndexError:
                        cur = None
            else:
                idx = _match_index(cur if isinstance(cur, list) else [], sel) \
                    or 0
                res += f"[{idx}]"
                if isinstance(cur, list) and idx < len(cur):
                    cur = cur[idx]
        else:
            res += part
            if part and isinstance(cur, dict):
                cur = cur.get(part, {})
    return res


def _provider_of(d, primary_path: str) -> str | None:
    """Active provider name = prefix before '/' of the primary slot's value.
    Used to resolve `{provider}` in endpoint paths (e.g. opencode/provider.X)."""
    rp = resolve_list_path(d, primary_path)
    v = get_in_path(d, rp)
    if isinstance(v, str) and "/" in v:
        return v.split("/", 1)[0]
    return None


def make_adapter(adapter_id: str, name: str, path: Path, slot_paths: dict[str, str],
                 endpoint_paths: dict[str, str] | None = None,
                 follow: tuple[str, ...] = (),
                 base_url_v1: bool = False):
    """Build+register a JSON-path adapter. slot_paths: {slot_label: json_path}.
    The first key in slot_paths is treated as the adapter's primary slot (`--model`).
    Each label becomes both the human label and the profile key suffix
    (`adapter_id.label`).

    endpoint_paths: optional {kind: json_path} for base_url/api_key slots.
    A path may contain `{provider}`, resolved to the active provider name
    (the prefix before '/' of the primary slot's value).

    follow: extra slot labels set alongside the primary by `--model NAME`
    (e.g. ("defaultModel",) → `--model` also sets adapter.defaultModel)."""
    paths = slot_paths
    primary = next(iter(paths))
    ep = endpoint_paths or {}
    follow_keys = tuple(f"{adapter_id}.{k}" for k in follow)

    def _ep_path(kind: str, d) -> str | None:
        t = ep.get(kind)
        if t is None:
            return None
        if "{provider}" in t:
            prov = _provider_of(d, paths[primary])
            if not prov:
                return None
            t = t.replace("{provider}", prov)
        return t

    def slots(self):
        if not path.exists():
            return []
        d = config.load_json(path) or {}
        out = []
        for label, p in paths.items():
            rp = resolve_list_path(d, p)
            cur = get_in_path(d, rp)
            if cur is None or cur == "":
                cur = None  # empty = unset (e.g. snow advancedModel="")
            out.append(Slot(key=f"{adapter_id}.{label}", label=label, current=cur))
        for kind, label in ((KIND_BASE_URL, "base_url"), (KIND_API_KEY, "api_key")):
            p = _ep_path(kind, d)
            if p is None:
                continue
            rp = resolve_list_path(d, p)
            cur = get_in_path(d, rp)
            if cur == "":
                cur = None
            out.append(Slot(key=f"{adapter_id}.{label}", label=f"{label} ({p})",
                            current=cur, kind=kind))
        return out

    def apply(self, assignments, dry=False):
        relevant = {k[len(adapter_id) + 1:]: v for k, v in assignments.items()
                    if k.startswith(adapter_id + ".")}
        if not relevant or not path.exists():
            return []
        d = config.load_json(path) or {}
        diffs = []
        for label, val in relevant.items():
            p = paths.get(label)
            if p is None and label in (KIND_BASE_URL, KIND_API_KEY):
                p = _ep_path(label, d)
            if p is None:
                continue
            if base_url_v1 and label == KIND_BASE_URL:
                # OpenAI SDK appends /chat/completions to baseUrl; a bare
                # gateway root returns HTML, so normalize to .../v1.
                val = config.ensure_openai_v1(val)
            rp = resolve_list_path(d, p)
            old = get_in_path(d, rp)
            if old != val:
                if set_in_path(d, rp, val):
                    diffs.append(f"  {p}: {old!r} -> {val!r}")
        if diffs and not dry:
            config.keep_mode_write_json(path, d)
        return diffs

    cls = type(
        f"_{adapter_id}_adapter",
        (object,),
        {"id": adapter_id, "name": name, "path": path,
         "available": property(lambda self: path.exists()),
         "primary": f"{adapter_id}.{primary}",
         "follow": follow_keys,
         "slots": slots, "apply": apply},
    )
    register(cls)
    return cls


if __name__ == "__main__":
    obj = {"providers": [{"id": "x", "model": "a"}, {"id": "y", "model": "b"}],
           "model": {"name": "z"}}
    print(resolve_list_path(obj, "providers[id=y].model"))
    print(get_in_path(obj, resolve_list_path(obj, "providers[id=y].model")))
    print(set_in_path(obj, resolve_list_path(obj, "providers[id=y].model"), "NEW"))
    print(obj)