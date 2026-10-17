/**
 * ccse Landing Page — Reactive & Cyber-Motion Engine (React Bits Inspired)
 * Zero external dependencies: Native Canvas WebGL/2D Aurora, Spotlight Cards,
 * Interactive Terminal Playground, and 53 Adapters Matrix.
 */

(function () {
  "use strict";

  // Check prefers-reduced-motion
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ==========================================================================
     1. Aurora & Nebula Particle Background (React Bits Inspired)
     ========================================================================== */
  const canvas = document.getElementById("aurora-canvas");
  if (canvas && !reduceMotion) {
    const ctx = canvas.getContext("2d");
    let width = 0, height = 0;
    let mouse = { x: -1000, y: -1000, targetX: -1000, targetY: -1000 };
    let animationFrameId;

    const resize = () => {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };
    window.addEventListener("resize", resize, { passive: true });
    resize();

    window.addEventListener("pointermove", (e) => {
      mouse.targetX = e.clientX;
      mouse.targetY = e.clientY;
    }, { passive: true });

    // Floating Aurora Nodes
    const nodes = [
      { x: 0.2, y: 0.25, r: 420, color: "rgba(0, 242, 254, 0.08)", vx: 0.0003, vy: 0.0002 },
      { x: 0.8, y: 0.35, r: 480, color: "rgba(139, 92, 246, 0.08)", vx: -0.0002, vy: 0.0003 },
      { x: 0.5, y: 0.7,  r: 400, color: "rgba(59, 130, 246, 0.06)", vx: 0.0002, vy: -0.0002 },
      { x: 0.15, y: 0.8, r: 350, color: "rgba(168, 85, 247, 0.05)", vx: -0.0001, vy: 0.0002 }
    ];

    // Constellation Particles
    const PARTICLE_COUNT = Math.min(Math.floor(window.innerWidth / 24), 50);
    const particles = Array.from({ length: PARTICLE_COUNT }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      size: Math.random() * 1.5 + 0.5,
      alpha: Math.random() * 0.4 + 0.1,
      speedX: (Math.random() - 0.5) * 0.25,
      speedY: (Math.random() - 0.5) * 0.25
    }));

    let t = 0;
    const render = () => {
      t += 0.01;
      ctx.clearRect(0, 0, width, height);

      // Smooth mouse lag
      mouse.x += (mouse.targetX - mouse.x) * 0.05;
      mouse.y += (mouse.targetY - mouse.y) * 0.05;

      // Draw Aurora gradient blobs
      nodes.forEach((n, idx) => {
        n.x += Math.sin(t * 0.5 + idx) * n.vx * 3;
        n.y += Math.cos(t * 0.5 + idx) * n.vy * 3;

        const posX = n.x * width;
        const posY = n.y * height;

        const grad = ctx.createRadialGradient(posX, posY, 0, posX, posY, n.r);
        grad.addColorStop(0, n.color);
        grad.addColorStop(1, "transparent");

        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(posX, posY, n.r, 0, Math.PI * 2);
        ctx.fill();
      });

      // Mouse reactive spotlight halo in background
      if (mouse.x > 0 && mouse.y > 0) {
        const mouseGrad = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, 350);
        mouseGrad.addColorStop(0, "rgba(0, 242, 254, 0.06)");
        mouseGrad.addColorStop(0.5, "rgba(139, 92, 246, 0.02)");
        mouseGrad.addColorStop(1, "transparent");
        ctx.fillStyle = mouseGrad;
        ctx.beginPath();
        ctx.arc(mouse.x, mouse.y, 350, 0, Math.PI * 2);
        ctx.fill();
      }

      // Draw faint constellation particles
      ctx.fillStyle = "rgba(255, 255, 255, 0.25)";
      particles.forEach((p) => {
        p.x += p.speedX;
        p.y += p.speedY;
        if (p.x < 0) p.x = width;
        if (p.x > width) p.x = 0;
        if (p.y < 0) p.y = height;
        if (p.y > height) p.y = 0;

        ctx.globalAlpha = p.alpha;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.globalAlpha = 1;

      animationFrameId = requestAnimationFrame(render);
    };

    // Auto pause when off screen
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) cancelAnimationFrame(animationFrameId);
      else animationFrameId = requestAnimationFrame(render);
    });

    render();
  }

  /* ==========================================================================
     2. Spotlight Card Mouse Coordinates (React Bits Spotlight Effect)
     ========================================================================== */
  const initSpotlight = () => {
    const cards = document.querySelectorAll(".spotlight-card, .terminal-box, .bento-item");
    cards.forEach((card) => {
      card.addEventListener("pointermove", (e) => {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        card.style.setProperty("--mouse-x", `${x}px`);
        card.style.setProperty("--mouse-y", `${y}px`);
      });
    });
  };
  initSpotlight();

  /* ==========================================================================
     3. Interactive CLI Playground (Interactive Terminal Simulator)
     ========================================================================== */
  const terminalDemos = {
    model: {
      cmd: 'ccse --model "claude-sonnet-5-5"',
      desc: "一行切换全 agent 主模型，自动为 Claude 追加 [1M]，subagent 槽位智能跟随",
      output: `[claude] Claude Code
  env.CLAUDE_CODE_SUBAGENT_MODEL: 'glm-5.3-flash[1M]' -> 'claude-sonnet-5-5[1M]'
[opencode] OpenCode
  model: 'newapi/gemini-3.8-flash' -> 'newapi/claude-sonnet-5-5'
  agent.build.model: 'newapi/gemini-3.8-flash' -> 'newapi/claude-sonnet-5-5'
  agent.explore.model: 'newapi/gemini-3.8-flash' -> 'newapi/claude-sonnet-5-5'
  agent.general.model: 'newapi/gemini-3.8-flash' -> 'newapi/claude-sonnet-5-5'
  agent.plan.model: 'newapi/gemini-3.8-flash' -> 'newapi/claude-sonnet-5-5'
[openclaw] OpenClaw
  agents.defaults.model.primary: 'dmx/gemini-3.8-flash' -> 'dmx/claude-sonnet-5-5'
  agents.defaults.subagents.model: 'newapi/gemini-3.8-flash' -> 'newapi/claude-sonnet-5-5'

<span class="t-success">applied: 95 field(s) changed across 53 agents.</span>
<span class="t-cyan">snapshot saved: 20261017-094120 (undo: ccse undo 20261017-094120)</span>`
    },
    endpoint: {
      cmd: 'ccse --base-url "https://api.openai-proxy.com/v1" --api-key "sk-live-09f87a..."',
      desc: "同时更新全 agent 端点与密钥；env 型变量自动写入 ~/.zshrc，Windows 走 setx",
      output: `[codex] Codex
  providers.custom.base_url: 'http://127.0.0.1:6333/v1' -> 'https://api.openai-proxy.com/v1'
  providers.custom.api_key: 'sk-old***' -> 'sk-liv***'
[gemini] Gemini CLI
  GEMINI_BASE_URL: 'http://127.0.0.1:6333/v1' -> 'https://api.openai-proxy.com/v1'
  GEMINI_API_KEY: 'sk-old***' -> 'sk-liv***'
[claude] Claude Code
  env.ANTHROPIC_BASE_URL: 'http://127.0.0.1:6333' -> 'https://api.openai-proxy.com/v1'
  env.ANTHROPIC_AUTH_TOKEN: 'sk-old***' -> 'sk-liv***'

<span class="t-success">applied: base_url & key updated for all configured agents.</span>
<span class="t-dim">~/.zshrc updated with new export lines.</span>`
    },
    verify: {
      cmd: "ccse verify",
      desc: "探测所有已配置 agent：检查 API Key 权限与目标模型是否存在于 /v1/models",
      output: `  <span class="t-success">✓</span> codex        <span class="t-success">PASS</span>  endpoint ok, 284 models listed, 'claude-sonnet-5-5' present
  <span class="t-success">✓</span> gemini       <span class="t-success">PASS</span>  native v1beta generateContent ok
  <span class="t-success">✓</span> opencode     <span class="t-success">PASS</span>  endpoint ok, target model verified
  <span class="t-warn">!</span> droid        <span class="t-warn">WARN</span>  endpoint ok, but model 'custom:glm' NOT in /models (284 listed)
  <span class="t-error">✘</span> mu           <span class="t-error">FAIL</span>  HTTP 401 — api_key rejected by upstream gateway
  <span class="t-dim">·</span> cline        <span class="t-dim">SKIP</span>  no base_url slot configured
  <span class="t-dim">·</span> dsh          <span class="t-dim">SKIP</span>  agent not installed on this system

<span class="t-cyan">verify summary: 36 pass, 1 warn, 1 fail, 15 skip (53 total adapters)</span>`
    },
    rules: {
      cmd: "ccse rules --apply",
      desc: "把 caveman (超浓缩极简输出) + rtk (命令行代理节能) 幂等注入到所有 agent 的 AGENTS.md / CLAUDE.md",
      output: `snippet: built-in caveman+rtk (markers: &lt;!-- ccse:caveman-rtk:START --&gt;)
  <span class="t-success">append</span>  claude      /home/tony/.claude/CLAUDE.md
  <span class="t-success">update</span>  zcode       /home/tony/.zcode/AGENTS.md
  <span class="t-success">create</span>  opencode    /home/tony/.config/opencode/AGENTS.md
  <span class="t-success">append</span>  codex       /home/tony/.codex/AGENTS.md
  <span class="t-success">create</span>  mu          /home/tony/.mu/AGENTS.md

<span class="t-success">rules applied: 25 instruction files updated with idempotent blocks.</span>
<span class="t-dim">(to clean up anytime: ccse rules --rm)</span>`
    },
    undo: {
      cmd: "ccse undo",
      desc: "写前自动备份！一键安全回滚最近一次 apply 改动，同时自动创建 pre-restore 保护副本",
      output: `restored 6 file(s) from snapshot <span class="t-cyan">20261017-094120</span>:
  ~/.claude/settings.json
  ~/.config/opencode/opencode.json
  ~/.codex/config.toml
  ~/.openclaw/openclaw.json
  ~/.prime/agent/settings.json
  ~/.zshrc

<span class="t-success">undo success: all files restored to pre-apply state.</span>
<span class="t-dim">(pre-restore backup saved to *.ccse.pre-restore.20261017-094120)</span>`
    }
  };

  const termCmdElem = document.getElementById("terminal-cmd");
  const termDescElem = document.getElementById("terminal-desc");
  const termBodyElem = document.getElementById("terminal-body");
  const termTabs = document.querySelectorAll(".term-tab");
  let typeTimer = null;

  const playDemo = (key) => {
    const data = terminalDemos[key];
    if (!data) return;

    if (typeTimer) clearInterval(typeTimer);

    // Update Tab state
    termTabs.forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.demo === key);
    });

    if (termDescElem) termDescElem.textContent = data.desc;

    // Simulate Typing
    if (termCmdElem && termBodyElem) {
      termCmdElem.textContent = "";
      termBodyElem.innerHTML = `<span class="t-dim">Executing command...</span>`;

      let i = 0;
      const cmdText = data.cmd;
      const speed = 25;

      typeTimer = setInterval(() => {
        if (i < cmdText.length) {
          termCmdElem.textContent += cmdText.charAt(i);
          i++;
        } else {
          clearInterval(typeTimer);
          typeTimer = null;
          setTimeout(() => {
            termBodyElem.innerHTML = data.output;
          }, 150);
        }
      }, speed);
    }
  };

  termTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      playDemo(tab.dataset.demo);
    });
  });

  // Start with model demo
  playDemo("model");

  /* ==========================================================================
     4. 53 Adapters Catalog & Live Interactive Filter
     ========================================================================== */
  const ADAPTERS_DATA = [
    { id: "claude", name: "Claude Code", cat: "cli", type: "JSON+Env", path: "~/.claude/settings.json", note: "主模型/各梯队/subagent/1M标记" },
    { id: "codex", name: "Codex", cat: "cli", type: "TOML", path: "~/.codex/config.toml", note: "顶层 model + providers 目录" },
    { id: "opencode", name: "OpenCode", cat: "cli", type: "JSON", path: "~/.config/opencode/opencode.json", note: "主模型 + 4个 agent 槽位同步" },
    { id: "gemini", name: "Gemini CLI", cat: "cli", type: "Dotenv", path: "~/.gemini/.env", note: "原生 v1beta 探活 + GEMINI_MODEL" },
    { id: "qwen", name: "Qwen Code", cat: "cli", type: "JSON", path: "~/.qwen/settings.json", note: "model.name + 端点重设" },
    { id: "prime", name: "Prime", cat: "cli", type: "JSON", path: "~/.prime/agent/settings.json", note: "settings + models.json 级联" },
    { id: "mu", name: "Mu", cat: "cli", type: "JSON", path: "~/.mu/agent/settings.json", note: "快照关联 models.json" },
    { id: "trae", name: "Trae CLI", cat: "cli", type: "YAML", path: "~/.trae/trae_cli.yaml", note: "models[] 目录自动追加与选择" },
    { id: "devin", name: "Devin CLI", cat: "cli", type: "Env", path: "DEVIN_MODEL (setx / rc)", note: "纯环境变量驱动切换" },
    { id: "openclaw", name: "OpenClaw", cat: "cli", type: "JSON", path: "~/.openclaw/openclaw.json", note: "primary + subagents 双槽跟随" },
    { id: "aider", name: "Aider", cat: "cli", type: "YAML", path: "~/.aider.conf.yml", note: "裸名自动补 openai/ 前缀" },
    { id: "cline", name: "Cline", cat: "ide", type: "JSON", path: "~/.cline/.../providers.json", note: "VS Code 流行自主编程插件" },
    { id: "kilocode", name: "KiloCode", cat: "ide", type: "JSON", path: "~/.kilocode/cli/config.json", note: "VS Code / IDE 插件配置" },
    { id: "nvim", name: "Neovim Minuet", cat: "ide", type: "Env", path: "NEWAPI_MODEL / rc", note: "Neovim AI 补全插件" },
    { id: "codebuddy", name: "CodeBuddy", cat: "ide", type: "JSON", path: "~/.codebuddy/settings.json", note: "IDE 编码辅助扩展" },
    { id: "crush", name: "Crush", cat: "cli", type: "JSON", path: "~/.config/crush/crush.json", note: "models.large + providers 镜像同步" },
    { id: "ante", name: "Ante", cat: "cli", type: "JSON", path: "~/.ante/settings.json", note: "model/provider + 兼容端点" },
    { id: "qoder", name: "Qoder CLI", cat: "cli", type: "JSON", path: "~/.qoder/settings.json", note: "customModels 组合键 + $VAR 保值" },
    { id: "qodercn", name: "Qoder CLI (CN)", cat: "cli", type: "JSON", path: "~/.qoder-cn/settings.json", note: "国内版多模型路由" },
    { id: "atomcode", name: "AtomCode", cat: "cli", type: "TOML", path: "~/.atomcode/config.toml", note: "models 组合键复用克隆" },
    { id: "amp", name: "Amp CLI", cat: "cli", type: "Env", path: "AMP_URL / AMP_API_KEY", note: "云端路由探针 SKIP 处理" },
    { id: "muse", name: "Muse", cat: "cli", type: "JSON", path: "~/.config/muse/settings.json", note: "平铺键模型设置" },
    { id: "agy", name: "Antigravity CLI", cat: "cli", type: "JSON", path: "~/.gemini/antigravity-cli/...", note: "modelProvider / baseURL" },
    { id: "swival", name: "Swival", cat: "cli", type: "TOML", path: "~/.config/swival/config.toml", note: "config.toml 平铺键支持" },
    { id: "droid", name: "Droid / Factory", cat: "cli", type: "JSON", path: "~/.factory/settings.json", note: "customModels 组合 ID" },
    { id: "snow", name: "Snow", cat: "cli", type: "JSON", path: "~/.snow/config.json", note: "basicModel 智能跟随" },
    { id: "commandcode", name: "Command Code", cat: "cli", type: "JSON", path: "~/.commandcode/settings.json", note: "feature.* 槽位智能跟随" },
    { id: "kilo", name: "Kilo", cat: "cli", type: "JSON", path: "~/.config/kilo/kilo.json", note: "本地配置直接重写" },
    { id: "jcode", name: "JCode", cat: "cli", type: "TOML", path: "~/.jcode/config.toml", note: "providers 列表更新" },
    { id: "dsh", name: "DSH", cat: "cli", type: "YAML", path: "~/.dsh/settings.yaml", note: "命令行开发工具" },
    { id: "openclaude", name: "OpenClaude", cat: "cli", type: "JSON", path: "~/.openclaude/settings.json", note: "开源 Claude 兼容运行时" },
    { id: "openhands", name: "OpenHands", cat: "cli", type: "JSON", path: "~/.openhands/agent_settings.json", note: "自主软件工程代理" },
    { id: "mcode", name: "MCode", cat: "cli", type: "YAML", path: "~/.minimax/config.yaml", note: "MiniMax 编码客户端" },
    { id: "mimo", name: "Mimo", cat: "cli", type: "JSONC", path: "~/.config/mimocode/mimocode.jsonc", note: "带注释 JSON 格式安全写入" },
    { id: "mmx", name: "MMX", cat: "cli", type: "JSON", path: "~/.mmx/config.json", note: "MiniMax 极速 CLI" },
    { id: "pigo", name: "Pigo", cat: "cli", type: "TOML", path: "~/.config/pigo/config.toml", note: "轻量 Rust 终端代理" },
    { id: "penguin", name: "Penguin", cat: "cli", type: "TOML", path: "~/.penguin/.../config.toml", note: "多项目分层配置" },
    { id: "pi", name: "Pi", cat: "cli", type: "JSON", path: "~/.pi/agent/settings.json", note: "defaultModel 跟随机制" },
    { id: "reasonix", name: "Reasonix", cat: "cli", type: "TOML", path: "~/.reasonix/config.toml", note: "深度推理代理" },
    { id: "grok", name: "Grok CLI", cat: "cli", type: "TOML", path: "~/.grok/config.toml", note: "xAI Grok 兼容适配" },
    { id: "forge", name: "Forge", cat: "cli", type: "TOML", path: "~/.forge/.forge.toml", note: "TOML + 凭证分离" },
    { id: "step", name: "Step Code", cat: "cli", type: "JSON", path: "~/.stepcode/agent/settings.json", note: "阶跃星辰终端插件" },
    { id: "arkcli", name: "Ark CLI", cat: "cli", type: "YAML", path: "~/.arkcli/config.yaml", note: "火山引擎方舟客户端" },
    { id: "hermes", name: "Hermes", cat: "cli", type: "YAML", path: "~/.hermes/config.yaml", note: "自主工作流 Agent" },
    { id: "omp", name: "OMP", cat: "cli", type: "YAML", path: "~/.omp/agent/config.yml", note: "双文件级联同步" },
    { id: "memmy", name: "Memmy", cat: "cli", type: "YAML", path: "~/.memmy/config.yaml", note: "记忆代理配置" },
    { id: "openakita", name: "OpenAkita", cat: "cli", type: "JSON", path: "~/.openakita/.../llm_endpoints.json", note: "多端点管理" },
    { id: "kimi", name: "Kimi Code", cat: "cli", type: "Env", path: "KIMI_MODEL_NAME", note: "Moonshot Kimi CLI" },
    { id: "copaw", name: "CoPAW", cat: "cli", type: "Env", path: "COPAW_MODEL_NAME", note: "多智能体协同环境" },
    { id: "fx", name: "fx", cat: "cli", type: "Env", path: "FX_MODEL", note: "命令行 JSON 处理增强" },
    { id: "nmragent", name: "NMRagent", cat: "srv", type: "Dotenv", path: "backend/.env", note: "脉冲程序科研后端模型代理" },
    { id: "graphpulse", name: "GraphPulse", cat: "srv", type: "Dotenv", path: ".env.local", note: "前端 Vite 代理与图谱引擎" },
    { id: "zcode", name: "ZCode", cat: "rules", type: "Markdown", path: "~/.zcode/AGENTS.md", note: "全局行为规范与指令切入点" }
  ];

  const gridContainer = document.getElementById("adapters-grid");
  const searchInput = document.getElementById("adapter-search");
  const filterBtns = document.querySelectorAll(".af-btn");
  const countBadge = document.getElementById("adapter-count-badge");

  let currentCategory = "all";
  let searchKeyword = "";

  const renderAdapters = () => {
    if (!gridContainer) return;

    const filtered = ADAPTERS_DATA.filter((item) => {
      const matchCat = currentCategory === "all" || item.cat === currentCategory;
      const q = searchKeyword.toLowerCase().trim();
      const matchSearch =
        !q ||
        item.id.toLowerCase().includes(q) ||
        item.name.toLowerCase().includes(q) ||
        item.type.toLowerCase().includes(q) ||
        item.note.toLowerCase().includes(q);
      return matchCat && matchSearch;
    });

    if (countBadge) {
      countBadge.textContent = `${filtered.length} / ${ADAPTERS_DATA.length}`;
    }

    if (filtered.length === 0) {
      gridContainer.innerHTML = `
        <div class="adapters-empty">
          <p>未找到匹配 "${searchKeyword}" 的适配器</p>
          <button class="pill pill--line" id="btn-reset-filter">重置搜索</button>
        </div>
      `;
      document.getElementById("btn-reset-filter")?.addEventListener("click", () => {
        if (searchInput) searchInput.value = "";
        searchKeyword = "";
        currentCategory = "all";
        filterBtns.forEach((b) => b.classList.toggle("active", b.dataset.cat === "all"));
        renderAdapters();
      });
      return;
    }

    gridContainer.innerHTML = filtered
      .map(
        (item) => `
        <div class="adapter-card spotlight-card" data-cat="${item.cat}">
          <div class="ac-header">
            <span class="ac-id">${item.id}</span>
            <span class="ac-badge ac-badge--${item.type.toLowerCase().split("+")[0]}">${item.type}</span>
          </div>
          <div class="ac-name">${item.name}</div>
          <div class="ac-path" title="${item.path}">${item.path}</div>
          <div class="ac-note">${item.note}</div>
        </div>
      `
      )
      .join("");

    // Re-bind mouse spotlight coordinate tracker on newly rendered cards
    initSpotlight();
  };

  // Search input event
  searchInput?.addEventListener("input", (e) => {
    searchKeyword = e.target.value;
    renderAdapters();
  });

  // Category filter tabs
  filterBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      filterBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentCategory = btn.dataset.cat;
      renderAdapters();
    });
  });

  renderAdapters();

  /* ==========================================================================
     5. Number Stat Count-Up Animation
     ========================================================================== */
  const statElem = document.getElementById("stat-number");
  if (statElem) {
    const targetVal = 53;
    let counted = false;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && !counted) {
            counted = true;
            let start = null;
            const duration = 1200;
            const step = (timestamp) => {
              if (!start) start = timestamp;
              const progress = Math.min((timestamp - start) / duration, 1);
              // ease-out expo
              const eased = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
              statElem.textContent = Math.round(eased * targetVal);
              if (progress < 1) {
                requestAnimationFrame(step);
              } else {
                statElem.textContent = targetVal;
              }
            };
            requestAnimationFrame(step);
          }
        });
      },
      { threshold: 0.2 }
    );
    observer.observe(statElem);
  }

  /* ==========================================================================
     6. Clipboard Copy & Toast Feedback
     ========================================================================== */
  const toast = document.getElementById("global-toast");
  let toastTimer = null;

  const showToast = (msg) => {
    if (!toast) return;
    toast.textContent = msg || "已成功复制到剪贴板";
    toast.classList.add("visible");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.remove("visible");
    }, 2200);
  };

  document.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const text = btn.dataset.copy;
      if (!text) return;
      navigator.clipboard.writeText(text).then(() => {
        const originalText = btn.innerHTML;
        btn.dataset.copied = "true";
        showToast(`✓ 已复制: ${text.slice(0, 36)}${text.length > 36 ? "..." : ""}`);
        setTimeout(() => {
          delete btn.dataset.copied;
        }, 2000);
      });
    });
  });
})();
