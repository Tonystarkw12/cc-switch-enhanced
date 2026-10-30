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
strips it. Adapters without a startup-read global instructions file are listed
in EXCLUDED with the reason (``ccse rules`` status prints them). Primary
workhorse agents (PROTECTED) are skipped by apply/remove unless named via
`--only` — their instruction files are hand-curated and stay frozen.
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

## 3. Server defaults — hardware-tuned, always apply

- **Threads**: start parallelizable jobs (builds, tests, preprocessing) at 32 worker threads/processes (server: 64 logical cores — leave headroom for interactive work). Never silently drop to 1-8.
- **Load cap**: aggregate CPU usage stays ≤90% of the machine. Check current load before launching and monitor heavy runs (`uptime` / `mpstat`): scale down when the box is busy, scale up past 32 when usage sits well below the cap and the job still benefits — 90% is the hard ceiling, 32 is just the starting point.
- **Long tasks (>1h compute)**: any job expected to burn >1h of CPU/GPU compute requires rigorous pre-flight verification before launch — verify configs, arguments, paths and checkpoint logic; run a tiny canary / dry-run first to prove correctness before committing hours of compute. Always build checkpoint/resume in from the start: persist progress/state to disk in resumable batches so an interrupted run continues where it stopped instead of restarting from zero.
- **GPU**: 4× RTX 4090 on this server. Any GPU-worthy job (training, embedding, batch inference) uses all 4 by default (DataParallel / DDP / `device_map="auto"`) — a single card only when the workload can't be split.

## 4. Working rules — safety and delivery discipline

- **Secrets**: reading keys from env files/vars and writing user-provided keys into them (`.env`, `~/.zshrc`, ccse providers) is normal work. But never print a key's VALUE in your reply, logs or diffs: when asked for a key, hand back a command the user runs themselves (e.g. `echo $VAR_NAME`, `grep NAME ~/.zshrc`) instead of the literal. Keys never go into git history; report any leak immediately.
- **Destructive ops need explicit confirmation first**: `rm -rf`, service restarts (`systemctl`, `docker`), dropping DBs/tables, deleting data dirs, killing processes. Diagnose the actual root cause before acting — never restart as a guess.
- **Verify before claiming done**: run the tests/build and report the real output; if you can't run them, say so explicitly. Never report success unverified.
- **Minimal diff**: touch only the files the task names — no drive-by reformatting or "improvements". Small refactors that serve the task are fine; large ones (multi-file restructuring, architecture or public-interface changes) are announced first and wait for approval before starting. Stop and explain when a fix outgrows the task.
- **Python tooling**: envs on this server are mamba-managed — create/activate with `mamba`, install only inside the active env; a project pinning `uv.lock` stays on uv. Never install into system/base python.
- **Git checkpoints**: before a large refactor or risky multi-file change, make sure a clean checkpoint exists — commit the current state (or ask the user to), then work on a dedicated branch (open a worktree only when parallel work in the main tree is needed), committing small steps often. Never push without being asked, never force-push shared branches, never commit keys or `.env` files.
- **Subagent delegation**: actively delegate independent, read-heavy, or granular chores (broad codebase searches, doc lookups, test sub-suites, repetitive log/diff audits) to background subagents. Keep the main turn clean for orchestration, architectural decisions, and core edits; avoid bloating the main context with raw discovery dumps.
- **Codebase intelligence (repowise / zg)**: understand code and architecture through dedicated repo intelligence tools first (`repowise` MCP/CLI tools like `get_answer`, `search_codebase`, `distill`; `zg` semantic search `zg query`). Avoid brute-force unbounded grep or dumping whole unfamiliar files; fall back to native `Read`/`rg` only for targeted, verified edits.
"""

# adapter id -> global instructions path. Filenames follow each agent's own
# convention (AGENTS.md by default; CLAUDE.md / GEMINI.md / openakita AGENT.md
# by exception). Every path is grounded: binary/bundle strings, the tool's
# own source, or official docs. Adapters absent from this dict are in
# EXCLUDED below with the reason.
INSTRUCTION_FILES: dict[str, Path] = {
    "claude":     HOME / ".claude" / "CLAUDE.md",
    "zcode":      HOME / ".zcode" / "AGENTS.md",
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
    "mu":         HOME / ".mu" / "AGENTS.md",
    "memmy":      HOME / ".memmy" / "AGENTS.md",
    "codebuddy":  HOME / ".codebuddy" / "AGENTS.md",
    "pi":         HOME / ".pi" / "AGENTS.md",
    "openclaw":   HOME / ".openclaw" / "AGENTS.md",
    "kilocode":   HOME / ".kilocode" / "AGENTS.md",
    "cline":      HOME / ".cline" / "AGENTS.md",
    # ante binary strings: "~/.ante/AGENTS.md"
    "ante":       HOME / ".ante" / "AGENTS.md",
    # command-code bundle getUserMemoryPath(): "${home}/.commandcode/AGENTS.md"
    "commandcode": HOME / ".commandcode" / "AGENTS.md",
    # openclaude bundle: global memory = <OPENCLAUDE_CONFIG_DIR>/CLAUDE.md,
    # default ~/.openclaude (CC-clone convention)
    "openclaude": HOME / ".openclaude" / "CLAUDE.md",
    # dsh-agent-instructions: USER_GLOBAL_FILE="AGENTS.md" under $DSH_HOME
    "dsh":       HOME / ".dsh" / "AGENTS.md",
}

# Primary workhorse agents. Their instruction files carry hand-curated stacks
# (LifeOS, memory backend, per-agent tuning) on top of the injected block, so
# `ccse rules` apply/remove never rewrites them by default — their injected
# state stays frozen at whatever version they last got. An explicit
# `--only <id>` names them and overrides the protection.
PROTECTED = {"claude", "zcode", "codex", "opencode", "prime"}

# Registered adapters with no startup-read global instructions file, and why.
# Printed by status() so `ccse rules` shows the full adapter fleet.
EXCLUDED: dict[str, str] = {
    # env-only adapters: behavior surfaces are shell env vars, no file to mark
    "amp":       "env-only (AMP_URL/AMP_API_KEY; model routing is server-side)",
    "copaw":     "env-only adapter",
    "devin":     "env-only adapter (web agent)",
    "fx":        "env-only (FX_MODEL in ~/.zshrc)",
    "kimi":      "env-only adapter",
    "nvim":      "env-only adapter",
    # tony's own services, not agent CLIs
    "graphpulse": "personal service (vite dev proxy), not an agent",
    "nmragent":  "personal service (NMRagent backend .env), not an agent",
    # rules surface is project-scoped only — no global file to inject into
    "aider":     "conventions via --read conf key; no global md file",
    "arkcli":    "profile/model CLI; no instructions surface",
    "mcode":     "project AGENTS.md only; memory is internal",
    "mimo":      "project AGENTS.md only; reads ~/.claude/CLAUDE.md (covered by claude)",
    "openhands": "global microagents are keyword-triggered, not startup-read",
    "qoder":     "rules are project .qoder/rules/ only",
    "qodercn":   "rules are project .qoder-cn rules only",
    "step":      "context-file discovery is project-scoped",
    "swival":    "project AGENTS.md only",
    "trae":      "global rules managed by IDE settings, not a file",
    # the agent's own managed state — injecting there would fight the harness
    "penguin":   "AGENTS.md is per-agent harness state, not user config",
    "pigo":      "memory is sqlite (~/.pigo/memory/index.db), no md surface",
    # no instructions surface found (binary/bundle probes came up empty)
    "atomcode":  "no instructions surface; config is TOML only",
    "mmx":       "API chat CLI, no agent instructions surface",
    "muse":      "no global instructions surface found (workspace init only)",
}
# agy (Antigravity) has no entry on purpose: its documented global rules files
# include ~/.gemini/GEMINI.md — already covered by the gemini injection.
EXCLUDED["agy"] = "global rules file is ~/.gemini/GEMINI.md — covered by gemini entry"

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


def _explicit(only) -> set[str]:
    return {s.strip() for s in only.split(",")} if only else set()


def status(only=None, exclude=None) -> None:
    """Print per-agent state: injected / missing / symlink / no-file-convention."""
    print(f"snippet: built-in caveman+rtk  (markers: {START[:30]}...)")
    explicit = _explicit(only)
    for aid, p in _scope(only, exclude):
        if p.is_symlink():
            state = "symlink (skip)"
        elif not p.parent.exists():
            state = "not installed"
        elif not p.exists():
            state = "missing"
        elif START in p.read_text("utf-8-sig"):
            state = "injected"
        else:
            state = "present, no block"
        if aid in PROTECTED and aid not in explicit:
            state += " [primary]"
        print(f"  {aid:<11} {state:<18} {p}")
    for aid, reason in EXCLUDED.items():
        onlyset = {s.strip() for s in only.split(",")} if only else None
        excl = {s.strip() for s in exclude.split(",")} if exclude else None
        if onlyset and aid not in onlyset:
            continue
        if excl and aid in excl:
            continue
        print(f"  {aid:<11} {'excluded':<18} {reason}")


def apply(only=None, exclude=None, snippet: str | None = None, dry: bool = False) -> None:
    """Inject (or refresh) the marked block in every in-scope agent's file.

    Skips agents whose instruction file's parent directory is absent —
    that means the agent itself was never installed/run, and creating the
    dir+file would litter $HOME with orphans. Run the agent once, re-run
    `ccse rules --apply`."""
    body = snippet if snippet is not None else DEFAULT_SNIPPET
    block = _block(body)
    changed = 0
    explicit = _explicit(only)
    for aid, p in _scope(only, exclude):
        if aid in PROTECTED and aid not in explicit:
            print(f"  skip    {aid:<11} (primary agent — protected; "
                  f"--only {aid} to override)")
            continue
        if p.is_symlink():
            print(f"  skip    {aid:<11} (symlink) {p}")
            continue
        if not p.parent.exists():
            print(f"  skip    {aid:<11} ({p.parent} absent — agent not installed?)")
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            if not dry:
                config.write_text_atomic(p, block + "\n")
            print(f"  create  {aid:<11} {p}")
            changed += 1
            continue
        txt = p.read_text("utf-8-sig")
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
    explicit = _explicit(only)
    for aid, p in _scope(only, exclude):
        if aid in PROTECTED and aid not in explicit:
            print(f"  skip    {aid:<11} (primary agent — protected; "
                  f"--only {aid} to override)")
            continue
        if not p.exists() or p.is_symlink():
            continue
        txt = p.read_text("utf-8-sig")
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
