from __future__ import annotations

import os
from pathlib import Path
from typing import Any


LINUX_ADS_PROCESS_NAMES = {"hpeesofde", "hpeesofemx"}
WINDOWS_ADS_PROCESS_NAMES = {"hpeesofde.exe", "hpeesofemx.exe"}


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


def managed_ads_processes(
    managed_session_id: str,
    slot: str,
    launcher_pid: int | None = None,
) -> list[dict[str, Any]]:
    """Return Linux ADS processes carrying the exact managed launch identity.

    The public ``ads`` executable may be a short-lived wrapper.  Its real
    ``hpeesofemx`` and ``hpeesofde`` children inherit the session nonce and
    slot, then may be re-parented after the wrapper exits.  Matching both
    environment values avoids claiming unrelated ADS processes.
    """
    if not managed_session_id or not slot:
        return []
    if os.name == "nt":
        return [
            item
            for item in _windows_launch_processes(launcher_pid)
            if item["process_name"].lower() in WINDOWS_ADS_PROCESS_NAMES
        ]
    return _linux_managed_ads_processes(managed_session_id, slot)


def managed_host_processes(
    managed_session_id: str,
    slot: str,
    launcher_pid: int | None = None,
) -> list[dict[str, Any]]:
    """Return all Linux processes carrying the exact managed launch identity.

    This broader inventory is observation-only.  It includes separate-process
    UI helpers such as the ADS product selector, but it is never used as proof
    that the primary ADS runtime is alive or agent-owned.
    """
    if not managed_session_id or not slot:
        return []
    if os.name == "nt":
        return _windows_launch_processes(launcher_pid)
    return _linux_managed_host_processes(managed_session_id, slot)


def _windows_launch_processes(launcher_pid: int | None) -> list[dict[str, Any]]:
    """Return the launcher and its Windows descendants from one Toolhelp snapshot.

    Windows does not expose another process's environment through a stable
    standard-library API. The launcher PID is reserved before the launch and
    is therefore the ownership root; descendants are inventory only until the
    embedded bridge returns the nonce.
    """
    try:
        root_pid = int(launcher_pid or 0)
    except (TypeError, ValueError):
        return []
    if root_pid <= 0 or os.name != "nt":
        return []

    import ctypes
    from ctypes import wintypes

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    invalid_handle = wintypes.HANDLE(-1).value
    if snapshot == invalid_handle:
        return []
    entries: dict[int, tuple[int, str]] = {}
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(entry)
        if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                entries[int(entry.th32ProcessID)] = (int(entry.th32ParentProcessID), entry.szExeFile)
                entry.dwSize = ctypes.sizeof(entry)
                if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snapshot)

    selected = _descendant_pids(root_pid, entries)
    matches: list[dict[str, Any]] = []
    for pid in selected:
        if pid not in entries:
            continue
        parent_pid, process_name = entries[pid]
        normalized = process_name.lower()
        role = (
            "design-environment"
            if normalized == "hpeesofde.exe"
            else "ads-runtime"
            if normalized == "hpeesofemx.exe"
            else "managed-child"
        )
        matches.append(
            {"pid": pid, "parent_pid": parent_pid, "process_name": process_name, "role": role}
        )
    priority = {"design-environment": 0, "ads-runtime": 1, "managed-child": 2}
    matches.sort(key=lambda item: (priority[item["role"]], item["pid"]))
    return matches


def _descendant_pids(root_pid: int, entries: dict[int, tuple[int, str]]) -> set[int]:
    selected = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, (parent_pid, _name) in entries.items():
            if parent_pid in selected and pid not in selected:
                selected.add(pid)
                changed = True
    return selected


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
