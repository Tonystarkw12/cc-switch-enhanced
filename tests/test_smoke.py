"""Smoke + roundtrip self-check. Run: `python -m pytest tests/` or just the file."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ccse import config
from ccse.registry import all_adapters


def test_registry_loads_all_targets():
    from ccse import claude, cline, codex, gemini, opencode, qwen, prime  # noqa: F401
    from ccse import openakita, jcode, dsh, openclaude  # noqa: F401
    from ccse import extra  # noqa: F401
    ids = {a.id for a in all_adapters()}
    for expect in ("claude", "codex", "opencode", "gemini", "qwen", "cline",
                   "codebuddy", "pi", "openclaw", "kilocode", "reasonix",
                   "grok", "forge", "hermes", "snow", "crush", "droid",
                   "memmy", "prime", "omp", "kilo", "openakita", "jcode",
                   "dsh", "openclaude"):
        assert expect in ids, f"missing adapter {expect}"


def test_ensure_openai_v1():
    assert config.ensure_openai_v1("http://host:6333") == "http://host:6333/v1"
    assert config.ensure_openai_v1("http://host:6333/") == "http://host:6333/v1"
    assert config.ensure_openai_v1("http://host:6333/v1") == "http://host:6333/v1"
    assert config.ensure_openai_v1("http://host:6333/v1/") == "http://host:6333/v1/"
    assert config.ensure_openai_v1("") == ""
    assert config.ensure_openai_v1(None) is None


def test_prime_base_url_normalized(tmp_path: Path, monkeypatch):
    """prime adapter appends /v1 to a bare gateway base_url (openai SDK
    appends /chat/completions, so a root URL returns the gateway's HTML)."""
    from ccse import prime as prime_mod
    settings = tmp_path / "settings.json"
    models = tmp_path / "models.json"
    settings.write_text(json.dumps({
        "defaultProvider": "newapi",
        "defaultModel": "deepseek-v4-pro",
        "recentModels": ["newapi/deepseek-v4-pro"],
    }))
    models.write_text(json.dumps({
        "providers": {"newapi": {
            "baseUrl": "http://host:6333",
            "api": "openai-completions",
            "apiKey": "OPENAI_API_KEY",
            "models": [{"id": "deepseek-v4-pro", "name": "Deepseek V4 Pro"}],
        }}
    }))
    monkeypatch.setattr(prime_mod, "MODELS_JSON", models, raising=False)
    monkeypatch.setattr(prime_mod.PrimeAdapter, "path", settings, raising=False)
    a = prime_mod.PrimeAdapter()
    diffs = a.apply({"prime.base_url": "http://host:6333"}, dry=False)
    assert any("baseUrl" in d and "/v1" in d for d in diffs)
    assert json.loads(models.read_text())["providers"]["newapi"]["baseUrl"] == \
        "http://host:6333/v1"


def test_pi_base_url_normalized(tmp_path: Path, monkeypatch):
    """pi adapter (make_adapter base_url_v1) appends /v1 to a bare gateway baseUrl."""
    from ccse.jsonpath import make_adapter
    from ccse.registry import REGISTRY
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({
        "llm": {"model": "deepseek-v4-pro", "baseUrl": "http://host:6333",
                "apiKey": "OPENAI_API_KEY"},
        "defaultModel": "deepseek-v4-pro",
    }))
    make_adapter(
        "pi_test", "Pi Test", settings,
        {"model": "llm.model", "defaultModel": "defaultModel"},
        endpoint_paths={"base_url": "llm.baseUrl", "api_key": "llm.apiKey"},
        follow=("defaultModel",),
        base_url_v1=True,
    )
    try:
        a = REGISTRY["pi_test"]()
        diffs = a.apply({"pi_test.base_url": "http://host:6333"}, dry=False)
        assert any("baseUrl" in d and "/v1" in d for d in diffs)
        assert json.loads(settings.read_text())["llm"]["baseUrl"] == "http://host:6333/v1"
        # already-correct /v1 is left untouched
        assert a.apply({"pi_test.base_url": "http://host:6333/v1"}, dry=False) == []
    finally:
        del REGISTRY["pi_test"]


def test_omp_base_url_normalized(tmp_path: Path, monkeypatch):
    """omp adapter appends /v1 to a bare gateway llm.baseUrl."""
    try:
        import ruamel.yaml  # noqa
    except ImportError:
        return
    from ccse import extra as extra_mod
    cfg = tmp_path / "config.yml"
    cfg.write_text(
        "llm:\n"
        "  model: deepseek-v4-pro\n"
        "  baseUrl: http://host:6333\n"
        "  apiKey: ${OPENAI_API_KEY}\n"
        "defaultModel: deepseek-v4-pro\n", "utf-8")
    extra_mod.OmpAdapter.path = cfg  # type: ignore
    a = extra_mod.OmpAdapter()
    diffs = a.apply({"omp.base_url": "http://host:6333"}, dry=False)
    assert any("baseUrl" in d and "/v1" in d for d in diffs)
    assert "baseUrl: http://host:6333/v1" in cfg.read_text("utf-8")
    extra_mod.OmpAdapter.path = config.HOME / ".omp" / "agent" / "config.yml"


def _patch_home(adapters_mods, tmp_path):
    import ccse.config as cfg
    cfg.HOME = tmp_path
    cfg.DATA_DIR = tmp_path / ".ccse"
    cfg.HISTORY_INDEX = cfg.DATA_DIR / "history.jsonl"
    cfg.SNAPSHOT_DIR = cfg.DATA_DIR / "snapshots"


def test_claude_apply_roundtrip(tmp_path: Path, monkeypatch):
    from ccse import claude as claude_mod
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({
        "env": {"ANTHROPIC_MODEL": "glm-5.2[1M]",
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": "old-haiku"},
        "other": {"keep": 1},
    }))
    monkeypatch.setattr(claude_mod, "HOME", tmp_path, raising=False)
    monkeypatch.setattr(config, "HOME", tmp_path, raising=False)
    claude_mod.ClaudeAdapter.path = settings  # type: ignore[misc]
    a = claude_mod.ClaudeAdapter()
    diffs = a.apply({"claude.model": "qwen3.6-plus", "claude.haiku": "qwen3.6-plus"},
                    dry=False)
    assert any("ANTHROPIC_MODEL" in d for d in diffs)
    after = json.loads(settings.read_text())
    assert after["env"]["ANTHROPIC_MODEL"] == "qwen3.6-plus"
    assert after["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "qwen3.6-plus"
    assert after["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME"] == "qwen3.6-plus"
    assert after["other"] == {"keep": 1}  # untouched
    # restore class path to default to avoid bleed
    claude_mod.ClaudeAdapter.path = config.HOME / ".claude" / "settings.json"


def test_qwen_apply_roundtrip(tmp_path: Path, monkeypatch):
    from ccse import qwen as qwen_mod
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"model": {"name": "old", "baseUrl": "u"},
                               "$version": 4}))
    qwen_mod.QwenAdapter.path = cfg  # type: ignore[misc]
    a = qwen_mod.QwenAdapter()
    diffs = a.apply({"qwen.model": "qwen3.6-plus"}, dry=False)
    assert diffs
    after = json.loads(cfg.read_text())
    assert after["model"]["name"] == "qwen3.6-plus"
    assert after["model"]["baseUrl"] == "u"
    assert after["$version"] == 4
    qwen_mod.QwenAdapter.path = config.HOME / ".qwen" / "settings.json"


def test_openakita_apply_roundtrip(tmp_path: Path, monkeypatch):
    from ccse import openakita as oa_mod
    cfg = tmp_path / "llm_endpoints.json"
    cfg.write_text(json.dumps({
        "endpoints": [
            {"name": "primary", "priority": 1, "model": "gpt-5.6-sol",
             "base_url": "http://192.168.0.14:6333/v1", "api_key_env": "OPENAI_API_KEY"},
        ],
        "compiler_endpoints": [{"name": "compiler-primary", "model": "gpt-5.4-mini"}],
        "settings": {"retry_count": 2},
    }))
    oa_mod.OpenAkitaAdapter.path = cfg  # type: ignore[misc]
    a = oa_mod.OpenAkitaAdapter()
    # slots detect the primary endpoint values
    slots = {s.key: s.current for s in a.slots()}
    assert slots["openakita.model"] == "gpt-5.6-sol"
    assert slots["openakita.base_url"] == "http://192.168.0.14:6333/v1"
    # apply model + base_url
    diffs = a.apply({"openakita.model": "qwen3.6-plus",
                     "openakita.base_url": "http://10.0.0.1:8000/v1"}, dry=False)
    assert any("endpoints[0].model" in d and "qwen3.6-plus" in d for d in diffs)
    after = json.loads(cfg.read_text())
    assert after["endpoints"][0]["model"] == "qwen3.6-plus"
    assert after["endpoints"][0]["base_url"] == "http://10.0.0.1:8000/v1"
    assert after["compiler_endpoints"][0]["model"] == "gpt-5.4-mini"  # untouched
    assert after["settings"]["retry_count"] == 2
    # idempotent: re-applying same values yields no diffs
    assert a.apply({"openakita.model": "qwen3.6-plus"}, dry=False) == []
    # falls back to endpoints[0] when no priority:1 entry
    cfg.write_text(json.dumps({"endpoints": [{"model": "m1", "base_url": "u1"}]}))
    assert a.slots()[0].current == "m1"
    oa_mod.OpenAkitaAdapter.path = config.HOME / ".openakita" / "data" / "llm_endpoints.json"


def test_model_switch_includes_follows_slots(tmp_path: Path, monkeypatch):
    """`--model NAME` must cover every model slot flagged ``follows=True``
    (opencode subagents), keeping each slot's structural <prefix>/ route."""
    import ccse.cli as cli_mod
    from ccse import opencode as oc_mod
    cfg = tmp_path / "opencode.json"
    cfg.write_text(json.dumps({
        "model": "newapi/old-main",
        "agent": {"build": {"model": "newapi/old-build"},
                  "plan": {"model": "newapi/old-plan"}},
        "provider": {"newapi": {"options": {"baseURL": "u", "apiKey": "k"}}},
    }))
    oc_mod.OpenCodeAdapter.path = cfg  # type: ignore[misc]
    monkeypatch.setattr(cli_mod, "_load_adapters", lambda: [oc_mod.OpenCodeAdapter()])
    monkeypatch.setattr(cli_mod, "_filter_adapters", lambda ads, o, e: ads)
    assigns = cli_mod._model_assignments("glm-5.2", None, None)
    assert assigns["opencode.model"] == "newapi/glm-5.2"            # prefix kept
    assert assigns["opencode.agent.build.model"] == "newapi/glm-5.2"  # follows
    assert assigns["opencode.agent.plan.model"] == "newapi/glm-5.2"   # follows
    oc_mod.OpenCodeAdapter.path = (config.HOME / ".config" / "opencode"
                                   / "opencode.json")


def test_codex_literal_api_key(tmp_path: Path, monkeypatch):
    """Codex provider may carry a literal ``api_key`` (no ``env_key``): the slot
    reads the literal and apply writes it back into config.toml, not ~/.zshrc."""
    import tomllib
    from ccse import codex as codex_mod
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'model = "old"\nmodel_provider = "newapi"\n'
        '[model_providers.newapi]\nname = "NewAPI"\n'
        'base_url = "https://x/v1"\napi_key = "sk-old-literal"\n')
    codex_mod.CodexAdapter.path = cfg  # type: ignore[misc]
    a = codex_mod.CodexAdapter()
    slots = {s.key: s for s in a.slots()}
    assert slots["codex.api_key"].current == "sk-old-literal"  # literal, not env name
    # apply writes the literal into the toml provider block
    diffs = a.apply({"codex.api_key": "sk-new-literal"}, dry=False)
    assert any("api_key" in d for d in diffs)
    assert not any("(zshrc)" in d for d in diffs)  # not routed to shell rc
    d = tomllib.loads(cfg.read_text())
    assert d["model_providers"]["newapi"]["api_key"] == "sk-new-literal"
    codex_mod.CodexAdapter.path = config.HOME / ".codex" / "config.toml"


def test_jcode_roundtrip(tmp_path: Path, monkeypatch):
    """JCode: model writes mirror into the provider block + registry; a stale
    default_provider falls back to the first providers.* block; api_key env-var
    mode routes to ~/.zshrc (asserted in dry mode, no write)."""
    import tomllib
    from ccse import jcode as jc_mod
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[provider]\ndefault_provider = "openai-compatible"\n'
        'default_model = "gpt-5.6-terra"\n'
        '[providers.newapi]\ntype = "openai-compatible"\n'
        'base_url = "http://192.168.0.14:6333/v1"\n'
        'api_key_env = "JCODE_PROVIDER_NEWAPI_API_KEY"\n'
        'default_model = "gpt-5.6-terra"\n'
        '[[providers.newapi.models]]\nid = "gpt-5.6-terra"\n')
    jc_mod.JCodeAdapter.path = cfg  # type: ignore[misc]
    a = jc_mod.JCodeAdapter()
    slots = {s.key: s for s in a.slots()}
    assert slots["jcode.model"].current == "gpt-5.6-terra"
    assert slots["jcode.base_url"].current == "http://192.168.0.14:6333/v1"
    assert slots["jcode.api_key"].current == "JCODE_PROVIDER_NEWAPI_API_KEY"  # env name
    # model switch mirrors + adds registry entry (provider resolved via fallback)
    diffs = a.apply({"jcode.model": "glm-5.2"}, dry=False)
    assert any("provider.default_model" in d for d in diffs)
    assert any("providers[newapi].default_model" in d for d in diffs)
    assert any("models" in d and "glm-5.2" in d for d in diffs)
    d = tomllib.loads(cfg.read_text())
    assert d["provider"]["default_model"] == "newapi:glm-5.2"  # qualified "<provider>:<model>"
    assert d["provider"]["default_provider"] == "newapi"  # stale "openai-compatible" ref corrected
    assert d["providers"]["newapi"]["default_model"] == "glm-5.2"  # block-local stays bare
    assert any(m.get("id") == "glm-5.2" for m in d["providers"]["newapi"]["models"])
    # idempotent: re-applying same model adds no duplicate registry entry
    a.apply({"jcode.model": "glm-5.2"}, dry=False)
    d = tomllib.loads(cfg.read_text())
    assert sum(1 for m in d["providers"]["newapi"]["models"] if m.get("id") == "glm-5.2") == 1
    # base_url switch
    a.apply({"jcode.base_url": "http://10.0.0.5/v1"}, dry=False)
    assert tomllib.loads(cfg.read_text())["providers"]["newapi"]["base_url"] == "http://10.0.0.5/v1"
    # api_key env-var mode routes to zshrc (dry → diff only, no write)
    kd = a.apply({"jcode.api_key": "sk-new"}, dry=True)
    assert any("(zshrc)" in x and "JCODE_PROVIDER_NEWAPI_API_KEY" in x for x in kd)
    jc_mod.JCodeAdapter.path = config.HOME / ".jcode" / "config.toml"


def test_rules_inject_remove(tmp_path: Path, monkeypatch):
    """`ccse rules`: idempotent marked-block inject into an agent's global
    instructions file, update on changed snippet, remove restores original."""
    from ccse import rules
    f = tmp_path / "AGENTS.md"
    f.write_text("# existing\nsome content\n")
    monkeypatch.setitem(rules.INSTRUCTION_FILES, "codex", f)
    rules.apply(only="codex", snippet="RULE BODY")          # inject
    txt = f.read_text("utf-8")
    assert rules.START in txt and "RULE BODY" in txt
    assert "# existing" in txt and "some content" in txt     # original preserved
    rules.apply(only="codex", snippet="RULE BODY")          # idempotent
    assert f.read_text("utf-8") == txt
    rules.apply(only="codex", snippet="NEW BODY")           # update
    after = f.read_text("utf-8")
    assert "NEW BODY" in after and "RULE BODY" not in after
    rules.remove(only="codex")                               # remove
    final = f.read_text("utf-8")
    assert rules.START not in final and rules.END not in final
    assert "# existing" in final and "some content" in final


def test_dsh_roundtrip(tmp_path: Path, monkeypatch):
    """DSH: model writes agentDefaultModel.model in settings.yaml, preserving
    the existing ui-onboarding section; provider defaults on a fresh section;
    idempotent."""
    import ruamel.yaml as _y
    from ccse import dsh as dsh_mod
    cfg = tmp_path / "settings.yaml"
    cfg.write_text("ui-onboarding:\n  welcomeNoticeVersion: 2026-08-13.1\n")
    dsh_mod.DshAdapter.path = cfg  # type: ignore[misc]
    a = dsh_mod.DshAdapter()
    assert a.slots()[0].current is None  # agentDefaultModel absent
    diffs = a.apply({"dsh.model": "glm-5.2"}, dry=False)
    assert diffs and "glm-5.2" in diffs[0]
    doc = _y.YAML().load(cfg.read_text("utf-8"))
    assert doc["agentDefaultModel"]["model"] == "glm-5.2"
    assert doc["agentDefaultModel"]["provider"] == "deepseek-official"  # defaulted
    assert doc["ui-onboarding"]["welcomeNoticeVersion"] == "2026-08-13.1"  # preserved
    # idempotent
    assert a.apply({"dsh.model": "glm-5.2"}, dry=False) == []
    # slot now reflects written value
    assert a.slots()[0].current == "glm-5.2"
    dsh_mod.DshAdapter.path = config.HOME / ".dsh" / "settings.yaml"


def test_openclaude_roundtrip(tmp_path: Path, monkeypatch):
    """OpenClaude: env block write preserves existing settings (hooks etc.);
    idempotent; endpoint slots write ANTHROPIC_BASE_URL/AUTH_TOKEN."""
    from ccse import openclaude as oc_mod
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"command": "x"}]}]}}))
    oc_mod.OpenClaudeAdapter.path = cfg  # type: ignore[misc]
    a = oc_mod.OpenClaudeAdapter()
    assert a.slots()[0].current is None
    diffs = a.apply({"openclaude.model": "glm-5.2",
                     "openclaude.base_url": "http://10.0.0.5/v1",
                     "openclaude.api_key": "sk-new"}, dry=False)
    assert len(diffs) == 3
    after = json.loads(cfg.read_text())
    assert after["env"]["ANTHROPIC_MODEL"] == "glm-5.2"
    assert after["env"]["ANTHROPIC_BASE_URL"] == "http://10.0.0.5/v1"
    assert after["env"]["ANTHROPIC_AUTH_TOKEN"] == "sk-new"
    assert "Stop" in after["hooks"]  # preserved
    assert a.apply({"openclaude.model": "glm-5.2"}, dry=False) == []  # idempotent
    oc_mod.OpenClaudeAdapter.path = config.HOME / ".openclaude" / "settings.json"


def test_jsonpath_list_selector_roundtrip():
    from ccse.jsonpath import resolve_list_path, get_in_path, set_in_path
    obj = {"providers": [{"id": "x", "model": "a"}, {"id": "y", "model": "b"}]}
    r = resolve_list_path(obj, "providers[id=y].model")
    assert r == "providers[1].model"
    assert get_in_path(obj, r) == "b"
    assert set_in_path(obj, r, "b2")
    assert obj["providers"][1]["model"] == "b2"
    obj2 = {"providers": {"openai-codex-cli": {"settings": {"model": "z"}}}}
    assert get_in_path(obj2, "providers.openai-codex-cli.settings.model") == "z"


def test_reasonix_toml_roundtrip(tmp_path, monkeypatch):
    """Reasonix TOML: set active provider model, comment-preserving."""
    from ccse import extra as extra_mod
    cfg = tmp_path / "config.toml"
    # tomlkit required write path; skip if absent
    try:
        import tomlkit  # noqa
    except ImportError:
        return
    cfg.write_text(
        '# top comment\n'
        'default_model = "newapi"\n'
        'language = "zh"\n\n'
        '[[providers]]\n'
        'name = "newapi"\n'
        'model = "gpt-5.6-terra"\n'
        'base_url = "http://192.168.0.14:6333/v1"\n\n'
        '[[providers]]\n'
        'name = "deepseek-flash"\n'
        'model = "deepseek-v4-flash"\n')
    monkeypatch.setattr(extra_mod, "HOME", tmp_path, raising=False)
    extra_mod.ReasonixAdapter.path = cfg  # type: ignore
    a = extra_mod.ReasonixAdapter()
    diffs = a.apply({"reasonix.model": "gpt-5.6-sol"}, dry=False)
    assert diffs and any("providers[newapi].model" in d for d in diffs)
    text = cfg.read_text()
    assert '# top comment' in text          # comment preserved
    assert 'language = "zh"' in text        # unrelated kv preserved
    assert 'model = "gpt-5.6-sol"' in text
    assert 'model = "deepseek-v4-flash"' in text  # other provider untouched
    extra_mod.ReasonixAdapter.path = config.HOME / ".reasonix" / "config.toml"


def test_launch_claude_menu(monkeypatch):
    from ccse import cli as cli_mod
    a = type("X", (), {"id": "claude", "name": "Claude Code",
                       "path": Path("/x"), "available": True,
                       "primary": "claude.model",
                       "slots": lambda self: [], "apply": lambda *a, **k: []})
    cli_mod.REGISTRY_backup = None
    assert cli_mod._primary_key(a()) == "claude.model"


def test_envrc_kimi_zshrc(tmp_path, monkeypatch):
    """envrc adapter rewrites `export KIMI_MODEL_NAME=...` line, nothing else;
    handles bracketed model names like glm-5.2[1M] via single-quoting."""
    from ccse import envrc as envrc_mod
    rc = tmp_path / ".zshrc"
    rc.write_text(
        "# head\n"
        "export KIMI_MODEL_NAME=gpt-5.6-terra\n"
        "export OPENAI_API_KEY=sk-xxx\n"     # must NOT be touched
        "export OTHER='q-5.6'\n"
        "# tail\n", "utf-8")
    monkeypatch.setattr(envrc_mod, "HOME", tmp_path, raising=False)
    cls = envrc_mod.make_envrc_adapter(
        "kimi_test", "Kimi Test", {"model": "KIMI_MODEL_NAME"}, path=rc)
    a = cls()
    slots = a.slots()
    assert slots[0].label == "model"
    assert slots[0].current == "gpt-5.6-terra"
    diffs = a.apply({"kimi_test.model": "glm-5.2[1M]"}, dry=False)
    assert diffs and any("KIMI_MODEL_NAME" in d for d in diffs)
    text = rc.read_text("utf-8")
    assert "export KIMI_MODEL_NAME='glm-5.2[1M]'" in text
    assert "export OPENAI_API_KEY=sk-xxx" in text
    assert "export OTHER='q-5.6'" in text
    assert text.startswith("# head\n")
    assert "# tail\n" in text
    # re-read equals new value
    again = cls()
    assert again.slots()[0].current == "glm-5.2[1M]"


def test_envrc_nvim_minuet(tmp_path, monkeypatch):
    """nvim (minuet) envrc adapter: 3 slots; base_url + api_key rewrite existing
    export lines in place, model appends when the var is absent from the rc."""
    from ccse import envrc as envrc_mod
    from ccse.registry import KIND_API_KEY, KIND_BASE_URL
    rc = tmp_path / ".zshrc"
    rc.write_text(
        "export NEWAPI_BASE_URL=http://192.168.0.14:6333\n"
        "export NEWAPI_API_KEY='sk-old'\n"
        "export OTHER=1\n", "utf-8")
    monkeypatch.setattr(envrc_mod, "HOME", tmp_path, raising=False)
    cls = envrc_mod.make_envrc_adapter(
        "nvim_test", "Neovim Test",
        {"model": "NEWAPI_MODEL", "base_url": "NEWAPI_BASE_URL", "api_key": "NEWAPI_API_KEY"},
        path=rc, kinds={"base_url": KIND_BASE_URL, "api_key": KIND_API_KEY})
    a = cls()
    slots = {s.label: s for s in a.slots()}
    assert slots["model"].current is None                       # var absent in rc
    assert slots["base_url"].current == "http://192.168.0.14:6333"
    assert slots["api_key"].current == "sk-old"
    diffs = a.apply({
        "nvim_test.model": "glm-5.2",
        "nvim_test.base_url": "http://10.0.0.5/v1",
        "nvim_test.api_key": "sk-new",
    }, dry=False)
    assert len(diffs) == 3
    text = rc.read_text("utf-8")
    assert "export NEWAPI_MODEL='glm-5.2'" in text               # appended
    assert "export NEWAPI_BASE_URL='http://10.0.0.5/v1'" in text  # rewritten
    assert "export NEWAPI_API_KEY='sk-new'" in text               # rewritten
    assert "export OTHER=1" in text                               # untouched
    assert "sk-old" not in text
    assert text.count("NEWAPI_BASE_URL") == 1                    # no duplicate


def test_envrc_in_sync_no_duplicate(tmp_path, monkeypatch):
    """When a var already equals the target, apply() must not report <unset> or
    append a duplicate export line."""
    from ccse import envrc as envrc_mod
    rc = tmp_path / ".zshrc"
    rc.write_text("export KIMI_MODEL_NAME='gpt-5.6-luna'\nexport OTHER=1\n", "utf-8")
    monkeypatch.setattr(envrc_mod, "HOME", tmp_path, raising=False)
    cls = envrc_mod.make_envrc_adapter(
        "kimi_t2", "Kimi T2", {"model": "KIMI_MODEL_NAME"}, path=rc)
    a = cls()
    diffs = a.apply({"kimi_t2.model": "gpt-5.6-luna"}, dry=True)
    assert diffs == []  # already in sync → nothing to change, no false append
    text = rc.read_text("utf-8")
    assert text.count("KIMI_MODEL_NAME") == 1  # no duplicate line added


def test_envrc_windows_user_env(tmp_path, monkeypatch):
    """Windows: no shell rc — slots read os.environ, apply persists via setx."""
    import os
    from ccse import envrc as envrc_mod, config as cfg

    monkeypatch.setattr(cfg, "OS_NAME", "windows", raising=False)
    monkeypatch.setattr(cfg, "SHELL_RC", None, raising=False)
    calls = []
    monkeypatch.setattr(envrc_mod, "_setx", lambda var, val: calls.append((var, val)) or True,
                        raising=False)
    monkeypatch.setenv("KIMI_MODEL_NAME", "gpt-5.6-terra")
    cls = envrc_mod.make_envrc_adapter("kimi_win", "Kimi Win",
                                       {"model": "KIMI_MODEL_NAME"})
    a = cls()
    assert a.available is True  # no rc file → env-based, still available
    assert a.slots()[0].current == "gpt-5.6-terra"
    diffs = a.apply({"kimi_win.model": "glm-5.2[1M]"}, dry=False)
    assert diffs and calls == [("KIMI_MODEL_NAME", "glm-5.2[1M]")]
    # already in sync → no setx, no false diff
    diffs2 = a.apply({"kimi_win.model": "gpt-5.6-terra"}, dry=False)
    assert diffs2 == [] and len(calls) == 1


def test_kilo_adapter(tmp_path, monkeypatch):
    """Kilo CLI ~/.config/kilo/kilo.json: --model rewrites every `newapi/<name>`
    model string (model, subagent/small/swe_pruner, each agent.*.model) AND
    (re)creates provider.<prov>.models.<bare> so startup validation passes."""
    from ccse import extra as extra_mod
    cfg = tmp_path / "kilo.json"
    cfg.write_text(json.dumps({
        "model": "newapi/gpt-5.6-terra",
        "subagent_model": "newapi/gpt-5.6-terra",
        "small_model": "newapi/gpt-5.6-terra",
        "experimental": {"swe_pruner_model": "newapi/gpt-5.6-terra"},
        "agent": {"code": {"model": "newapi/gpt-5.6-terra"},
                  "ask": {"model": "newapi/gpt-5.6-terra"}},
        "subagent_variant_overrides": {"newapi/gpt-5.6-terra": "high"},
        "provider": {"newapi": {
            "options": {"baseURL": "http://a/v1"},
            "models": {"gpt-5.6-terra": {
                "name": "gpt-5.6-terra", "reasoning": True,
                "modalities": {"input": ["text", "image"],
                               "output": ["text"]}}}}},
    }))
    monkeypatch.setattr(extra_mod, "HOME", tmp_path, raising=False)
    extra_mod.KiloAdapter.path = cfg  # type: ignore[misc]
    a = extra_mod.KiloAdapter()
    slots = {s.key: s for s in a.slots()}
    assert slots["kilo.model"].current == "newapi/gpt-5.6-terra"
    assert slots["kilo.base_url"].current == "http://a/v1"

    diffs = a.apply({"kilo.model": "newapi/deepseek-v4-pro"}, dry=False)
    assert any("model: 'newapi/gpt-5.6-terra' -> 'newapi/deepseek-v4-pro'" in d
               for d in diffs)
    assert any("models[deepseek-v4-pro]" in d for d in diffs)

    after = json.loads(cfg.read_text())
    assert after["model"] == "newapi/deepseek-v4-pro"
    assert after["subagent_model"] == "newapi/deepseek-v4-pro"
    assert after["small_model"] == "newapi/deepseek-v4-pro"
    assert after["experimental"]["swe_pruner_model"] == "newapi/deepseek-v4-pro"
    assert after["agent"]["code"]["model"] == "newapi/deepseek-v4-pro"
    assert after["agent"]["ask"]["model"] == "newapi/deepseek-v4-pro"
    assert "newapi/deepseek-v4-pro" in after["subagent_variant_overrides"]
    reg = after["provider"]["newapi"]["models"]["deepseek-v4-pro"]
    assert reg["name"] == "deepseek-v4-pro"
    assert reg["modalities"]["output"] == ["text"]  # copied from old entry
    assert after["provider"]["newapi"]["options"]["baseURL"] == "http://a/v1"
    extra_mod.KiloAdapter.path = config.HOME / ".config" / "kilo" / "kilo.json"



    from ccse import config as cfg
    assert cfg.OS_NAME in ("linux", "darwin", "windows")
    # windows ⇔ no shell rc; posix ⇔ ~/.zshrc
    assert (cfg.SHELL_RC is None) == (cfg.OS_NAME == "windows")
    if cfg.SHELL_RC is not None:
        assert cfg.SHELL_RC.name == ".zshrc"


def test_memmy_adapter(tmp_path, monkeypatch):
    """Memmy YAML: agents.defaults.model + active provider apiBase/apiKey.
    apiKey is ${ENV_VAR}; --api-key persists literal via envrc, config keeps ref."""
    from ccse import extra as extra_mod
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "agents:\n"
        "  defaults:\n"
        "    provider: openai\n"
        "    model: gpt-5.6-terra\n"
        "providers:\n"
        "  openai:\n"
        "    apiKey: ${NEWAPI_API_KEY}\n"
        "    apiBase: http://192.168.0.14:6333/v1\n", "utf-8")
    monkeypatch.setattr(extra_mod, "HOME", tmp_path, raising=False)
    extra_mod.MemmyAdapter.path = cfg  # type: ignore[misc]
    from ccse import envrc as envrc_mod
    env_writes = []
    monkeypatch.setattr(envrc_mod, "ensure_env_var",
                        lambda var, val: env_writes.append((var, val)) or ("old", val),
                        raising=False)
    a = extra_mod.MemmyAdapter()
    slots = {s.kind: s for s in a.slots()}
    assert slots["model"].current == "gpt-5.6-terra"
    assert slots["base_url"].current == "http://192.168.0.14:6333/v1"
    assert slots["api_key"].current == "${NEWAPI_API_KEY}"
    diffs = a.apply({"memmy.model": "glm-5.2",
                     "memmy.base_url": "http://b/v1",
                     "memmy.api_key": "sk-2"}, dry=False)
    assert len(diffs) == 3
    assert env_writes == [("NEWAPI_API_KEY", "sk-2")]  # literal persisted via envrc
    text = cfg.read_text()
    assert "model: glm-5.2" in text
    assert "apiBase: http://b/v1" in text
    assert "apiKey: ${NEWAPI_API_KEY}" in text  # config keeps the ref
    extra_mod.MemmyAdapter.path = config.HOME / ".memmy" / "config.yaml"


def test_rewrite_project(tmp_path):
    """rewrite flips base/api/model across .env + env-read defaults; skips
    noise dirs and non-LLM code."""
    from ccse import rewrite
    (tmp_path / ".git").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".env").write_text(
        "# comment\nOPENAI_MODEL=gpt-4o\nOPENAI_API_KEY=sk-old\n"
        "OPENAI_BASE_URL=http://a/v1\n", "utf-8")
    (tmp_path / "app.py").write_text(
        'import os\n'
        'model = os.getenv("OPENAI_MODEL", "gpt-4o")\n'
        'key = os.getenv("OPENAI_API_KEY", "sk-old")\n'
        'client = OpenAI(base_url=os.environ["OPENAI_BASE_URL"], api_key=key)\n'
        'plain_model = keras.Model()\n', "utf-8")
    (tmp_path / "ui.ts").write_text(
        'const m = process.env.OPENAI_MODEL ?? "gpt-4o";\n'
        'apiKey = "sk-old"\n'
        'const unrelated = count ?? "gpt-4o";\n', "utf-8")
    (tmp_path / ".git" / "config").write_text("OPENAI_MODEL=git\n", "utf-8")
    (tmp_path / "node_modules" / "x.js").write_text("model=node\n", "utf-8")

    rc = rewrite.run(tmp_path, {"model": "deepseek-v4-flash",
                                "api_key": "sk-new",
                                "base_url": "http://b/v1"}, dry=False)
    assert rc == 0
    env = (tmp_path / ".env").read_text()
    assert "OPENAI_MODEL=deepseek-v4-flash" in env
    assert "OPENAI_API_KEY=sk-new" in env
    assert "OPENAI_BASE_URL=http://b/v1" in env
    assert "# comment" in env
    py = (tmp_path / "app.py").read_text()
    assert 'os.getenv("OPENAI_MODEL", "deepseek-v4-flash")' in py
    assert 'os.getenv("OPENAI_API_KEY", "sk-new")' in py
    assert 'os.environ["OPENAI_BASE_URL"]' in py  # no-default read untouched
    assert "plain_model = keras.Model()" in py  # non-LLM model= untouched
    ts = (tmp_path / "ui.ts").read_text()
    assert 'process.env.OPENAI_MODEL ?? "deepseek-v4-flash"' in ts
    assert 'apiKey = "sk-new"' in ts
    assert 'count ?? "gpt-4o"' in ts  # non-slot key untouched
    # noise dirs untouched
    assert (tmp_path / ".git" / "config").read_text() == "OPENAI_MODEL=git\n"
    assert (tmp_path / "node_modules" / "x.js").read_text() == "model=node\n"


def test_rewrite_dry_no_write(tmp_path):
    """dry-run reports but writes nothing."""
    from ccse import rewrite
    (tmp_path / ".env").write_text("OPENAI_MODEL=gpt-4o\n", "utf-8")
    rewrite.run(tmp_path, {"model": "x"}, dry=True)
    assert (tmp_path / ".env").read_text() == "OPENAI_MODEL=gpt-4o\n"


def test_prime_adapter(tmp_path, monkeypatch):
    """Prime resolves model from settings.defaultModel + models.json provider
    catalog, NOT the env.ANTHROPIC_MODEL block."""
    from ccse import prime as prime_mod
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({
        "defaultProvider": "newapi",
        "defaultModel": "gpt-5.6-terra",
        "recentModels": ["newapi/gpt-5.6-terra"],
        "env": {"ANTHROPIC_MODEL": "gpt-5.6-terra"},  # inert for prime
    }))
    models = tmp_path / "models.json"
    models.write_text(json.dumps({"providers": {"newapi": {
        "baseUrl": "http://a", "apiKey": "OPENAI_API_KEY",
        "models": [{"id": "gpt-5.6-terra", "name": "GPT-5.6 Terra"}]}}}))
    monkeypatch.setattr(prime_mod, "HOME", tmp_path, raising=False)
    monkeypatch.setattr(prime_mod, "MODELS_JSON", models, raising=False)
    monkeypatch.setattr(config, "HOME", tmp_path, raising=False)
    prime_mod.PrimeAdapter.path = settings  # type: ignore[misc]
    a = prime_mod.PrimeAdapter()
    slots = {s.key: s for s in a.slots()}
    assert slots["prime.default_model"].current == "gpt-5.6-terra"
    assert slots["prime.base_url"].current == "http://a"
    assert slots["prime.api_key"].current == "OPENAI_API_KEY"
    assert a.primary == "prime.default_model"
    diffs = a.apply({"prime.default_model": "deepseek-v4-flash",
                     "prime.base_url": "http://b"}, dry=False)
    assert any("defaultModel" in d for d in diffs)
    assert any("models[0].id" in d for d in diffs)
    s_after = json.loads(settings.read_text())
    assert s_after["defaultModel"] == "deepseek-v4-flash"
    assert "newapi/deepseek-v4-flash" in s_after["recentModels"]
    m_after = json.loads(models.read_text())
    assert m_after["providers"]["newapi"]["models"][0]["id"] == "deepseek-v4-flash"
    assert m_after["providers"]["newapi"]["models"][0]["name"] == "Deepseek V4 Flash"
    assert m_after["providers"]["newapi"]["baseUrl"] == "http://b/v1"
    prime_mod.PrimeAdapter.path = config.HOME / ".prime" / "agent" / "settings.json"


def test_omp_adapter(tmp_path, monkeypatch):
    """OMP YAML: llm.model + defaultModel + modelRoles.default (`prov/model:lvl`)
    all follow --model; api_key ${VAR} persists via envrc."""
    from ccse import extra as extra_mod
    cfg = tmp_path / "config.yml"
    cfg.write_text(
        "llm:\n"
        "  provider: openai\n"
        "  baseUrl: http://192.168.0.14:6333/v1\n"
        "  model: gpt-5.6-sol\n"
        "  apiKey: \"${OPENAI_API_KEY}\"\n"
        "defaultProvider: local-openai\n"
        "defaultModel: gpt-5.6-sol\n"
        "modelRoles:\n"
        "  default: local-openai/gpt-5.6-sol:xhigh\n", "utf-8")
    monkeypatch.setattr(extra_mod, "HOME", tmp_path, raising=False)
    extra_mod.OmpAdapter.path = cfg  # type: ignore[misc]
    from ccse import envrc as envrc_mod
    env_writes = []
    monkeypatch.setattr(envrc_mod, "ensure_env_var",
                        lambda var, val: env_writes.append((var, val)) or ("old", val),
                        raising=False)
    a = extra_mod.OmpAdapter()
    slots = {s.key: s for s in a.slots()}
    assert slots["omp.model"].current == "gpt-5.6-sol"
    assert slots["omp.defaultModel"].current == "gpt-5.6-sol"
    assert slots["omp.modelRole"].current == "local-openai/gpt-5.6-sol:xhigh"
    assert slots["omp.api_key"].current == "${OPENAI_API_KEY}"
    diffs = a.apply({"omp.model": "deepseek-v4-flash",
                     "omp.defaultModel": "deepseek-v4-flash",
                     "omp.modelRole": "local-openai/deepseek-v4-flash",
                     "omp.api_key": "sk-2"}, dry=False)
    assert len(diffs) == 4
    assert env_writes == [("OPENAI_API_KEY", "sk-2")]
    text = cfg.read_text()
    assert "model: deepseek-v4-flash" in text
    assert "defaultModel: deepseek-v4-flash" in text
    assert "default: local-openai/deepseek-v4-flash:xhigh" in text  # level kept
    assert 'apiKey: "${OPENAI_API_KEY}"' in text  # config keeps the var ref
    extra_mod.OmpAdapter.path = config.HOME / ".omp" / "agent" / "config.yml"


def test_omp_model_catalog_sync(tmp_path, monkeypatch):
    """OMP keeps config.yml and models.yml local-openai model catalog in sync."""
    try:
        import ruamel.yaml  # noqa
    except ImportError:
        return
    from ccse import extra as extra_mod
    cfg = tmp_path / "config.yml"
    models_yml = tmp_path / "models.yml"
    cfg.write_text(
        "llm:\n"
        "  provider: openai\n"
        "  baseUrl: http://192.168.0.14:6333/v1\n"
        "  model: gpt-5.6-sol\n"
        "  apiKey: \"${OPENAI_API_KEY}\"\n"
        "defaultProvider: local-openai\n"
        "defaultModel: gpt-5.6-sol\n"
        "modelRoles:\n"
        "  default: local-openai/gpt-5.6-sol:xhigh\n"
        "providers:\n"
        "  local-openai:\n"
        "    models:\n"
        "      - id: gpt-5.6-sol\n"
        "        name: GPT 5.6 SOL\n", "utf-8")
    models_yml.write_text(
        "providers:\n"
        "  local-openai:\n"
        "    models:\n"
        "      - id: gpt-5.6-sol\n"
        "        name: GPT 5.6 SOL\n", "utf-8")
    extra_mod.OmpAdapter.path = cfg  # type: ignore[misc]
    a = extra_mod.OmpAdapter()
    diffs = a.apply({"omp.model": "gpt-5.6-terra"}, dry=False)
    assert any("models[0].id" in d for d in diffs)
    assert "id: gpt-5.6-terra" in cfg.read_text("utf-8")
    assert "id: gpt-5.6-terra" in models_yml.read_text("utf-8")
    extra_mod.OmpAdapter.path = config.HOME / ".omp" / "agent" / "config.yml"


def test_make_adapter_follow(tmp_path):
    """--model on a json-path adapter also sets follow slots (pi defaultModel)."""
    from ccse import extra as extra_mod
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"llm": {"model": "a"}, "defaultModel": "a"}))
    extra_mod.make_adapter("pi_f", "Pi", cfg,
                           {"model": "llm.model", "defaultModel": "defaultModel"},
                           follow=("defaultModel",))
    from ccse.registry import REGISTRY
    a = REGISTRY["pi_f"]()
    assert a.follow == ("pi_f.defaultModel",)  # extra slot besides primary
    diffs = a.apply({"pi_f.model": "x", "pi_f.defaultModel": "x"}, dry=False)
    assert len(diffs) == 2
    after = json.loads(cfg.read_text())
    assert after["llm"]["model"] == "x" and after["defaultModel"] == "x"


def test_keep_prefix_logic():
    """Bare model name keeps each adapter's route prefix; full name is verbatim."""
    from ccse import cli as cli_mod
    # stand up fake adapters with known current primary values
    fake = {
        "claude": ("claude.model", "glm-5.2[1M]"),     # bare + [1M] suffix
        "opencode": ("opencode.model", "newapi/gpt-5.6-sol"),  # prefixed
        "gemini": ("gemini.model", "krill/gpt-5.6-terra"),     # prefixed
        "forge": ("forge.model", "krill/gpt-5.6-sol"),        # prefixed
        "openclaw": ("openclaw.primary", "dmx/gpt-5.6-terra"),  # prefixed
    }

    class A:
        def __init__(self, aid, key, cur, avail=True, suffix=""):
            self.id, self.name, self.path = aid, aid, Path("/x")
            self.available, self.primary = avail, key
            self._cur = cur
            self.suffix = suffix
        def slots(_self):
            from ccse.registry import Slot
            return [Slot(key=_self.primary, label=_self.primary, current=_self._cur)]
        def apply(_self, *a, **k): return []

    fakes = [
        A("claude", "claude.model", "glm-5.2[1M]", suffix="[1M]"),
        A("opencode", "opencode.model", "newapi/gpt-5.6-sol"),
        A("gemini", "gemini.model", "krill/gpt-5.6-terra"),
        A("forge", "forge.model", "krill/gpt-5.6-sol"),
        A("openclaw", "openclaw.primary", "dmx/gpt-5.6-terra"),
    ]
    cli_mod._load_adapters = lambda: fakes  # type: ignore
    cli_mod._filter_adapters = lambda ads, o, e: ads  # type: ignore

    # bare name -> prefixes preserved, claude gets [1M] appended
    got = cli_mod._model_assignments("glm-5.2", None, None, keep_prefix=True)
    assert got["claude.model"] == "glm-5.2[1M]"
    assert got["opencode.model"] == "newapi/glm-5.2"
    assert got["gemini.model"] == "krill/glm-5.2"
    assert got["forge.model"] == "krill/glm-5.2"
    assert got["openclaw.primary"] == "dmx/glm-5.2"

    # raw mode
    got2 = cli_mod._model_assignments("glm-5.2", None, None, keep_prefix=False)
    assert got2["opencode.model"] == "glm-5.2"
    assert got2["claude.model"] == "glm-5.2[1M]"  # suffix still applied

    # full name passed -> used verbatim even with keep_prefix
    got3 = cli_mod._model_assignments("proxy/glm-5.2", None, None, keep_prefix=True)
    assert got3["opencode.model"] == "proxy/glm-5.2"
    assert got3["claude.model"] == "proxy/glm-5.2[1M]"

    # name already carrying [1M] -> not doubled
    got4 = cli_mod._model_assignments("glm-5.2[1M]", None, None, keep_prefix=True)
    assert got4["claude.model"] == "glm-5.2[1M]"


def test_model_follow_subagent():
    """claude `--model X` also sets claude.subagent (CLAUDE_CODE_SUBAGENT_MODEL)."""
    from ccse import cli as cli_mod

    class A:
        id = name = "claude"
        path = Path("/x")
        available = True
        primary = "claude.model"
        follow = ("claude.subagent",)
        suffix = "[1M]"
        def slots(_self):
            from ccse.registry import Slot
            return [Slot(key="claude.model", label="m", current="glm-5.2[1M]"),
                    Slot(key="claude.subagent", label="s", current="glm-5.2[1M]")]
        def apply(_self, *a, **k): return []

    cli_mod._load_adapters = lambda: [A()]  # type: ignore
    cli_mod._filter_adapters = lambda ads, o, e: ads  # type: ignore
    got = cli_mod._model_assignments("gpt-5.6-luna", None, None, keep_prefix=True)
    assert got["claude.model"] == "gpt-5.6-luna[1M]"
    assert got["claude.subagent"] == "gpt-5.6-luna[1M]"


def test_snow_adapter(tmp_path, monkeypatch):
    """Snow ~/.snow/config.json snowcfg.advancedModel (and basicModel slot)."""
    from ccse import extra as extra_mod
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"snowcfg": {"baseUrl": "http://x/v1",
                                           "advancedModel": "",
                                           "basicModel": ""}}))
    extra_mod.make_adapter(
        "snow_test", "Snow", cfg,
        {"advancedModel": "snowcfg.advancedModel",
         "basicModel": "snowcfg.basicModel"})
    from ccse.registry import REGISTRY
    cls = REGISTRY["snow_test"]
    a = cls()
    assert a.primary == "snow_test.advancedModel"
    assert a.slots()[0].current is None  # empty string -> None (via get_in_path)
    diffs = a.apply({"snow_test.advancedModel": "glm-5.2"}, dry=False)
    assert diffs
    after = json.loads(cfg.read_text())
    assert after["snowcfg"]["advancedModel"] == "glm-5.2"
    assert after["snowcfg"]["basicModel"] == ""


def test_snow_endpoint_slots_roundtrip(tmp_path):
    """Endpoint slots (base_url/api_key) read + write through a JSON adapter."""
    from ccse import extra as extra_mod
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({
        "snowcfg": {"baseUrl": "http://a/v1", "apiKey": "sk-old",
                    "advancedModel": "m1"}}))
    extra_mod.make_adapter(
        "snow_ep", "Snow", cfg,
        {"advancedModel": "snowcfg.advancedModel"},
        endpoint_paths={"base_url": "snowcfg.baseUrl", "api_key": "snowcfg.apiKey"})
    from ccse.registry import KIND_API_KEY, KIND_BASE_URL, REGISTRY
    a = REGISTRY["snow_ep"]()
    slots = {s.kind: s for s in a.slots()}
    assert slots[KIND_BASE_URL].current == "http://a/v1"
    assert slots[KIND_API_KEY].current == "sk-old"
    diffs = a.apply({"snow_ep.base_url": "http://b/v1", "snow_ep.api_key": "sk-new"},
                    dry=False)
    assert len(diffs) == 2
    after = json.loads(cfg.read_text())
    assert after["snowcfg"]["baseUrl"] == "http://b/v1"
    assert after["snowcfg"]["apiKey"] == "sk-new"
    assert after["snowcfg"]["advancedModel"] == "m1"  # model untouched


def test_claude_endpoint_slots_roundtrip(tmp_path, monkeypatch):
    """Claude env endpoint slots write ANTHROPIC_BASE_URL/AUTH_TOKEN."""
    from ccse import claude as claude_mod
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"env": {"ANTHROPIC_MODEL": "m[1M]",
                                            "ANTHROPIC_BASE_URL": "http://a"}}))
    monkeypatch.setattr(claude_mod, "HOME", tmp_path, raising=False)
    monkeypatch.setattr(config, "HOME", tmp_path, raising=False)
    claude_mod.ClaudeAdapter.path = settings  # type: ignore[misc]
    a = claude_mod.ClaudeAdapter()
    slots = {s.kind: s for s in a.slots()}
    from ccse.registry import KIND_API_KEY, KIND_BASE_URL
    assert slots[KIND_BASE_URL].current == "http://a"
    assert slots[KIND_API_KEY].current is None
    diffs = a.apply({"claude.base_url": "http://b/v1", "claude.api_key": "sk-new"},
                    dry=False)
    assert len(diffs) == 2
    after = json.loads(settings.read_text())
    assert after["env"]["ANTHROPIC_BASE_URL"] == "http://b/v1"
    assert after["env"]["ANTHROPIC_AUTH_TOKEN"] == "sk-new"
    assert after["env"]["ANTHROPIC_MODEL"] == "m[1M]"  # model untouched
    claude_mod.ClaudeAdapter.path = config.HOME / ".claude" / "settings.json"


def _fake_server(models, status=200):
    """HTTP server returning /models list (or status)."""
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/models":
                body = json.dumps({"data": [{"id": m} for m in models]}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_forge_adapter(tmp_path, monkeypatch):
    """Forge: model in .forge.toml [session], endpoint on active provider in
    credentials.json; other providers untouched."""
    from ccse import extra as extra_mod
    toml_f = tmp_path / ".forge.toml"
    toml_f.write_text('[session]\nprovider_id = "openai_compatible"\n'
                      'model_id = "krill/deepseek-v4-flash"\n')
    creds_f = tmp_path / ".credentials.json"
    creds_f.write_text(json.dumps([
        {"id": "openai_compatible",
         "auth_details": {"api_key": "sk-1"},
         "url_params": {"OPENAI_URL": "http://a"}},
        {"id": "other", "auth_details": {"api_key": "sk-x"},
         "url_params": {"OPENAI_URL": "http://x"}},
    ]))
    monkeypatch.setattr(extra_mod, "HOME", tmp_path, raising=False)
    extra_mod.ForgeAdapter.path = toml_f  # type: ignore[misc]
    extra_mod.ForgeAdapter._creds_path = creds_f  # type: ignore[misc]
    a = extra_mod.ForgeAdapter()
    slots = a.slots()
    assert any(s.kind == "base_url" and s.current == "http://a" for s in slots)
    assert any(s.kind == "api_key" and s.current == "sk-1" for s in slots)
    diffs = a.apply({"forge.model": "krill/gpt-5.6-luna",
                     "forge.base_url": "http://b", "forge.api_key": "sk-2"},
                    dry=False)
    assert len(diffs) == 3
    assert 'model_id = "krill/gpt-5.6-luna"' in toml_f.read_text()
    c = json.loads(creds_f.read_text())
    assert c[0]["url_params"]["OPENAI_URL"] == "http://b"
    assert c[0]["auth_details"]["api_key"] == "sk-2"
    assert c[1]["auth_details"]["api_key"] == "sk-x"  # untouched
    extra_mod.ForgeAdapter.path = config.HOME / ".forge" / ".forge.toml"


def test_crush_adapter(tmp_path, monkeypatch):
    """Crush: model lives in providers.json, credentials in crush.json."""
    from ccse import extra as extra_mod
    cfg = tmp_path / "crush.json"
    cfg.write_text(json.dumps({"providers": {"zai": {"id": "zai",
                                                     "base_url": "http://a",
                                                     "api_key": "sk-1"}}}))
    provs = tmp_path / "providers.json"
    provs.write_text(json.dumps([{"id": "zai", "default_large_model_id": "glm-5.2"}]))

    monkeypatch.setattr(extra_mod, "HOME", tmp_path, raising=False)
    cls = type("_CrushTest", (extra_mod.CrushAdapter,), {
        "path": cfg, "available": property(lambda self: True)})
    # reuse the real adapter but point providers path at tmp
    real = extra_mod.CrushAdapter
    real._providers_path = lambda self: provs  # type: ignore[method-assign]

    a = cls()
    slots = a.slots()
    assert slots[0].current == "glm-5.2"
    diffs = a.apply({"crush.model": "deepseek-v4-flash",
                     "crush.base_url": "http://b",
                     "crush.api_key": "sk-2"}, dry=False)
    assert len(diffs) == 3
    assert json.loads(provs.read_text())[0]["default_large_model_id"] == "deepseek-v4-flash"
    after = json.loads(cfg.read_text())
    assert after["providers"]["zai"]["base_url"] == "http://b"
    assert after["providers"]["zai"]["api_key"] == "sk-2"


def test_droid_adapter(tmp_path, monkeypatch):
    """Droid: active model id + matching customModel baseUrl/apiKey."""
    from ccse import extra as extra_mod
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({
        "sessionDefaultSettings": {"model": "custom:m1-0"},
        "customModels": [{"id": "custom:m1-0", "baseUrl": "http://a",
                          "apiKey": "sk-1", "model": "m1"}],
    }))
    monkeypatch.setattr(extra_mod, "HOME", tmp_path, raising=False)
    extra_mod.DroidAdapter.path = cfg  # type: ignore[misc]
    a = extra_mod.DroidAdapter()
    slots = a.slots()
    assert slots[0].current == "custom:m1-0"
    diffs = a.apply({"droid.base_url": "http://b", "droid.api_key": "sk-2"},
                    dry=False)
    assert len(diffs) == 2
    after = json.loads(cfg.read_text())
    assert after["customModels"][0]["baseUrl"] == "http://b"
    assert after["customModels"][0]["apiKey"] == "sk-2"
    extra_mod.DroidAdapter.path = config.HOME / ".factory" / "settings.json"


def test_probe_endpoint_pass_warn_fail():
    from ccse import cli as cli_mod

    srv, base = _fake_server(["deepseek-v4-flash", "gpt-5.6-luna"])
    try:
        st, _ = cli_mod._probe_endpoint(base, "sk-x", "deepseek-v4-flash", 5)
        assert st == "PASS"
        # prefixed + suffixed model still matched after normalization
        st, _ = cli_mod._probe_endpoint(base, "sk-x", "newapi/deepseek-v4-flash[1M]", 5)
        assert st == "PASS"
        st, msg = cli_mod._probe_endpoint(base, "sk-x", "nonexistent-model", 5)
        assert st == "WARN" and "NOT in /models" in msg
    finally:
        srv.shutdown()


def test_probe_endpoint_bad_key():
    from ccse import cli as cli_mod

    srv, base = _fake_server([], status=401)
    try:
        st, msg = cli_mod._probe_endpoint(base, "sk-bad", None, 5)
        assert st == "FAIL" and "api_key rejected" in msg
    finally:
        srv.shutdown()


def test_resolve_key_env_name():
    import os
    from ccse import cli as cli_mod

    os.environ["CCSE_TEST_KEY"] = "sk-literal-from-env"
    try:
        assert cli_mod._resolve_key("CCSE_TEST_KEY") == "sk-literal-from-env"
        assert cli_mod._resolve_key("sk-inline-key") == "sk-inline-key"
        assert cli_mod._resolve_key(None) is None
        assert cli_mod._resolve_key("NOT_A_SET_VAR_XYZ") == "NOT_A_SET_VAR_XYZ"
    finally:
        del os.environ["CCSE_TEST_KEY"]


def test_endpoint_assignments_filters_by_kind():
    """_endpoint_assignments picks only base_url/api_key slots."""
    from ccse import cli as cli_mod
    from ccse.registry import Slot

    class A:
        id, name, path = "x", "X", Path("/x")
        available = True
        primary = "x.model"
        slots = lambda self: [
            Slot(key="x.model", label="m", current="m1"),
            Slot(key="x.base_url", label="b", current="http://a",
                 kind="base_url"),
            Slot(key="x.api_key", label="k", current="sk-1", kind="api_key"),
        ]
        def apply(self, *a, **k): return []

    cli_mod._load_adapters = lambda: [A()]  # type: ignore
    cli_mod._filter_adapters = lambda ads, o, e: ads  # type: ignore
    got = cli_mod._endpoint_assignments("base_url", "http://b", None, None)
    assert got == {"x.base_url": "http://b"}
    got2 = cli_mod._endpoint_assignments("api_key", "sk-2", None, None)
    assert got2 == {"x.api_key": "sk-2"}


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))