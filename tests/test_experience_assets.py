from pathlib import Path

from eda_bridge_runtime import validate_compiled_shortcut_binding, validate_experience_library

from ads_agent_bridge.experience_shortcuts import (
    get_asset,
    list_assets,
    validate_shortcut,
)


def test_packaged_experience_library_and_all_compiled_shortcuts_match():
    root = Path(__file__).parents[1] / "src" / "ads_agent_bridge" / "experience_assets"
    manifest = validate_experience_library(root)

    assert len(manifest["assets"]) == 5
    assert any(
        item["id"] == "ads.native.circuit-simulate-and-validate" for item in manifest["assets"]
    )
    ads_2027_native = list_assets(version="ADS 2027", profile="de", capability="native.execute")
    assert [item["id"] for item in ads_2027_native["assets"]] == [
        "ads.native.circuit-simulate-and-validate"
    ]
    native_body = (root / "workflows" / "native-circuit-simulate.md").read_text(encoding="utf-8")
    assert "names the dataset after the schematic cell" in native_body
    assert 'context["artifact_root"] + "/ac_minimal.ds"' in native_body
    assert 'wire.add_wire_label("R1_v")' in native_body
    assert 'r1.parameters["R"].value = "3.0 kOhm"' in native_body
    assert "design.save_design()" in native_body
    assert "successful\n`run_netlist()` may return `None`" in native_body
    assert "never reuse the source workspace" in native_body
    assert 'optional `instance`\nfield to `"schematic"`' in native_body
    assert "from keysight.edatoolbox import ads" in native_body
    assert "`DesignMode.READ` is not an ADS 2027 member" in native_body
    assert "no greater than `300000` milliseconds" in native_body
    assert "Reuse these validated ADS 2027 mechanics directly" in native_body
    assert 'context["top_design"]` is invalid' in native_body
    assert '"continuation_context": "<workspace.create continuation_ref>"' in native_body
    assert "word `dataset` alone never selects DDS" in (
        Path(__file__).parents[1]
        / "src"
        / "ads_agent_bridge"
        / "skill_assets"
        / "ads-agent-bridge"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "version-matched official ADS Python API" not in native_body
    for operation, profile in (
        ("design.apply", "de"),
        ("circuit.simulate", "de"),
        ("dds.create", "dds"),
        ("momentum.run_generated", "de"),
    ):
        validate_compiled_shortcut_binding(
            validate_shortcut(operation, version="2026", profile=profile),
            library_root=root,
            eda="keysight-ads",
            version="2026",
            profile=profile,
        )
        assert (
            validate_shortcut(operation, version="2026", profile=profile)["fallback"]
            == "governed_native_execution"
        )
    selected = get_asset("ads.schematic.apply-transaction")
    assert selected["implementation"]["operation"] == "design.apply"
    assert selected["implementation"]["contract"]["parameter_schema"]["plan_schema"] == (
        "ads.design-plan/v1"
    )
    assert "implementation" not in get_asset("ads.native.circuit-simulate-and-validate")
    selected_by_contract = get_asset(version="ADS 2027", profile="de", capability="native.execute")
    assert selected_by_contract["asset"]["id"] == ("ads.native.circuit-simulate-and-validate")


def test_experience_get_exact_selectors_must_resolve_uniquely():
    try:
        get_asset(version="2027", profile="de", capability="missing.operation")
    except ValueError as exc:
        assert "matched 0 assets" in str(exc)
    else:
        raise AssertionError("zero-match selectors must be rejected")

    try:
        get_asset(
            "ads.native.circuit-simulate-and-validate",
            version="2027",
            profile="de",
            capability="native.execute",
        )
    except ValueError as exc:
        assert "either asset_id or exact selectors" in str(exc)
    else:
        raise AssertionError("mixed selector modes must be rejected")


def test_absent_knowledge_does_not_disable_compiled_execution(tmp_path, monkeypatch):
    from ads_agent_bridge import experience_shortcuts

    monkeypatch.setattr(experience_shortcuts, "_ROOT", tmp_path / "absent")
    for operation, profile in (("design.apply", "de"), ("dds.create", "dds")):
        binding = validate_shortcut(operation, version="2026", profile=profile)
        state = experience_shortcuts.shortcut_state(operation, version="2026", profile=profile)
        assert binding["fallback"] == "governed_native_execution"
        assert state["available"] and state["healthy"]
        assert not state["asset_eligible"]
