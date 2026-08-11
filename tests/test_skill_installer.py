from pathlib import Path

import pytest

from ads_agent_bridge.skill_installer import install_docs_skill, skill_status, uninstall_docs_skill


def test_docs_skill_install_is_idempotent_and_recoverable(tmp_path: Path) -> None:
    root = tmp_path / "skills"

    installed = install_docs_skill(root=root)
    installed_skill_file = Path(installed["path"], "SKILL.md")
    assert installed_skill_file.is_file()
    skill_text = installed_skill_file.read_text(encoding="utf-8")
    assert "ads-agent docs get <source-ref>" in skill_text
    assert "ads-policy:execution-route/v1" in skill_text
    assert "Do not open raw ADS HTML" in skill_text
    assert "reserve one of those three rounds" in skill_text
    assert "full signature for each required dependency" in skill_text
    assert "return the boundary instead of guessing code" in skill_text
    assert "The follow-up `get` belongs to the same" in skill_text
    assert "source_path" not in skill_text
    reused = install_docs_skill(root=root)
    removed = uninstall_docs_skill(root=root)

    assert installed["status"] == "ready"
    assert installed["reused"] is False
    assert reused["status"] == "ready"
    assert reused["reused"] is True
    assert removed["status"] == "removed"
    assert Path(removed["backup"]).is_dir()
    assert skill_status(root=root)["status"] == "missing"


def test_docs_skill_does_not_replace_unmanaged_content_without_force(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    destination = root / "ads-kb-docs"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("user content", encoding="utf-8")

    result = install_docs_skill(root=root)

    assert result["status"] == "conflict"
    assert (destination / "SKILL.md").read_text(encoding="utf-8") == "user content"
    with pytest.raises(ValueError, match="unmanaged"):
        uninstall_docs_skill(root=root)
