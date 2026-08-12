"""`ccse` CLI: show / list / apply / genprofile / profiles / diff / undo / history.

Primary UX: `ccse --model "glm-5.2"` switches every agent's primary model slot
in one shot. `ccse undo` reverts the last apply (snapshots in ~/.ccse/snapshots)."""
from __future__ import annotations

import argparse
import sys
import tomllib
from datetime import datetime
from pathlib import Path

from . import config
from .registry import all_adapters

PROFILES_PATH = config.HOME / ".ccse" / "profiles.toml"


def _load_adapters():
    # import side-effect registers adapters
    from . import claude, cline, codex, gemini, opencode, qwen  # noqa: F401
    from . import extra, envrc  # noqa: F401
    return all_adapters()


def _primary_key(a) -> str:
    """Profile key that `--model NAME` targets for adapter `a`."""
    return getattr(a, "primary", f"{a.id}.model")


def _follow_keys(a) -> list[str]:
    """Keys set alongside the primary by `--model NAME` (e.g. claude.subagent)."""
    return list(getattr(a, "follow", ()) or ())


def _filter_adapters(adapters, only: str | None, exclude: str | None):
    onlyset = {s.strip() for s in only.split(",")} if only else None
    excl = {s.strip() for s in exclude.split(",")} if exclude else None
    out = []
    for a in adapters:
        if onlyset and a.id not in onlyset:
            continue
        if excl and a.id in excl:
            continue
        out.append(a)
    return out


# ---- show / list / profiles ---------------------------------------------

def cmd_list(_args) -> int:
    adapters = _load_adapters()
    print(f"{'adapter':<12} {'name':<16} {'avail':<5} path")
    for a in adapters:
        print(f"{a.id:<12} {a.name:<16} {'✓' if a.available else '—':<5} {a.path}")
    return 0


def cmd_show(args) -> int:
    adapters = _filter_adapters(_load_adapters(), args.only, args.exclude)
    any_slot = False
    for a in adapters:
        slots = a.slots()
        if not slots:
            continue
        head = f"[{a.id}] {a.name}  {'(installed)' if a.available else '(missing)'}"
        print(head)
        for s in slots:
            cur = s.current if s.current is not None else "<unset>"
            mark = " ★" if s.key == _primary_key(a) else ""
            print(f"  {s.label:<28} = {cur}{mark}")
        any_slot = True
    if not any_slot:
        print("no configured agents found", file=sys.stderr)
    print("(★ = primary slot, the one --model sets)", file=sys.stderr)
    return 0


def _read_profiles() -> dict[str, dict[str, str]]:
    if not PROFILES_PATH.exists():
        return {}
    d = tomllib.loads(PROFILES_PATH.read_text("utf-8"))
    out: dict[str, dict[str, str]] = {}
    for name, section in d.items():
        if not isinstance(section, dict):
            continue
        flat: dict[str, str] = {}
        for k, v in section.items():
            if isinstance(v, str):
                flat[k] = v
        out[name] = flat
    return out


def cmd_profiles(_args) -> int:
    profs = _read_profiles()
    if not profs:
        print(f"(no profiles in {PROFILES_PATH})", file=sys.stderr)
        return 0
    for name, assignments in profs.items():
        print(f"[{name}]")
        for k, v in assignments.items():
            print(f"  {k} = {v}")
    return 0


def _resolve_profile(name: str) -> dict[str, str]:
    profs = _read_profiles()
    if name not in profs:
        config.die(f"profile {name!r} not found in {PROFILES_PATH}")
    return profs[name]


# ---- apply core ----------------------------------------------------------

def _apply_assignments(assignments: dict[str, str], *, dry: bool,
                       no_backup: bool, only: str | None,
                       exclude: str | None, tag: str) -> int:
    adapters = _filter_adapters(_load_adapters(), only, exclude)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    mode = "dry-run" if dry else "applied"

    # snapshot before writing (all in-scope installed files, deduped — envrc
    # adapters may share ~/.zshrc)
    if not dry:
        touched: list[Path] = []
        seen: set[Path] = set()
        for a in adapters:
            if a.path.exists() and a.path not in seen:
                seen.add(a.path)
                touched.append(a.path)
        if touched:
            config.save_snapshot(touched, stamp)
            config.append_history({
                "stamp": stamp, "tag": tag, "mode": mode,
                "n_files": len(touched),
                "assignments": {k: v for k, v in assignments.items()},
            })

    total = 0
    for a in adapters:
        diffs = a.apply(assignments, dry=dry)
        if diffs:
            print(f"[{a.id}] {a.name}")
            for line in diffs:
                print(line)
            total += len(diffs)
    print(f"\n{mode}: {total} field(s) changed across agents. "
          f"{'(snapshot ' + stamp + ')'}" if not dry and total
          else f"\n{mode}: {total} field(s) changed across agents.",
          file=sys.stderr)
    if total == 0 and not dry:
        print("(already in sync — nothing written)", file=sys.stderr)
    elif not dry:
        print(f"snapshot saved: {stamp}  (undo: ccse undo {stamp})",
              file=sys.stderr)
    return 0


def _model_target(name: str, cur: str | None, keep_prefix: bool, suffix: str) -> str:
    """Compute the value a slot should get from a bare ``--model NAME``.

    - keep_prefix: if the current value carries a structural ``<prefix>/<model>``
      route id and the user passed a bare name (no ``/``), keep the prefix so the
      agent's upstream router still resolves. A NAME already containing ``/`` is
      used verbatim.
    - suffix: adapters that declare a ``suffix`` (e.g. claude needs ``[1M]``)
      get it appended to bare names — that marker is aggregator-specific and no
      other agent has it."""
    target = name
    if keep_prefix and "/" not in name and cur and "/" in cur:
        target = cur.rsplit("/", 1)[0] + "/" + name
    if suffix and not target.endswith(suffix):
        target += suffix
    return target


def _model_assignments(name: str, only, exclude, keep_prefix: bool = True) -> dict[str, str]:
    """Build {slot_key: target} for every adapter in scope.

    Sets the adapter's primary slot; adapters that declare ``follow``
    (e.g. claude.main + claude.subagent) get those too."""
    adapters = _filter_adapters(_load_adapters(), only, exclude)
    out: dict[str, str] = {}
    for a in adapters:
        if not a.available:
            continue
        slots = {s.key: s for s in a.slots()}
        keys = [_primary_key(a), *_follow_keys(a)]
        for key in keys:
            if key not in slots:
                continue
            cur = slots[key].current
            out[key] = _model_target(
                name, cur, keep_prefix, getattr(a, "suffix", "") or "")
    return out


def cmd_apply(args) -> int:
    if args.model is not None:
        assignments = _model_assignments(args.model, args.only, args.exclude,
                                         keep_prefix=not args.no_keep_prefix)
        tag = f"--model {args.model}" + ("" if not args.no_keep_prefix else " (raw)")
    elif args.profile:
        assignments = _resolve_profile(args.profile)
        tag = f"profile {args.profile}"
    else:
        config.die("apply needs either --model NAME or a PROFILE name")
    return _apply_assignments(assignments, dry=False, no_backup=args.no_backup,
                              only=args.only, exclude=args.exclude, tag=tag)


def cmd_diff(args) -> int:
    if args.model is not None:
        assignments = _model_assignments(args.model, args.only, args.exclude,
                                         keep_prefix=not args.no_keep_prefix)
        tag = f"--model {args.model}" + ("" if not args.no_keep_prefix else " (raw)")
    elif args.profile:
        assignments = _resolve_profile(args.profile)
        tag = f"profile {args.profile}"
    else:
        config.die("diff needs either --model NAME or a PROFILE name")
    return _apply_assignments(assignments, dry=True, no_backup=True,
                              only=args.only, exclude=args.exclude, tag=tag)


def cmd_genprofile(args) -> int:
    adapters = _load_adapters()
    flat: dict[str, str] = {}
    for a in adapters:
        for s in a.slots():
            if s.current:
                flat[s.key] = s.current
    name = args.name or "snapshot"
    profs = _read_profiles()
    profs[name] = flat
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = _dump_flat_profiles(profs)
    config.write_text_atomic(PROFILES_PATH, text)
    print(f"wrote profile [{name}] -> {PROFILES_PATH} ({len(flat)} fields)",
          file=sys.stderr)
    return 0


def _dump_flat_profiles(profs: dict[str, dict[str, str]]) -> str:
    lines: list[str] = []
    for name, flat in profs.items():
        lines.append(f"[{name}]")
        for k in sorted(flat):
            lines.append(f'"{k}" = {_toml_str(flat[k])}')
        lines.append("")
    return "\n".join(lines) + "\n"


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---- undo / history ------------------------------------------------------

def cmd_history(_args) -> int:
    import json
    if not config.HISTORY_INDEX.exists():
        print("(no apply history yet)", file=sys.stderr)
        return 0
    rows = [json.loads(l) for l in config.HISTORY_INDEX.read_text("utf-8").splitlines()
            if l.strip()]
    if not rows:
        print("(history empty)", file=sys.stderr)
        return 0
    print(f"{'stamp':<20} {'tag':<28} files")
    for r in rows[-20:]:
        print(f"{r.get('stamp','?'):<20} {str(r.get('tag','')):<28} {r.get('n_files','?')}")
    print(f"({len(rows)} total; undo last: `ccse undo`)", file=sys.stderr)
    return 0


def cmd_snapshots(_args) -> int:
    snaps = config.list_snapshots()
    if not snaps:
        print("(no snapshots)", file=sys.stderr)
        return 0
    print("\n".join(snaps))
    return 0


def cmd_undo(args) -> int:
    snaps = config.list_snapshots()
    if not snaps:
        print("(no snapshots to restore)", file=sys.stderr)
        return 1
    stamp = args.stamp or snaps[0]  # newest first
    if stamp not in snaps:
        config.die(f"snapshot {stamp!r} not found; see `ccse snapshots`")
    restored = config.restore_snapshot(stamp)
    print(f"restored {len(restored)} file(s) from snapshot {stamp}:")
    for f in restored:
        print(f"  {f}")
    print(f"(pre-restore copies saved as *.ccse.pre-restore.{stamp})",
          file=sys.stderr)
    return 0


# ---- parser --------------------------------------------------------------

def _add_scope(p):
    p.add_argument("--only", help="comma-separated adapter ids to include")
    p.add_argument("--exclude", help="comma-separated adapter ids to skip")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ccse",
        description="One-line model-name switch across coding agents. "
                    "Default action with --model: switch all agents' primary slot.")
    p.add_argument("-m", "--model", metavar="NAME",
                   help="switch every agent's primary model slot to NAME "
                        "(shorthand for `apply --model NAME`). Bare names keep "
                        "each adapter's own route prefix (newapi/..., dmx/..., "
                        "krill/...); pass a NAME with '/' to override verbatim.")
    p.add_argument("--only", help="comma-separated adapter ids to include")
    p.add_argument("--exclude", help="comma-separated adapter ids to skip")
    p.add_argument("--dry", action="store_true",
                   help="with --model: preview only, don't write")
    p.add_argument("--no-backup", action="store_true",
                   help="skip snapshot before edits")
    p.add_argument("--no-keep-prefix", action="store_true",
                   help="set the model name verbatim, dropping any 'prefix/' "
                        "route id the adapter had (use with care)")
    sub = p.add_subparsers(dest="cmd")

    sl = sub.add_parser("list", help="list installed/known adapters")
    sl.set_defaults(func=cmd_list)

    ss = sub.add_parser("show", help="show current model per agent slot")
    _add_scope(ss)
    ss.set_defaults(func=cmd_show)

    sp = sub.add_parser("profiles", help="list profiles in ~/.ccse/profiles.toml")
    sp.set_defaults(func=cmd_profiles)

    pa = sub.add_parser("apply", help="write --model or a profile into all agents")
    _add_scope(pa)
    pa.add_argument("--model", metavar="NAME",
                    help="set every agent's primary slot to NAME (prefix kept)")
    pa.add_argument("profile", nargs="?", help="profile name from profiles.toml")
    pa.add_argument("--no-backup", action="store_true", help="skip snapshot")
    pa.add_argument("--no-keep-prefix", action="store_true",
                    help="set model verbatim (drop route prefix)")
    pa.set_defaults(func=cmd_apply)

    pd = sub.add_parser("diff", help="preview changes (dry-run)")
    _add_scope(pd)
    pd.add_argument("--model", metavar="NAME")
    pd.add_argument("profile", nargs="?")
    pd.add_argument("--no-keep-prefix", action="store_true",
                    help="set model verbatim (drop route prefix)")
    pd.set_defaults(func=cmd_diff)

    pg = sub.add_parser("genprofile", help="snapshot current state into a profile")
    pg.add_argument("--name", default="snapshot", help="profile section name")
    pg.set_defaults(func=cmd_genprofile)

    pu = sub.add_parser("undo", help="restore files from a previous apply snapshot")
    pu.add_argument("stamp", nargs="?",
                    help="snapshot stamp; default = newest (see `ccse snapshots`)")
    pu.set_defaults(func=cmd_undo)

    ph = sub.add_parser("history", help="show apply history")
    ph.set_defaults(func=cmd_history)

    psn = sub.add_parser("snapshots", help="list saved snapshots")
    psn.set_defaults(func=cmd_snapshots)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # top-level --model shorthand: act as `apply --model`
    if getattr(args, "cmd", None) is None:
        if getattr(args, "model", None) is not None:
            kp = not getattr(args, "no_keep_prefix", False)
            assignments = _model_assignments(args.model, args.only, args.exclude,
                                             keep_prefix=kp)
            tag = f"--model {args.model}" + ("" if kp else " (raw)")
            return _apply_assignments(
                assignments, dry=args.dry, no_backup=args.no_backup,
                only=args.only, exclude=args.exclude, tag=tag)
        parser.print_help(sys.stderr)
        return 2
    return args.func(args)