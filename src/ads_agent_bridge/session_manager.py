from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bridge_client import list_sessions, normalize_slot, request, select_session
from .config import select_instance
from .models import AdsInstance
from .paths import _override_root
from .processes import managed_ads_processes, managed_host_processes, pid_running


DEFAULT_WAIT_SECONDS = 120.0
MANAGED_PREFIX = "managed-session-"


class SessionError(ValueError):
    """Raised when the requested ADS session state cannot be produced safely."""


def runtime_dir(*, ensure: bool = True) -> Path:
    override = _override_root(ensure=ensure)
    path = (override / "runtime") if override else (Path.home() / ".ads-agent" / "runtime")
    if ensure:
        path.mkdir(parents=True, exist_ok=True)
    return path


def looks_like_workspace(path: Path) -> bool:
    candidate = path.expanduser()
    if not candidate.is_dir():
        return False
    return (candidate / "workspace.ads").is_file() or (
        (candidate / "lib.defs").is_file() and (candidate / "cds.lib").is_file()
    )


def same_path(left: str | Path | None, right: str | Path | None) -> bool:
    if left is None or right is None:
        return False
    left_path = Path(left).expanduser().resolve()
    right_path = Path(right).expanduser().resolve()
    try:
        return left_path.samefile(right_path)
    except OSError:
        return os.path.normcase(str(left_path)) == os.path.normcase(str(right_path))


def default_slot(instance: AdsInstance) -> str:
    return normalize_slot(instance.instance_id)


def _managed_path(slot: str, *, ensure: bool = True) -> Path:
    return runtime_dir(ensure=ensure) / f"{MANAGED_PREFIX}{normalize_slot(slot)}.json"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        try:
            os.chmod(temporary_name, 0o600)
        except OSError:
            pass
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _tail_text(path: Path, max_bytes: int = 8192) -> str:
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - max_bytes), os.SEEK_SET)
            return stream.read(max_bytes).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _managed_record(slot: str) -> dict[str, Any] | None:
    return _read_json(_managed_path(slot, ensure=False))


def _managed_records() -> list[dict[str, Any]]:
    directory = runtime_dir(ensure=False)
    if not directory.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob(f"{MANAGED_PREFIX}*.json")):
        payload = _read_json(path)
        if payload is not None:
            payload["record_file"] = str(path)
            records.append(payload)
    return records


def _remove_managed_record(slot: str, managed_session_id: str) -> bool:
    path = _managed_path(slot, ensure=False)
    payload = _read_json(path)
    if payload is None or payload.get("managed_session_id") != managed_session_id:
        return False
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def _cleanup_stale_bridge_records(slot: str, managed_session_id: str) -> list[str]:
    """Remove only dead bridge records belonging to a completed managed slot."""
    normalized = normalize_slot(slot)
    removed: list[str] = []
    directory = runtime_dir(ensure=False)
    if not directory.is_dir():
        return removed
    for path in sorted(directory.glob(f"session-{normalized}-*.json")):
        payload = _read_json(path)
        if payload is None or normalize_slot(str(payload.get("slot") or "")) != normalized:
            continue
        if pid_running(payload.get("pid")):
            continue
        profile = str(payload.get("profile") or "")
        record_identity = payload.get("managed_session_id")
        if profile == "de" and record_identity != managed_session_id:
            continue
        if profile != "de" and record_identity not in {None, "", managed_session_id}:
            continue
        try:
            path.unlink()
            removed.append(str(path))
        except FileNotFoundError:
            pass
    return removed


def _live_slot_records(slot: str) -> list[dict[str, Any]]:
    normalized = normalize_slot(slot)
    directory = runtime_dir(ensure=False)
    if not directory.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob(f"session-{normalized}-*.json")):
        payload = _read_json(path)
        if payload is None or normalize_slot(str(payload.get("slot") or "")) != normalized:
            continue
        if pid_running(payload.get("pid")):
            records.append(
                {
                    "profile": payload.get("profile"),
                    "pid": payload.get("pid"),
                    "session_file": str(path),
                }
            )
    return records


@contextmanager
def _slot_operation_lock(slot: str):
    """Serialize lifecycle mutations for one slot across local client processes."""
    normalized = normalize_slot(slot)
    path = runtime_dir() / f"{MANAGED_PREFIX}{normalized}.lock"
    stream = path.open("a+b")
    try:
        if path.stat().st_size == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise SessionError(
                f"Another ADS lifecycle operation is already in progress for slot {normalized!r}."
            ) from exc
        try:
            yield
        finally:
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        stream.close()


def _live_bridge(slot: str) -> dict[str, Any] | None:
    try:
        session = select_session(slot, "de")
        response = request("ping", {}, slot, "de", timeout=1.0)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return session if response.get("ok") else None


def _bridge_status(slot: str, session: dict[str, Any] | None = None) -> dict[str, Any] | None:
    session = session or _live_bridge(slot)
    if session is None:
        return None
    try:
        response = request("status", {}, slot, "de", timeout=3.0)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}
    return response


def _identity_matches(record: dict[str, Any] | None, bridge: dict[str, Any] | None) -> bool:
    if not record or not bridge:
        return False
    recorded_pid = int(record.get("ads_pid") or 0)
    bridge_pid = int(bridge.get("pid") or 0)
    return (
        record.get("managed_session_id")
        and record.get("managed_session_id") == bridge.get("managed_session_id")
        and normalize_slot(str(record.get("slot") or "")) == normalize_slot(str(bridge.get("slot") or ""))
        and (recorded_pid == 0 or recorded_pid == bridge_pid)
    )


def _managed_process_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    """Refresh a managed Linux launch from the nonce-bearing ADS processes."""
    managed_session_id = str(record.get("managed_session_id") or "")
    slot = normalize_slot(str(record.get("slot") or ""))
    processes = managed_ads_processes(managed_session_id, slot)
    if not processes:
        return record
    refreshed = dict(record)
    refreshed["managed_processes"] = processes
    refreshed["ads_pid"] = processes[0]["pid"]
    return refreshed


def _host_ui_wait_contract(managed: dict[str, Any]) -> dict[str, Any]:
    managed_session_id = str(managed.get("managed_session_id") or "")
    slot = normalize_slot(str(managed.get("slot") or ""))
    candidate_processes = managed_host_processes(managed_session_id, slot)
    if not candidate_processes:
        candidate_processes = managed.get("managed_processes", [])
    return {
        "required": True,
        "phase": "pre-bridge",
        "reason": "managed-ads-process-alive-but-embedded-bridge-unreachable",
        "display": managed.get("display"),
        "workspace": managed.get("workspace"),
        "managed_processes": managed.get("managed_processes", []),
        "candidate_processes": candidate_processes,
        "observation": "Inspect only windows owned by the listed candidate processes.",
        "action_policy": (
            "A host Agent may inspect accessibility or a target-window image, but must not guess a "
            "license choice, click an unverified window, or relaunch the same slot."
        ),
    }


def _session_summary(slot: str, bridge: dict[str, Any] | None, managed: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_slot(slot)
    if bridge is None:
        if managed is None:
            return {"slot": normalized, "state": "absent", "ownership": "none", "reachable": False}
        managed = _managed_process_snapshot(managed)
        ads_alive = pid_running(managed.get("ads_pid"))
        launcher_alive = pid_running(managed.get("launcher_pid"))
        starting = managed.get("state") in {"starting", "waiting-for-host-ui"} and (ads_alive or launcher_alive)
        alive = ads_alive or launcher_alive
        waiting_for_host_ui = starting and ads_alive and (
            managed.get("state") == "waiting-for-host-ui" or not launcher_alive
        )
        state = (
            "waiting-for-host-ui"
            if waiting_for_host_ui
            else "starting"
            if starting
            else "degraded"
            if alive
            else "orphaned"
        )
        summary = {
            "slot": normalized,
            "state": state,
            "ownership": "agent-owned-unverified" if starting else "agent-owned-record" if alive else "orphaned-record",
            "reachable": False,
            "managed_session_id": managed.get("managed_session_id"),
            "ads_pid": managed.get("ads_pid"),
            "launcher_pid": managed.get("launcher_pid"),
            "workspace": managed.get("workspace"),
            "display": managed.get("display"),
            "log_path": managed.get("log_path"),
            "warning": (
                "A nonce-bound ADS process is alive, but its embedded bridge is not reachable; host UI inspection is required."
                if waiting_for_host_ui
                else "ADS was launched and is still waiting for its authenticated DE bridge."
                if starting
                else "Managed ADS process has no reachable DE bridge."
                if alive
                else "Managed session record is stale."
            ),
            "next_actions": (
                [
                    "Inspect only windows owned by the reported managed ADS processes on the reported display.",
                    "Resolve a verified startup dialog under the host Agent risk policy, then run status again.",
                ]
                if waiting_for_host_ui
                else ["Inspect the launch log or ADS window for a license or first-run dialog.", "Run status again after resolving it."]
                if starting
                else ["Inspect the launch log and ADS window; do not start another session in this slot."]
                if alive
                else ["The stale record can be replaced by the next launch after verifying ADS is not running."]
            ),
        }
        if waiting_for_host_ui:
            summary["host_ui"] = _host_ui_wait_contract(managed)
        if managed.get("managed_processes"):
            summary["managed_processes"] = managed["managed_processes"]
        return summary

    response = _bridge_status(normalized, bridge)
    result = (response or {}).get("result") if (response or {}).get("ok") else {}
    result = result if isinstance(result, dict) else {}
    owned = _identity_matches(managed, bridge)
    ui = result.get("ui") if isinstance(result.get("ui"), dict) else {}
    workspace_open = result.get("workspace_is_open") is True
    state = "blocked-by-dialog" if ui.get("modal_blocking") else "workspace-ready" if workspace_open else "bridge-ready"
    summary: dict[str, Any] = {
        "slot": normalized,
        "state": state,
        "ownership": "agent-owned" if owned else "user-owned",
        "reachable": bool((response or {}).get("ok")),
        "managed_session_id": bridge.get("managed_session_id"),
        "ads_pid": bridge.get("pid"),
        "workspace": result.get("workspace"),
        "workspace_is_open": result.get("workspace_is_open"),
        "display": result.get("display"),
        "modal": ui,
        "ui": ui,
        "bridge_started_at": bridge.get("started_at"),
    }
    if state == "blocked-by-dialog":
        summary["next_actions"] = [
            "Inspect the dialog with bridge dialog-snapshot or dialog-watch.",
            "Act only through its exact fingerprint and button ID under the documented risk policy, then verify status.",
        ]
    if response and not response.get("ok"):
        summary.update({"state": "degraded", "reachable": False, "error": response.get("error")})
    if managed is not None and not owned:
        summary["warning"] = "Managed record does not match the live bridge identity; treating it as user-owned."
    return summary


def status(slot: str | None = None) -> dict[str, Any]:
    managed_by_slot = {normalize_slot(str(item.get("slot") or "")): item for item in _managed_records()}
    live_by_slot = {normalize_slot(str(item.get("slot") or "")): item for item in list_sessions("de")}
    if slot is not None:
        normalized = normalize_slot(slot)
        sessions = [_session_summary(normalized, live_by_slot.get(normalized), managed_by_slot.get(normalized))]
    else:
        slots = sorted(set(live_by_slot) | set(managed_by_slot))
        sessions = [_session_summary(item, live_by_slot.get(item), managed_by_slot.get(item)) for item in slots]
    return {"status": "ok", "sessions": sessions}


def _launch_environment(instance: AdsInstance, slot: str, managed_session_id: str, display: str | None) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "HPEESOF_DIR": instance.install_root,
            "ADS_AGENT_SLOT": slot,
            "ADS_DEBUG_BRIDGE_SLOT": slot,
            "DE_DEBUG_BRIDGE_SLOT": slot,
            "DDS_DEBUG_BRIDGE_SLOT": slot,
            "ADS_AGENT_MANAGED_SESSION_ID": managed_session_id,
        }
    )
    if display:
        environment["DISPLAY"] = display
    return environment


def _wait_for_bridge(slot: str, wait_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.0, wait_seconds)
    while time.monotonic() < deadline:
        session = _live_bridge(slot)
        if session is not None:
            return session
        time.sleep(0.5)
    raise SessionError(f"Timed out waiting for the DE bridge for slot {slot!r}.")


def _verified_workspace(slot: str, expected: Path) -> dict[str, Any]:
    response = request("status", {}, slot, "de", timeout=5.0)
    result = response.get("result") if response.get("ok") else None
    result = result if isinstance(result, dict) else {}
    actual = result.get("workspace")
    return {
        "ok": response.get("ok") is True and result.get("workspace_is_open") is True and same_path(actual, expected),
        "expected": str(expected),
        "actual": actual,
        "bridge_response": response,
    }


def _reuse_session(instance: AdsInstance, slot: str, workspace: Path) -> dict[str, Any]:
    before = request("status", {}, slot, "de", timeout=5.0)
    result = before.get("result") if before.get("ok") else None
    result = result if isinstance(result, dict) else {}
    actual_install_root = result.get("hpeesof_dir")
    if not same_path(actual_install_root, instance.install_root):
        raise SessionError(
            f"Slot {slot!r} is running a different or unverifiable ADS installation: "
            f"{actual_install_root!r}; requested {instance.install_root!r}. Refusing to reuse it."
        )
    current = result.get("workspace")
    if current and not same_path(current, workspace):
        raise SessionError(
            f"Slot {slot!r} already has a different workspace open: {current}. "
            "Refusing to switch or close it."
        )
    opened = False
    if not current:
        response = request("open_workspace", {"workspace": str(workspace)}, slot, "de", timeout=60.0)
        if not response.get("ok"):
            raise SessionError(f"Could not open workspace in existing ADS session: {response.get('error')}")
        opened = True
    verification = _verified_workspace(slot, workspace)
    if not verification["ok"]:
        raise SessionError(f"Existing ADS session did not bind the requested workspace: {verification}")
    bridge = select_session(slot, "de")
    managed = _managed_record(slot)
    ownership = "agent-owned" if _identity_matches(managed, bridge) else "user-owned"
    return {
        "status": "ready",
        "launched": False,
        "reused": True,
        "opened_workspace": opened,
        "ownership": ownership,
        "instance_id": instance.instance_id,
        "actual_install_root": actual_install_root,
        "slot": slot,
        "workspace": str(workspace),
        "workspace_verification": verification,
    }


def launch(
    instance_id: str | None,
    workspace: Path,
    slot: str | None = None,
    display: str | None = None,
    wait_seconds: float = DEFAULT_WAIT_SECONDS,
    reuse_existing: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    instance = select_instance(instance_id)
    normalized_slot = normalize_slot(slot or default_slot(instance))
    with _slot_operation_lock(normalized_slot):
        return _launch_locked(
            instance,
            workspace,
            normalized_slot,
            display,
            wait_seconds,
            reuse_existing,
            dry_run,
        )


def _launch_locked(
    instance: AdsInstance,
    workspace: Path,
    normalized_slot: str,
    display: str | None,
    wait_seconds: float,
    reuse_existing: bool,
    dry_run: bool,
) -> dict[str, Any]:
    workspace = workspace.expanduser().resolve()
    if not looks_like_workspace(workspace):
        raise SessionError(
            f"Path does not look like an ADS workspace: {workspace}. "
            "Expected workspace.ads or both lib.defs and cds.lib."
        )
    if not instance.executable:
        raise SessionError(f"Selected ADS instance has no GUI executable: {instance.instance_id}")
    executable = Path(instance.executable).expanduser().resolve()
    if not executable.is_file():
        raise SessionError(f"ADS executable not found: {executable}")
    selected_display = display or os.environ.get("DISPLAY")
    if os.name != "nt" and not selected_display:
        raise SessionError("DISPLAY is required to launch GUI ADS on this platform.")

    existing = _live_bridge(normalized_slot)
    if existing is not None:
        if not reuse_existing:
            raise SessionError(
                f"Slot {normalized_slot!r} already has a live ADS session. "
                "Pass --reuse-existing to verify and reuse it."
            )
        return _reuse_session(instance, normalized_slot, workspace)
    previous = _managed_record(normalized_slot)
    if previous is not None:
        previous = _managed_process_snapshot(previous)
    if previous is not None and (
        pid_running(previous.get("ads_pid")) or pid_running(previous.get("launcher_pid"))
    ):
        raise SessionError(
            f"Slot {normalized_slot!r} already has a managed ADS launch in state "
            f"{previous.get('state') or 'unknown'!r}. Run status and resolve it before retrying."
        )
    other_live_profiles = _live_slot_records(normalized_slot)
    if other_live_profiles:
        raise SessionError(
            f"Slot {normalized_slot!r} has live non-DE bridge records: {other_live_profiles}. "
            "Refusing to claim a partially occupied slot."
        )

    managed_session_id = uuid.uuid4().hex
    command = [str(executable), str(workspace)]
    environment = _launch_environment(instance, normalized_slot, managed_session_id, selected_display)
    log_path = runtime_dir() / f"{MANAGED_PREFIX}{normalized_slot}.log"
    plan = {
        "instance_id": instance.instance_id,
        "product_version": instance.product_version,
        "slot": normalized_slot,
        "executable": str(executable),
        "workspace": str(workspace),
        "working_directory": str(workspace),
        "display": selected_display,
        "log_path": str(log_path),
        "command": command,
        "ownership": "agent-owned",
    }
    if dry_run:
        return {"status": "planned", "dry_run": True, "plan": plan}

    popen_kwargs: dict[str, Any] = {
        "cwd": str(workspace),
        "env": environment,
        "stdin": subprocess.DEVNULL,
        "stderr": subprocess.STDOUT,
    }
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True
    log_stream = log_path.open("ab", buffering=0)
    try:
        log_path.chmod(0o600)
    except OSError:
        pass
    popen_kwargs["stdout"] = log_stream
    try:
        process = subprocess.Popen(command, **popen_kwargs)
    except OSError as exc:
        raise SessionError(f"Could not start ADS: {exc}") from exc
    finally:
        log_stream.close()

    record = {
        "schema_version": 1,
        "state": "starting",
        "managed_session_id": managed_session_id,
        "ownership": "agent-owned-unverified",
        "slot": normalized_slot,
        "instance_id": instance.instance_id,
        "product_version": instance.product_version,
        "install_root": instance.install_root,
        "executable": str(executable),
        "workspace": str(workspace),
        "display": selected_display,
        "log_path": str(log_path),
        "launcher_pid": process.pid,
        "ads_pid": None,
        "bridge_started_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(_managed_path(normalized_slot), record)

    try:
        bridge = _wait_for_bridge(normalized_slot, wait_seconds)
    except SessionError as exc:
        record = _managed_process_snapshot(record)
        if record.get("managed_processes"):
            record["state"] = "waiting-for-host-ui"
            _write_json(_managed_path(normalized_slot), record)
        session = _session_summary(normalized_slot, None, record)
        return {
            "status": session.get("state") if session.get("state") == "waiting-for-host-ui" else "starting",
            "launched": True,
            "reused": False,
            "ownership": "agent-owned-unverified",
            "plan": plan,
            "session": session,
            "warning": str(exc),
            "diagnostics": {
                "log_path": str(log_path),
                "log_tail": _tail_text(log_path),
                "next_actions": [
                    "Use the session host_ui contract to inspect only nonce-bound ADS process windows.",
                    "Resolve a verified startup dialog and run status again; do not launch the same slot twice.",
                ],
            },
        }

    if bridge.get("managed_session_id") != managed_session_id:
        record.update(
            {
                "state": "ownership-unverified",
                "ownership": "unverified",
                "observed_ads_pid": bridge.get("pid"),
                "observed_managed_session_id": bridge.get("managed_session_id"),
            }
        )
        _write_json(_managed_path(normalized_slot), record)
        return {
            "status": "ownership-unverified",
            "launched": True,
            "reused": False,
            "ownership": "unverified",
            "plan": plan,
            "session": _session_summary(normalized_slot, bridge, record),
            "warning": (
                "The live bridge did not return the launch ownership nonce. Ownership was not claimed; "
                "reinstall the packaged add-on before retrying."
            ),
        }
    verification = _verified_workspace(normalized_slot, workspace)
    bridge_status = request("status", {}, normalized_slot, "de", timeout=5.0)
    record.update(
        {
            "ownership": "agent-owned",
            "ads_pid": bridge.get("pid"),
            "bridge_started_at": bridge.get("started_at"),
        }
    )
    if not verification["ok"]:
        record["state"] = "degraded"
        _write_json(_managed_path(normalized_slot), record)
        return {
            "status": "degraded",
            "launched": True,
            "reused": False,
            "ownership": "agent-owned",
            "plan": plan,
            "session": _session_summary(normalized_slot, bridge, record),
            "workspace_verification": verification,
            "bridge_status": bridge_status,
            "warning": "ADS launched but did not bind the requested workspace.",
        }

    record["state"] = "ready"
    _write_json(_managed_path(normalized_slot), record)
    session = _session_summary(normalized_slot, bridge, record)
    launch_status = "blocked" if session.get("state") == "blocked-by-dialog" else "ready"
    return {
        "status": launch_status,
        "launched": True,
        "reused": False,
        "ownership": "agent-owned",
        "plan": plan,
        "session": session,
        "workspace_verification": verification,
        "bridge_status": bridge_status,
    }


def disconnect(slot: str | None = None) -> dict[str, Any]:
    selected = normalize_slot(slot) if slot else None
    return {
        "status": "disconnected",
        "slot": selected,
        "ads_left_running": True,
        "detail": "Bridge requests are short-lived; no persistent client connection was held.",
    }


def shutdown(slot: str | None = None, wait_seconds: float = 30.0) -> dict[str, Any]:
    if slot is None:
        candidates = [
            item for item in status()["sessions"] if item.get("ownership") == "agent-owned"
        ]
        if len(candidates) != 1:
            raise SessionError(
                "Shutdown without --slot requires exactly one live agent-owned ADS session; "
                f"found {len(candidates)}."
            )
        slot = str(candidates[0]["slot"])
    normalized = normalize_slot(slot)
    with _slot_operation_lock(normalized):
        return _shutdown_locked(normalized, wait_seconds)


def _shutdown_locked(normalized: str, wait_seconds: float) -> dict[str, Any]:
    managed = _managed_record(normalized)
    bridge = _live_bridge(normalized)
    summary = _session_summary(normalized, bridge, managed)
    if summary.get("ownership") != "agent-owned":
        raise SessionError(
            f"Refusing to close slot {normalized!r}: ownership is {summary.get('ownership')!r}, not agent-owned."
        )
    modal = summary.get("modal") if isinstance(summary.get("modal"), dict) else {}
    if modal.get("modal_blocking"):
        raise SessionError(
            f"Refusing to close slot {normalized!r} while a modal dialog is active: "
            f"{modal.get('title') or modal.get('class_name') or 'unknown dialog'}"
        )
    assert managed is not None
    managed_session_id = str(managed["managed_session_id"])
    try:
        response = request("safe_shutdown", {}, normalized, "de", timeout=10.0)
    except OSError as exc:
        if pid_running(managed.get("ads_pid")):
            raise SessionError(f"ADS did not acknowledge the safe shutdown request: {exc}") from exc
        response = {"ok": True, "result": {"accepted": True, "bridge_disconnected_during_exit": True}}
    if not response.get("ok"):
        raise SessionError(f"ADS rejected the safe shutdown request: {response.get('error')}")
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    if result.get("accepted") is not True:
        return {
            "status": "blocked" if result.get("reason") == "modal_dialog_active" else "cancelled",
            "slot": normalized,
            "ownership": "agent-owned",
            "ads_left_running": True,
            "bridge_response": response,
        }

    deadline = time.monotonic() + max(0.0, wait_seconds)
    last_runtime_status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        if (
            not pid_running(managed.get("ads_pid"))
            and _live_bridge(normalized) is None
            and not _live_slot_records(normalized)
        ):
            stale_records_removed = _cleanup_stale_bridge_records(normalized, managed_session_id)
            removed = _remove_managed_record(normalized, managed_session_id)
            return {
                "status": "exited",
                "slot": normalized,
                "ownership": "agent-owned",
                "record_removed": removed,
                "stale_bridge_records_removed": stale_records_removed,
                "bridge_response": response,
            }
        live = _live_bridge(normalized)
        runtime_response = _bridge_status(normalized, live) if live is not None else None
        runtime_result = (
            runtime_response.get("result")
            if isinstance(runtime_response, dict) and runtime_response.get("ok") is True
            else None
        )
        if isinstance(runtime_result, dict):
            last_runtime_status = runtime_result
            shutdown_state = runtime_result.get("shutdown")
            shutdown_state = shutdown_state if isinstance(shutdown_state, dict) else {}
            if shutdown_state.get("state") == "cancelled":
                return {
                    "status": "cancelled",
                    "slot": normalized,
                    "ownership": "agent-owned",
                    "ads_left_running": True,
                    "record_retained": True,
                    "shutdown": shutdown_state,
                    "bridge_response": response,
                }
            if shutdown_state.get("state") == "failed":
                raise SessionError(
                    f"ADS failed during safe shutdown: {shutdown_state.get('error') or 'unknown error'}"
                )
        time.sleep(0.5)
    shutdown_state = last_runtime_status.get("shutdown")
    shutdown_state = shutdown_state if isinstance(shutdown_state, dict) else {}
    ui = last_runtime_status.get("ui")
    ui = ui if isinstance(ui, dict) else {}
    awaiting_user = shutdown_state.get("state") == "prompting" or ui.get("modal_blocking") is True
    return {
        "status": "awaiting-user-action" if awaiting_user else "closing",
        "slot": normalized,
        "ownership": "agent-owned",
        "ads_pid": managed.get("ads_pid"),
        "record_retained": True,
        "live_slot_records": _live_slot_records(normalized),
        "bridge_response": response,
        "shutdown": shutdown_state,
        "ui": ui,
        "warning": (
            "ADS is waiting for the user to resolve its native save or modal dialog; no controls were clicked automatically."
            if awaiting_user
            else "ADS accepted the safe exit request but has not exited before the timeout; no force termination was attempted."
        ),
    }
