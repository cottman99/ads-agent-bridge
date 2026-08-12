from pathlib import Path

import pytest

from ads_agent_bridge.skill_installer import (
    install_skills,
    skill_status,
    uninstall_skills,
)


def _by_name(payload: dict) -> dict[str, dict]:
    return {item["skill"]: item for item in payload["skills"]}


def test_public_skills_install_together_idempotently_and_recoverably(tmp_path: Path) -> None:
    root = tmp_path / "skills"

    installed = install_skills(root=root)
    results = _by_name(installed)
    bridge_text = Path(results["ads-agent-bridge"]["path"], "SKILL.md").read_text(encoding="utf-8")
    docs_text = Path(results["ads-kb-docs"]["path"], "SKILL.md").read_text(encoding="utf-8")

    assert installed["status"] == "ready"
    assert "$ads-kb-docs" in bridge_text
    assert "$ads-agent-bridge" in docs_text
    assert "slot + profile" in bridge_text
    assert "Launching a DE workspace neither launches nor proves a DDS runtime" in bridge_text
    assert "Do not open raw ADS HTML" in docs_text
    assert "full signature for each required dependency" in docs_text

    reused = install_skills(root=root)
    assert reused["status"] == "ready"
    assert all(item["reused"] for item in reused["skills"])

    removed = uninstall_skills(root=root)
    assert removed["status"] == "removed"
    assert all(Path(item["backup"]).is_dir() for item in removed["skills"])
    assert skill_status(root=root)["status"] == "missing"


def test_docs_skill_can_be_managed_without_bridge_skill(tmp_path: Path) -> None:
    root = tmp_path / "skills"

    installed = install_skills("docs", root=root)
    assert installed["status"] == "ready"
    assert installed["skill"] == "ads-kb-docs"
    assert skill_status("bridge", root=root)["status"] == "missing"

    removed = uninstall_skills("docs", root=root)
    assert removed["status"] == "removed"


def test_all_preserves_complete_unmanaged_docs_and_installs_bridge(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    destination = root / "ads-kb-docs"
    (destination / "agents").mkdir(parents=True)
    kit_skill = "---\nname: ads-kb-docs\ndescription: Kit docs\n---\n\n# Kit Docs\n"
    (destination / "SKILL.md").write_text(kit_skill, encoding="utf-8")
    (destination / "agents" / "openai.yaml").write_text("interface: {}\n", encoding="utf-8")

    result = install_skills(root=root)
    skills = _by_name(result)

    assert result["status"] == "ready"
    assert skills["ads-agent-bridge"]["status"] == "ready"
    assert skills["ads-kb-docs"]["status"] == "preserved"
    assert skills["ads-kb-docs"]["satisfied_by_existing"] is True
    assert (destination / "SKILL.md").read_text(encoding="utf-8") == kit_skill
    status = skill_status(root=root)
    assert status["status"] == "ready"
    assert _by_name(status)["ads-kb-docs"]["status"] == "compatible"


def test_all_keeps_an_unmanaged_bridge_skill_as_a_conflict(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    destination = root / "ads-agent-bridge"
    (destination / "agents").mkdir(parents=True)
    (destination / "SKILL.md").write_text("foreign bridge\n", encoding="utf-8")
    (destination / "agents" / "openai.yaml").write_text("interface: {}\n", encoding="utf-8")

    result = install_skills(root=root)
    skills = _by_name(result)

    assert result["status"] == "conflict"
    assert skills["ads-agent-bridge"]["status"] == "conflict"
    assert "satisfied_by_existing" not in skills["ads-agent-bridge"]
    assert (destination / "SKILL.md").read_text(encoding="utf-8") == "foreign bridge\n"


def test_incomplete_unmanaged_content_remains_a_conflict(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    destination = root / "ads-kb-docs"
    destination.mkdir(parents=True)
    (destination / "SKILL.md").write_text("incomplete user content", encoding="utf-8")

    result = install_skills(root=root)

    assert result["status"] == "conflict"
    assert (destination / "SKILL.md").read_text(encoding="utf-8") == "incomplete user content"
    with pytest.raises(ValueError, match="unmanaged"):
        uninstall_skills("docs", root=root)


def test_complete_but_invalid_unmanaged_docs_content_remains_a_conflict(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    destination = root / "ads-kb-docs"
    (destination / "agents").mkdir(parents=True)
    (destination / "SKILL.md").write_text("not a valid skill\n", encoding="utf-8")
    (destination / "agents" / "openai.yaml").write_text("interface: {}\n", encoding="utf-8")

    result = install_skills(root=root)

    assert result["status"] == "conflict"
    assert (destination / "SKILL.md").read_text(encoding="utf-8") == "not a valid skill\n"


def test_force_replaces_unmanaged_skill_only_after_backup(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    destination = root / "ads-agent-bridge"
    (destination / "agents").mkdir(parents=True)
    (destination / "SKILL.md").write_text("user bridge skill", encoding="utf-8")
    (destination / "agents" / "openai.yaml").write_text("interface: {}\n", encoding="utf-8")

    blocked = install_skills("bridge", root=root)
    replaced = install_skills("bridge", root=root, force=True)

    assert blocked["status"] == "conflict"
    assert replaced["status"] == "ready"
    assert Path(replaced["backup"], "SKILL.md").read_text(encoding="utf-8") == "user bridge skill"
