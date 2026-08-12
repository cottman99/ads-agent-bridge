from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Any


OWNER = "ads-agent-bridge"
MARKER_NAME = ".ads-agent-bridge.json"
SKILL_ALIASES = {
    "bridge": "ads-agent-bridge",
    "docs": "ads-kb-docs",
}


def _backup_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")


def _codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser().resolve() if configured else Path.home() / ".codex"


def default_skill_root(target: str = "codex") -> Path:
    if target == "codex":
        return _codex_home() / "skills"
    if target == "agents":
        return Path.home() / ".agents" / "skills"
    raise ValueError(f"Unknown skill target: {target}")


def _selected_skill_names(selection: str) -> tuple[str, ...]:
    if selection == "all":
        return tuple(SKILL_ALIASES.values())
    try:
        return (SKILL_ALIASES[selection],)
    except KeyError as exc:
        choices = ", ".join(("all", *SKILL_ALIASES))
        raise ValueError(f"Unknown skill selection {selection!r}; choose one of: {choices}") from exc


def _source_files(skill_name: str) -> dict[str, bytes]:
    root = files("ads_agent_bridge").joinpath("skill_assets", skill_name)
    payload: dict[str, bytes] = {}
    for relative in ("SKILL.md", "agents/openai.yaml"):
        payload[relative] = root.joinpath(*relative.split("/")).read_bytes()
    return payload


def _digest(payload: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(payload.items()):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def _installed_files(path: Path) -> dict[str, bytes] | None:
    payload: dict[str, bytes] = {}
    for relative in ("SKILL.md", "agents/openai.yaml"):
        candidate = path / Path(relative)
        if not candidate.is_file():
            return None
        payload[relative] = candidate.read_bytes()
    return payload


def _declares_skill_name(path: Path, expected_name: str) -> bool:
    try:
        lines = (path / "SKILL.md").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return False
    if not lines or lines[0].strip() != "---":
        return False
    for line in lines[1:]:
        if line.strip() == "---":
            return False
        key, separator, value = line.partition(":")
        if separator and key.strip() == "name":
            return value.strip().strip("\"'") == expected_name
    return False


def _single_status(
    skill_name: str,
    *,
    target: str,
    root: Path | None,
) -> dict[str, Any]:
    skill_root = (root or default_skill_root(target)).expanduser().resolve()
    destination = skill_root / skill_name
    expected = _source_files(skill_name)
    actual = _installed_files(destination) if destination.is_dir() else None
    marker_path = destination / MARKER_NAME
    marker: dict[str, Any] | None = None
    if marker_path.is_file():
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            marker = None
    if actual is None:
        state = "missing" if not destination.exists() else "conflict"
    elif _digest(actual) == _digest(expected):
        state = "ready"
    elif (
        not marker_path.exists()
        and skill_name == "ads-kb-docs"
        and _declares_skill_name(destination, skill_name)
    ):
        state = "compatible"
    else:
        state = "stale" if marker and marker.get("owner") == OWNER else "conflict"
    return {
        "status": state,
        "skill": skill_name,
        "target": target,
        "path": str(destination),
        "managed": bool(
            marker
            and marker.get("owner") == OWNER
            and marker.get("skill") == skill_name
        ),
        "expected_digest": _digest(expected),
        "installed_digest": _digest(actual) if actual is not None else None,
    }


def _aggregate_status(results: list[dict[str, Any]]) -> str:
    states = {str(item.get("status")) for item in results}
    if states <= {"ready", "compatible", "preserved"}:
        return "ready"
    if "conflict" in states:
        return "conflict"
    if "stale" in states:
        return "stale"
    if states == {"missing"}:
        return "missing"
    if states == {"removed"}:
        return "removed"
    return "partial"


def skill_status(
    selection: str = "all",
    *,
    target: str = "codex",
    root: Path | None = None,
) -> dict[str, Any]:
    names = _selected_skill_names(selection)
    results = [_single_status(name, target=target, root=root) for name in names]
    if len(results) == 1:
        return results[0]
    return {
        "status": _aggregate_status(results),
        "selection": selection,
        "target": target,
        "skills": results,
    }


def _install_one(
    skill_name: str,
    *,
    target: str,
    root: Path | None,
    force: bool,
    preserve_complete_unmanaged: bool,
) -> dict[str, Any]:
    state = _single_status(skill_name, target=target, root=root)
    destination = Path(state["path"])
    if state["status"] == "ready":
        return {**state, "reused": True}
    if destination.exists() and not force:
        complete_unmanaged = (
            _installed_files(destination) is not None
            and _declares_skill_name(destination, skill_name)
            and not state["managed"]
        )
        if preserve_complete_unmanaged and complete_unmanaged:
            return {
                **state,
                "status": "preserved",
                "reused": True,
                "satisfied_by_existing": True,
                "reason": "A complete unmanaged skill already owns this name and was preserved.",
            }
        return {
            **state,
            "status": "conflict",
            "reused": False,
            "remediation": f"Review {destination}, then rerun with --force to create a backup and replace it.",
        }

    destination.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if destination.exists():
        backup_root = destination.parent / ".ads-agent-backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup = backup_root / f"{skill_name}-{_backup_stamp()}"
        shutil.move(str(destination), str(backup))

    temporary = Path(tempfile.mkdtemp(prefix=f".{skill_name}.", dir=destination.parent))
    try:
        for relative, content in _source_files(skill_name).items():
            output = temporary / Path(relative)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
        marker = {
            "schema_version": 1,
            "owner": OWNER,
            "skill": skill_name,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "digest": state["expected_digest"],
        }
        (temporary / MARKER_NAME).write_text(
            json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {
        **_single_status(skill_name, target=target, root=root),
        "reused": False,
        "backup": str(backup) if backup else None,
    }


def install_skills(
    selection: str = "all",
    *,
    target: str = "codex",
    root: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    names = _selected_skill_names(selection)
    results = [
        _install_one(
            name,
            target=target,
            root=root,
            force=force,
            preserve_complete_unmanaged=selection == "all" and name == "ads-kb-docs",
        )
        for name in names
    ]
    if len(results) == 1:
        return results[0]
    return {
        "status": _aggregate_status(results),
        "selection": selection,
        "target": target,
        "skills": results,
    }


def _uninstall_one(
    skill_name: str,
    *,
    target: str,
    root: Path | None,
    preserve_unmanaged: bool,
) -> dict[str, Any]:
    state = _single_status(skill_name, target=target, root=root)
    destination = Path(state["path"])
    if state["status"] == "missing":
        return {**state, "removed": False}
    if not state["managed"]:
        if preserve_unmanaged:
            return {
                **state,
                "status": "preserved",
                "removed": False,
                "reason": "Unmanaged skill content was preserved.",
            }
        raise ValueError(f"Refusing to remove an unmanaged skill directory: {destination}")
    backup_root = destination.parent / ".ads-agent-backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / f"{skill_name}-removed-{_backup_stamp()}"
    shutil.move(str(destination), str(backup))
    return {
        "status": "removed",
        "skill": skill_name,
        "target": target,
        "path": str(destination),
        "removed": True,
        "backup": str(backup),
    }


def uninstall_skills(
    selection: str = "all",
    *,
    target: str = "codex",
    root: Path | None = None,
) -> dict[str, Any]:
    names = _selected_skill_names(selection)
    results = [
        _uninstall_one(
            name,
            target=target,
            root=root,
            preserve_unmanaged=selection == "all",
        )
        for name in names
    ]
    if len(results) == 1:
        return results[0]
    return {
        "status": _aggregate_status(results),
        "selection": selection,
        "target": target,
        "skills": results,
    }
