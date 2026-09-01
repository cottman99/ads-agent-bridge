from pathlib import Path

from eda_bridge_runtime import validate_experience_library

from ads_agent_bridge.experience_shortcuts import validate_shortcut


def test_packaged_experience_library_and_all_compiled_shortcuts_match():
    root = Path(__file__).parents[1] / "src" / "ads_agent_bridge" / "experience_assets"
    manifest = validate_experience_library(root)

    assert len(manifest["assets"]) == 5
    assert any(
        item["id"] == "ads.native.circuit-simulate-and-validate"
        for item in manifest["assets"]
    )
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
