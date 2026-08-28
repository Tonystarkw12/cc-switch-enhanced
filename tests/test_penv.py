"""penv: provider store + project .env switch. Run: `python -m pytest tests/`."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from ccse import config
import ccse.cli as cli
from ccse.penv import read_providers


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    # DATA_DIR/SNAPSHOT_DIR/HISTORY_INDEX are import-time constants — patch
    # them too or snapshots/history leak into the real ~/.ccse.
    cc = tmp_path / ".ccse"
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", cc)
    monkeypatch.setattr(config, "SNAPSHOT_DIR", cc / "snapshots")
    monkeypatch.setattr(config, "HISTORY_INDEX", cc / "history.jsonl")
    return tmp_path


def _add(home: Path, name: str = "prov1"):
    rc = cli.main(["penv", name, "--base-url", "http://gw:6333/v1",
                   "--api-key", "sk-test-0123456789abcdef", "--model", "glm-5.2"])
    assert rc == 0
    return read_providers()[name]


def test_penv_add_and_read_roundtrip(home: Path):
    entry = _add(home)
    assert entry == {"base_url": "http://gw:6333/v1",
                     "api_key": "sk-test-0123456789abcdef",
                     "model": "glm-5.2"}
    # upsert keeps the file's other providers
    assert cli.main(["penv", "prov2", "--base-url", "http://b2/v1"]) == 0
    assert set(read_providers()) == {"prov1", "prov2"}


def test_penv_use_creates_env_with_canonical_keys(home: Path, tmp_path: Path):
    _add(home)
    proj = tmp_path / "proj"
    proj.mkdir()
    assert cli.main(["penv", str(proj), "prov1"]) == 0
    text = (proj / ".env").read_text("utf-8")
    assert "OPENAI_BASE_URL=http://gw:6333/v1" in text
    assert "OPENAI_API_KEY=sk-test-0123456789abcdef" in text
    assert "OPENAI_MODEL=glm-5.2" in text


def test_penv_use_rewrites_llm_keys_spares_others(home: Path, tmp_path: Path):
    _add(home)
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".env").write_text(
        "LLM_BASE_URL=http://old/v1\n"
        "LLM_API_KEY=sk-old-0123456789abcdef\n"
        "DATABASE_URL=postgres://x\n"
        "DEBUG=1\n", "utf-8")
    assert cli.main(["penv", str(proj), "prov1", "--model", "gpt-5.6-sol"]) == 0
    text = (proj / ".env").read_text("utf-8")
    assert "LLM_BASE_URL=http://gw:6333/v1" in text
    assert "LLM_API_KEY=sk-test-0123456789abcdef" in text
    assert "OPENAI_MODEL=gpt-5.6-sol" in text  # --model overrides provider model
    assert "DATABASE_URL=postgres://x" in text
    assert "DEBUG=1" in text
    assert "http://old" not in text


def test_penv_dry_writes_nothing(home: Path, tmp_path: Path):
    _add(home)
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".env").write_text("OPENAI_MODEL=keep\n", "utf-8")
    assert cli.main(["penv", str(proj), "prov1", "--dry"]) == 0
    assert (proj / ".env").read_text("utf-8") == "OPENAI_MODEL=keep\n"
    assert not (home / ".ccse" / "snapshots").exists() or \
        not list((home / ".ccse" / "snapshots").iterdir())


def test_penv_snapshots_and_redacts_history(home: Path, tmp_path: Path):
    _add(home)
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".env").write_text("OPENAI_BASE_URL=http://old/v1\n", "utf-8")
    assert cli.main(["penv", str(proj), "prov1"]) == 0
    snaps = list((home / ".ccse" / "snapshots").iterdir())
    assert len(snaps) == 1
    hist = (home / ".ccse" / "history.jsonl").read_text("utf-8")
    assert "sk-test-0123456789abcdef" not in hist
    assert "sk-tes***" in hist


def test_penv_unknown_provider_dies(home: Path, tmp_path: Path):
    proj = tmp_path / "proj"
    proj.mkdir()
    with pytest.raises(SystemExit) as e:
        cli.main(["penv", str(proj), "nope"])
    assert e.value.code == 2
