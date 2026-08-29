"""Bounded creation and opaque Runtime context for ADS workspaces."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Any

from .bridge_client import runtime_dir
from .config import select_instance

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")


def _context_path(context_id: str) -> Path:
    root = runtime_dir() / "contexts"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{context_id}.json"


def _write_context(target: dict[str, Any]) -> tuple[str, int]:
    stable = json.dumps(
        {
            key: target.get(key)
            for key in ("workspace", "top_design", "slot", "profile")
        },
        sort_keys=True,
    )
    context_id = "ctx_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:20]
    path = _context_path(context_id)
    generation = 1
    if path.is_file():
        try:
            generation = (
                int(json.loads(path.read_text(encoding="utf-8"))["generation"]) + 1
            )
        except (OSError, ValueError, KeyError, TypeError):
            pass
    payload = {
        "schema_version": 1,
        "generation": generation,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "target": target,
    }
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return context_id, generation


def resolve_context(context_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"ctx_[A-Fa-f0-9]{20}", context_id):
        raise ValueError("invalid ADS Runtime context id")
    path = _context_path(context_id)
    if not path.is_file():
        raise ValueError("ADS Runtime context is unavailable on this host")
    return json.loads(path.read_text(encoding="utf-8"))


def create_workspace(
    *,
    workspace: str | Path,
    library: str,
    cell: str,
    instance_id: str | None,
    slot: str | None,
    profile: str,
    connection_id: str | None,
    expected_display: str | None,
    timeout: float,
) -> dict[str, Any]:
    if profile != "de":
        raise ValueError("workspace.create requires the ADS DE profile")
    if not _NAME.fullmatch(library) or not _NAME.fullmatch(cell):
        raise ValueError("library and cell must be simple ADS identifiers")
    actual_display = os.environ.get("DISPLAY")
    if expected_display and actual_display != expected_display:
        raise RuntimeError(
            f"Configured DISPLAY mismatch: expected {expected_display}, got {actual_display}"
        )
    workspace_path = Path(workspace).expanduser().resolve()
    if workspace_path.exists():
        raise FileExistsError(
            f"Refusing to overwrite an existing workspace: {workspace_path}"
        )
    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    instance = select_instance(instance_id)
    if not instance.python_executable:
        raise RuntimeError(
            f"ADS Python was not discovered for {instance.product_version}"
        )
    runner = files("ads_agent_bridge").joinpath("minimal_workspace.py")
    command = [
        instance.python_executable,
        str(runner),
        "--workspace",
        str(workspace_path),
        "--library",
        library,
        "--cell",
        cell,
    ]
    environment = os.environ.copy()
    environment["HPEESOF_DIR"] = instance.install_root
    environment["PATH"] = (
        str(Path(instance.install_root) / "bin")
        + os.pathsep
        + environment.get("PATH", "")
    )
    if sys.platform.startswith("linux"):
        libraries = [
            str(Path(instance.install_root) / "tools" / "python" / "lib"),
            str(Path(instance.install_root) / "tools" / "python" / "lib64"),
            str(Path(instance.install_root) / "lib" / "linux_x86_64"),
            str(Path(instance.install_root) / "lib" / "linux_x86"),
        ]
        if environment.get("LD_LIBRARY_PATH"):
            libraries.append(environment["LD_LIBRARY_PATH"])
        environment["LD_LIBRARY_PATH"] = os.pathsep.join(libraries)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
            cwd=str(workspace_path.parent),
            check=False,
        )
        record = None
        for line in reversed((completed.stdout or "").splitlines()):
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and "ok" in candidate:
                record = candidate
                break
        if completed.returncode or not record or not record.get("ok"):
            detail = (record or {}).get("error") or (completed.stderr or "")[-1000:]
            raise RuntimeError(f"ADS workspace creation failed: {detail}")
    except Exception:
        if workspace_path.is_dir():
            shutil.rmtree(workspace_path, ignore_errors=True)
        elif workspace_path.exists():
            workspace_path.unlink(missing_ok=True)
        raise
    top_design = str(record["top_design"])
    selected_slot = slot or instance.instance_id
    target = {
        "connection_id": connection_id,
        "slot": selected_slot,
        "profile": profile,
        "instance": instance.instance_id,
        "workspace": str(workspace_path),
        "top_design": top_design,
        "display": actual_display,
    }
    context_id, generation = _write_context(target)
    from eda_bridge_runtime import EDAContext, capability_digest, stable_origin_id

    locator = {"context_id": context_id, "slot": selected_slot, "profile": profile}
    if connection_id:
        locator["connection_id"] = connection_id
    capability_states = {name: "available" for name in ("open", "inspect", "edit", "simulate")}
    token = EDAContext(
        eda="keysight-ads",
        target_kind="workspace",
        locator={key: value for key, value in locator.items() if value},
        display_name=f"{workspace_path.name}:{top_design}",
        generation=generation,
        capabilities_hint=tuple(capability_states),
        origin={"origin_id": stable_origin_id("keysight-ads")},
        session={
            "session_id": None,
            "display": actual_display,
            "profile": profile,
            "state": "not-launched",
        },
        target={
            "workspace": workspace_path.name,
            "top_design": top_design,
            "instance": instance.instance_id,
        },
        capabilities={
            "states": capability_states,
            "digest": capability_digest(capability_states),
        },
        freshness={"scope": "durable", "generation": generation, "state": "reopenable"},
    ).encode()
    return {
        "status": "passed",
        "created": True,
        "workspace": workspace_path.name,
        "top_design": top_design,
        "display": actual_display,
        "eda_context": token,
        "context_id": context_id,
    }
