"""Small authenticated localhost bridge running inside ADS embedded Python."""

from __future__ import annotations

import contextlib
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
    from PySide6 import QtCore
except ImportError:
    try:
        from PySide2 import QtCore
    except ImportError:
        from qtpy import QtCore


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


def _jsonable(value: Any, depth: int = 0) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if depth >= 3:
        return {"type": type(value).__name__, "repr": _safe_repr(value)}
    if isinstance(value, dict):
        return {str(key): _jsonable(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item, depth + 1) for item in value]
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
        self.namespace: dict[str, Any] = {"__builtins__": __builtins__, "Path": Path}
        try:
            from keysight.ads import ael

            self.namespace["ael"] = ael
        except Exception:
            pass
        try:
            from keysight.ads import de

            self.namespace["de"] = de
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
            return {"ok": True, "result": _jsonable(result), "stdout": out.getvalue(), "stderr": err.getvalue(), "error": None}
        except Exception as exc:
            return {"ok": False, "result": None, "stdout": out.getvalue(), "stderr": err.getvalue(), "error": str(exc), "traceback": traceback.format_exc()}

    def _dispatch(self, command: str, args: dict[str, Any]) -> Any:
        if command == "ping":
            return {"status": "ok", "profile": self.profile, "slot": self.slot, "pid": os.getpid()}
        if command == "capabilities":
            return {
                "safe_commands": ["ping", "status", "capabilities"],
                "unsafe_commands": ["eval", "exec", "ael_call"],
                "unsafe_enabled": os.environ.get("ADS_AGENT_UNSAFE") == "1",
                "localhost_only": True,
                "token_required": True,
            }
        if command == "status":
            return self._status()
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
        }
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


def _required_text(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


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
