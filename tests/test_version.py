import re
from pathlib import Path

from ads_agent_bridge import __version__


def test_runtime_version_matches_package_metadata():
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)

    assert match is not None
    assert __version__ == match.group(1)


def test_public_release_references_match_package_version():
    root = Path(__file__).parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)

    assert match is not None
    version = match.group(1)
    expected_tag = f"v{version}"

    readme = (root / "README.md").read_text(encoding="utf-8")
    installer_tags = set(
        re.findall(r"releases/download/(v[^/]+)/install\.(?:sh|ps1)", readme)
    )
    assert installer_tags == {expected_tag}

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    first_release = re.search(r"^## (\d[^ ]*) - ", changelog, re.MULTILINE)
    assert first_release is not None
    assert first_release.group(1) == version


def test_public_skills_are_separate_and_route_to_each_other():
    root = Path(__file__).parents[1] / "src" / "ads_agent_bridge" / "skill_assets"
    bridge = (root / "ads-agent-bridge" / "SKILL.md").read_text(encoding="utf-8")
    docs = (root / "ads-kb-docs" / "SKILL.md").read_text(encoding="utf-8")

    assert "name: ads-agent-bridge" in bridge
    assert "name: ads-kb-docs" in docs
    assert "$ads-kb-docs" in bridge
    assert "$ads-agent-bridge" in docs
    for name in ("ads-agent-bridge", "ads-kb-docs"):
        assert (root / name / "agents" / "openai.yaml").is_file()


def test_github_actions_are_pinned_to_full_commit_shas():
    workflows = Path(__file__).parents[1] / ".github" / "workflows"

    for workflow in workflows.glob("*.yml"):
        text = workflow.read_text(encoding="utf-8")
        for action_ref in re.findall(r"^\s*- uses:\s+([^\s#]+)", text, re.MULTILINE):
            _, separator, ref = action_ref.rpartition("@")
            assert separator == "@", (
                f"missing action ref in {workflow.name}: {action_ref}"
            )
            assert re.fullmatch(r"[0-9a-f]{40}", ref), (
                f"unpinned action in {workflow.name}: {action_ref}"
            )


def test_bilingual_readmes_share_navigation_and_user_facing_visual_assets():
    root = Path(__file__).parents[1]
    english = (root / "README.md").read_text(encoding="utf-8")
    chinese = (root / "README.zh-CN.md").read_text(encoding="utf-8")

    assert 'href="README.zh-CN.md"' in english
    assert 'href="README.md"' in chinese
    assert "docs/CLI_REFERENCE.md" in english
    assert "docs/CLI_REFERENCE.md" in chinese

    for relative_path in (
        "docs/assets/readme/logo.png",
        "docs/assets/readme/ads-user-value-v2.png",
    ):
        assert (root / relative_path).is_file()
        assert relative_path in english
        assert relative_path in chinese

    assert (root / "docs/assets/readme/social-preview-v2.png").is_file()


def test_public_capability_claims_keep_plugin_and_comparison_scope_explicit():
    root = Path(__file__).parents[1]
    english = (root / "README.md").read_text(encoding="utf-8")
    chinese = (root / "README.zh-CN.md").read_text(encoding="utf-8")
    matrix = (root / "docs" / "CAPABILITY_MATRIX.md").read_text(
        encoding="utf-8"
    )

    for readme in (english, chinese):
        assert "docs/CAPABILITY_MATRIX.md" in readme
        assert "docs/BENCHMARK_ADS2027_HEADLESS_AC.md" in readme
        assert "docs/benchmarks/ads2027-headless-ac-v1-summary.json" in readme
        assert "Copy ADS Context" in readme
        assert "ADS_CONTEXT" in readme

    assert "not a full-product comparison" in english
    assert "不是完整产品对比" in chinese
    assert "**Validated**" in matrix
    assert "**Compared**" in matrix
    assert "**Available (bounded)**" in matrix
    assert "not Bridge capabilities" in matrix
    assert "BENCHMARK_ADS2027_HEADLESS_AC.md" in matrix

    execution_summary = root / "docs" / "benchmarks" / "ads2027-headless-ac-v1-summary.json"
    execution_chart = root / "docs" / "assets" / "readme" / "ads2027-headless-ac-benchmark.svg"
    assert execution_summary.is_file()
    assert execution_chart.is_file()
