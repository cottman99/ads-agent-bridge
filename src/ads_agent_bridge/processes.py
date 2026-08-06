from __future__ import annotations

import os
from pathlib import Path
from typing import Any


LINUX_ADS_PROCESS_NAMES = {"hpeesofde", "hpeesofemx"}


def pid_running(value: object) -> bool:
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_running(pid)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _windows_pid_running(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def managed_ads_processes(managed_session_id: str, slot: str) -> list[dict[str, Any]]:
    """Return Linux ADS processes carrying the exact managed launch identity.

    The public ``ads`` executable may be a short-lived wrapper.  Its real
    ``hpeesofemx`` and ``hpeesofde`` children inherit the session nonce and
    slot, then may be re-parented after the wrapper exits.  Matching both
    environment values avoids claiming unrelated ADS processes.
    """
    if os.name == "nt" or not managed_session_id or not slot:
        return []
    return _linux_managed_ads_processes(managed_session_id, slot)


def managed_host_processes(managed_session_id: str, slot: str) -> list[dict[str, Any]]:
    """Return all Linux processes carrying the exact managed launch identity.

    This broader inventory is observation-only.  It includes separate-process
    UI helpers such as the ADS product selector, but it is never used as proof
    that the primary ADS runtime is alive or agent-owned.
    """
    if os.name == "nt" or not managed_session_id or not slot:
        return []
    return _linux_managed_host_processes(managed_session_id, slot)


def _linux_managed_ads_processes(
    managed_session_id: str,
    slot: str,
    *,
    proc_root: Path = Path("/proc"),
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return matches
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            process_name = (entry / "comm").read_text(encoding="utf-8", errors="replace").strip()
            if process_name not in LINUX_ADS_PROCESS_NAMES:
                continue
            environment = _parse_linux_environment((entry / "environ").read_bytes())
        except OSError:
            continue
        if environment.get("ADS_AGENT_MANAGED_SESSION_ID") != managed_session_id:
            continue
        if environment.get("ADS_AGENT_SLOT") != slot:
            continue
        matches.append(
            {
                "pid": int(entry.name),
                "process_name": process_name,
                "role": "design-environment" if process_name == "hpeesofde" else "ads-runtime",
            }
        )
    matches.sort(key=lambda item: (item["process_name"] != "hpeesofde", item["pid"]))
    return matches


def _linux_managed_host_processes(
    managed_session_id: str,
    slot: str,
    *,
    proc_root: Path = Path("/proc"),
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return matches
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            environment = _parse_linux_environment((entry / "environ").read_bytes())
            if environment.get("ADS_AGENT_MANAGED_SESSION_ID") != managed_session_id:
                continue
            if environment.get("ADS_AGENT_SLOT") != slot:
                continue
            process_name = (entry / "comm").read_text(encoding="utf-8", errors="replace").strip()
            parent_pid = _linux_parent_pid(entry / "status")
        except OSError:
            continue
        role = (
            "design-environment"
            if process_name == "hpeesofde"
            else "ads-runtime"
            if process_name == "hpeesofemx"
            else "managed-child"
        )
        matches.append(
            {
                "pid": int(entry.name),
                "parent_pid": parent_pid,
                "process_name": process_name,
                "role": role,
            }
        )
    priority = {"design-environment": 0, "ads-runtime": 1, "managed-child": 2}
    matches.sort(key=lambda item: (priority[item["role"]], item["pid"]))
    return matches


def _linux_parent_pid(status_path: Path) -> int | None:
    for line in status_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("PPid:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def _parse_linux_environment(payload: bytes) -> dict[str, str]:
    environment: dict[str, str] = {}
    for raw_item in payload.split(b"\0"):
        if not raw_item or b"=" not in raw_item:
            continue
        raw_key, raw_value = raw_item.split(b"=", 1)
        key = raw_key.decode("utf-8", errors="replace")
        if key not in {"ADS_AGENT_MANAGED_SESSION_ID", "ADS_AGENT_SLOT"}:
            continue
        environment[key] = raw_value.decode("utf-8", errors="replace")
    return environment
