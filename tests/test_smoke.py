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
    from ccse import claude, cline, codex, gemini, opencode, qwen  # noqa: F401
    from ccse import extra  # noqa: F401
    ids = {a.id for a in all_adapters()}
    for expect in ("claude", "codex", "opencode", "gemini", "qwen", "cline",
                   "codebuddy", "pi", "openclaw", "kilocode", "reasonix",
                   "grok", "forge", "hermes"):
        assert expect in ids, f"missing adapter {expect}"


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


def test_keep_prefix_logic():
    """Bare model name keeps each adapter's route prefix; full name is verbatim."""
    from ccse import cli as cli_mod
    # stand up fake adapters with known current primary values
    fake = {
        "claude": ("claude.model", "glm-5.2[1M]"),     # bare
        "opencode": ("opencode.model", "newapi/gpt-5.6-sol"),  # prefixed
        "gemini": ("gemini.model", "krill/gpt-5.6-terra"),     # prefixed
        "forge": ("forge.model", "krill/gpt-5.6-sol"),        # prefixed
        "openclaw": ("openclaw.primary", "dmx/gpt-5.6-terra"),  # prefixed
    }

    class A:
        def __init__(self, aid, key, cur, avail=True):
            self.id, self.name, self.path = aid, aid, Path("/x")
            self.available, self.primary = avail, key
            self._cur = cur
        def slots(_self):
            from ccse.registry import Slot
            return [Slot(key=_self.primary, label=_self.primary, current=_self._cur)]
        def apply(_self, *a, **k): return []

    fakes = [A(k, k, v) for k, v in fake.values()]
    cli_mod._load_adapters = lambda: fakes  # type: ignore
    cli_mod._filter_adapters = lambda ads, o, e: ads  # type: ignore

    # bare name -> prefixes preserved
    got = cli_mod._model_assignments("glm-5.2", None, None, keep_prefix=True)
    assert got["claude.model"] == "glm-5.2"
    assert got["opencode.model"] == "newapi/glm-5.2"
    assert got["gemini.model"] == "krill/glm-5.2"
    assert got["forge.model"] == "krill/glm-5.2"
    assert got["openclaw.primary"] == "dmx/glm-5.2"

    # raw mode
    got2 = cli_mod._model_assignments("glm-5.2", None, None, keep_prefix=False)
    assert got2["opencode.model"] == "glm-5.2"

    # full name passed -> used verbatim even with keep_prefix
    got3 = cli_mod._model_assignments("proxy/glm-5.2", None, None, keep_prefix=True)
    assert got3["opencode.model"] == "proxy/glm-5.2"
    assert got3["claude.model"] == "proxy/glm-5.2"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))