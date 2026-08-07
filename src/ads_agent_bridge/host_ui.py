from __future__ import annotations

import ctypes
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from .session_manager import status as session_status


RISK_LEVELS = {"low": 0, "medium": 1, "high": 2}
AUTHORIZATION_LEVELS = {"automatic": 0, "workflow-policy": 1, "user-confirmed": 2}


class HostUiError(ValueError):
    """Raised when a pre-bridge host UI cannot be observed or acted on safely."""


def _platform_name() -> str:
    return os.name


def _selected_waiting_session(slot: str) -> dict[str, Any]:
    payload = session_status(slot)
    sessions = payload.get("sessions")
    if not isinstance(sessions, list) or len(sessions) != 1:
        raise HostUiError(f"Could not resolve exactly one managed session for slot {slot!r}")
    session = sessions[0]
    if session.get("state") != "waiting-for-host-ui":
        raise HostUiError(
            f"Slot {slot!r} is {session.get('state')!r}, not 'waiting-for-host-ui'; "
            "host UI access is limited to the pre-bridge wait state"
        )
    contract = session.get("host_ui")
    if not isinstance(contract, dict):
        raise HostUiError(f"Slot {slot!r} returned no host_ui identity contract")
    return session


def _candidate_pids(session: dict[str, Any]) -> set[int]:
    contract = session.get("host_ui") or {}
    candidates = contract.get("candidate_processes") or []
    result: set[int] = set()
    for candidate in candidates:
        try:
            pid = int(candidate.get("pid"))
        except (AttributeError, TypeError, ValueError):
            continue
        if pid > 0:
            result.add(pid)
    if not result:
        raise HostUiError("The host_ui contract contains no candidate process ids")
    return result


def _window_fingerprint(slot: str, session: dict[str, Any], window: dict[str, Any]) -> str:
    identity = {
        "slot": slot,
        "managed_session_id": session.get("managed_session_id"),
        "display": session.get("display"),
        "window_id": window.get("window_id"),
        "pid": window.get("pid"),
        "title": window.get("title"),
        "class_name": window.get("class_name"),
        "geometry": window.get("geometry"),
        "coordinate_space": window.get("coordinate_space"),
    }
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _select_window(windows: list[dict[str, Any]], window_id: str | None) -> dict[str, Any]:
    if window_id is not None:
        normalized = _normalize_window_id(window_id)
        matches = [window for window in windows if _normalize_window_id(window["window_id"]) == normalized]
        if len(matches) != 1:
            raise HostUiError(f"Window {window_id!r} is not a visible nonce-bound candidate")
        return matches[0]
    if len(windows) != 1:
        raise HostUiError(
            f"Host UI image/action requires one target window; observed {len(windows)}. Pass --window-id explicitly."
        )
    return windows[0]


def _normalize_window_id(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise HostUiError(f"Invalid window id: {value!r}") from exc


def _identity_fields(window: dict[str, Any]) -> dict[str, Any]:
    return {
        key: window.get(key)
        for key in (
            "window_id",
            "pid",
            "title",
            "class_name",
            "visible",
            "enabled",
            "geometry",
            "coordinate_space",
        )
    }


def _require_same_window(expected: dict[str, Any], observed: dict[str, Any]) -> None:
    if _identity_fields(expected) != _identity_fields(observed):
        raise HostUiError("Host window identity changed immediately before capture or actuation")


def snapshot(
    slot: str,
    *,
    window_id: str | None = None,
    image_out: Path | None = None,
) -> dict[str, Any]:
    session = _selected_waiting_session(slot)
    pids = _candidate_pids(session)
    contract = session.get("host_ui") or {}
    display_name = str(session.get("display") or os.environ.get("DISPLAY") or "")
    xauthority = str(contract.get("xauthority") or os.environ.get("XAUTHORITY") or "") or None
    if _platform_name() == "nt":
        backend = "windows-user32"
        windows = _windows_candidate_windows(pids)
    else:
        if not display_name:
            raise HostUiError("The managed session has no X display identity")
        backend = "linux-x11"
        windows = _linux_candidate_windows(display_name, pids, xauthority)
    for window in windows:
        window["fingerprint"] = _window_fingerprint(slot, session, window)

    selected: dict[str, Any] | None = None
    if image_out is not None:
        target = _select_window(windows, window_id)
        path = image_out.expanduser().resolve()
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite host UI image: {path}")
        if not path.parent.is_dir():
            raise FileNotFoundError(f"Host UI image parent directory not found: {path.parent}")
        if _platform_name() == "nt":
            _windows_capture(target, path)
        else:
            _linux_capture(display_name, xauthority, target, path)
        selected = {
            "window_id": target["window_id"],
            "fingerprint": target["fingerprint"],
            "image_path": str(path),
        }

    return {
        "status": "ready" if windows else "no-visible-candidate-window",
        "phase": "pre-bridge",
        "backend": backend,
        "slot": slot,
        "managed_session_id": session.get("managed_session_id"),
        "display": session.get("display"),
        "workspace": session.get("workspace"),
        "candidate_pids": sorted(pids),
        "windows": windows,
        "selected": selected,
        "action_policy": (
            "Use Agent vision only on a targeted image. Actions must bind the exact window fingerprint, "
            "declare risk and authorization, and be followed by status/image verification."
        ),
    }


def action(
    slot: str,
    *,
    window_id: str,
    fingerprint: str,
    operation: str,
    risk: str,
    authorization: str,
    reason: str,
    x: int | None = None,
    y: int | None = None,
) -> dict[str, Any]:
    if risk not in RISK_LEVELS:
        raise HostUiError(f"Unsupported risk declaration: {risk!r}")
    if authorization not in AUTHORIZATION_LEVELS:
        raise HostUiError(f"Unsupported authorization: {authorization!r}")
    if not reason.strip():
        raise HostUiError("A concrete action reason is required")
    if AUTHORIZATION_LEVELS[authorization] < RISK_LEVELS[risk]:
        raise HostUiError(f"Authorization {authorization!r} is insufficient for {risk!r} risk")
    if operation not in {"click", "close"}:
        raise HostUiError(f"Unsupported host UI operation: {operation!r}")

    current = snapshot(slot)
    target = _select_window(current["windows"], window_id)
    if target.get("fingerprint") != fingerprint:
        raise HostUiError("Host UI fingerprint changed; take a new snapshot before acting")
    geometry = target.get("geometry") or {}
    if not target.get("visible") or not target.get("enabled"):
        raise HostUiError("Target host window is not visible and enabled")
    if operation == "click":
        if x is None or y is None:
            raise HostUiError("A click requires client-relative x and y")
        width = int(geometry.get("width") or 0)
        height = int(geometry.get("height") or 0)
        if not (0 <= x < width and 0 <= y < height):
            raise HostUiError(f"Click coordinate {x},{y} is outside the {width}x{height} target window")

    if _platform_name() == "nt":
        if operation == "click":
            _windows_click(target, int(x), int(y))
        else:
            _windows_close(target)
    else:
        display_name = str(current.get("display") or os.environ.get("DISPLAY") or "")
        session = _selected_waiting_session(slot)
        contract = session.get("host_ui") or {}
        xauthority = str(contract.get("xauthority") or os.environ.get("XAUTHORITY") or "") or None
        if operation == "click":
            _linux_click(display_name, xauthority, target, int(x), int(y))
        else:
            _linux_close(display_name, xauthority, target)
    time.sleep(0.25)
    return {
        "status": "accepted",
        "phase": "pre-bridge",
        "slot": slot,
        "window_id": target["window_id"],
        "fingerprint": fingerprint,
        "operation": operation,
        "point": {"x": x, "y": y} if operation == "click" else None,
        "decision": {"risk": risk, "authorization": authorization, "reason": reason},
        "postcondition": "Run host-ui snapshot or status and verify the expected state before continuing.",
    }


def _linux_connection(display_name: str, xauthority: str | None = None):
    try:
        from Xlib import display
    except ImportError as exc:  # pragma: no cover - packaging gate covers the dependency
        raise HostUiError("Linux host UI requires the packaged python-xlib dependency") from exc
    previous = os.environ.get("XAUTHORITY")
    if xauthority:
        os.environ["XAUTHORITY"] = xauthority
    try:
        return display.Display(display_name)
    except Exception as exc:
        raise HostUiError(f"Could not connect to X display {display_name!r}: {exc}") from exc
    finally:
        if xauthority:
            if previous is None:
                os.environ.pop("XAUTHORITY", None)
            else:
                os.environ["XAUTHORITY"] = previous


def _linux_candidate_windows(
    display_name: str,
    pids: set[int],
    xauthority: str | None = None,
) -> list[dict[str, Any]]:
    from Xlib import X

    connection = _linux_connection(display_name, xauthority)
    root = connection.screen().root
    client_atom = connection.intern_atom("_NET_CLIENT_LIST")
    clients = root.get_full_property(client_atom, X.AnyPropertyType)
    window_ids = list(clients.value) if clients is not None else [child.id for child in root.query_tree().children]
    windows: list[dict[str, Any]] = []
    for raw_id in window_ids:
        try:
            observed = _linux_window_details(connection, int(raw_id))
            if observed["pid"] in pids and observed["visible"]:
                windows.append(observed)
        except Exception:
            continue
    connection.close()
    windows.sort(key=lambda item: (item["pid"], _normalize_window_id(item["window_id"])))
    return windows


def _linux_window_details(connection, raw_id: int) -> dict[str, Any]:
    from Xlib import X

    root = connection.screen().root
    window = connection.create_resource_object("window", raw_id)
    pid_atom = connection.intern_atom("_NET_WM_PID")
    pid_property = window.get_full_property(pid_atom, X.AnyPropertyType)
    pid = int(pid_property.value[0]) if pid_property is not None and len(pid_property.value) else 0
    attributes = window.get_attributes()
    geometry = window.get_geometry()
    origin = root.translate_coords(window, 0, 0)
    title = window.get_wm_name() or ""
    if isinstance(title, bytes):
        title = title.decode("utf-8", errors="replace")
    wm_class = window.get_wm_class() or ()
    return {
        "window_id": f"0x{raw_id:x}",
        "pid": pid,
        "title": str(title),
        "class_name": ".".join(str(item) for item in wm_class),
        "visible": attributes.map_state == X.IsViewable,
        "enabled": True,
        "geometry": {
            "x": int(origin.x),
            "y": int(origin.y),
            "width": int(geometry.width),
            "height": int(geometry.height),
        },
        "coordinate_space": "x11-client-pixels",
    }


def _linux_capture(
    display_name: str,
    xauthority: str | None,
    target: dict[str, Any],
    path: Path,
) -> None:
    from PIL import Image
    from Xlib import X

    connection = _linux_connection(display_name, xauthority)
    raw_id = _normalize_window_id(target["window_id"])
    observed = _linux_window_details(connection, raw_id)
    _require_same_window(target, observed)
    window = connection.create_resource_object("window", raw_id)
    geometry = target["geometry"]
    width, height = int(geometry["width"]), int(geometry["height"])
    raw = window.get_image(0, 0, width, height, X.ZPixmap, 0xFFFFFFFF).data
    if len(raw) == width * height * 4:
        image = Image.frombytes("RGB", (width, height), raw, "raw", "BGRX")
    elif len(raw) == width * height * 3:
        image = Image.frombytes("RGB", (width, height), raw, "raw", "BGR")
    else:
        connection.close()
        raise HostUiError(f"Unsupported X11 image buffer size: {len(raw)} for {width}x{height}")
    connection.close()
    image.save(path, format="PNG")


def _linux_activate(connection, window) -> None:
    from Xlib import X
    from Xlib.protocol import event

    root = connection.screen().root
    active_atom = connection.intern_atom("_NET_ACTIVE_WINDOW")
    request = event.ClientMessage(
        window=window,
        client_type=active_atom,
        data=(32, [2, X.CurrentTime, 0, 0, 0]),
    )
    root.send_event(request, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
    connection.sync()
    time.sleep(0.15)
    active = root.get_full_property(active_atom, X.AnyPropertyType)
    if active is None or not len(active.value) or int(active.value[0]) != int(window.id):
        raise HostUiError("The verified X11 host window could not be activated")


def _linux_click(
    display_name: str,
    xauthority: str | None,
    target: dict[str, Any],
    x: int,
    y: int,
) -> None:
    from Xlib import X
    from Xlib.ext import xtest

    connection = _linux_connection(display_name, xauthority)
    root = connection.screen().root
    raw_id = _normalize_window_id(target["window_id"])
    observed = _linux_window_details(connection, raw_id)
    _require_same_window(target, observed)
    window = connection.create_resource_object("window", raw_id)
    _linux_activate(connection, window)
    _require_same_window(target, _linux_window_details(connection, raw_id))
    origin = root.translate_coords(window, 0, 0)
    root_x, root_y = int(origin.x + x), int(origin.y + y)
    screen = root.get_geometry()
    if not (0 <= root_x < screen.width and 0 <= root_y < screen.height):
        connection.close()
        raise HostUiError("Translated click coordinate is outside the selected X display")
    xtest.fake_input(connection, X.MotionNotify, x=root_x, y=root_y)
    connection.sync()
    time.sleep(0.1)
    xtest.fake_input(connection, X.ButtonPress, 1)
    connection.sync()
    time.sleep(0.05)
    xtest.fake_input(connection, X.ButtonRelease, 1)
    connection.sync()
    connection.close()


def _linux_close(display_name: str, xauthority: str | None, target: dict[str, Any]) -> None:
    from Xlib import X
    from Xlib.protocol import event

    connection = _linux_connection(display_name, xauthority)
    raw_id = _normalize_window_id(target["window_id"])
    observed = _linux_window_details(connection, raw_id)
    _require_same_window(target, observed)
    window = connection.create_resource_object("window", raw_id)
    protocols_atom = connection.intern_atom("WM_PROTOCOLS")
    delete_atom = connection.intern_atom("WM_DELETE_WINDOW")
    protocols = window.get_full_property(protocols_atom, X.AnyPropertyType)
    if protocols is None or delete_atom not in list(protocols.value):
        connection.close()
        raise HostUiError("The verified X11 host window does not support WM_DELETE_WINDOW")
    message = event.ClientMessage(
        window=window,
        client_type=protocols_atom,
        data=(32, [delete_atom, X.CurrentTime, 0, 0, 0]),
    )
    window.send_event(message, event_mask=X.NoEventMask)
    connection.sync()
    connection.close()


def _windows_candidate_windows(pids: set[int]) -> list[dict[str, Any]]:
    from ctypes import wintypes

    _windows_enable_dpi_awareness()
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    windows: list[dict[str, Any]] = []

    class Rect(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @enum_proc_type
    def visit(hwnd, _lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) not in pids or not user32.IsWindowVisible(hwnd):
            return True
        title_length = user32.GetWindowTextLengthW(hwnd)
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
        class_buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buffer, len(class_buffer))
        rect = Rect()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return True
        origin = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
            return True
        width, height = int(rect.right - rect.left), int(rect.bottom - rect.top)
        if width <= 0 or height <= 0:
            return True
        windows.append(
            {
                "window_id": f"0x{int(hwnd):x}",
                "pid": int(pid.value),
                "title": title_buffer.value,
                "class_name": class_buffer.value,
                "visible": True,
                "enabled": bool(user32.IsWindowEnabled(hwnd)),
                "geometry": {"x": int(origin.x), "y": int(origin.y), "width": width, "height": height},
                "coordinate_space": "physical-client-pixels",
            }
        )
        return True

    if not user32.EnumWindows(visit, 0):
        raise HostUiError(f"EnumWindows failed with Windows error {ctypes.get_last_error()}")
    windows.sort(key=lambda item: (item["pid"], _normalize_window_id(item["window_id"])))
    return windows


def _windows_enable_dpi_awareness() -> None:
    """Keep User32 geometry, Pillow capture, and click coordinates in one space.

    Windows virtualizes coordinates for DPI-unaware callers while Pillow grabs
    physical desktop pixels. A thread-local per-monitor context is preferred so
    every short-lived CLI invocation observes and acts in physical client
    pixels, including on mixed-DPI desktops.
    """

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    per_monitor_v2 = ctypes.c_void_p(-4)
    thread_setter = getattr(user32, "SetThreadDpiAwarenessContext", None)
    if thread_setter is not None:
        thread_setter.argtypes = [ctypes.c_void_p]
        thread_setter.restype = ctypes.c_void_p
        ctypes.set_last_error(0)
        if thread_setter(per_monitor_v2):
            return
        error = ctypes.get_last_error()
        if error not in {0, 5}:
            raise HostUiError(f"Could not enable per-monitor DPI awareness: Windows error {error}")

    process_setter = getattr(user32, "SetProcessDpiAwarenessContext", None)
    if process_setter is not None:
        process_setter.argtypes = [ctypes.c_void_p]
        process_setter.restype = ctypes.c_bool
        ctypes.set_last_error(0)
        if process_setter(per_monitor_v2):
            return
        error = ctypes.get_last_error()
        if error not in {0, 5}:
            raise HostUiError(f"Could not enable process DPI awareness: Windows error {error}")

    legacy_setter = getattr(user32, "SetProcessDPIAware", None)
    if legacy_setter is None or not legacy_setter():
        error = ctypes.get_last_error()
        if error not in {0, 5}:
            raise HostUiError(f"Could not enable legacy DPI awareness: Windows error {error}")


def _windows_capture(target: dict[str, Any], path: Path) -> None:
    from PIL import ImageGrab

    _windows_require_target(target)
    ctypes.WinDLL("user32", use_last_error=True).SetForegroundWindow(_normalize_window_id(target["window_id"]))
    time.sleep(0.1)
    _windows_require_target(target)
    geometry = target["geometry"]
    left, top = int(geometry["x"]), int(geometry["y"])
    right, bottom = left + int(geometry["width"]), top + int(geometry["height"])
    image = ImageGrab.grab(bbox=(left, top, right, bottom), include_layered_windows=True, all_screens=True)
    image.save(path, format="PNG")


def _windows_click(target: dict[str, Any], x: int, y: int) -> None:
    _windows_require_target(target)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = _normalize_window_id(target["window_id"])
    wm_mousemove, wm_lbuttondown, wm_lbuttonup, mk_lbutton = 0x0200, 0x0201, 0x0202, 0x0001
    lparam = (y << 16) | (x & 0xFFFF)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.1)
    _windows_require_target(target)
    if not user32.PostMessageW(hwnd, wm_mousemove, 0, lparam):
        raise HostUiError(f"Could not post mouse move: Windows error {ctypes.get_last_error()}")
    if not user32.PostMessageW(hwnd, wm_lbuttondown, mk_lbutton, lparam):
        raise HostUiError(f"Could not post mouse down: Windows error {ctypes.get_last_error()}")
    if not user32.PostMessageW(hwnd, wm_lbuttonup, 0, lparam):
        raise HostUiError(f"Could not post mouse up: Windows error {ctypes.get_last_error()}")


def _windows_close(target: dict[str, Any]) -> None:
    _windows_require_target(target)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = _normalize_window_id(target["window_id"])
    if not user32.PostMessageW(hwnd, 0x0010, 0, 0):
        raise HostUiError(f"Could not post WM_CLOSE: Windows error {ctypes.get_last_error()}")


def _windows_require_target(target: dict[str, Any]) -> None:
    matches = [
        window
        for window in _windows_candidate_windows({int(target["pid"])})
        if _normalize_window_id(window["window_id"]) == _normalize_window_id(target["window_id"])
    ]
    if len(matches) != 1:
        raise HostUiError("Verified Windows host window is no longer available")
    _require_same_window(target, matches[0])
