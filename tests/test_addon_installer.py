import xml.etree.ElementTree as ET
import sys
import types
from pathlib import Path

from ads_agent_bridge import addon_installer
from ads_agent_bridge.addon_installer import ADDON_NAME, addon_status, install_addon, uninstall_addon


def test_addon_install_preserves_other_entries_and_uninstalls(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    config = tmp_path / "hpeesof" / "config"
    config.mkdir(parents=True)
    source = config / "eesof_addons.xml"
    source.write_text(
        "<?xml version='1.0' encoding='utf-8'?><EESof_Addons><Addon Name='KeepMe' FilePath='/keep.py' Enabled='1'/></EESof_Addons>",
        encoding="utf-8",
    )

    result = install_addon(config, ("de",))
    root = ET.parse(source).getroot()

    assert result["status"] == "installed"
    assert [node.get("Name") for node in root.findall("Addon")] == ["KeepMe", ADDON_NAME]
    assert Path(root.findall("Addon")[1].get("FilePath", "")).is_file()
    assert addon_status(config)["profiles"][0]["registrations"][0]["Enabled"] == "1"

    removed = uninstall_addon(config, ("de",))
    assert removed["registrations"][0]["removed"] == 1
    assert [node.get("Name") for node in ET.parse(source).getroot().findall("Addon")] == ["KeepMe"]


def test_addon_install_replaces_own_registration_and_creates_backup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    config = tmp_path / "config"
    first = install_addon(config, ("dds",))
    second = install_addon(config, ("dds",))

    assert first["registrations"][0]["replaced"] == 0
    assert second["registrations"][0]["replaced"] == 1
    assert Path(second["registrations"][0]["backup"]).is_file()
    assert len(ET.parse(config / "dds_addons.xml").getroot().findall("Addon")) == 1


def test_profile_entrypoints_execute_without_dunder_file_and_dds_has_no_de_hook(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    config = tmp_path / "config"
    installed = install_addon(config, ("de", "dds"))
    fake_common = types.ModuleType("entrypoint_common")
    fake_common.setup_profile = lambda profile, addon: (profile, addon)
    fake_common.shutdown_profile = lambda addon: addon
    fake_common.generate_de_menu = lambda addon, win_def: (addon, win_def)
    monkeypatch.setitem(sys.modules, "entrypoint_common", fake_common)

    namespaces = {}
    for profile, filename in installed["entrypoints"].items():
        entrypoint = Path(filename)
        namespace = {"__name__": "AdsAgentBridge_{0}_exec_test".format(profile)}
        exec(compile(entrypoint.read_text(encoding="utf-8"), str(entrypoint), "exec"), namespace)
        namespaces[profile] = namespace

    assert callable(namespaces["de"]["setup_addon"])
    assert callable(namespaces["de"]["generate_menu"])
    assert callable(namespaces["dds"]["setup_addon"])
    assert "generate_menu" not in namespaces["dds"]
    assert "__file__" not in namespaces["de"]
    assert Path(ET.parse(config / "eesof_addons.xml").getroot().find("Addon").get("FilePath")).name == "de_entrypoint.py"
    assert Path(ET.parse(config / "dds_addons.xml").getroot().find("Addon").get("FilePath")).name == "dds_entrypoint.py"


def test_windows_default_config_prefers_ads_registry_home(tmp_path: Path, monkeypatch) -> None:
    registry_home = tmp_path / "ads-home"
    expected = registry_home / "hpeesof" / "config"
    expected.mkdir(parents=True)
    monkeypatch.setattr(addon_installer.os, "name", "nt")
    monkeypatch.setattr(addon_installer, "_windows_registry_homes", lambda: [registry_home])
    monkeypatch.delenv("ADS_AGENT_ADS_CONFIG_DIR", raising=False)

    assert addon_installer.default_ads_config_dir() == expected.resolve()
