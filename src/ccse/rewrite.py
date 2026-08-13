"""`ccse rewrite` — scan a project dir and rewrite LLM config across scripts.

Independent of the agent adapters: this targets user code that reads LLM
credentials from env vars or a .env file (``os.getenv("OPENAI_BASE_URL", ...)``,
``process.env.OPENAI_API_KEY``, ``OPENAI_MODEL=`` in .env). Switching one
aggregator flips a whole project's endpoints in one shot.

Conservative by design — only lines that *look like* LLM config get touched:
env-var reads whose key names a base_url/api_key/model slot, .env keys, and
explicit ``api_key``/``base_url`` literals. Plain ``model = "..."`` assignments
are left alone (too easy to misfire on non-LLM code — the env/.env paths cover
the switch anyway).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from . import config

# dotted-directory / build noise to never scan
_SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    "target", ".next", ".turbo", ".idea", ".vscode", ".env", "env",
}
_SOURCE_EXTS = {".py", ".ts", ".js", ".mts", ".cts", ".mjs", ".cjs"}

# env-var / .env key-name -> which LLM slot it holds
_KIND_KEYS: dict[str, re.Pattern] = {
    "base_url": re.compile(r"BASE[_]?URL|BASEURL|ENDPOINT", re.I),
    "api_key": re.compile(r"API[_]?KEY|APIKEY|API[_]?TOKEN|AUTH[_]?TOKEN", re.I),
    "model": re.compile(r"MODEL", re.I),
}

# env-var read with an inline literal default → rewrite the default when the
# key names a slot in scope. os.environ["KEY"] (no default) is left alone.
_SRC_PATTERNS = {
    "py": re.compile(
        r'(?:os\.environ\.get|os\.getenv|getenv)\s*\(\s*["\'](?P<key>[A-Za-z_][A-Za-z0-9_]*)["\']'
        r'\s*,\s*["\'](?P<val>[^"\']*)["\']'),
    "js": re.compile(
        r'process\.env\s*(?:\.\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)|\[\s*["\'](?P<key2>[A-Za-z_][A-Za-z0-9_]*)["\']\s*\])\s*'
        r'(?:\?\?|\|\|)\s*["\'](?P<val>[^"\']*)["\']'),
}

# explicit api_key/base_url literal at start of a line (`api_key = "sk-..."`).
_LITERAL = re.compile(
    r'^(?P<indent>\s*)(?P<field>api[_]?key|base[_]?url|apiKey|baseUrl)\s*'
    r'(?P<op>[:=])\s*(?P<quote>["\'])(?P<val>[^"\']*)(?P=quote)', re.I)


def _slot_kind(key: str) -> str | None:
    for kind, pat in _KIND_KEYS.items():
        if pat.search(key):
            return kind
    return None


def _iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix in _SOURCE_EXTS or fn == ".env" or fn.startswith(".env."):
                yield p


def _rewrite_source(path: Path, assignments: dict[str, str], dry: bool) -> list[str]:
    lang = "js" if path.suffix in (".ts", ".js", ".mts", ".cts", ".mjs", ".cjs") else "py"
    pat = _SRC_PATTERNS[lang]
    diffs: list[str] = []
    out: list[str] = []

    def _repl(m: re.Match) -> str:
        key = m.group("key") or m.group("key2")
        kind = _slot_kind(key)
        if kind not in assignments or m.group("val") == assignments[kind]:
            return m.group(0)
        diffs.append(f"  {path}: {key} default: {m.group('val')!r} -> "
                     f"{assignments[kind]!r}")
        return m.group(0).replace(f'"{m.group("val")}"', f'"{assignments[kind]}"')

    for line in path.read_text("utf-8", errors="replace").splitlines(keepends=True):
        new_line = pat.sub(_repl, line)
        lm = _LITERAL.match(new_line)
        if lm:
            field = lm.group("field").lower()
            slot = "api_key" if "key" in field else "base_url"
            if slot in assignments and lm.group("val") != assignments[slot]:
                diffs.append(f"  {path}: {lm.group('field')}: {lm.group('val')!r} -> "
                             f"{assignments[slot]!r}")
                new_line = (f"{lm.group('indent')}{lm.group('field')} "
                            f"{lm.group('op')} {lm.group('quote')}"
                            f"{assignments[slot]}{lm.group('quote')}\n")
        out.append(new_line)
    if diffs and not dry:
        config.write_text_atomic(path, "".join(out))
    return diffs


def _rewrite_env(path: Path, assignments: dict[str, str], dry: bool) -> list[str]:
    diffs: list[str] = []
    out: list[str] = []
    for line in path.read_text("utf-8", errors="replace").splitlines(keepends=True):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        key, _, val = stripped.partition("=")
        kind = _slot_kind(key.strip())
        if kind not in assignments or val.strip() == assignments[kind]:
            out.append(line)
            continue
        diffs.append(f"  {path}: {key.strip()}: {val.strip()!r} -> {assignments[kind]!r}")
        out.append(f"{key}={assignments[kind]}\n" if not dry else line)
    if diffs and not dry:
        config.write_text_atomic(path, "".join(out))
    return diffs


def run(root: Path, assignments: dict[str, str], dry: bool) -> int:
    root = root.expanduser()
    if not root.is_dir():
        config.die(f"{root} is not a directory")
    diffs: list[str] = []
    n_files = 0
    for p in _iter_files(root):
        d = (_rewrite_source(p, assignments, dry) if p.suffix in _SOURCE_EXTS
             else _rewrite_env(p, assignments, dry))
        if d:
            diffs.extend(d)
            n_files += 1
    for line in diffs:
        print(line)
    mode = "dry-run" if dry else "rewritten"
    print(f"\n{mode}: {len(diffs)} line(s) across {n_files} file(s).", file=sys.stderr)
    return 0
