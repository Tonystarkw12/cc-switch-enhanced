<div align="center">

# `ccse` · cc-switch-enhanced

**一行命令，给 26 个 AI 编程助手同时换模型 / 中转地址 / key**

专为「已用聚合 API（NewAPI / omniroute / 百炼 Coding Plan / 各种镜像站），换了订阅导致模型名、端点或 key 变了，要逐个 agent 改回来」的场景。`cc-switch` GUI 适配面太窄，本工具把适配铺开，并补上 subagent 跟随、端点探测、行为注入。

[![license](https://img.shields.io/badge/license-MIT-blue)](#)
[![python](https://img.shields.io/badge/python-%E2%89%A53.11-green)](#)
[![platform](https://img.shields.io/badge/platform-linux%20%7C%20macOS%20%7C%20win-lightgrey)](#)
[![deps](https://img.shields.io/badge/deps-stdlib%20first%20%2B%202-success)](#)
[![agents](https://img.shields.io/badge/adapters-26-orange)](#)

</div>

---

| | | |
|:--:|:--:|:--:|
| 🔄 **一键切模型** | 🧬 **subagent 跟随** | 🛡️ **自动快照 / undo** |
| 📋 **profile 配方** | ✅ **verify 端点探测** | 📝 **rules 行为注入** |

## 目录

- [TL;DR](#tldr)
- [安装](#安装)
- [`ccse rules` —— 行为注入（caveman + rtk）](#ccse-rules--行为注入caveman--rtk)
- [profile —— 多槽位配方](#profile--多槽位配方)
- [adapter 覆盖（26 个）](#adapter-覆盖26-个)
- [verify —— 换完确认没改坏](#verify--换完确认没改坏)
- [rewrite —— 项目内一键切 LLM 配置](#rewrite--项目内一键切-llm-配置)
- [撤回机制](#撤回机制)
- [自定义 agent](#自定义-agent)
- [安全](#安全)
- [原则 / ROADMAP](#原则--roadmap)

## TL;DR

```bash
ccse --model "glm-5.2"                  # 一行切全部 agent 的主模型名（+ subagent）
ccse --base-url "http://10.0.0.5/v1"    # 一行切全部 base_url
ccse --api-key "sk-xxx"                 # 一行切全部 api_key（env 型写入 ~/.zshrc）
ccse --model "glm-5.2" --base-url U --api-key K   # 三个一起切
ccse --model "glm-5.2" --dry            # 只预览，不写盘
ccse --model "X" --only claude,codex    # 只切某些
ccse --model "X" --exclude pi,openclaw  # 跳过某些
ccse show                               # 看每个 agent 当前值（★=主槽位）
ccse verify                             # 换完验证：探测每个端点+模型
ccse undo                               # 撤回最近一次 apply
ccse rules --apply                      # 给全部 agent 注入 caveman+rtk 行为
ccse list                               # 列全部 adapter（含未安装）
```

**`--model` 现在连 subagent 一起换**：opencode 的 `agent.{build,explore,general,plan}`、openclaw 的 subagent、snow 的 basicModel、claude 的 `CLAUDE_CODE_SUBAGENT_MODEL` 都跟着主模型走，各槽保留自己的路由前缀（`newapi/...`、`dmx/...`）。Claude 的 haiku/sonnet/opus 三档默认不动——想统一再单独切。

## 安装

```bash
git clone https://github.com/Tonystarkw12/cc-switch-enhanced
cd cc-switch-enhanced
uv tool install .        # 或 pipx install . ；升级加 --force
```

最新版本见 [Releases](https://github.com/Tonystarkw12/cc-switch-enhanced/releases)（v0.3.0+ 含 Windows BOM/坏配置加固）。

**跨平台**（`ccse list` 首行显示当前 OS）：
- **linux / macOS**（zsh）：env 型变量写 `~/.zshrc` 的 `export VAR=...` 行；配置路径 `~/<点目录>/...`，`Path.home()` 通用。
- **Windows**（PowerShell）：env 型变量用 `setx` 持久化到用户环境（新开 shell 生效），不碰 `.zshrc`。

## `ccse rules` —— 行为注入（caveman + rtk）

模型 / base_url / key 是 ccse 的**结构化切换面**；输出风格和命令输出路由是**行为**，只有 agent 启动时读进去才生效。`ccse rules` 把一段行为 snippet（内置 caveman full + rtk 路由）注入到每个 agent 的**全局指令文件**（`AGENTS.md` / `CLAUDE.md` / `GEMINI.md` / openakita 的 `AGENT.md`），让一行命令把全 fleet 的行为统一切掉——和 `--model` 切模型一个套路。

```bash
ccse rules                          # 看每个 agent 注入状态
ccse rules --apply                  # 注入内置 caveman+rtk（默认全部 agent）
ccse rules --apply --only codex,opencode --dry
ccse rules --apply --snippet ~/.myrules.md    # 用自定义 snippet
ccse rules --rm                     # 移除注入的标记块（还原原文件其余内容）
```

- **幂等**：用 `<!-- ccse:caveman-rtk:START/END -->` 标记块包裹，重跑只更新不重复；`--rm` 干净移除，原文件其余内容不动。
- **覆盖 22 个**（含 claude → `CLAUDE.md`、gemini → `GEMINI.md`、openakita → `identity/AGENT.md`）；kimi/copaw 纯 env 无指令面，排除。
- ⚠️ **rtk 是指令依赖**：要 agent 真去调 `rtk read/git/...` 而非裸命令。CLI 类、指令跟随好的基本照做；跟随差或不读全局 AGENTS.md 的 agent 无效。caveman 是纯输出风格，跟随率最高。

## profile —— 多槽位配方

换一组中转经常是好几个 agent + 好几个字段一起变。存成 profile，以后一条命令切回：

```toml
# ~/.ccse/profiles.toml
[bailian-coding]
"claude.model"     = "qwen3.6-plus"
"claude.haiku"     = "qwen3.6-plus"
"codex.model"      = "qwen3.6-plus"
"openclaw.primary" = "qwen3.6-plus"
```

```bash
ccse apply bailian-coding     # 一键切
ccse diff bailian-coding      # 预览差异
ccse genprofile --name snap   # 把当前状态抓成 profile
ccse profiles                 # 列已有 profile
```

- `agent.slot = "name"`：`agent` 选 adapter，`slot` 选该 adapter 内字段。
- profile 里省略的槽位**不动** → 可只切部分 agent。

## adapter 覆盖（26 个）

**结构化配置**（`--model` 改主槽位 + subagent；`--base-url`/`--api-key` 改对应字段）：

| adapter | 配置文件 | 格式 | `--model` 字段 | base_url | api_key |
|---|---|---|---|---|---|
| `claude` | `~/.claude/settings.json` | JSON | `env.ANTHROPIC_MODEL`（自动 `[1M]`）+ `CLAUDE_CODE_SUBAGENT_MODEL` | `env.ANTHROPIC_BASE_URL` | `env.ANTHROPIC_AUTH_TOKEN` |
| `codex` | `~/.codex/config.toml` | TOML | 顶层 `model` | 活动 provider `base_url` | `env_key` → ~/.zshrc，或字面 `api_key` |
| `opencode` | `~/.config/opencode/opencode.json` | JSON | `model` + `agent.{build,explore,general,plan}.model`（同步 `provider.<active>.models` 目录） | `provider.<active>.options.baseURL` | `provider.<active>.options.apiKey` |
| `gemini` | `~/.gemini/.env` | env | `GEMINI_MODEL` | `GOOGLE_GEMINI_BASE_URL` | `GEMINI_API_KEY` |
| `qwen` | `~/.qwen/settings.json` | JSON | `model.name` | `model.baseUrl` | `env.<provider envKey>` |
| `cline` | `~/.cline/data/settings/providers.json` | JSON | `providers[lastUsed].settings.model` | — | — |
| `codebuddy` | `~/.codebuddy/settings.json` | JSON | `model`（保 `custom-local:` 前缀 + 同步 `models.json` 目录） | — | — |
| `pi` | `~/.pi/agent/settings.json` | JSON | `llm.model`（+`defaultModel`） | `llm.baseUrl` | `llm.apiKey` |
| `openclaw` | `~/.openclaw/openclaw.json` | JSON | `agents.defaults.model.primary`（+subagent） | `models.providers.<active>.baseUrl` | `models.providers.<active>.apiKey` |
| `kilocode` | `~/.kilocode/cli/config.json` | JSON | `providers[newapi].apiModelId` | `providers[newapi].openAiBaseUrl` | `providers[newapi].openAiApiKey` |
| `kilo` | `~/.config/kilo/kilo.json` | JSON | `model` + `subagent_model`/`small_model` + `agent.<*>.model`（保 `provider/` 前缀 + 注册表） | `provider.<active>.options.baseURL` | `provider.<active>.options.apiKey` |
| `snow` | `~/.snow/config.json` | JSON | `snowcfg.advancedModel`（+`basicModel`） | `snowcfg.baseUrl` | `snowcfg.apiKey` |
| `mmx` | `~/.mmx/config.json` | JSON | `default_text_model` | `base_url`（写入自动剥尾部 `/v1`；聊天走 anthropic 格式 `/v1/messages`） | `api_key` |
| `aider` | `~/.aider.conf.yml` | YAML | `model`（裸名自动补 `openai/` 前缀） | `openai-api-base`（自动补 `/v1`） | `api-key`（`openai=<key>`） |
| `pigo` | `~/.config/pigo/config.toml` | TOML | `model` | `base_url`（自动补 `/v1` + 确保 `protocol="openai"`） | `api_key`（字面 key） |
| `penguin` | `~/.penguin/data/default_project/.project_config.toml` | TOML | `default_model`（`provider/model_id`；裸名复用已有条目或落 `newapi` 组 + 自动建 `[[models]]` 条目） | 活动 `models[].base_url` | 活动 `models[].api_key`（字面 key） |
| `reasonix` | `~/.reasonix/config.toml` | TOML | 活动 `[[providers]]` 的 `model` | 活动 provider `base_url` | `api_key_env` → ~/.zshrc |
| `grok` | `~/.grok/config.toml` | TOML | `[models].default`（同步 `[model."<def>"]` 表） | `[model."<def>"].base_url` | `env_key` → ~/.zshrc |
| `forge` | `~/.forge/.forge.toml` | TOML | `[session].model_id`（自动 `merge_system_messages=true`） | — | — |
| `crush` | `~/.config/crush/crush.json` + `~/.local/share/crush/providers.json` | JSON | 已配置 provider 的 `default_large_model_id`（同步 `models[]` 目录） | `providers.<id>.base_url` | `providers.<id>.api_key` |
| `droid` | `~/.factory/settings.json` | JSON | `sessionDefaultSettings.model`（裸名自动解析/新建 `customModels[]` 条目 → `custom:<name>-N` id） | 活动 `customModels[].baseUrl` | 活动 `customModels[].apiKey` |
| `hermes` | `~/.hermes/config.yaml` | YAML | `model.default` | `model.base_url` | `model.api_key` |
| `omp` | `~/.omp/agent/config.yml` | YAML | `llm.model` + `defaultModel` + `modelRoles.default`（保 `provider/` 前缀和 `:level`） | `llm.baseUrl` | `llm.apiKey` 的 `${ENV_VAR}` → ~/.zshrc / setx |
| `memmy` | `~/.memmy/config.yaml` | YAML | `agents.defaults.model` | 活动 provider `apiBase` | `apiKey` 的 `${ENV_VAR}` → ~/.zshrc / setx |
| `prime` | `~/.prime/agent/settings.json` + `models.json` | JSON | `defaultModel`（自动修复悬空 `defaultProvider` + 同步 provider 目录） | `providers.<active>.baseUrl` | `providers.<active>.apiKey`（**字面 key**，自动内联裸变量名） |
| `openakita` | `~/.openakita/data/llm_endpoints.json` | JSON | `endpoints[0].model`（priority:1 优先） | `endpoints[0].base_url` | key 在 ~/.env（`api_key_env` 指向） |
| `jcode` | `~/.jcode/config.toml` | TOML | `[provider].default_model`（+镜像 provider 块 + `[[...models]]` 注册表） | `providers.<active>.base_url` | `api_key_env` → ~/.zshrc |
| `openclaude` | `~/.openclaude/settings.json` | JSON | `env.ANTHROPIC_MODEL` | `env.ANTHROPIC_BASE_URL` | `env.ANTHROPIC_AUTH_TOKEN` |
| `openhands` | `~/.openhands/agent_settings.json` | JSON | `llm.model`（litellm slug，如 `openai/...`） | `llm.base_url` | `llm.api_key` |
| `commandcode` | `~/.commandcode/settings.json` | JSON | `model`（+`featureModels.*` 跟随；云目录 id 或 BYO id） | —（云端 auth / BYO 未实例化） | — |
| `mmx` | `~/.mmx/config.json` | JSON | `default_text_model` | `base_url`（网关根，写时剥 `/v1`） | `api_key` |
| `pigo` | `~/.config/pigo/config.toml` | TOML | `model` | `base_url`（同时保证 `protocol = "openai"`） | `api_key` |
| `penguin` | `~/.penguin/data/default_project/.project_config.toml` | TOML | `default_model.model_id`（+`[[models]]` 注册表条目同步） | `models[...].base_url` | `models[...].api_key` |
| `aider` | `~/.aider.conf.yml` | YAML | `model`（裸名自动补 `openai/` 前缀走网关） | `openai-api-base` | `api-key`（`provider=key`） |

**env / shell-rc**（模型名在 `~/.zshrc` 的 `export` 行）：

| adapter | 环境变量 | 说明 |
|---|---|---|
| `kimi` | `KIMI_MODEL_NAME` / `KIMI_MODEL_API_KEY` | Kimi Code 模型名走 env provider `__kimi_env__` |
| `copaw` | `COPAW_MODEL_NAME` / `COPAW_MODEL_API_KEY` | CoPAW 走 NewAPI fallback 的稳定引用 |
| `nvim` | `NEWAPI_MODEL` / `NEWAPI_BASE_URL` / `NEWAPI_API_KEY` | Neovim minuet.nvim 经 env 读配置 |
| `nvim` | `NEWAPI_MODEL` / `NEWAPI_BASE_URL` / `NEWAPI_API_KEY` | minuet.nvim 读 env 变量（见 minuet.lua）；base_url 带/不带 `/v1` 均可（minuet 自行 strip 再拼） |

envrc 适配器只改它声明的那一行 `export VAR=...`（单引号转义，`glm-5.2[1M]` 这类含特殊字符的名字也安全），rc 文件里其它内容一字不动；snapshot/undo 同样覆盖 `~/.zshrc`。

> **api_key 的两种形态**：codex/grok/reasonix/jcode/memmy 不存明文 key，而是声明 `env_key`（或 `${ENV_VAR}`）环境变量名。`ccse --api-key K` 对它们：先把 key 字面量**写入 `~/.zshrc`**（Windows 用 `setx`；可 undo），再让配置继续指向该变量。codex 例外——它也能存字面 `api_key`，ccse 自动识别两种模式；切到非 OpenAI 官方域名时 ccse 自动把 `requires_openai_auth` 置 `false`（否则 codex 强制 OAuth、无视 key，直接不可用）。其余 agent 的 api_key 是明文配置字段，直接写文件。`show`/`verify` 对 api_key 只显示前 6 位脱敏。

> **`[1M]` 后缀**：Claude Code 模型名带聚合端上下文窗口标记（`glm-5.2[1M]`），其它 agent 不需要。`ccse --model "glm-5.2"` 对 claude 自动补 `[1M]`；显式写 `glm-5.2[1M]` 不会叠加。

> **crush / droid 的坑**：crush 模型名在 `providers.json`（模型目录），凭据在 `crush.json`，`--model` 改的是你配置的那个 provider 的 `default_large_model_id`。droid 的模型槽是**组合 id**（如 `custom:GLM-4.7-[GLM-Coding-Plan-China]-0`），`ccse --model <那个 id>` 才命中。

字段路径支持 JSON-path 选择器：`providers[id=newapi].model`、`providers[newapi].apiModelId`（shorthand 匹配 id/provider/name/key）、`providers.openai-codex-cli.settings.model`。

## verify —— 换完确认没改坏

`ccse verify` 对每个已装 adapter 做一次轻量探测，返回 `PASS / WARN / FAIL / SKIP`，有 FAIL 退出码 `1`，方便接脚本。

- **OpenAI 兼容端点**（大多数）：`GET {base_url}/models`，验证 key 有效 + 模型在列表里。模型名自动剥路由前缀（`newapi/X`）和 claude `[1M]` 再比对。
- **Anthropic 端点**（claude）：`POST {base}/v1/messages`（1 token）。
- **Gemini 原生端点**（gemini）：`POST {base}/v1beta/models/{model}:generateContent`。本地 OpenAI 兼容端会 404 → FAIL。
- **无端点的 env 型**（cline/codebuddy/forge/kimi/copaw）：SKIP。

```bash
ccse verify --only claude,codex      # 只验证某些
ccse verify --timeout 3              # 收紧超时（默认 8s）
```

## rewrite —— 项目内一键切 LLM 配置

`ccse rewrite <dir>` 递归扫描 `.py/.ts/.js/.mjs/.cjs/.mts/.cts` 和 `.env*`，把 LLM 配置（base_url / api_key / model）替换成新值。适合脚本用环境变量或 `.env` 读凭据的场景——换一个聚合端，整个项目一次切完。与 agent 适配无关。

```bash
ccse rewrite . --model deepseek-v4-flash --base-url http://b/v1 --api-key sk-x
ccse rewrite ./worker --model glm-5.2 --dry      # 先预览
```

替换规则（保守，只碰 LLM 特征行）：`.env*` 里键名含 `BASE_URL`/`API_KEY`/`MODEL` 的行换值；脚本里 `os.getenv("OPENAI_MODEL", "gpt-4o")` / `process.env.OPENAI_MODEL ?? "gpt-4o"` 这类**带默认值的 env 读取**替换默认值，行首 `api_key = "sk-..."` 字面量也替换；`os.environ["KEY"]`（无默认值）不动。自动跳过 `.git`/`node_modules`/`.venv`/`dist`/`build`；`model = keras.Model()` 这类非 LLM 代码不碰。`--dry` 预览；无快照（靠 git 管）。

## 撤回机制

每次 `apply` / `--model`（非 dry）**写前自动快照**到 `~/.ccse/snapshots/<时间戳>/`：

```bash
ccse snapshots          # 列所有快照
ccse undo               # 恢复最新快照
ccse undo 20260812-132700   # 恢复指定快照
ccse history            # 看 apply 历史
```

恢复前会把当前文件先备份成 `*.ccse.pre-restore.<stamp>`，不会二次丢数据。

## 自定义 agent

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

- 写前自动快照（`--no-backup` 可关，不建议）；api_key 写 `~/.zshrc` 时同样纳入快照。
- 原子写：临时文件 + `os.replace`，parse 失败→中止，不改原文件。
- **坏配置不炸批**：某 agent 配置带 BOM/损坏解析失败时，跳过该 agent 并告警一行，不影响其余切换（Windows BOM 已能直接解析）。
- 只动声明过的槽位（model / base_url / api_key），其它配置一律不碰。
- `--dry` / `diff` 预览不落盘；`show`/`verify` 对 api_key 只显示前 6 位脱敏。
- ⚠️ **api_key 走命令行会在 shell history 留痕**。批量换 key 建议用 profile：`~/.ccse/profiles.toml` 里写 `"codex.api_key" = "sk-..."` 再 `ccse apply <profile>`，key 不进 history。

## 原则 / ROADMAP

pipx/uv 装一个 CLI，stdlib（`argparse`/`tomllib`/`json`/`urllib`）为主；第三方只 `tomlkit`（TOML 写保注释）、`ruamel.yaml`（YAML 写保格式）。不写 GUI，不引框架，能少一行少一行。

**ROADMAP**

- [x] 31 adapter（claude/codex/opencode/gemini/qwen/cline + codebuddy/pi/openclaw/kilocode/reasonix/grok/forge/hermes/snow/crush/droid/memmy/prime/omp/openakita/jcode + openhands/commandcode/mmx/aider/pigo/penguin + kimi/copaw/nvim envrc）
- [x] `--model NAME` 全量一键 + **subagent 跟随** + `--only`/`--exclude` + 保前缀 + claude 自动 `[1M]`
- [x] `--base-url` / `--api-key` 全量一键（env 型写 ~/.zshrc、env_key 解析、codex 字面 api_key）
- [x] `apply`/`diff` 双模式 + profile 多槽位 + `genprofile` 快照成 profile
- [x] `undo` / `history` / `snapshots` 撤回链
- [x] `verify`：换完探测每个端点+模型（OpenAI/Anthropic/Gemini 三协议）
- [x] `rewrite`：项目内 LLM 配置一键切
- [x] `rules`：行为 snippet（caveman + rtk）注入 / 移除
- [ ] continue / crush best-effort（模型在 SQLite，脆弱）
- [ ] trae / roo / copilot 探测（大概率无明文 → 不支持）
- [ ] `ccse current` 反查当前命中的 profile
- [ ] profile 校验：roundtrip 自检

---

<div align="center">

**[GitHub](https://github.com/Tonystarkw12/cc-switch-enhanced)** · 觉得有用给个 ⭐ · issue / PR 欢迎

</div>
