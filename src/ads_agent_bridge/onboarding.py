from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from importlib.resources import files
from pathlib import Path

from .addon_installer import addon_status, install_addon
from .config import select_instance, update_instances
from .discovery import discover
from .docs_kb import ensure_fast_index, query, start_background_build
from .paths import data_dir
from .skill_installer import install_docs_skill


def setup(
    *,
    roots: list[Path],
    search_roots: list[Path],
    non_interactive: bool,
    config_dir: Path | None = None,
    install_skill: bool = False,
    start_docs_build: bool = False,
) -> dict[str, object]:
    instances = discover(roots, search_roots)
    if not instances:
        raise ValueError("No ADS installation found. Pass --ads-root with the installation directory.")
    if len(instances) == 1:
        selected = instances[0]
    elif non_interactive:
        choices = ", ".join(item.instance_id for item in instances)
        raise ValueError(f"Multiple ADS installations found ({choices}). Pass one --ads-root or run interactively.")
    else:
        print("Discovered ADS installations:")
        for index, instance in enumerate(instances, start=1):
            print(f"  {index}. {instance.product_version} [{instance.support_tier}] {instance.install_root}")
        raw = input("Select the default ADS installation [1]: ").strip() or "1"
        try:
            selected = instances[int(raw) - 1]
        except (ValueError, IndexError) as exc:
            raise ValueError("Invalid ADS installation selection.") from exc
    config = update_instances(instances, selected.instance_id)
    docs = (
        ensure_fast_index(selected)
        if selected.capabilities.get("local_docs")
        else {"status": "not_available", "reason": "No installed local HTML documentation was discovered."}
    )
    docs_build = None
    if start_docs_build and selected.capabilities.get("local_docs"):
        try:
            docs_build = start_background_build(selected)
        except (OSError, ValueError) as exc:
            docs_build = {"status": "failed_to_start", "error": str(exc)}
    addon = (
        install_addon(config_dir)
        if selected.capabilities.get("python_addon_generation") == "available"
        else {
            "status": "skipped",
            "reason": "This ADS generation does not advertise Python add-on support; headless Python may still be tried.",
        }
    )
    skill = install_docs_skill() if install_skill else {"status": "skipped", "reason": "Skill installation not requested."}
    return {
        "status": "ready",
        "selected_instance": selected.to_dict(),
        "config": config,
        "docs": docs,
        "docs_build": docs_build,
        "addon": addon,
        "docs_skill": skill,
        "bridge": (
            "installed; starts when ADS DE or DDS is launched"
            if addon["status"] == "installed"
            else "not installed for this ADS generation"
        ),
        "next": ["ads-agent examples list", "ads-agent quickstart"],
    }


def quickstart(
    instance_id: str | None = None,
    workspace: Path | None = None,
    timeout: float = 300,
    config_dir: Path | None = None,
) -> tuple[dict[str, object], int]:
    instance = select_instance(instance_id)
    if not instance.python_executable:
        raise ValueError(f"ADS Python was not discovered for {instance.product_version}")

    quickstart_root = data_dir() / "quickstarts"
    quickstart_root.mkdir(parents=True, exist_ok=True)
    selected_workspace = (workspace or (quickstart_root / time.strftime("minimal-ac-%Y%m%d-%H%M%S"))).expanduser().resolve()
    if selected_workspace.exists():
        raise ValueError(f"Quickstart workspace already exists: {selected_workspace}")
    if instance.capabilities.get("local_docs"):
        docs = ensure_fast_index(instance)
        probe = query(instance, "Python", limit=3)
    else:
        docs = {"status": "not_available", "reason": "No installed local HTML documentation was discovered."}
        probe = {"results": []}
    runner = files("ads_agent_bridge").joinpath("quickstart_circuit.py")
    command = [instance.python_executable, str(runner), "--workspace", str(selected_workspace)]
    environment = os.environ.copy()
    environment["HPEESOF_DIR"] = instance.install_root
    environment["PATH"] = str(Path(instance.install_root) / "bin") + os.pathsep + environment.get("PATH", "")
    if sys.platform.startswith("linux"):
        linux_libraries = [
            str(Path(instance.install_root) / "tools" / "python" / "lib"),
            str(Path(instance.install_root) / "tools" / "python" / "lib64"),
            str(Path(instance.install_root) / "lib" / "linux_x86_64"),
            str(Path(instance.install_root) / "lib" / "linux_x86"),
        ]
        if environment.get("LD_LIBRARY_PATH"):
            linux_libraries.append(environment["LD_LIBRARY_PATH"])
        environment["LD_LIBRARY_PATH"] = os.pathsep.join(linux_libraries)
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
        cwd=str(quickstart_root),
    )
    simulation: dict[str, object] = {
        "ok": False,
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }
    for line in reversed(completed.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and "ok" in candidate:
            simulation.update(candidate)
            break
    documentation_available = docs.get("status") != "not_available"
    addon = addon_status(config_dir)
    addon_installed = any(item["registrations"] for item in addon["profiles"])
    addon_required = instance.capabilities.get("python_addon_generation") == "available"
    ok = (
        bool(simulation.get("ok"))
        and (bool(probe["results"]) or not documentation_available)
        and (addon_installed or not addon_required)
    )
    payload = {
        "status": "passed" if ok else "failed",
        "instance": instance.to_dict(),
        "gates": {
            "documentation_index": "passed" if documentation_available else "not_available",
            "documentation_query": "passed" if probe["results"] else "not_available" if not documentation_available else "no_results",
            "addon_registration": "installed" if addon_installed else "not_required" if not addon_required else "not_installed",
            "workspace_creation": "passed" if simulation.get("workspace") else "failed",
            "circuit_simulation": "passed" if simulation.get("ok") else "failed",
            "dataset_readback": "passed" if simulation.get("rows", 0) else "failed",
        },
        "docs": docs,
        "query_result_count": len(probe["results"]),
        "simulation": simulation,
    }
    return payload, 0 if ok else 2
