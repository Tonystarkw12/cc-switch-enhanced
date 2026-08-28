"""`ccse penv` — named provider store + one-shot project .env switch.

`ccse rewrite` flips values already present in a tree but needs explicit
--base-url/--api-key each time. penv adds the missing half: providers saved by
name in ~/.ccse/providers.toml, then `ccse penv <dir> <name>` rewrites every
LLM-shaped key in <dir>/.env* (same conservative heuristics as rewrite) and
appends <PREFIX>BASE_URL / <PREFIX>API_KEY / <PREFIX>MODEL when absent, so a
fresh project picks up the provider with zero edits.
"""
from __future__ import annotations

import sys
import tomllib
from datetime import datetime
from pathlib import Path

from . import config, rewrite

# slot kind -> canonical env key suffix appended when the project .env lacks it
_CANON = (("base_url", "BASE_URL"), ("api_key", "API_KEY"), ("model", "MODEL"))


def _providers_path() -> Path:
    return config.HOME / ".ccse" / "providers.toml"


def read_providers() -> dict[str, dict[str, str]]:
    p = _providers_path()
    if not p.exists():
        return {}
    d = tomllib.loads(p.read_text("utf-8"))
    return {name: {k: v for k, v in section.items() if isinstance(v, str)}
            for name, section in d.items() if isinstance(section, dict)}


def _save(provs: dict[str, dict[str, str]]) -> None:
    lines: list[str] = []
    for name in sorted(provs):
        lines.append(f"[{name}]")
        entry = provs[name]
        ordered = [k for k in ("base_url", "api_key", "model") if k in entry]
        ordered += sorted(k for k in entry if k not in ordered)
        for k in ordered:
            v = entry[k].replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{v}"')
        lines.append("")
    p = _providers_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    config.write_text_atomic(p, "\n".join(lines) + "\n")


def add(name: str | None, base_url: str | None = None,
        api_key: str | None = None, model: str | None = None) -> None:
    """Upsert provider NAME (at least one of base_url/api_key required)."""
    if not name:
        config.die("penv upsert needs a provider NAME")
    if not (base_url or api_key):
        config.die("penv upsert needs --base-url or --api-key (--model optional)")
    entry = read_providers().get(name, {})
    entry.update({k: v for k, v in (("base_url", base_url), ("api_key", api_key),
                                    ("model", model)) if v})
    profs = read_providers()
    profs[name] = entry
    _save(profs)
    print(f"provider {name!r} saved -> {_providers_path()} "
          f"(keys: {', '.join(sorted(entry))})", file=sys.stderr)


def remove(name: str | None) -> int:
    if not name:
        config.die("penv --rm needs a provider NAME")
    provs = read_providers()
    if name not in provs:
        config.die(f"provider {name!r} not found in {_providers_path()}")
    del provs[name]
    _save(provs)
    print(f"provider {name!r} removed", file=sys.stderr)
    return 0


def show_providers() -> int:
    provs = read_providers()
    if not provs:
        print(f"(no providers in {_providers_path()}; add one: "
              f"`ccse penv NAME --base-url URL --api-key KEY`)", file=sys.stderr)
        return 0
    for name, entry in sorted(provs.items()):
        print(f"[{name}]")
        for k, v in entry.items():
            print(f"  {k} = {config.redact(v) if k == 'api_key' else v}")
    return 0


def status(root: Path, env_name: str = ".env") -> int:
    """Show LLM-shaped keys currently in <root>/<env_name>, keys redacted."""
    p = root.expanduser() / env_name
    if not p.exists():
        print(f"({p} not found)", file=sys.stderr)
        return 0
    for line in p.read_text("utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        if rewrite._slot_kind(key.strip()):
            print(f"  {key.strip()} = {config.redact(val.strip())}")
    return 0


def use(root: Path, name: str, model: str | None = None, prefix: str = "OPENAI_",
        env_name: str = ".env", dry: bool = False) -> int:
    """Apply provider NAME to <root>/.env*: rewrite matching keys in place,
    append canonical <PREFIX>KEY=... lines missing from the main file."""
    entry = read_providers().get(name)
    if entry is None:
        config.die(f"provider {name!r} not found in {_providers_path()}; "
                   f"add it first")
    root = root.expanduser()
    if not root.is_dir():
        config.die(f"{root} is not a directory")
    assignments = {k: entry[k] for k, _ in _CANON if entry.get(k)}
    if model:
        assignments["model"] = model

    main = root / env_name
    files = [p for p in sorted({main, *root.glob(f"{env_name}.*")}) if p.exists()]

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    diffs: list[str] = []
    changed: set[Path] = set()
    for p in files:
        d = rewrite._rewrite_env(p, assignments, dry)
        if d:
            diffs.extend(d)
            changed.add(p)

    # re-read AFTER in-place rewrites — _rewrite_env may have just written main
    main_text = main.read_text("utf-8", errors="replace") if main.exists() else ""
    have = {line.partition("=")[0].strip().upper()
            for line in main_text.splitlines()
            if line.strip() and not line.strip().startswith("#")
            and "=" in line}
    missing = [(k, f"{prefix}{suffix}") for k, suffix in _CANON
               if f"{prefix}{suffix}".upper() not in have and k in assignments]

    if missing:
        text = main_text
        if text and not text.endswith("\n"):
            text += "\n"
        for kind, key in missing:
            line = f"{key}={assignments[kind]}\n"
            shown = config.redact(assignments[kind]) if kind == "api_key" \
                else assignments[kind]
            diffs.append(f"  {main}: + {key}={shown}")
            text += line
        if not dry:
            config.write_text_atomic(main, text)
        changed.add(main)

    if diffs and not dry:
        touched = sorted(changed)
        config.save_snapshot(touched, stamp)
        config.append_history({
            "stamp": stamp, "tag": f"penv {name} -> {root}", "mode": "applied",
            "n_files": len(touched),
            "assignments": {k: (config.redact(v) if k == "api_key" else v)
                            for k, v in assignments.items()},
        })
    for line in diffs:
        print(line)
    mode = "dry-run" if dry else "applied"
    print(f"\npenv {mode}: provider {name!r} -> {len(diffs)} change(s) across "
          f"{len(changed) if diffs else 0} file(s)"
          + ("  (nothing written)" if dry else ""), file=sys.stderr)
    return 0
