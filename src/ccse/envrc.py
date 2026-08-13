"""Shell-rc / env-var adapter: mutates `export VAR=...` lines.

For agents whose model name lives in an environment variable (e.g. Kimi Code
reads ``KIMI_MODEL_NAME`` from a shell rc file), not a structured config. On
posix (linux/macOS) the value lives in ``~/.zshrc`` as ``export VAR=...``;
on Windows it lives in the user environment, persisted via ``setx``. We only
touch the given VAR; nothing else in the rc file changes, and writes are
single-quoted so names with shell glob metachars (``glm-5.2[1M]``) stay
literal.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from . import config
from .registry import KIND_API_KEY, KIND_MODEL, Slot, register

HOME = config.HOME

# matches: [export|setenv] VAR = <rhs>   where rhs may be bare, 'single', or "double"
_LINE = re.compile(
    r"^(?:\s*)(?:export\s+|setenv\s+)?(?P<var>[A-Za-z_][A-Za-z0-9_]*)"
    r"\s*=\s*(?P<val>.*)$"
)


def _unquote(rhs: str) -> str:
    rhs = rhs.strip()
    if len(rhs) >= 2 and rhs[0] == "'" and rhs[-1] == "'":
        return rhs[1:-1].replace("'\''", "'")
    if len(rhs) >= 2 and rhs[0] == '"' and rhs[-1] == '"':
        return rhs[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    # strip a trailing inline comment for bare values (best-effort)
    if "#" in rhs:
        bare = rhs.split("#", 1)[0].strip()
        if bare:
            return bare
    return rhs


def _quote(val: str) -> str:
    return "'" + val.replace("'", "'\\''") + "'"


def _setx(var: str, value: str) -> bool:
    """Persist `VAR=value` into the Windows user environment (survives reboot;
    current process won't see it until next shell)."""
    import subprocess
    try:
        r = subprocess.run(["setx", var, value], capture_output=True, text=True)
        return r.returncode == 0
    except OSError:
        return False


def ensure_env_var(var: str, value: str, path: Path | None = None) -> tuple[str, str] | None:
    """Persist `VAR=value`. posix: update or append `export VAR='value'` in the
    shell rc file (default config.SHELL_RC); windows: `setx` into the user env.

    Returns (old, new) if a change is needed, else None. Reuses the same line
    rewrite logic as apply() so agent env-var keys (codex/grok/reasonix) can
    persist a literal key into the shell rc / user env once.
    """
    if config.OS_NAME == "windows":
        old = os.environ.get(var)
        if old == value:
            return None
        if _setx(var, value):
            return (old or "<unset>", value)
        return None
    file_path = path or config.SHELL_RC
    if file_path is None:
        return None
    if not file_path.exists():
        return None
    lines = file_path.read_text("utf-8").splitlines()
    new_lines: list[str] = []
    old_val: str | None = None
    replaced = False
    for line in lines:
        m = _LINE.match(line)
        if m and m.group("var") == var:
            old_val = _unquote(m.group("val"))
            if old_val == value:
                return None
            new_lines.append(f"export {var}={_quote(value)}")
            replaced = True
            continue
        new_lines.append(line)
    if not replaced:
        new_lines.append(f"export {var}={_quote(value)}")
    config.write_text_atomic(file_path, "\n".join(new_lines) + "\n")
    return (old_val or "<unset>", value)


def _read_vars(path: Path, want: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text("utf-8").splitlines():
        m = _LINE.match(line)
        if m and m.group("var") in want:
            out[m.group("var")] = _unquote(m.group("val"))
    return out


def make_envrc_adapter(
    adapter_id: str,
    name: str,
    var_map: dict[str, str],
    path: Path | None = None,
    kinds: dict[str, str] | None = None,
):
    """Build+register a shell-rc / user-env adapter. var_map: {slot_label: ENV_VAR}.
    The first key is the adapter's primary slot. `path` defaults to
    config.SHELL_RC (posix shell rc); on Windows it is None and values are read
    from / written to the user environment via setx.
    `kinds`: {slot_label: slot_kind} for non-model slots (e.g. api_key)."""
    file_path = path if path is not None else config.SHELL_RC
    # slot -> env var
    slot2var = var_map
    var2slot = {v: k for k, v in var_map.items()}
    primary = next(iter(slot2var))
    slot_kind = dict(kinds or {})

    def _is_windows() -> bool:
        return config.OS_NAME == "windows"

    def slots(self):
        if _is_windows():
            out = []
            for label, var in slot2var.items():
                out.append(Slot(key=f"{adapter_id}.{label}", label=label,
                                current=os.environ.get(var),
                                kind=slot_kind.get(label, KIND_MODEL)))
            return out
        if file_path is None or not file_path.exists():
            return []
        found = _read_vars(file_path, set(slot2var.values()))
        out = []
        for label, var in slot2var.items():
            cur = found.get(var)
            if cur is None:
                # not declared yet but file exists → still show <unset>
                cur = None
            out.append(Slot(key=f"{adapter_id}.{label}", label=label, current=cur,
                            kind=slot_kind.get(label, KIND_MODEL)))
        return out

    def apply(self, assignments, dry=False):
        relevant = {k[len(adapter_id) + 1:]: v for k, v in assignments.items()
                    if k.startswith(adapter_id + ".")}
        if not relevant:
            return []
        if _is_windows():
            diffs: list[str] = []
            for label, val in relevant.items():
                var = slot2var.get(label)
                if not var:
                    continue
                old = os.environ.get(var)
                if old == val:
                    continue
                diffs.append(f"  env {var}: {old!r} -> {val!r}")
                if not dry:
                    _setx(var, val)
            return diffs
        if file_path is None or not file_path.exists():
            return []
        want_vars = {slot2var[label]: v for label, v in relevant.items()
                     if label in slot2var}
        if not want_vars:
            return []
        lines = file_path.read_text("utf-8").splitlines()
        diffs: list[str] = []
        written: set[str] = set()
        new_lines: list[str] = []
        for line in lines:
            m = _LINE.match(line)
            if m and m.group("var") in want_vars:
                var = m.group("var")
                old = _unquote(m.group("val"))
                val = want_vars[var]
                written.add(var)  # present in file; never append a duplicate
                if old != val:
                    new_lines.append(f"export {var}={_quote(val)}")
                    diffs.append(f"  export {var}: {old!r} -> {val!r}")
                else:
                    new_lines.append(line)  # already in sync, keep as-is
                continue
            new_lines.append(line)
        # append any vars not present in the file
        for var, val in want_vars.items():
            if var not in written:
                new_lines.append(f"export {var}={_quote(val)}")
                diffs.append(f"  export {var}: <unset> -> {val!r} (appended)")
        if diffs and not dry:
            config.write_text_atomic(file_path, "\n".join(new_lines) + "\n")
        return diffs

    cls = type(
        f"_{adapter_id}_envrc",
        (object,),
        {"id": adapter_id, "name": name, "path": file_path,
         "available": property(lambda self: file_path.exists()),
         "primary": f"{adapter_id}.{primary}",
         "slots": slots, "apply": apply},
    )
    register(cls)
    return cls


# Kimi Code: model name in shell rc / user env as KIMI_MODEL_NAME=...
make_envrc_adapter(
    "kimi", "Kimi Code",
    {"model": "KIMI_MODEL_NAME", "api_key": "KIMI_MODEL_API_KEY"},
    kinds={"api_key": KIND_API_KEY},
)
# CoPAW: export COPAW_MODEL_NAME=... (kept since other CoPAW model infra is
# dynamic; this is the one stable reference users wire for NewAPI fallback).
make_envrc_adapter(
    "copaw", "CoPAW",
    {"model": "COPAW_MODEL_NAME", "api_key": "COPAW_MODEL_API_KEY"},
    kinds={"api_key": KIND_API_KEY},
)


if __name__ == "__main__":
    # ad-hoc self-check
    import tempfile, os
    tf = Path(tempfile.mktemp())
    tf.write_text(
        "export KIMI_MODEL_NAME=gpt-5.6-terra\n"
        "export OTHER=x\n"
        "export QUOTED=\"q-5.6\"\n", "utf-8")
    print(_read_vars(tf, {"KIMI_MODEL_NAME", "QUOTED"}))
    os.unlink(tf)