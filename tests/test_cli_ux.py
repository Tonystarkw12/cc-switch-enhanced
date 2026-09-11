"""CLI polish: --version, completion, current, --json, -v/-q. `pytest tests/`."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ccse import config
import ccse.cli as cli


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    cc = tmp_path / ".ccse"
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", cc)
    monkeypatch.setattr(config, "SNAPSHOT_DIR", cc / "snapshots")
    monkeypatch.setattr(config, "HISTORY_INDEX", cc / "history.jsonl")
    return tmp_path


def test_version_and_completion(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    assert capsys.readouterr().out.startswith("ccse ")
    for shell in ("zsh", "bash"):
        assert cli.main(["completion", shell]) == 0
        out = capsys.readouterr().out
        assert "_ccse" in out and ("compdef ccse" in out or "complete -F" in out)


def test_current_json_no_match(home, capsys):
    (config.HOME / ".ccse").mkdir(parents=True, exist_ok=True)
    (config.HOME / ".ccse" / "profiles.toml").write_text(
        '[snap]\n"claude.model" = "glm-5.2[1M]"\n', "utf-8")
    assert cli.main(["current", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["profiles"][0]["matched"] == 0
    assert data["profiles"][0]["exact"] is False
    assert data["best"] is None or isinstance(data["best"], str)


def test_readonly_commands_json(home, capsys):
    for argv in (["list", "--json"], ["show", "--json"],
                 ["profiles", "--json"], ["history", "--json"],
                 ["snapshots", "--json"]):
        assert cli.main(argv) == 0
        json.loads(capsys.readouterr().out)  # every one must be valid JSON
