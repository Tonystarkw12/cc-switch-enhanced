"""`ccse` CLI: show / list / apply / genprofile / profiles / diff / undo /
history / verify.

Primary UX: `ccse --model "glm-5.2" --base-url URL --api-key KEY` switches
every agent's model slot, endpoint and key in one shot. `ccse undo` reverts
the last apply (snapshots in ~/.ccse/snapshots). `ccse verify` probes every
agent's configured endpoint to confirm the switch still works."""
from __future__ import annotations

import argparse
import os
import sys
import tomllib
from datetime import datetime
from pathlib import Path

from . import config
from .registry import KIND_API_KEY, KIND_BASE_URL, KIND_MODEL, all_adapters

PROFILES_PATH = config.HOME / ".ccse" / "profiles.toml"

# adapters whose api_key is an env-var reference and get the literal written to
# the shell rc / user env (codex/grok/reasonix/memmy/omp/prime). verify must
# snapshot that file too.
_ENV_KEY_ADAPTERS = ("codex", "grok", "reasonix", "memmy", "omp", "prime")


def _load_adapters():
    # import side-effect registers adapters
    from . import claude, cline, codex, gemini, opencode, qwen, prime  # noqa: F401
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
    rc = str(config.SHELL_RC) if config.SHELL_RC else "user env (setx)"
    print(f"{'adapter':<12} {'name':<16} {'avail':<5} path   [os={config.OS_NAME}, env={rc}]")
    for a in adapters:
        p = a.path if a.path is not None else "user env (setx)"
        print(f"{a.id:<12} {a.name:<16} {'✓' if a.available else '—':<5} {p}")
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
            if s.kind == KIND_API_KEY and s.current is not None:
                cur = config.redact(s.current)
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
    # adapters may share the shell rc). Env-key adapters write their api_key
    # literal into the shell rc (posix), so that file is in scope whenever an
    # api_key is assigned.
    if not dry:
        touched: list[Path] = []
        seen: set[Path] = set()
        writes_zshrc = any(a.id in _ENV_KEY_ADAPTERS for a in adapters)
        has_api_key = any(k.endswith(".api_key") for k in assignments)
        if writes_zshrc and has_api_key and config.SHELL_RC is not None:
            z = config.SHELL_RC
            if z not in seen and z.exists():
                seen.add(z)
                touched.append(z)
        for a in adapters:
            if a.path is not None and a.path.exists() and a.path not in seen:
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
    skipped = 0
    for a in adapters:
        if not a.available:
            skipped += 1
            continue
        diffs = a.apply(assignments, dry=dry)
        if diffs:
            print(f"[{a.id}] {a.name}")
            for line in diffs:
                print(line)
            total += len(diffs)
    note = f" ({skipped} not-installed skipped)" if skipped else ""
    summary = f"\n{mode}: {total} field(s) changed across agents.{note}"
    if not dry and total:
        summary += f"  (snapshot {stamp})"
    print(summary, file=sys.stderr)
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


def _endpoint_assignments(kind: str, value: str, only, exclude) -> dict[str, str]:
    """Build {slot_key: value} for every adapter slot of the given kind
    (base_url | api_key) in scope."""
    adapters = _filter_adapters(_load_adapters(), only, exclude)
    out: dict[str, str] = {}
    for a in adapters:
        if not a.available:
            continue
        for s in a.slots():
            if s.kind == kind:
                out[s.key] = value
    return out


def cmd_apply(args) -> int:
    assignments: dict[str, str] = {}
    tags: list[str] = []
    if args.model is not None:
        assignments.update(_model_assignments(
            args.model, args.only, args.exclude,
            keep_prefix=not args.no_keep_prefix))
        tags.append(f"--model {args.model}" + ("" if not args.no_keep_prefix else " (raw)"))
    elif args.profile:
        assignments.update(_resolve_profile(args.profile))
        tags.append(f"profile {args.profile}")
    else:
        config.die("apply needs --model NAME, --base-url/--api-key, or a PROFILE name")
    if getattr(args, "base_url", None):
        assignments.update(_endpoint_assignments(
            KIND_BASE_URL, args.base_url, args.only, args.exclude))
        tags.append(f"--base-url {args.base_url}")
    if getattr(args, "api_key", None):
        assignments.update(_endpoint_assignments(
            KIND_API_KEY, args.api_key, args.only, args.exclude))
        tags.append("--api-key <redacted>")
    if not assignments:
        config.die("nothing to do")
    return _apply_assignments(assignments, dry=False, no_backup=args.no_backup,
                              only=args.only, exclude=args.exclude,
                              tag=", ".join(tags))


def cmd_diff(args) -> int:
    assignments: dict[str, str] = {}
    if args.model is not None:
        assignments.update(_model_assignments(
            args.model, args.only, args.exclude,
            keep_prefix=not args.no_keep_prefix))
    elif args.profile:
        assignments.update(_resolve_profile(args.profile))
    if getattr(args, "base_url", None):
        assignments.update(_endpoint_assignments(
            KIND_BASE_URL, args.base_url, args.only, args.exclude))
    if getattr(args, "api_key", None):
        assignments.update(_endpoint_assignments(
            KIND_API_KEY, args.api_key, args.only, args.exclude))
    if not assignments:
        config.die("diff needs --model, --base-url/--api-key, or a PROFILE name")
    return _apply_assignments(assignments, dry=True, no_backup=True,
                              only=args.only, exclude=args.exclude, tag="diff")


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


# ---- verify --------------------------------------------------------------

def _resolve_key(slot_current: str | None) -> str | None:
    """An api_key slot may hold a literal key or the NAME of an env var
    (codex/grok/reasonix store env_key). Resolve env-var names to their value."""
    if slot_current and slot_current.isidentifier() and slot_current in os.environ:
        return os.environ[slot_current]
    return slot_current


def _probe_endpoint(base: str, key: str | None, model: str | None,
                    timeout: int = 8) -> tuple[str, str]:
    """OpenAI-style GET {base}/models. Returns (status, message):
    PASS / WARN (model not listed) / FAIL."""
    import json
    import socket
    import ssl
    import urllib.error
    import urllib.request

    url = base.rstrip("/") + "/models"
    headers = {"Authorization": "Bearer " + key} if key else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                    timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return ("FAIL", f"HTTP {e.code} — api_key rejected")
        return ("FAIL", f"HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError,
            OSError) as e:
        return ("FAIL", f"endpoint unreachable: {getattr(e, 'reason', e)}")
    except Exception as e:
        return ("FAIL", f"response parse error: {e}")
    ids = [m.get("id") for m in body.get("data", []) if isinstance(m, dict)]
    if model and ids:
        probe_model = model.split("/", 1)[-1]  # strip router prefix (newapi/X)
        probe_model = probe_model.removesuffix("[1M]")  # strip claude suffix
        if probe_model not in ids:
            return ("WARN", f"endpoint ok, but model {model!r} NOT in /models "
                            f"({len(ids)} listed) — calls will fail")
    return ("PASS", f"endpoint ok, {len(ids)} models listed"
            + (f", model {model!r} present" if model and ids else ""))


def cmd_verify(args) -> int:
    adapters = _filter_adapters(_load_adapters(), args.only, args.exclude)
    results: list[tuple[str, str, str]] = []
    for a in adapters:
        if not a.available:
            results.append((a.id, "SKIP", "not installed"))
            continue
        slots = a.slots()
        model = next((s.current for s in slots if s.kind == KIND_MODEL and s.current), None)
        base = next((s.current for s in slots if s.kind == KIND_BASE_URL), None)
        key = next((s.current for s in slots if s.kind == KIND_API_KEY), None)
        if not base:
            results.append((a.id, "SKIP", "no base_url slot (env-only/unsupported)"))
            continue
        key = _resolve_key(key)
        probe = getattr(a, "probe", None)
        if callable(probe):
            status, msg = probe(timeout=args.timeout)
        else:
            status, msg = _probe_endpoint(base, key, model, args.timeout)
        results.append((a.id, status, msg))

    for aid, status, msg in results:
        mark = {"PASS": "✓", "WARN": "!", "FAIL": "✘", "SKIP": "·"}[status]
        print(f"  {mark} {aid:<12} {status:<5} {msg}")
    n_pass = sum(1 for _, s, _ in results if s == "PASS")
    n_warn = sum(1 for _, s, _ in results if s == "WARN")
    n_fail = sum(1 for _, s, _ in results if s == "FAIL")
    n_skip = sum(1 for _, s, _ in results if s == "SKIP")
    print(f"\n{n_pass} pass, {n_warn} warn, {n_fail} fail, {n_skip} skip "
          f"(of {len(results)} adapters)", file=sys.stderr)
    return 1 if n_fail else 0


# ---- parser --------------------------------------------------------------

def _add_scope(p):
    p.add_argument("--only", help="comma-separated adapter ids to include")
    p.add_argument("--exclude", help="comma-separated adapter ids to skip")


def _add_endpoint(p):
    p.add_argument("--base-url", metavar="URL",
                   help="switch every agent's base_url slot to URL")
    p.add_argument("--api-key", metavar="KEY",
                   help="switch every agent's api_key slot to KEY. For env-var "
                        "agents (codex/grok/reasonix) the literal is persisted to "
                        "the shell rc (posix) / user env (windows). Prefer "
                        "profiles to keep keys out of shell history.")


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
    _add_endpoint(p)
    sub = p.add_subparsers(dest="cmd")

    sl = sub.add_parser("list", help="list installed/known adapters")
    sl.set_defaults(func=cmd_list)

    ss = sub.add_parser("show", help="show current model per agent slot")
    _add_scope(ss)
    ss.set_defaults(func=cmd_show)

    sp = sub.add_parser("profiles", help="list profiles in ~/.ccse/profiles.toml")
    sp.set_defaults(func=cmd_profiles)

    pa = sub.add_parser("apply", help="write --model/--base-url/--api-key or a profile into all agents")
    _add_scope(pa)
    pa.add_argument("--model", metavar="NAME",
                    help="set every agent's primary slot to NAME (prefix kept)")
    pa.add_argument("profile", nargs="?", help="profile name from profiles.toml")
    pa.add_argument("--no-backup", action="store_true", help="skip snapshot")
    pa.add_argument("--no-keep-prefix", action="store_true",
                    help="set model verbatim (drop route prefix)")
    _add_endpoint(pa)
    pa.set_defaults(func=cmd_apply)

    pd = sub.add_parser("diff", help="preview changes (dry-run)")
    _add_scope(pd)
    pd.add_argument("--model", metavar="NAME")
    pd.add_argument("profile", nargs="?")
    pd.add_argument("--no-keep-prefix", action="store_true",
                    help="set model verbatim (drop route prefix)")
    _add_endpoint(pd)
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

    pv = sub.add_parser(
        "verify", help="probe every agent's configured endpoint + model "
                       "(run after a switch to confirm it still works)")
    _add_scope(pv)
    pv.add_argument("--timeout", type=int, default=8,
                    help="per-endpoint HTTP timeout in seconds (default 8)")
    pv.set_defaults(func=cmd_verify)

    pr = sub.add_parser(
        "rewrite", help="rewrite LLM base_url/api_key/model across a project "
                        "dir (.py/.ts/.js/.env) — independent of agent adapters")
    pr.add_argument("dir", nargs="?", default=".",
                    help="project dir to scan (default: .)")
    pr.add_argument("--base-url", metavar="URL", help="new base_url value")
    pr.add_argument("--api-key", metavar="KEY", help="new api_key value")
    pr.add_argument("--model", metavar="NAME", help="new model value")
    pr.add_argument("--dry", action="store_true", help="preview only, write nothing")
    pr.set_defaults(func=cmd_rewrite)

    return p


def cmd_rewrite(args) -> int:
    from . import rewrite
    assignments = {}
    if args.base_url:
        assignments["base_url"] = args.base_url
    if args.api_key:
        assignments["api_key"] = args.api_key
    if args.model:
        assignments["model"] = args.model
    if not assignments:
        config.die("rewrite needs at least one of --base-url/--api-key/--model")
    return rewrite.run(Path(args.dir), assignments, dry=args.dry)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # top-level --model shorthand: act as `apply --model`
    if getattr(args, "cmd", None) is None:
        if getattr(args, "model", None) is not None or \
                getattr(args, "base_url", None) or getattr(args, "api_key", None):
            assignments: dict[str, str] = {}
            if getattr(args, "model", None) is not None:
                kp = not getattr(args, "no_keep_prefix", False)
                assignments.update(_model_assignments(
                    args.model, args.only, args.exclude, keep_prefix=kp))
            if getattr(args, "base_url", None):
                assignments.update(_endpoint_assignments(
                    KIND_BASE_URL, args.base_url, args.only, args.exclude))
            if getattr(args, "api_key", None):
                assignments.update(_endpoint_assignments(
                    KIND_API_KEY, args.api_key, args.only, args.exclude))
            parts = [p for p in (
                f"--model {args.model}" if getattr(args, "model", None) else None,
                f"--base-url {args.base_url}" if getattr(args, "base_url", None) else None,
                "--api-key <redacted>" if getattr(args, "api_key", None) else None,
            ) if p]
            tag = " --".join(parts)
            return _apply_assignments(
                assignments, dry=args.dry, no_backup=args.no_backup,
                only=args.only, exclude=args.exclude, tag=tag)
        parser.print_help(sys.stderr)
        return 2
    return args.func(args)