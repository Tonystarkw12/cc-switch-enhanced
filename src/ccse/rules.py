"""`ccse rules` — inject a behavioral-rules snippet (caveman + rtk by default)
into every ccse-supported agent's *global* instructions file, idempotently.

Why: model/base_url/api_key are ccse's structured-switch surface; output style
and command-output routing are behavioral, and only take effect if the agent
reads them at startup. Each agent loads a global instructions file (AGENTS.md
mostly; CLAUDE.md / GEMINI.md / openakita's AGENT.md by exception). This module
appends a marked block to those files so a one-line switch repoints behavior
across the whole fleet, the same way `--model` repoints models.

Marked block (`<!-- ccse:caveman-rtk:START --> ... :END -->`) is appended if
absent, replaced in place if present → re-runnable, drift-free. `ccse rules rm`
strips it. kimi/copaw are env-only (no instruction file) and thus excluded.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import config

HOME = config.HOME

START = "<!-- ccse:caveman-rtk:START -->"
END = "<!-- ccse:caveman-rtk:END -->"

DEFAULT_SNIPPET = """\
# Default Operating Mode — always active

## 1. Caveman Full Mode (every response)

Terse caveman. Drop articles (a/an/the), filler (just/really/basically/actually/simply), pleasantries (sure/certainly/of course), hedging. Fragments OK. Short synonyms (fix not "implement a solution for").
**Technical substance stays exact**: code, commits, PRs, error strings, file paths, commands, exact values — never compressed or paraphrased.

Pattern: `[thing] [action] [reason]. [next step].`
- Bad: "Sure! I'd be happy to help. The issue is likely caused by…"
- Good: "Bug in auth middleware. Token expiry check uses `<` not `<=`. Fix:"

## 2. RTK for command output

Route any large/verbose command output through the `rtk` CLI proxy instead of the raw command:

`rtk read <file>` · `rtk git <…>` · `rtk tree` · `rtk ls` · `rtk smart <file>` (2-line summary) · `rtk gh / glab / aws / psql / pnpm / json` · `rtk err` / `rtk test` (errors/failures only).

Compress aggressively but PRESERVE technical substance: code, URLs, file paths, commands, exact values, structure.
"""

# adapter id -> global instructions path. Filenames follow each agent's own
# convention (AGENTS.md by default; CLAUDE.md / GEMINI.md / openakita AGENT.md
# by exception). kimi / copaw are env-only and intentionally absent.
INSTRUCTION_FILES: dict[str, Path] = {
    "claude":     HOME / ".claude" / "CLAUDE.md",
    "codex":      HOME / ".codex" / "AGENTS.md",
    "opencode":   HOME / ".config" / "opencode" / "AGENTS.md",
    "grok":       HOME / ".grok" / "AGENTS.md",
    "hermes":     HOME / ".hermes" / "AGENTS.md",
    "openakita":  HOME / ".openakita" / "identity" / "AGENT.md",
    "jcode":      HOME / ".jcode" / "AGENTS.md",
    "gemini":     HOME / ".gemini" / "GEMINI.md",
    "qwen":       HOME / ".qwen" / "AGENTS.md",
    "snow":       HOME / ".snow" / "AGENTS.md",
    "crush":      HOME / ".config" / "crush" / "AGENTS.md",
    "kilo":       HOME / ".config" / "kilo" / "AGENTS.md",
    "omp":        HOME / ".omp" / "AGENTS.md",
    "reasonix":   HOME / ".reasonix" / "AGENTS.md",
    "droid":      HOME / ".factory" / "AGENTS.md",
    "forge":      HOME / ".forge" / "AGENTS.md",
    "prime":      HOME / ".prime" / "AGENTS.md",
    "memmy":      HOME / ".memmy" / "AGENTS.md",
    "codebuddy":  HOME / ".codebuddy" / "AGENTS.md",
    "pi":         HOME / ".pi" / "AGENTS.md",
    "openclaw":   HOME / ".openclaw" / "AGENTS.md",
    "kilocode":   HOME / ".kilocode" / "AGENTS.md",
    "cline":      HOME / ".cline" / "AGENTS.md",
}

_BLOCK_RE = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)


def _scope(only, exclude) -> list[tuple[str, Path]]:
    onlyset = {s.strip() for s in only.split(",")} if only else None
    excl = {s.strip() for s in exclude.split(",")} if exclude else None
    out = []
    for aid, p in INSTRUCTION_FILES.items():
        if onlyset and aid not in onlyset:
            continue
        if excl and aid in excl:
            continue
        out.append((aid, p))
    return out


def _block(snippet: str) -> str:
    return f"{START}\n{snippet.rstrip()}\n{END}"


def status(only=None, exclude=None) -> None:
    """Print per-agent state: injected / missing / symlink / no-file-convention."""
    print(f"snippet: built-in caveman+rtk  (markers: {START[:30]}...)")
    for aid, p in _scope(only, exclude):
        if p.is_symlink():
            state = "symlink (skip)"
        elif not p.exists():
            state = "missing"
        elif START in p.read_text("utf-8"):
            state = "injected"
        else:
            state = "present, no block"
        print(f"  {aid:<11} {state:<18} {p}")


def apply(only=None, exclude=None, snippet: str | None = None, dry: bool = False) -> None:
    """Inject (or refresh) the marked block in every in-scope agent's file."""
    body = snippet if snippet is not None else DEFAULT_SNIPPET
    block = _block(body)
    changed = 0
    for aid, p in _scope(only, exclude):
        if p.is_symlink():
            print(f"  skip    {aid:<11} (symlink) {p}")
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            if not dry:
                config.write_text_atomic(p, block + "\n")
            print(f"  create  {aid:<11} {p}")
            changed += 1
            continue
        txt = p.read_text("utf-8")
        if START in txt:
            new = _BLOCK_RE.sub(block, txt)
            if new != txt:
                if not dry:
                    config.write_text_atomic(p, new)
                print(f"  update  {aid:<11} {p}")
                changed += 1
            else:
                print(f"  ok      {aid:<11} {p}")
        else:
            sep = "\n\n" if txt.strip() and not txt.endswith("\n\n") else "\n"
            if not dry:
                config.write_text_atomic(p, txt + sep + block + "\n")
            print(f"  append  {aid:<11} {p}")
            changed += 1
    verb = "would change" if dry else "changed"
    print(f"{verb}: {changed} file(s)" + ("  (dry-run)" if dry else ""))


def remove(only=None, exclude=None, dry: bool = False) -> None:
    """Strip the marked block from every in-scope agent's file."""
    changed = 0
    for aid, p in _scope(only, exclude):
        if not p.exists() or p.is_symlink():
            continue
        txt = p.read_text("utf-8")
        if START not in txt:
            continue
        new = _BLOCK_RE.sub("", txt).rstrip() + "\n"
        if new != txt:
            if not dry:
                config.write_text_atomic(p, new)
            print(f"  removed {aid:<11} {p}")
            changed += 1
    verb = "would change" if dry else "changed"
    print(f"{verb}: {changed} file(s)" + ("  (dry-run)" if dry else ""))
