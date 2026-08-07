"""Small authenticated localhost bridge running inside ADS embedded Python."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
import queue
import re
import secrets
import socket
import sys
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from .context import ContextRegistry
except ImportError:
    from context import ContextRegistry

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    try:
        from PySide2 import QtCore, QtWidgets
    except ImportError:
        from qtpy import QtCore, QtWidgets


HOST = "127.0.0.1"
BASE_PORTS = {"de": 8875, "dds": 8876}
MAX_REQUEST_BYTES = 1024 * 1024


def detect_profile(addon: Any) -> str:
    module = type(addon).__module__.lower()
    if ".dds." in module:
        return "dds"
    if ".de." in module:
        return "de"
    try:
        from keysight.ads import dds

        if dds.is_dds_app():
            return "dds"
    except Exception:
        pass
    return "de"


def _normalized_slot() -> str:
    value = os.environ.get("ADS_AGENT_SLOT") or os.environ.get("ADS_DEBUG_BRIDGE_SLOT")
    if not value:
        value = Path(os.environ.get("HPEESOF_DIR", "ads")).name
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower() or "default"


def _state_root() -> Path:
    override = os.environ.get("ADS_AGENT_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".ads-agent"


def _session_path(slot: str, profile: str) -> Path:
    return _state_root() / "runtime" / f"session-{slot}-{profile}.json"


def _jsonable(value: Any, depth: int = 0, max_depth: int = 3) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if depth >= max_depth:
        return {"type": type(value).__name__, "repr": _safe_repr(value)}
    if isinstance(value, dict):
        return {str(key): _jsonable(item, depth + 1, max_depth) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item, depth + 1, max_depth) for item in value]
    return {"type": type(value).__name__, "module": type(value).__module__, "repr": _safe_repr(value)}


def _safe_repr(value: Any) -> str:
    try:
        return repr(value)
    except Exception:
        return f"<{type(value).__name__}>"


@dataclass
class _Task:
    callback: Callable[[], dict[str, Any]]
    completed: threading.Event
    result: dict[str, Any] | None = None


class _Dispatcher(QtCore.QObject):
    def __init__(self) -> None:
        super().__init__()
        self._tasks: queue.Queue[_Task] = queue.Queue()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._drain)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def call(self, callback: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        if QtCore.QThread.currentThread() == self.thread():
            return callback()
        task = _Task(callback, threading.Event())
        self._tasks.put(task)
        if not task.completed.wait(timeout=60):
            raise TimeoutError("ADS main-thread dispatch timed out")
        assert task.result is not None
        return task.result

    def _drain(self) -> None:
        while True:
            try:
                task = self._tasks.get_nowait()
            except queue.Empty:
                return
            try:
                task.result = task.callback()
            except Exception as exc:
                task.result = _error(exc)
            finally:
                task.completed.set()


def _error(exc: BaseException | str) -> dict[str, Any]:
    return {"ok": False, "result": None, "stdout": "", "stderr": "", "error": str(exc)}


class _Runtime:
    def __init__(self, profile: str, slot: str) -> None:
        self.profile = profile
        self.slot = slot
        self.contexts = ContextRegistry(profile, slot=slot)
        self._shutdown_state: dict[str, Any] = {"state": "idle"}
        self._dialog_action_state: dict[str, Any] = {"state": "idle"}
        self.namespace: dict[str, Any] = {"__builtins__": __builtins__, "Path": Path}
        try:
            from keysight.ads import ael

            self.namespace["ael"] = ael
        except Exception:
            pass
        try:
            from keysight.ads import de

            self.namespace["de"] = de
            try:
                from keysight.ads.de import app as de_app

                self.namespace["de_app"] = de_app
            except Exception:
                pass
        except Exception:
            pass
        try:
            from keysight.ads import dds

            self.namespace["dds"] = dds
        except Exception:
            pass

    def execute(self, command: str, args: dict[str, Any]) -> dict[str, Any]:
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                result = self._dispatch(command, args)
            max_depth = 8 if command.startswith("context_") else 3
            return {
                "ok": True,
                "result": _jsonable(result, max_depth=max_depth),
                "stdout": out.getvalue(),
                "stderr": err.getvalue(),
                "error": None,
            }
        except Exception as exc:
            return {"ok": False, "result": None, "stdout": out.getvalue(), "stderr": err.getvalue(), "error": str(exc), "traceback": traceback.format_exc()}

    def _dispatch(self, command: str, args: dict[str, Any]) -> Any:
        if command == "ping":
            return {"status": "ok", "profile": self.profile, "slot": self.slot, "pid": os.getpid()}
        if command == "capabilities":
            return {
                "safe_commands": [
                    "ping",
                    "status",
                    "capabilities",
                    "dialog_snapshot",
                    "context_capabilities",
                    "context_list",
                    "context_get",
                    "context_refresh",
                    "context_drop",
                ],
                "bounded_commands": [
                    "dds_readback",
                    "ael_workspace_path",
                    "open_workspace",
                    "safe_shutdown",
                    "dialog_action",
                ],
                "unsafe_commands": ["eval", "exec", "ael_call"],
                "unsafe_enabled": os.environ.get("ADS_AGENT_UNSAFE") == "1",
                "localhost_only": True,
                "token_required": True,
            }
        if command == "status":
            return self._status()
        if command == "context_capabilities":
            return self.contexts.capabilities()
        if command == "context_list":
            return self.contexts.list()
        if command == "context_get":
            return self.contexts.get(_required_text(args, "context"))
        if command == "context_refresh":
            return self.contexts.refresh(_required_text(args, "context"))
        if command == "context_drop":
            context = _required_text(args, "context")
            return {"context": context, "dropped": self.contexts.drop(context)}
        if command == "dialog_snapshot":
            return self._dialog_snapshot(bool(args.get("include_image")))
        if command == "dialog_action":
            return self._dialog_action(args)
        if command == "dds_readback":
            return self._dds_readback(args)
        if command == "ael_workspace_path":
            return self._ael_workspace_path()
        if command == "open_workspace":
            return self._open_workspace(args)
        if command == "safe_shutdown":
            return self._safe_shutdown()
        if command in {"eval", "exec", "ael_call"}:
            self._require_unsafe(command)
        if command == "eval":
            expression = _required_text(args, "expression")
            return eval(expression, self.namespace, self.namespace)
        if command == "exec":
            code = _required_text(args, "code")
            exec(compile(code, "<ads-agent-bridge>", "exec"), self.namespace, self.namespace)
            return None
        if command == "ael_call":
            name = _required_text(args, "name")
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
                raise ValueError("ael_call name must be a simple AEL function name")
            call_args = args.get("args", [])
            if not isinstance(call_args, list):
                raise ValueError("ael_call args must be a list")
            ael = self.namespace.get("ael")
            if ael is None:
                raise RuntimeError("keysight.ads.ael is unavailable")
            return getattr(ael.call, name)(*call_args)
        raise ValueError(f"Unsupported command: {command}")

    def _ael_workspace_path(self) -> dict[str, Any]:
        if self.profile != "de":
            raise RuntimeError("ael_workspace_path requires the DE bridge profile")
        ael = self.namespace.get("ael")
        if ael is None:
            raise RuntimeError("keysight.ads.ael is unavailable")
        workspace_path = ael.call.de_get_open_workspace_pathname()
        return {
            "function": "de_get_open_workspace_pathname",
            "workspace_path": str(workspace_path or ""),
            "bounded": True,
            "unsafe_python_enabled": os.environ.get("ADS_AGENT_UNSAFE") == "1",
        }

    def _open_workspace(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.profile != "de":
            raise RuntimeError("open_workspace requires the DE bridge profile")
        de = self.namespace.get("de")
        if de is None:
            raise RuntimeError("keysight.ads.de is unavailable")
        workspace = Path(_required_text(args, "workspace")).expanduser().resolve()
        if not workspace.is_dir() or not (
            (workspace / "workspace.ads").is_file()
            or ((workspace / "lib.defs").is_file() and (workspace / "cds.lib").is_file())
        ):
            raise ValueError(f"Path does not look like an ADS workspace: {workspace}")
        before = str(de.active_workspace().path) if de.workspace_is_open() else None
        if before is not None and not _same_path(before, workspace):
            raise RuntimeError(
                f"A different workspace is already open: {before}. "
                "The bounded command never closes or force-switches workspaces."
            )
        opened = False
        if before is None:
            de.open_workspace(str(workspace))
            opened = True
        actual = str(de.active_workspace().path) if de.workspace_is_open() else None
        if not _same_path(actual, workspace):
            raise RuntimeError(f"ADS did not bind the requested workspace: {actual}")
        return {"workspace": actual, "opened": opened, "verified": True, "bounded": True}

    def _safe_shutdown(self) -> dict[str, Any]:
        if self.profile != "de":
            raise RuntimeError("safe_shutdown requires the DE bridge profile")
        modal = self._modal_state()
        if modal.get("modal_blocking"):
            return {"accepted": False, "reason": "modal_dialog_active", "modal": modal, "bounded": True}
        de_app = self.namespace.get("de_app")
        prompt = getattr(de_app, "prompt_and_save_modified_workspace", None) if de_app is not None else None
        exit_application = getattr(de_app, "exit_application", None) if de_app is not None else None
        if not callable(prompt) or not callable(exit_application):
            raise RuntimeError(
                "This ADS runtime does not expose de.app.prompt_and_save_modified_workspace() "
                "and de.app.exit_application(); no fallback will discard unsaved work."
            )
        current = self._shutdown_status()
        if current.get("state") in {"scheduled", "prompting", "exiting"}:
            return {"accepted": True, "shutdown": current, "bounded": True}

        # Run prompting on the Qt event loop after the authenticated response is returned.
        self._set_shutdown_state("scheduled")
        QtCore.QTimer.singleShot(100, self._prompt_then_exit)
        return {
            "accepted": True,
            "state": "scheduled",
            "method": "prompt_and_save_modified_workspace_then_exit_application",
            "bounded": True,
        }

    def _prompt_then_exit(self) -> None:
        de_app = self.namespace.get("de_app")
        prompt = getattr(de_app, "prompt_and_save_modified_workspace", None) if de_app is not None else None
        exit_application = getattr(de_app, "exit_application", None) if de_app is not None else None
        try:
            self._set_shutdown_state("prompting")
            if not bool(prompt()):
                self._set_shutdown_state("cancelled", reason="user_cancelled")
                return
            self._set_shutdown_state("exiting")
            exit_application(0)
        except Exception as exc:
            self._set_shutdown_state("failed", error=str(exc))

    def _set_shutdown_state(self, state: str, **details: Any) -> None:
        self._shutdown_state = {"state": state, **details}

    def _shutdown_status(self) -> dict[str, Any]:
        current = getattr(self, "_shutdown_state", None)
        return dict(current) if isinstance(current, dict) else {"state": "idle"}

    def _dialog_snapshot(self, include_image: bool = False) -> dict[str, Any]:
        return self._dialog_snapshot_data(include_image)

    def _dialog_snapshot_data(self, include_image: bool = False) -> dict[str, Any]:
        application = QtWidgets.QApplication.instance()
        widget = application.activeModalWidget() if application is not None else None
        if widget is None:
            return {"present": False, "bounded": True}

        labels: list[str] = []
        label_type = getattr(QtWidgets, "QLabel", None)
        if label_type is not None:
            try:
                label_widgets = list(widget.findChildren(label_type))
            except Exception:
                label_widgets = []
            for label in label_widgets[:80]:
                text = self._widget_text(label, "text", 500)
                if text and text not in labels:
                    labels.append(text)

        buttons: list[dict[str, Any]] = []
        button_type = getattr(QtWidgets, "QAbstractButton", None)
        if button_type is not None:
            try:
                button_widgets = list(widget.findChildren(button_type))
            except Exception:
                button_widgets = []
            for index, button in enumerate(button_widgets[:80]):
                item = self._button_summary(widget, button, index)
                buttons.append(item)

        identity = {
            "pid": os.getpid(),
            "class_name": type(widget).__name__,
            "object_name": self._widget_text(widget, "objectName", 160),
            "title": self._widget_text(widget, "windowTitle", 300),
            "labels": labels,
            "buttons": buttons,
        }
        encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        snapshot: dict[str, Any] = {
            "present": True,
            **identity,
            "dialog_fingerprint": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
            "geometry": self._widget_geometry(widget),
            "bounded": True,
        }
        if include_image:
            snapshot["image_png_base64"] = self._widget_png_base64(widget)
        return snapshot

    def _dialog_action(self, args: dict[str, Any]) -> dict[str, Any]:
        expected_fingerprint = _required_text(args, "dialog_fingerprint")
        button_id = _required_text(args, "button_id")
        decision = args.get("decision")
        if not isinstance(decision, dict):
            raise ValueError("decision must be an object")
        risk = _required_text(decision, "risk")
        authorization = _required_text(decision, "authorization")
        reason = _required_text(decision, "reason")
        if risk not in {"low", "medium", "high"}:
            raise ValueError("decision.risk must be low, medium, or high")
        if authorization not in {"automatic", "workflow-policy", "user-confirmed"}:
            raise ValueError(
                "decision.authorization must be automatic, workflow-policy, or user-confirmed"
            )

        snapshot = self._dialog_snapshot_data(False)
        if not snapshot.get("present"):
            raise RuntimeError("No active modal dialog is available for the requested action")
        if snapshot.get("dialog_fingerprint") != expected_fingerprint:
            raise RuntimeError("The active dialog changed after observation; take a fresh snapshot")
        button = next((item for item in snapshot.get("buttons", []) if item.get("button_id") == button_id), None)
        if not isinstance(button, dict):
            raise ValueError("button_id is not present in the current dialog")
        if not button.get("visible") or not button.get("enabled"):
            raise RuntimeError("The selected dialog button is not visible and enabled")

        declared_rank = {"low": 0, "medium": 1, "high": 2}[risk]
        floor = str(button.get("risk_floor") or "low")
        floor_rank = {"low": 0, "medium": 1, "high": 2}[floor]
        if declared_rank < floor_rank:
            raise PermissionError(f"The selected Qt button requires at least {floor!r} risk")
        if risk == "medium" and authorization == "automatic":
            raise PermissionError("Medium-risk dialog actions require workflow-policy or user-confirmed authorization")
        if risk == "high" and authorization != "user-confirmed":
            raise PermissionError("High-risk dialog actions require user-confirmed authorization")

        self._set_dialog_action_state(
            "scheduled",
            dialog_fingerprint=expected_fingerprint,
            button_id=button_id,
        )
        QtCore.QTimer.singleShot(
            0,
            lambda: self._actuate_dialog_button(expected_fingerprint, button_id),
        )
        return {
            "accepted": True,
            "state": "scheduled",
            "dialog_fingerprint": expected_fingerprint,
            "button": button,
            "decision": {"risk": risk, "authorization": authorization, "reason": reason},
            "bounded": True,
        }

    def _actuate_dialog_button(self, expected_fingerprint: str, button_id: str) -> None:
        """Rebind a scheduled action to the still-active modal before clicking it."""
        try:
            snapshot = self._dialog_snapshot_data(False)
            if not snapshot.get("present"):
                self._set_dialog_action_state(
                    "rejected",
                    reason="dialog_absent_before_actuation",
                    dialog_fingerprint=expected_fingerprint,
                    button_id=button_id,
                )
                return
            if snapshot.get("dialog_fingerprint") != expected_fingerprint:
                self._set_dialog_action_state(
                    "rejected",
                    reason="dialog_changed_before_actuation",
                    dialog_fingerprint=expected_fingerprint,
                    observed_fingerprint=snapshot.get("dialog_fingerprint"),
                    button_id=button_id,
                )
                return
            button = next(
                (item for item in snapshot.get("buttons", []) if item.get("button_id") == button_id),
                None,
            )
            if not isinstance(button, dict):
                self._set_dialog_action_state(
                    "rejected",
                    reason="button_absent_before_actuation",
                    dialog_fingerprint=expected_fingerprint,
                    button_id=button_id,
                )
                return
            if not self._click_fresh_dialog_button(button):
                self._set_dialog_action_state(
                    "rejected",
                    reason="button_changed_before_actuation",
                    dialog_fingerprint=expected_fingerprint,
                    button_id=button_id,
                )
                return
            if not button.get("visible") or not button.get("enabled"):
                self._set_dialog_action_state(
                    "rejected",
                    reason="button_unavailable_before_actuation",
                    dialog_fingerprint=expected_fingerprint,
                    button_id=button_id,
                )
                return
            self._set_dialog_action_state(
                "actuated",
                dialog_fingerprint=expected_fingerprint,
                button_id=button_id,
            )
        except Exception as exc:
            self._set_dialog_action_state(
                "failed",
                error=str(exc),
                dialog_fingerprint=expected_fingerprint,
                button_id=button_id,
            )

    def _click_fresh_dialog_button(self, expected: dict[str, Any]) -> bool:
        """Reacquire a Qt button after semantic inspection may replace wrappers.

        Some native ADS dialogs rebuild their QDialogButtonBox controls while
        standard-button roles are queried. The wrappers collected for the
        fingerprint can therefore already be invalid even though the dialog is
        unchanged. Reacquire by the fingerprinted index, then compare raw stable
        fields without another role query before clicking.
        """
        application = QtWidgets.QApplication.instance()
        dialog = application.activeModalWidget() if application is not None else None
        button_type = getattr(QtWidgets, "QAbstractButton", None)
        if dialog is None or button_type is None:
            return False
        try:
            buttons = list(dialog.findChildren(button_type))
            index = int(expected.get("index"))
            target = buttons[index]
        except (IndexError, TypeError, ValueError):
            return False
        if type(target).__name__ != expected.get("class_name"):
            return False
        if self._widget_text(target, "objectName", 160) != expected.get("object_name"):
            return False
        if self._widget_text(target, "text", 300) != expected.get("text"):
            return False
        if not self._widget_bool(target, "isVisible") or not self._widget_bool(target, "isEnabled"):
            return False
        # Keep the dialog and the full fresh wrapper list alive until click()
        # returns. Native ADS dialogs can invalidate a child wrapper when those
        # owning Python references leave scope, even while the C++ dialog remains.
        target.click()
        return True

    def _set_dialog_action_state(self, state: str, **details: Any) -> None:
        self._dialog_action_state = {"state": state, **details}

    def _dialog_action_status(self) -> dict[str, Any]:
        current = getattr(self, "_dialog_action_state", None)
        return dict(current) if isinstance(current, dict) else {"state": "idle"}

    def _button_summary(self, dialog: Any, button: Any, index: int) -> dict[str, Any]:
        standard_value: int | None = None
        standard_name = ""
        role_value: int | None = None
        role_name = ""
        box_type = getattr(QtWidgets, "QDialogButtonBox", None)
        if box_type is not None:
            try:
                boxes = list(dialog.findChildren(box_type))
            except Exception:
                boxes = []
            for box in boxes:
                try:
                    standard = box.standardButton(button)
                    candidate = self._enum_int(standard)
                    if candidate:
                        standard_value = candidate
                        standard_name = str(standard)
                    role = box.buttonRole(button)
                    candidate_role = self._enum_int(role)
                    if candidate or candidate_role not in {None, -1}:
                        role_value = candidate_role
                        role_name = str(role)
                        break
                except Exception:
                    continue
        seed = {
            "index": index,
            "class_name": type(button).__name__,
            "object_name": self._widget_text(button, "objectName", 160),
            "text": self._widget_text(button, "text", 300),
            "standard_button": standard_value,
            "button_role": role_value,
        }
        encoded = json.dumps(seed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        medium_standard_buttons = {
            0x00000800,  # Save
            0x00001000,  # SaveAll
            0x00002000,  # Open
            0x00004000,  # Yes
            0x00008000,  # YesToAll
            0x00010000,  # No
            0x00020000,  # NoToAll
            0x02000000,  # Apply
            0x08000000,  # RestoreDefaults
        }
        risk_floor = (
            "high"
            if role_value == 2 or standard_value == 0x00800000
            else "medium"
            if role_value in {5, 6, 8} or standard_value in medium_standard_buttons
            else "low"
        )
        return {
            "button_id": hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20],
            **seed,
            "standard_button_name": standard_name,
            "button_role_name": role_name,
            "accessible_name": self._widget_text(button, "accessibleName", 300),
            "tool_tip": self._widget_text(button, "toolTip", 300),
            "visible": self._widget_bool(button, "isVisible"),
            "enabled": self._widget_bool(button, "isEnabled"),
            "risk_floor": risk_floor,
        }

    @staticmethod
    def _enum_int(value: Any) -> int | None:
        try:
            return int(value.value)
        except (AttributeError, TypeError, ValueError):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

    @staticmethod
    def _widget_text(widget: Any, method: str, limit: int) -> str:
        try:
            return str(getattr(widget, method)() or "")[:limit]
        except Exception:
            return ""

    @staticmethod
    def _widget_bool(widget: Any, method: str) -> bool:
        try:
            return bool(getattr(widget, method)())
        except Exception:
            return False

    @staticmethod
    def _widget_geometry(widget: Any) -> dict[str, int] | None:
        try:
            geometry = widget.frameGeometry()
            return {
                "x": int(geometry.x()),
                "y": int(geometry.y()),
                "width": int(geometry.width()),
                "height": int(geometry.height()),
            }
        except Exception:
            return None

    @staticmethod
    def _widget_png_base64(widget: Any) -> str:
        try:
            byte_array = QtCore.QByteArray()
            buffer = QtCore.QBuffer(byte_array)
            write_only = getattr(QtCore.QIODevice, "WriteOnly", None)
            if write_only is None:
                write_only = QtCore.QIODevice.OpenModeFlag.WriteOnly
            if not buffer.open(write_only) or not widget.grab().save(buffer, "PNG"):
                raise RuntimeError("Qt could not capture the active dialog")
            return base64.b64encode(bytes(byte_array)).decode("ascii")
        except Exception as exc:
            raise RuntimeError(f"Could not capture the active dialog image: {exc}") from exc

    def _dds_readback(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.profile != "dds":
            raise RuntimeError("dds_readback requires the DDS bridge profile")
        dds = self.namespace.get("dds")
        if dds is None:
            raise RuntimeError("keysight.ads.dds is unavailable")
        workspace = Path(_required_text(args, "workspace")).expanduser().resolve()
        dataset_path = Path(_required_text(args, "dataset")).expanduser().resolve()
        if not workspace.is_dir():
            raise FileNotFoundError(f"Workspace directory not found: {workspace}")
        if not dataset_path.is_file():
            raise FileNotFoundError(f"Dataset not found: {dataset_path}")
        output_name = "ads_agent_dds_readback.dds"
        output_path = workspace / output_name
        if output_path.exists():
            raise FileExistsError(f"Refusing to overwrite existing DDS file: {output_path}")
        dds.init_dds_path(workspace)
        dds_file = dds.new_dds_file(dataset_path, workspace)
        dds_file.add_dataset_alias("agent_dataset", str(dataset_path))
        page = dds_file.pages[0]
        page.name = "ADS Agent dataset readback"
        expression = "R1_v"
        equation = page.add_equation("agent_readback", expression)
        values = equation.variable.to_dataframe().values.tolist()
        dds_file.save(output_name, workspace)
        return {
            "ok": equation.status == "Valid" and bool(values) and output_path.is_file(),
            "workspace": str(workspace),
            "dataset_path": str(dataset_path),
            "dds_path": str(output_path),
            "equation": equation.expression,
            "equation_status": equation.status,
            "row_count": len(values),
            "dataset_aliases": dict(dds_file.dataset_aliases),
            "bounded": True,
        }

    def _require_unsafe(self, command: str) -> None:
        if os.environ.get("ADS_AGENT_UNSAFE") != "1":
            raise PermissionError(f"{command} is disabled; launch ADS with ADS_AGENT_UNSAFE=1 to opt in")

    def _status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "profile": self.profile,
            "slot": self.slot,
            "pid": os.getpid(),
            "display": os.environ.get("DISPLAY"),
            "home": os.environ.get("HOME") or os.environ.get("USERPROFILE"),
            "hpeesof_dir": os.environ.get("HPEESOF_DIR"),
            "python_executable": sys.executable,
            "ui": self._ui_state(),
            "shutdown": self._shutdown_status(),
            "dialog_action": self._dialog_action_status(),
        }
        contexts = getattr(self, "contexts", None)
        if contexts is not None:
            result["contexts"] = contexts.capabilities()
        de = self.namespace.get("de")
        if de is not None:
            for name in ("is_pde_app", "running_automation", "workspace_is_open"):
                try:
                    result[name] = bool(getattr(de, name)())
                except Exception as exc:
                    result[name] = {"error": str(exc)}
            if result.get("workspace_is_open") is True:
                try:
                    result["workspace"] = str(de.active_workspace().path)
                except Exception as exc:
                    result["workspace"] = {"error": str(exc)}
        return result

    def _modal_state(self) -> dict[str, Any]:
        snapshot = self._dialog_snapshot(False)
        if not snapshot.get("present"):
            return {"modal_blocking": False}
        return {
            "modal_blocking": True,
            "title": snapshot.get("title"),
            "class_name": snapshot.get("class_name"),
            "visible": True,
            "dialog": snapshot,
        }

    def _ui_state(self) -> dict[str, Any]:
        result = self._modal_state()
        application = QtWidgets.QApplication.instance()
        if application is None:
            return {**result, "application_ready": False, "visible_window_count": 0, "windows": []}
        windows: list[dict[str, Any]] = []
        try:
            top_level = list(application.topLevelWidgets())
        except Exception:
            top_level = []
        visible_count = 0
        for widget in top_level:
            try:
                if widget.isVisible():
                    visible_count += 1
                    if len(windows) < 20:
                        windows.append(self._widget_summary(widget))
            except Exception:
                continue
        try:
            active = application.activeWindow()
        except Exception:
            active = None
        return {
            **result,
            "application_ready": True,
            "visible_window_count": visible_count,
            "windows_truncated": visible_count > len(windows),
            "active_window": self._widget_summary(active) if active is not None else None,
            "windows": windows,
        }

    @staticmethod
    def _widget_summary(widget: Any) -> dict[str, Any]:
        try:
            title = str(widget.windowTitle() or "")[:160]
        except Exception:
            title = ""
        try:
            visible = bool(widget.isVisible())
        except Exception:
            visible = False
        return {"title": title, "class_name": type(widget).__name__, "visible": visible}


def _required_text(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _same_path(left: str | Path | None, right: str | Path | None) -> bool:
    if left is None or right is None:
        return False
    left_path = Path(left).expanduser().resolve()
    right_path = Path(right).expanduser().resolve()
    try:
        return left_path.samefile(right_path)
    except OSError:
        return os.path.normcase(str(left_path)) == os.path.normcase(str(right_path))


class BridgeServer:
    def __init__(self, profile: str) -> None:
        self.profile = profile
        self.slot = _normalized_slot()
        self._token = os.environ.get("ADS_AGENT_BRIDGE_TOKEN") or secrets.token_hex(24)
        self._dispatcher = _Dispatcher()
        self._runtime = _Runtime(profile, self.slot)
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._port: int | None = None
        self._started_at: str | None = None

    @property
    def contexts(self) -> ContextRegistry:
        return self._runtime.contexts

    def start(self) -> None:
        self._dispatcher.start()
        self._socket, self._port = self._bind()
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._write_session()
        self._thread = threading.Thread(target=self._serve, name="ads-agent-bridge", daemon=True)
        self._thread.start()
        print(f"ADS Agent Bridge [{self.slot}/{self.profile}] listening on {HOST}:{self._port}")

    def stop(self) -> None:
        self._stop.set()
        self._runtime.contexts.stop()
        self._dispatcher.stop()
        sock, self._socket = self._socket, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        self._remove_owned_session()

    def _bind(self) -> tuple[socket.socket, int]:
        key = f"ADS_AGENT_BRIDGE_PORT_{self.profile.upper()}"
        base = int(os.environ.get(key, BASE_PORTS[self.profile]))
        last_error: OSError | None = None
        for port in range(base, base + 25):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.bind((HOST, port))
                sock.listen()
                sock.settimeout(0.5)
                return sock, port
            except OSError as exc:
                last_error = exc
                sock.close()
        raise RuntimeError(f"No free localhost bridge port near {base}: {last_error}")

    def _serve(self) -> None:
        assert self._socket is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        with conn:
            try:
                raw = b""
                while len(raw) <= MAX_REQUEST_BYTES:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    raw += chunk
                if len(raw) > MAX_REQUEST_BYTES:
                    raise ValueError("Request too large")
                request = json.loads(raw.decode("utf-8"))
                if not isinstance(request, dict) or request.get("token") != self._token:
                    response = _error("Unauthorized")
                else:
                    command = _required_text(request, "command")
                    args = request.get("args", {})
                    if not isinstance(args, dict):
                        raise ValueError("args must be an object")
                    response = self._dispatcher.call(lambda: self._runtime.execute(command, args))
            except Exception as exc:
                response = _error(exc)
            conn.sendall((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))

    def _write_session(self) -> None:
        path = _session_path(self.slot, self.profile)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        payload = {
            "schema_version": 1,
            "pid": os.getpid(),
            "host": HOST,
            "port": self._port,
            "token": self._token,
            "slot": self.slot,
            "profile": self.profile,
            "started_at": self._started_at,
            "ads_version": os.environ.get("HPEESOF_DIR", ""),
            "managed_session_id": os.environ.get("ADS_AGENT_MANAGED_SESSION_ID"),
        }
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, path)

    def _remove_owned_session(self) -> None:
        path = _session_path(self.slot, self.profile)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("pid") == os.getpid() and payload.get("token") == self._token:
                path.unlink()
        except (OSError, ValueError):
            pass
