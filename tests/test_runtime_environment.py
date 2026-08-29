import os

from ads_agent_bridge.runtime_environment import ads_runtime_environment


def test_linux_ads_environment_covers_em_plugin_and_preserves_parent_paths(tmp_path):
    root = tmp_path / "ADS2026_Update2.1"
    environment = ads_runtime_environment(
        root,
        environment={"PATH": "parent-bin", "LD_LIBRARY_PATH": "parent-lib"},
        platform_name="linux",
    )

    assert environment["HPEESOF_DIR"] == str(root)
    assert environment["PATH"].split(os.pathsep) == [str(root / "bin"), "parent-bin"]
    assert environment["LD_LIBRARY_PATH"].split(os.pathsep) == [
        str(root / "bin" / "plugins" / "pde_core"),
        str(root / "tools" / "python" / "lib"),
        str(root / "tools" / "python" / "lib64"),
        str(root / "lib" / "linux_x86_64"),
        str(root / "lib" / "linux_x86"),
        "parent-lib",
    ]


def test_windows_ads_environment_does_not_invent_linux_loader_state(tmp_path):
    environment = ads_runtime_environment(
        tmp_path / "ADS2026_Update2",
        environment={"PATH": "parent-bin"},
        platform_name="win32",
    )

    assert "LD_LIBRARY_PATH" not in environment
