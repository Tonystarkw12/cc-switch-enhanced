# [自荐][开源推广] ccse —— 给 26 个 AI 编程助手同时换模型 / 中转 / key 的命令行小工具

## 开源推广声明

本帖使用社区开源推广，符合推广要求。我申明并遵循社区要求的以下内容：

- 我的帖子已经打上「开源推广」标签：**是**
- 我的开源项目完整开源，无未开源部分：**是**
- 我的开源项目已链接认可 LINUX DO 社区：**是**
- 我帖子内的项目介绍，AI 生成、润色内容部分已截图发出：**是**
- 以上选择我承诺是永久有效的，接受社区和佬友监督：**是**

---

> 说明：下面正文中，**我自己写的技术部分**（命令、表格、配置、安装步骤、个人吐槽）照常发文字；**AI 辅助润色的简介 / 卖点段落用截图发出**，位置已标出。

## 先吐个槽

各位用聚合中转的（NewAPI、omniroute、百炼 Coding Plan、各种镜像站），下面这场景应该熟：

订阅到期换了一家，模型名变了，中转地址和 key 也全换了。然后你打开 `~/.claude`、`~/.codex`、`~/.config/opencode`、`~/.qwen`、`~/.grok`……十几个配置文件一个一个手改。改完还提心吊胆，怕漏了哪个、怕写错。

`cc-switch` 那个 GUI 是好用，但它适配的 agent 太少，新出的那一堆 CLI 它根本不认。

所以我造了个轮子：**`ccse`（cc-switch-enhanced）**，纯命令行。具体是什么、强在哪，我让 AI 帮忙润色了一段，按社区要求截图发出

---

> **【AI 辅助润色的项目介绍 · 截图发出】**
>
> ![ccse 项目介绍首屏](https://201014.xyz/linuxdo/ccse-hero.png)
>
> 上图：项目 README 首屏，含项目定位与核心卖点简介（AI 辅助润色，按社区要求以截图形式发出）。

---

## 命令演示

```bash
# 全部 agent 的主模型名一次切成 glm-5.2（subagent 也跟着切）
ccse --model "glm-5.2"

# 三个一起切（模型 + 中转 + key）
ccse --model "glm-5.2" --base-url "http://10.0.0.5/v1" --api-key "sk-xxx"

# 只切某几个 / 跳过某几个
ccse --model "glm-5.2" --only claude,codex
ccse --model "glm-5.2" --exclude pi,openclaw

# 先预览，不写盘
ccse --model "glm-5.2" --dry
```

关于 subagent 跟随（这是我比较得意的一个点，`cc-switch` 没做）：`--model` 会把 subagent 槽位也带上——opencode 的 `agent.build/explore/general/plan`、openclaw 的 subagent、snow 的 basicModel、kilo/omp 的子模型都跟着主模型走，各槽位保留自己的路由前缀（`newapi/xxx`、`dmx/xxx`）。Claude 的 haiku/sonnet/opus 三档默认不被动，想统一再单独切。

`ccse show` 看当前每个 agent 的状态（★ 是主槽位）：

```
[claude] Claude Code  (installed)
  ANTHROPIC_MODEL (main)       = gpt-5.6-sol[1M] ★
  Haiku tier                   = deepseek-v4-flash[1M]
  base_url (ANTHROPIC_BASE_URL) = http://192.168.0.14:6333
[codex] Codex  (installed)
  model                        = gpt-5.6-sol ★
  provider base_url            = https://newapi.201014.xyz/v1
  provider api_key             = sk-xkl***
[opencode] OpenCode  (installed)
  model                        = newapi/deepseek-v4-flash ★
  agent.build.model            = newapi/gpt-5.6-sol
  agent.plan.model             = newapi/gpt-5.6-sol
[openakita] OpenAkita  (installed)
  endpoints[0].model           = deepseek-v4-flash ★
  endpoints[0].base_url        = http://192.168.0.14:6333/v1
...（共 25 个）
```

切完跑 `ccse verify`，对每个端点发一次轻量探测，返回 `PASS / WARN / FAIL / SKIP`：模型名不在列表里、key 失效、端点 404 全会暴露。有 FAIL 退出码非 0，方便接脚本。

## 覆盖的 agent（26 个）

| 结构化配置（23） | env / shell-rc（3） |
|---|---|
| claude · codex · opencode · gemini · qwen · cline · codebuddy · pi · prime · openclaw · kilocode · kilo · snow · reasonix · grok · forge · crush · droid · hermes · omp · memmy · openakita · jcode | kimi · copaw · nvim |

每个 adapter 只动它声明的 `model / base_url / api_key` 字段，**其它配置一字不碰**。像 Claude 那种模型名要带 `[1M]` 后缀的，`ccse --model glm-5.2` 会自动补成 `glm-5.2[1M]`，你不用记。

<details>
<summary>点开看完整 README 截图（含 25 adapter 字段表 + 全部功能说明）</summary>

![ccse README 全文](https://201014.xyz/linuxdo/ccse-readme-full.png)

</details>

## `ccse rules` —— 顺手还能切"行为"

模型 / base_url / key 是「结构化切换面」；输出风格是「行为面」，只有 agent 启动读进去才生效。`ccse rules` 把一段行为 snippet（内置 caveman + rtk 路由）注入每个 agent 的全局指令文件（`AGENTS.md` / `CLAUDE.md` / `GEMINI.md` …），让一行命令把整个 fleet 的行为也统一切掉——跟 `--model` 切模型一个套路。

```bash
ccse rules              # 看注入状态
ccse rules --apply      # 注入内置 caveman+rtk（默认全部 agent）
ccse rules --rm         # 干净移除标记块，原文件其余内容不动
```

用 `<!-- ccse:caveman-rtk:START/END -->` 标记块包裹，幂等，重跑只更新不重复。覆盖 22 个；kimi/copaw 纯 env 无指令面，排除。

## profile —— 一键配方

换一组中转经常是好几个 agent + 好几个字段一起变。存成 profile，以后一条命令切回：

```toml
# ~/.ccse/profiles.toml
[bailian-coding]
"claude.model"    = "qwen3.6-plus"
"claude.haiku"    = "qwen3.6-plus"
"codex.model"     = "qwen3.6-plus"
"openclaw.primary" = "qwen3.6-plus"
```

```bash
ccse apply bailian-coding     # 一键切
ccse diff bailian-coding      # 预览差异
ccse genprofile --name snap   # 把当前状态抓成 profile
```

## 安全设计（这块我比较在意）

- **写前自动快照** → `~/.ccse/snapshots/<时间戳>/`，`ccse undo` 秒回滚，回滚前还会再备份一次当前文件，不会二次丢数据。
- **原子写**：临时文件 + `os.replace`，解析失败就中止，原文件不动。
- api_key 在 `show` / `verify` 里只显示前 6 位脱敏。
- **api_key 走命令行会在 shell history 留痕**。批量换 key 推荐用 profile：把 key 写进 `~/.ccse/profiles.toml` 再 `ccse apply <profile>`，不进 history。

## 额外：改项目里的 LLM 配置

`ccse rewrite <dir>` 能递归扫描一个项目里的 `.py/.ts/.js/.env`，把 base_url / api_key / model 一次换掉——适合你那些用 `os.getenv("OPENAI_BASE_URL", "...")` 读凭据的脚本。保守替换，只碰 LLM 特征行，普通 `model = keras.Model()` 这种不误伤。

```bash
ccse rewrite ./worker --model glm-5.2 --base-url http://b/v1 --api-key sk-x --dry
```

## 安装

```bash
git clone https://github.com/Tonystarkw12/cc-switch-enhanced
cd cc-switch-enhanced
uv tool install .        # 或 pipx install .
```

Linux / macOS 写 `~/.zshrc`，Windows 用 `setx` 写用户环境变量，跨平台开箱即用（`ccse list` 首行会显示当前 OS）。依赖很轻：stdlib 为主，三方只有 `tomlkit`（保注释写 TOML）和 `ruamel.yaml`（保格式写 YAML）。不写 GUI，不引框架。

## 自己加一个 agent 也很简单

声明字段路径就够了，十几行：

```python
from ccse.jsonpath import make_adapter
from pathlib import Path
make_adapter(
    "myagent", "MyAgent",
    Path.home() / ".myagent" / "config.json",
    {"model": "providers[default].model"},   # 第一个键 = 主槽位
)
```

---

**GitHub：** https://github.com/Tonystarkw12/cc-switch-enhanced

纯个人造的轮子，解决自己天天遇到的「换中转要改十几个配置」问题。觉得有用的朋友给个 star，有想加的 agent 或者 bug 直接 issue / PR 都行，适配器写起来很快。
