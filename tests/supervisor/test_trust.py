import json
import stat

import pytest

from crew.supervisor.trust import TrustError, claude_config_file, trust_folder


def test_claude_config_file(tmp_path):
    assert claude_config_file({"CLAUDE_CONFIG_DIR": str(tmp_path)}) == tmp_path / ".claude.json"
    assert claude_config_file({"HOME": str(tmp_path)}) == tmp_path / ".claude.json"


def test_trust_folder_sets_flag_and_keeps_the_rest(tmp_path):
    config = tmp_path / ".claude.json"
    config.write_text(json.dumps({
        "numStartups": 3,
        "projects": {"/other": {"hasTrustDialogAccepted": True, "x": 1},
                     str(tmp_path / "wt"): {"allowedTools": ["a"]}},
    }))  # fmt: skip
    config.chmod(0o600)
    trust_folder(tmp_path / "wt", {"CLAUDE_CONFIG_DIR": str(tmp_path)})
    data = json.loads(config.read_text())
    assert data["numStartups"] == 3
    assert data["projects"]["/other"] == {"hasTrustDialogAccepted": True, "x": 1}
    assert data["projects"][str(tmp_path / "wt")] == {
        "allowedTools": ["a"],
        "hasTrustDialogAccepted": True,
    }
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == [".claude.json"]  # no temp file left


def test_trust_folder_refuses_unreadable_config(tmp_path):
    with pytest.raises(TrustError):
        trust_folder(tmp_path / "wt", {"CLAUDE_CONFIG_DIR": str(tmp_path)})
    (tmp_path / ".claude.json").write_text("[1]")
    with pytest.raises(TrustError):
        trust_folder(tmp_path / "wt", {"CLAUDE_CONFIG_DIR": str(tmp_path)})
