# cc-switch-enhanced · `ccse`

一键给一批 coding agent 切换配置里的大模型名。专为「已用聚合 API（NewAPI / omniroute / 百炼 Coding Plan 等），换了订阅导致模型名变了，要逐个 agent 改回来」的场景。`cc-switch` GUI 适配的 agent 太少，本工具把适配面铺开。

只切**模型名字符串**，不碰 base_url / api_key（那是聚合端点层面的事，名字变了就够用）。任何一次写入**自动快照**，`ccse undo` 一键撤回。

## TL;DR

```
ccse --model "glm-5.2"            # 一行切全部 agent 的主模型名为 glm-5.2
ccse --model "glm-5.2" --dry     # 只预览，不写盘
ccse --model "X" --only claude,codex      # 只切某些
ccse --model "X" --exclude pi,openclaw    # 跳过某些
ccse undo                        # 撤回最近一次 apply
ccse undo 20260812-132700        # 撤回指定快照
ccse show                        # 看每个 agent 当前模型名（★=主槽位）
ccse list                        # 列已识别 adapter
```

`--model NAME` 只动每个 adapter 声明的**主槽位**（`show` 里带 ★ 的那一行）；profile 模式（下)可以指定任意多槽位。

## 装哪

```
uv tool install .        # 或 pipx install .
```

## profile — 多槽位配方

`~/.ccse/profiles.toml`，每个 section 一个一键配方：

```toml
[bailian-coding]
"claude.model"    = "qwen3.6-plus"
"claude.haiku"    = "qwen3.6-plus"
"claude.sonnet"  = "qwen3.6-plus"
"claude.opus"    = "qwen3.6-plus"
"codex.model"    = "qwen3.6-plus"
"pi.model"       = "qwen3.6-plus"
"opencode.model" = "qwen3.6-plus"
"openclaw.primary" = "qwen3.6-plus"
```

```bash
ccse genprofile --name snapshot    # 抓当前状态存成 profile
ccse diff <profile>                # 预览
ccse apply <profile>               # 写进所有 agent
ccse profiles                      # 列已有 profile
```

- `agent.slot = "name"`：`agent` 选 adapter，`slot` 选该 adapter 内字段。
- profile 里省略的槽位**不动** → 可只切部分 agent。

## adapter 对照（17 个）

结构化配置文件：

| adapter | 配置文件 | 格式 | `--model` 改的字段 |
|---|---|---|---|
| `claude` | `~/.claude/settings.json` | JSON | `env.ANTHROPIC_MODEL`（自动带 `[1M]` 后缀） |
| `codex` | `~/.codex/config.toml` | TOML | 顶层 `model` |
| `opencode` | `~/.config/opencode/opencode.json` | JSON | 顶层 `model` |
| `gemini` | `~/.gemini/.env` | env | `GEMINI_MODEL` |
| `qwen` | `~/.qwen/settings.json` | JSON | `model.name` |
| `cline` | `~/.cline/data/settings/providers.json` | JSON | `providers[lastUsed].settings.model` |
| `codebuddy` | `~/.codebuddy/settings.json` | JSON | `model` |
| `pi` | `~/.pi/agent/settings.json` | JSON | `llm.model` (+`defaultModel` 等可手配) |
| `openclaw` | `~/.openclaw/openclaw.json` | JSON | `agents.defaults.model.primary` |
| `kilocode` | `~/.kilocode/cli/config.json` | JSON | `providers[newapi].apiModelId` |
| `reasonix` | `~/.reasonix/config.toml` | TOML | `default_model` 对应 `[[providers]]` 的 `model` |
| `grok` | `~/.grok/config.toml` | TOML | `[models].default` |
| `forge` | `~/.forge/.forge.toml` | TOML | `[session].model_id` |
| `hermes` | `~/.hermes/config.yaml` | YAML | `model.default` |
| `snow` | `~/.snow/config.json` | JSON | `snowcfg.advancedModel` (+`basicModel` 可手配) |

env / shell-rc（模型名在 `~/.zshrc` 的 `export` 行）：

| adapter | 环境变量 | 说明 |
|---|---|---|
| `kimi` | `KIMI_MODEL_NAME` | Kimi Code 模型名走 env provider `__kimi_env__` |
| `copaw` | `COPAW_MODEL_NAME` | CoPAW 走 NewAPI fallback 的稳定引用 |

envrc 适配器只改它声明的那个 `export VAR=...` 行（单引号转义，`glm-5.2[1M]` 这类含特殊字符的名字也安全），rc 文件里其它内容一字不动；snapshot/undo 同样覆盖 `~/.zshrc`。

### `[1M]` 后缀

Claude Code 的模型名带聚合端特有的上下文窗口标记（`glm-5.2[1M]`、`qwen3.8-max[1M]`），其它 agent 不需要。`ccse --model "glm-5.2"` 对 claude 会自动补 `[1M]`（`glm-5.2[1M]`）；你显式写 `glm-5.2[1M]` 不会再叠加。手写 profile 的 `claude.model` 请带 `[1M]`。

字段路径里支持 JSON-path 选择器：
- `providers[id=newapi].model` — 按 `id` 找列表项
- `providers[newapi].apiModelId` — shorthand，匹配 `id`/`provider`/`name`/`key`/`envKey`
- `providers.openai-codex-cli.settings.model` — 含点/破折号的 dict key 直接写

详见 `show` 的输出。

## 撤回机制

每次 `apply` / `--model`（非 dry）**写前自动快照**到 `~/.ccse/snapshots/<时间戳>/`：

```
ccse snapshots         # 列所有快照
ccse undo              # 恢复最新快照
ccse undo <stamp>      # 恢复指定快照
ccse history           # 看 apply 历史
```

恢复前会把当前文件先备份成 `*.ccse.pre-restore.<stamp>`，不会二次丢数据。

### 自定义 agent

写个适配器只需声明字段路径：

```python
from ccse.jsonpath import make_adapter
from pathlib import Path
make_adapter(
    "myagent", "MyAgent",
    Path.home() / ".myagent" / "config.json",
    {"model": "providers[default].model"},   # 第一个键 = 主槽位
)
```

TOML/YAML/env 带注释保持的用 `ccse.toml` / `ruamel.yaml` 走手写 adapter（见 `extra.py`）。

## 安全

- 写前自动快照（`--no-backup` 可关，不建议）。
- 原子写：临时文件 + `os.replace`，parse 失败→中止，不改原文件。
- 只动「模型名」字串，base_url / api_key / 其它配置一律不碰。
- `--dry` / `diff` 预览不落盘。

## 原则

pipx/uv 装一个 CLI，stdlib(`argparse`/`tomllib`/`json`)为主；第三方只 `tomlkit`（TOML 写保注释）、`ruamel.yaml`（YAML 写保格式）。不写 GUI，不引框架，能少一行少一行。

## ROADMAP

- [x] 17 adapter（claude/codex/opencode/gemini/qwen/cline + codebuddy/pi/openclaw/kilocode/reasonix/grok/forge/hermes/snow + kimi/copaw envrc）
- [x] `--model NAME` 全量一键 + `--only`/`--exclude` + 保前缀 + claude 自动 `[1M]`
- [x] `apply`/`diff` 双模式 + profile 多槽位
- [x] `genprofile` 快照成 profile
- [x] `undo` / `history` / `snapshots` 撤回链
- [ ] continue / crush best-effort（模型在 SQLite，脆弱）
- [ ] trae / roo / copilot 探测（大概率无明文 → 不支持）
- [ ] `ccse current` 反查当前命中的 profile
- [ ] profile 校验：roundtrip 自检