"""Filesystem helpers: locate homes, backup, atomic write, redact."""
from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

HOME = Path.home()
DATA_DIR = Path.home() / ".ccse"
HISTORY_INDEX = DATA_DIR / "history.jsonl"
SNAPSHOT_DIR = DATA_DIR / "snapshots"


def detect_tomli_w():
    try:
        import tomli_w  # noqa: F401
        return True
    except ImportError:
        return False


def write_text_atomic(path: Path, text: str) -> None:
    """Write text atomically, preserving perms where file exists."""
    d = path.parent
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=f".{path.name}.", suffix=".tmp")
    mode = 0o644
    if path.exists():
        mode = stat.S_IMODE(os.stat(path).st_mode)
    os.write(fd, text.encode("utf-8"))
    os.close(fd)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def load_json(path: Path) -> "dict | list | None":
    if not path.exists():
        return None
    return json.loads(path.read_text("utf-8"))


def dump_json(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def keep_mode_write_json(path: Path, obj):
    text = dump_json(obj)
    write_text_atomic(path, text)
    return text


# --- snapshots / undo ------------------------------------------------------
import json as _json  # noqa: E402

_SNAP_META = "files.json"  # per-snapshot manifest filename


def ensure_data_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def save_snapshot(files: list[Path], stamp: str) -> Path:
    """Copy `files` into SNAPSHOT_DIR/<stamp>/ and write a manifest mapping
    logical name -> absolute path. Returns the snapshot dir."""
    ensure_data_dirs()
    snap = SNAPSHOT_DIR / stamp
    snap.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    for f in files:
        if not f.exists():
            continue
        rel = f"{f.parent.name}__{f.name}"  # ponytail: flat unique-ish name
        # disambiguate collisions
        n, cand = rel, rel
        i = 2
        while cand in manifest:
            cand = f"{n}.{i}"
            i += 1
        shutil.copy2(f, snap / cand)
        manifest[cand] = str(f)
    (snap / _SNAP_META).write_text(_json.dumps(manifest, indent=2), "utf-8")
    return snap


def list_snapshots() -> list[str]:
    if not SNAPSHOT_DIR.exists():
        return []
    return sorted(
        (p.name for p in SNAPSHOT_DIR.iterdir() if p.is_dir()),
        reverse=True,
    )


def restore_snapshot(stamp: str) -> list[str]:
    snap = SNAPSHOT_DIR / stamp
    meta = snap / _SNAP_META
    if not meta.exists():
        die(f"snapshot {stamp!r} not found")
    manifest = _json.loads(meta.read_text("utf-8"))
    restored: list[str] = []
    for rel, target in manifest.items():
        src = snap / rel
        if not src.exists():
            continue
        t = Path(target)
        if t.exists():
            # back up what's currently there before overwriting
            shutil.copy2(t, t.with_name(f"{t.name}.ccse.pre-restore.{stamp}"))
        shutil.copy2(src, t)
        restored.append(str(t))
    return restored


def append_history(record) -> None:
    ensure_data_dirs()
    with HISTORY_INDEX.open("a", encoding="utf-8") as fh:
        fh.write(_json.dumps(record, ensure_ascii=False) + "\n")


def info(msg: str) -> None:
    print(msg, file=sys.stderr)


def die(msg: str, code: int = 2) -> None:
    print(f"ccse: {msg}", file=sys.stderr)
    raise SystemExit(code)


def redact(s: str | None) -> str:
    if s is None:
        return "<unset>"
    if len(s) > 12 and any(c in s for c in (" ", "\n")):
        return s  # not a token
    if s.startswith("sk-") or len(s) >= 24:
        return s[:6] + "***"
    return s