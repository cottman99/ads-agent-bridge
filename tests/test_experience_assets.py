from pathlib import Path

from eda_bridge_runtime import validate_experience_library

from ads_agent_bridge.experience_shortcuts import list_assets, validate_shortcut


def test_packaged_experience_library_and_all_compiled_shortcuts_match():
    root = Path(__file__).parents[1] / "src" / "ads_agent_bridge" / "experience_assets"
    manifest = validate_experience_library(root)

    assert len(manifest["assets"]) == 5
    assert any(
        item["id"] == "ads.native.circuit-simulate-and-validate"
        for item in manifest["assets"]
    )
    ads_2027_native = list_assets(
        version="ADS 2027", profile="de", capability="native.batch"
    )
    assert [item["id"] for item in ads_2027_native["assets"]] == [
        "ads.native.circuit-simulate-and-validate"
    ]
    native_body = (root / "workflows" / "native-circuit-simulate.md").read_text(
        encoding="utf-8"
    )
    assert "names the dataset after the schematic cell" in native_body
    assert 'context["artifact_root"] + "/ac_minimal.ds"' in native_body
    for operation, profile in (
        ("design.apply", "de"),
        ("circuit.simulate", "de"),
        ("dds.create", "dds"),
        ("momentum.run_generated", "de"),
    ):
        assert (
            validate_shortcut(operation, version="2026", profile=profile)["fallback"]
            == "governed_native_execution"
        )
