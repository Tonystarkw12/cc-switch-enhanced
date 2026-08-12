---
name: ccse
description: >
  Switch the model-name string across many coding agents (Claude Code, Codex, Gemini, Qwen,
  Cline, Grok, OpenCode, Pi, etc.) with one command. Use when the user wants to change the
  active model in coding-agent configs — phrases like "switch model", "change model name",
  "把模型改成 X", "切模型", "model changed / 名字变了要逐个改", "newapi 模型名变了",
  "ccse", or when editing model fields by hand across ~/.claude, ~/.codex, ~/.grok, ~/.qwen,
  ~/.gemini, ~/.zshrc (KIMI_MODEL_NAME/COPAW_MODEL_NAME). Prefers ccse over manual edits
  because it snapshots, writes atomically, and preserves route prefixes + context suffixes.
---

# ccse — one-line model switch across coding agents

`ccse` (cc-switch-enhanced) rewrites the **model-name string** in 17 coding-agent configs at
once. It touches *only* model names — never `base_url` / `api_key` / other fields. Every write
is snapshotted first and is atomic, so it is safer than hand-editing JSON/TOML/YAML/env files.

**Prefer `ccse` over manual `Edit` when** the task is changing model names in agent configs.
Hand-editing risks: wrong field, lost route prefix, broken JSON, no backup. `ccse` knows each
adapter's exact slot path and keeps prefixes/suffixes correct.

## Golden rule: preview before writing

Always dry-run first. Never apply blind.

```bash
ccse diff --model "glm-5.2"        # preview the exact diffs (writes nothing)
ccse --model "glm-5.2" --dry       # same, top-level form
ccse show                          # see current state first (★ = primary slot)
```

## Core commands

```bash
ccse show                          # current model per agent/slot (★ = the one --model sets)
ccse list                          # known adapters + whether file exists
ccse --model "glm-5.2"             # switch every agent's PRIMARY slot (★) to glm-5.2
ccse --model "glm-5.2" --dry       # preview only
ccse --model "X" --only claude,codex,grok      # restrict to these adapters
ccse --model "X" --exclude pi,copaw            # skip these
ccse undo                          # revert the most recent apply
ccse undo 20260812-132700          # revert a specific snapshot
ccse snapshots                     # list saved snapshots
ccse history                       # apply history
```

`ccse --model NAME` is shorthand for `ccse apply --model NAME`. It hits **only the primary
slot** (the ★ row in `show`) of each adapter, not every slot. To change multiple slots per
agent (e.g. Claude's haiku/sonnet/opus separately), use a **profile**.

## Prefix & suffix conventions — read before you pick a NAME

`ccse show` prints names like `newapi/gpt-5.6-sol`, `krill/gpt-5.6-terra`, `glm-5.2[1M]`.

- **Route prefix** (`newapi/`, `krill/`, `dmx/`, …): tells the agent which upstream to use.
  - A **bare** NAME (`glm-5.2`) **keeps** each adapter's existing prefix automatically. This is
    what you almost always want.
  - A NAME **containing `/`** (`newapi/glm-5.2`) is written **verbatim**, overriding the prefix.
  - `--no-keep-prefix` writes the name verbatim and **drops** the prefix — use only on purpose.
- **Context suffix** (`[1M]`): encodes the context-window size. Bare names preserve the suffix
  the adapter already had; pass it explicitly (`glm-5.2[1M]`) to set it. Don't strip it unless
  asked — it carries the 1M-context intent.

When the user says "change model to X" with no prefix, pass the **bare** name and let ccse keep
each adapter's prefix. Only inject a prefix if the user explicitly names a different upstream.

## Profiles — multi-slot recipes

For anything beyond "one model for every primary slot", use profiles in `~/.ccse/profiles.toml`:

```toml
[bailian-coding]
"claude.model"   = "qwen3.6-plus"
"claude.sonnet"  = "qwen3.8-max"     # different model per tier
"claude.opus"    = "qwen3.6-plus"
"codex.model"    = "qwen3.6-plus"
"grok.model"     = "qwen3.6-plus"
```

- Format: `"adapter.slot" = "model-name"`. `adapter` selects the config, `slot` selects the
  field inside it (see `ccse show` for exact slot names). Slots omitted from the profile are
  **not touched**.
- `ccse profiles` — list saved profiles
- `ccse diff <profile>` — preview
- `ccse apply <profile>` — write into all listed agents
- `ccse genprofile --name snapshot` — capture the *current* state as a reusable profile

This is how to express "Claude sonnet → qwen3.8-max, everything else → glm-5.2" cleanly.

## Safety model

- Every apply / `--model` (non-dry) **snapshots to `~/.ccse/snapshots/<stamp>/` before writing**.
  `--no-backup` skips this — do not use it unless the user insists.
- Restore re-backs the current file to `*.ccse.pre-restore.<stamp>` first, so undo never loses
  data a second time.
- Atomic writes (temp file + `os.replace`); a parse failure aborts without touching the original.

If a user says "I changed a model and something broke", reach for `ccse undo` (or
`ccse snapshots` → `ccse undo <stamp>`) before manual repair.

## Supported adapters (16)

| adapter | config file | `--model` sets |
|---|---|---|
| `claude` | `~/.claude/settings.json` | `env.ANTHROPIC_MODEL` |
| `codex` | `~/.codex/config.toml` | top-level `model` |
| `opencode` | `~/.config/opencode/opencode.json` | top-level `model` |
| `gemini` | `~/.gemini/.env` | `GEMINI_MODEL` |
| `qwen` | `~/.qwen/settings.json` | `model.name` |
| `cline` | `~/.cline/data/settings/providers.json` | `providers[lastUsed].settings.model` |
| `codebuddy` | `~/.codebuddy/settings.json` | `model` |
| `pi` | `~/.pi/agent/settings.json` | `llm.model` |
| `openclaw` | `~/.openclaw/openclaw.json` | `agents.defaults.model.primary` |
| `kilocode` | `~/.kilocode/cli/config.json` | `providers[newapi].apiModelId` |
| `reasonix` | `~/.reasonix/config.toml` | matched `[[providers]].model` |
| `grok` | `~/.grok/config.toml` | `[models].default` |
| `forge` | `~/.forge/.forge.toml` | `[session].model_id` |
| `hermes` | `~/.hermes/config.yaml` | `model.default` |
| `kimi` | `~/.zshrc` | `KIMI_MODEL_NAME` |
| `copaw` | `~/.zshrc` | `COPAW_MODEL_NAME` |

`ccse list` shows which adapter files are present on this machine; `ccse show` prints the live
value of every slot. Run `ccse show` before deciding what to switch.

## Workflows

**"Switch everything to one model"**
```bash
ccse show                              # confirm what's primary now
ccse --model "glm-5.2" --dry           # preview
ccse --model "glm-5.2"                 # apply
```

**"Switch only a few agents"**
```bash
ccse --model "glm-5.2" --only claude,grok,codex --dry
ccse --model "glm-5.2" --only claude,grok,codex
```

**"Different model per slot" (e.g. Claude sonnet differs from the rest)**
```bash
# write ~/.ccse/profiles.toml, then:
ccse diff myprofile
ccse apply myprofile
```

**"Revert a bad switch"**
```bash
ccse snapshots        # find the stamp
ccse undo             # or: ccse undo <stamp>
```

## Notes

- Requires `ccse` on PATH (installed via `uv tool install .` / `pipx install .` from the repo).
  If `command -v ccse` fails, the CLI isn't installed — tell the user rather than hand-editing.
- env-rc adapters (`kimi`, `copaw`) edit a single `export VAR=...` line in `~/.zshrc`; names with
  special chars (`glm-5.2[1M]`) are single-quote-escaped safely. Other rc content is untouched.
- JSON-path selectors supported in profiles: `providers[id=newapi].model`,
  `providers[newapi].apiModelId` (shorthand matching id/provider/name/key/envKey),
  `providers.openai-codex-cli.settings.model` (dotted/dashed keys verbatim).
