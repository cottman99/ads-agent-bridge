from __future__ import annotations

import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Any

from .paths import data_dir


ADDON_NAME = "AdsAgentBridge"
CONFIG_FILES = {"de": "eesof_addons.xml", "dds": "dds_addons.xml"}


def default_ads_config_dir() -> Path:
    explicit = os.environ.get("ADS_AGENT_ADS_CONFIG_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if os.name == "nt":
        registry_homes = _windows_registry_homes()
        candidates = [home / "hpeesof" / "config" for home in registry_homes]
        for candidate in candidates:
            if candidate.is_dir():
                return candidate.resolve()
        if candidates:
            return candidates[0].resolve()
        home = Path(os.environ.get("USERPROFILE") or Path.home())
    else:
        home = Path(os.environ.get("HOME") or Path.home())
    return (home / "hpeesof" / "config").resolve()


def _windows_registry_homes() -> list[Path]:
    """Return ADS eeenv HOME values, newest ADS registry generation first."""
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    records: list[tuple[tuple[int, ...], Path]] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Keysight\ADS") as root:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(root, index)
                except OSError:
                    break
                index += 1
                if re.fullmatch(r"\d+(?:\.\d+)+", name) is None:
                    continue
                try:
                    with winreg.OpenKey(root, name + r"\eeenv") as eeenv:
                        value, _ = winreg.QueryValueEx(eeenv, "HOME")
                except OSError:
                    continue
                if isinstance(value, str) and value.strip():
                    records.append((tuple(int(part) for part in name.split(".")), Path(value.strip())))
    except OSError:
        return []
    result: list[Path] = []
    seen: set[str] = set()
    for _, home in sorted(records, key=lambda item: item[0], reverse=True):
        key = os.path.normcase(str(home))
        if key not in seen:
            seen.add(key)
            result.append(home)
    return result


def install_addon(config_directory: Path | None = None, profiles: tuple[str, ...] = ("de", "dds")) -> dict[str, Any]:
    addon_dir = data_dir() / "addons" / ADDON_NAME
    # Resolve from the inert parent package so installer-side use never imports
    # the embedded Qt runtime outside ADS.
    source = files("ads_agent_bridge.addon").joinpath("AdsAgentBridge")
    addon_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for item in source.iterdir():
        if item.name.endswith(".py"):
            target = addon_dir / item.name
            with item.open("rb") as input_stream, target.open("wb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream)
            copied.append(str(target))
    entrypoint = (addon_dir / "__init__.py").resolve()
    config_dir = (config_directory or default_ads_config_dir()).expanduser().resolve()
    config_dir.mkdir(parents=True, exist_ok=True)
    records = [_upsert(config_dir / CONFIG_FILES[profile], entrypoint) for profile in profiles]
    return {"status": "installed", "addon": ADDON_NAME, "entrypoint": str(entrypoint), "copied": copied, "registrations": records}


def addon_status(config_directory: Path | None = None) -> dict[str, Any]:
    config_dir = (config_directory or default_ads_config_dir()).expanduser().resolve()
    records = []
    for profile, filename in CONFIG_FILES.items():
        path = config_dir / filename
        matches = _matching_nodes(path)
        records.append({"profile": profile, "config": str(path), "exists": path.is_file(), "registrations": matches})
    return {"addon": ADDON_NAME, "config_dir": str(config_dir), "profiles": records}


def uninstall_addon(config_directory: Path | None = None, profiles: tuple[str, ...] = ("de", "dds")) -> dict[str, Any]:
    config_dir = (config_directory or default_ads_config_dir()).expanduser().resolve()
    records = [_remove(config_dir / CONFIG_FILES[profile]) for profile in profiles]
    return {"status": "uninstalled", "addon": ADDON_NAME, "registrations": records}


def _root(path: Path) -> ET.Element:
    if not path.is_file():
        return ET.Element("EESof_Addons")
    root = ET.parse(path).getroot()
    if root.tag != "EESof_Addons":
        raise ValueError(f"Unexpected ADS addon root element in {path}: {root.tag}")
    return root


def _upsert(path: Path, entrypoint: Path) -> dict[str, Any]:
    root = _root(path)
    before = [node for node in root.findall("Addon") if node.get("Name") == ADDON_NAME]
    for node in before:
        root.remove(node)
    ET.SubElement(root, "Addon", {"Name": ADDON_NAME, "FilePath": str(entrypoint), "Enabled": "1"})
    backup = _atomic_xml_write(path, root)
    return {"config": str(path), "replaced": len(before), "backup": str(backup) if backup else None}


def _remove(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"config": str(path), "removed": 0, "backup": None}
    root = _root(path)
    nodes = [node for node in root.findall("Addon") if node.get("Name") == ADDON_NAME]
    for node in nodes:
        root.remove(node)
    backup = _atomic_xml_write(path, root) if nodes else None
    return {"config": str(path), "removed": len(nodes), "backup": str(backup) if backup else None}


def _matching_nodes(path: Path) -> list[dict[str, str | None]]:
    if not path.is_file():
        return []
    return [dict(node.attrib) for node in _root(path).findall("Addon") if node.get("Name") == ADDON_NAME]


def _atomic_xml_write(path: Path, root: ET.Element) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.is_file():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_name(f"{path.name}.bak.{timestamp}")
        shutil.copy2(path, backup)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        tree.write(temporary, encoding="utf-8", xml_declaration=True)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return backup
