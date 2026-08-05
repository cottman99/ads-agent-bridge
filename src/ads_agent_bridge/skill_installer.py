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


SKILL_NAME = "ads-kb-docs"
OWNER = "ads-agent-bridge"
MARKER_NAME = ".ads-agent-bridge.json"


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


def _source_files() -> dict[str, bytes]:
    root = files("ads_agent_bridge").joinpath("skill_assets", SKILL_NAME)
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


def skill_status(*, target: str = "codex", root: Path | None = None) -> dict[str, Any]:
    skill_root = (root or default_skill_root(target)).expanduser().resolve()
    destination = skill_root / SKILL_NAME
    expected = _source_files()
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
    else:
        state = "stale" if marker and marker.get("owner") == OWNER else "conflict"
    return {
        "status": state,
        "skill": SKILL_NAME,
        "target": target,
        "path": str(destination),
        "managed": bool(marker and marker.get("owner") == OWNER),
        "expected_digest": _digest(expected),
        "installed_digest": _digest(actual) if actual is not None else None,
    }


def install_docs_skill(
    *,
    target: str = "codex",
    root: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    state = skill_status(target=target, root=root)
    destination = Path(state["path"])
    if state["status"] == "ready":
        return {**state, "reused": True}
    if destination.exists() and not force:
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
        backup = backup_root / f"{SKILL_NAME}-{_backup_stamp()}"
        shutil.move(str(destination), str(backup))

    temporary = Path(tempfile.mkdtemp(prefix=f".{SKILL_NAME}.", dir=destination.parent))
    try:
        for relative, content in _source_files().items():
            output = temporary / Path(relative)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
        marker = {
            "schema_version": 1,
            "owner": OWNER,
            "skill": SKILL_NAME,
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
        **skill_status(target=target, root=root),
        "reused": False,
        "backup": str(backup) if backup else None,
    }


def uninstall_docs_skill(*, target: str = "codex", root: Path | None = None) -> dict[str, Any]:
    state = skill_status(target=target, root=root)
    destination = Path(state["path"])
    if state["status"] == "missing":
        return {**state, "removed": False}
    if not state["managed"]:
        raise ValueError(f"Refusing to remove an unmanaged skill directory: {destination}")
    backup_root = destination.parent / ".ads-agent-backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / f"{SKILL_NAME}-removed-{_backup_stamp()}"
    shutil.move(str(destination), str(backup))
    return {
        "status": "removed",
        "skill": SKILL_NAME,
        "target": target,
        "path": str(destination),
        "removed": True,
        "backup": str(backup),
    }
