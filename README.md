# cc-switch-enhanced · `ccse`

一键给一批 coding agent 切换配置里的**模型名 / base_url / api_key**。专为「已用聚合 API（NewAPI / omniroute / 百炼 Coding Plan 等），换了订阅导致模型名、端点或 key 变了，要逐个 agent 改回来」的场景。`cc-switch` GUI 适配的 agent 太少，本工具把适配面铺开。

任何一次写入**自动快照**，`ccse undo` 一键撤回；`ccse verify` 换完后实测每个 agent 的端点，确认没改坏。

## TL;DR

```
ccse --model "glm-5.2"                  # 一行切全部 agent 的主模型名为 glm-5.2
ccse --base-url "http://10.0.0.5/v1"    # 一行切全部 agent 的 base_url
ccse --api-key "sk-xxx"                 # 一行切全部 agent 的 api_key（env 型写入 ~/.zshrc）
ccse --model "glm-5.2" --base-url U --api-key K   # 三个一起切
ccse --model "glm-5.2" --dry           # 只预览，不写盘
ccse --model "X" --only claude,codex   # 只切某些
ccse --model "X" --exclude pi,openclaw # 跳过某些
ccse verify                            # 换完验证：探测每个 agent 的端点+模型
ccse undo                              # 撤回最近一次 apply
ccse undo 20260812-132700              # 撤回指定快照
ccse show                              # 看每个 agent 当前 model/base_url/api_key（★=主槽位）
ccse list                              # 列已识别 adapter
ccse rewrite ./myproj --model glm-5.2 --base-url U --api-key K   # 扫描项目改 LLM 配置
ccse rewrite ./myproj --model glm-5.2 --dry   # 只预览不写盘
```

`--model NAME` 只动每个 adapter 声明的**主槽位**（`show` 里带 ★ 的那一行）；`--base-url` / `--api-key` 动所有 `base_url` / `api_key` 槽位（`show` 里 kind 标识的）。profile 模式（下)可以指定任意多槽位。

## 装哪

```
uv tool install .        # 或 pipx install .
```

## 跨平台

启动时自动检测操作系统（`ccse list` 首行会显示 `os=...`）：

- **linux / macOS**（都是 unix/zsh，默认 shell 是 zsh）：env 型变量写入 `~/.zshrc` 的 `export VAR=...` 行；agent 配置路径一律 `~/<点目录>/...`，`Path.home()` 各系统通用。
- **Windows**（默认 PowerShell，无 shell rc）：env 型变量用 `setx` 持久化到用户环境变量（新开 shell 生效），不再碰 `.zshrc`；快照/undo 对 Windows 自动跳过 rc 文件。

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

## adapter 对照（18 个）

结构化配置文件（`--model` 改的字段 + `--base-url`/`--api-key` 改的字段）：

| adapter | 配置文件 | 格式 | `--model` 字段 | base_url | api_key |
|---|---|---|---|---|---|
| `claude` | `~/.claude/settings.json` | JSON | `env.ANTHROPIC_MODEL`（自动 `[1M]`） | `env.ANTHROPIC_BASE_URL` | `env.ANTHROPIC_AUTH_TOKEN` |
| `codex` | `~/.codex/config.toml` | TOML | 顶层 `model` | 活动 provider `base_url` | `env_key` → 写入 `~/.zshrc` |
| `opencode` | `~/.config/opencode/opencode.json` | JSON | 顶层 `model` | `provider.<active>.options.baseURL` | `provider.<active>.options.apiKey` |
| `gemini` | `~/.gemini/.env` | env | `GEMINI_MODEL` | `GOOGLE_GEMINI_BASE_URL` | `GEMINI_API_KEY` |
| `qwen` | `~/.qwen/settings.json` | JSON | `model.name` | `model.baseUrl` | `env.<provider envKey>` |
| `cline` | `~/.cline/data/settings/providers.json` | JSON | `providers[lastUsed].settings.model` | — | — |
| `codebuddy` | `~/.codebuddy/settings.json` | JSON | `model` | — | — |
| `pi` | `~/.pi/agent/settings.json` | JSON | `llm.model` (+`defaultModel` 等) | `llm.baseUrl` | `llm.apiKey` |
| `openclaw` | `~/.openclaw/openclaw.json` | JSON | `agents.defaults.model.primary` | `models.providers.<active>.baseUrl` | `models.providers.<active>.apiKey` |
| `kilocode` | `~/.kilocode/cli/config.json` | JSON | `providers[newapi].apiModelId` | `providers[newapi].openAiBaseUrl` | `providers[newapi].openAiApiKey` |
| `reasonix` | `~/.reasonix/config.toml` | TOML | 活动 `[[providers]]` 的 `model` | 活动 provider `base_url` | `api_key_env` → 写入 `~/.zshrc` |
| `grok` | `~/.grok/config.toml` | TOML | `[models].default` | `[model."<def>"].base_url` | `env_key` → 写入 `~/.zshrc` |
| `forge` | `~/.forge/.forge.toml` | TOML | `[session].model_id` | — | — |
| `crush` | `~/.config/crush/crush.json` + `~/.local/share/crush/providers.json` | JSON | 已配置 provider 的 `default_large_model_id` | `providers.<id>.base_url` | `providers.<id>.api_key` |
| `droid` | `~/.factory/settings.json` | JSON | `sessionDefaultSettings.model`（**模型 id**，非裸模型名） | 活动 `customModels[].baseUrl` | 活动 `customModels[].apiKey` |
| `hermes` | `~/.hermes/config.yaml` | YAML | `model.default` | `model.base_url` | `model.api_key` |
| `snow` | `~/.snow/config.json` | JSON | `snowcfg.advancedModel` (+`basicModel`) | `snowcfg.baseUrl` | `snowcfg.apiKey` |
| `memmy` | `~/.memmy/config.yaml` | YAML | `agents.defaults.model` | 活动 provider `apiBase` | `apiKey` 的 `${ENV_VAR}` → 写入 shell rc / setx |

env / shell-rc（模型名在 `~/.zshrc` 的 `export` 行）：

| adapter | 环境变量 | 说明 |
|---|---|---|
| `kimi` | `KIMI_MODEL_NAME` / `KIMI_MODEL_API_KEY` | Kimi Code 模型名走 env provider `__kimi_env__` |
| `copaw` | `COPAW_MODEL_NAME` / `COPAW_MODEL_API_KEY` | CoPAW 走 NewAPI fallback 的稳定引用 |

envrc 适配器只改它声明的那一行 `export VAR=...`（单引号转义，`glm-5.2[1M]` 这类含特殊字符的名字也安全），rc 文件里其它内容一字不动；snapshot/undo 同样覆盖 `~/.zshrc`。

**api_key 的红点**：codex/grok/reasonix/memmy 不把 key 存明文配置，而是声明 `env_key`（或 `${ENV_VAR}`）环境变量名。`ccse --api-key K` 对它们：先把 key 字面量**写入 `~/.zshrc`**（`export NEWAPI_API_KEY='...'`，Windows 下用 `setx` 写用户环境；都可被 undo 撤），再让配置继续指向该变量。`show`/`verify` 会解析这个环境变量名取当前 key。其余 agent 的 api_key 是明文配置字段，直接写文件。

**crush / droid 的坑**：
- crush 的模型名在 `providers.json`（模型目录），凭据在 `crush.json`（`providers.<id>.base_url/api_key`）。`--model` 改的是**你在 `crush.json` 里配置的那个 provider** 的 `default_large_model_id`；`show` 会标出是哪个 provider。
- droid 的模型槽是 `sessionDefaultSettings.model`，值是**组合 id**（如 `custom:GLM-4.7-[GLM-Coding-Plan-China]-0`），不是裸模型名。`ccse --model <那个 id>` 才能命中；base_url/api_key 写在匹配的 `customModels[]` 条目上。`show` 里一眼可见。

### `[1M]` 后缀

Claude Code 的模型名带聚合端特有的上下文窗口标记（`glm-5.2[1M]`、`qwen3.8-max[1M]`），其它 agent 不需要。`ccse --model "glm-5.2"` 对 claude 会自动补 `[1M]`（`glm-5.2[1M]`）；你显式写 `glm-5.2[1M]` 不会再叠加。手写 profile 的 `claude.model` 请带 `[1M]`。

字段路径里支持 JSON-path 选择器：
- `providers[id=newapi].model` — 按 `id` 找列表项
- `providers[newapi].apiModelId` — shorthand，匹配 `id`/`provider`/`name`/`key`/`envKey`
- `providers.openai-codex-cli.settings.model` — 含点/破折号的 dict key 直接写

详见 `show` 的输出。

## verify — 换完确认没改坏

`ccse verify` 对每个已装 adapter 做一次轻量探测，返回 `PASS / WARN / FAIL / SKIP`，退出码 `1` 当有 FAIL。

- **OpenAI 兼容端点**（大多数）：`GET {base_url}/models`，验证 api_key 有效 + 配置的模型在列表里。模型名会自动剥路由前缀（`newapi/X`）和 claude 的 `[1M]` 再比对。
- **Anthropic 端点**（claude）：`POST {base}/v1/messages`（1 token）。旧 API 或 OAuth token 会报 FAIL —— 那是真的用不了。
- **Gemini 原生端点**（gemini）：`POST {base}/v1beta/models/{model}:generateContent`。本地 OpenAI 兼容端点会 404 → FAIL，符合「不能用」。
- **无端点的 env 型**（cline/codebuddy/forge/kimi/copaw）：SKIP。

```
ccse verify --only claude,codex      # 只验证某些
ccse verify --timeout 3              # 收紧超时（默认 8s）
```

## rewrite — 项目内一键切 LLM 配置（与 agent 适配无关）

`ccse rewrite <dir>` 递归扫描目录下 `.py/.ts/.js/.mjs/.cjs/.mts/.cts` 和 `.env*`，
把 LLM 配置（base_url / api_key / model）替换成新值。适合你的脚本用环境变量或 `.env` 读
LLM 凭据的场景——换一个聚合端，整个项目的端点一次切完。

```
ccse rewrite . --model deepseek-v4-flash --base-url http://b/v1 --api-key sk-x
ccse rewrite ./worker --model glm-5.2 --dry      # 先预览
```

替换规则（保守，只碰 LLM 特征行）：
- **.env\***：键名含 `BASE_URL` / `API_KEY` / `MODEL` 特征的行，直接换值（保留注释）。
- **脚本**：`os.getenv("OPENAI_MODEL", "gpt-4o")` / `process.env.OPENAI_MODEL ?? "gpt-4o"`
  这类**带默认值的 env 读取**，替换默认值；行首的 `api_key = "sk-..."` / `baseUrl: "..."`
  字面量也替换。`os.environ["KEY"]`（无默认值）不动——值在 `.env`，那边已换。
- 自动跳过 `.git` / `node_modules` / `.venv` / `dist` / `build` 等目录；普通
  `model = keras.Model()` 这类非 LLM 代码不碰（`model` 字面量赋值只走 `.env`/env 默认值路径）。

`--dry` 预览；无快照（改的是项目文件，靠 git 管）。三个字段任意组合，至少给一个。

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

- 写前自动快照（`--no-backup` 可关，不建议）；api_key 写 `~/.zshrc` 时同样纳入快照。
- 原子写：临时文件 + `os.replace`，parse 失败→中止，不改原文件。
- 只动声明过的槽位（model / base_url / api_key），其它配置一律不碰。
- `--dry` / `diff` 预览不落盘；`show`/`verify` 对 api_key 只显示前 6 位脱敏。
- **api_key 走命令行会在 shell history 留痕**。批量换 key 建议用 profile：`~/.ccse/profiles.toml` 里写 `"codex.api_key" = "sk-..."` 再 `ccse apply <profile>`，key 不进 history。

## 原则

pipx/uv 装一个 CLI，stdlib(`argparse`/`tomllib`/`json`/`urllib`)为主；第三方只 `tomlkit`（TOML 写保注释）、`ruamel.yaml`（YAML 写保格式）。不写 GUI，不引框架，能少一行少一行。

## ROADMAP

- [x] 18 adapter（claude/codex/opencode/gemini/qwen/cline + codebuddy/pi/openclaw/kilocode/reasonix/grok/forge/hermes/snow/crush/droid/memmy + kimi/copaw envrc）
- [x] `--model NAME` 全量一键 + `--only`/`--exclude` + 保前缀 + claude 自动 `[1M]`
- [x] `--base-url` / `--api-key` 全量一键（含 env 型写入 ~/.zshrc、env_key 解析）
- [x] `apply`/`diff` 双模式 + profile 多槽位
- [x] `genprofile` 快照成 profile
- [x] `undo` / `history` / `snapshots` 撤回链
- [x] `verify`：换完探测每个 agent 端点+模型（OpenAI/Anthropic/Gemini 三种协议）
- [ ] continue / crush best-effort（模型在 SQLite，脆弱）
- [ ] trae / roo / copilot 探测（大概率无明文 → 不支持）
- [ ] `ccse current` 反查当前命中的 profile
- [ ] profile 校验：roundtrip 自检