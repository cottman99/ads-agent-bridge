from __future__ import annotations

import json
import re
import socket
from pathlib import Path
from typing import Any

from .paths import _override_root
from .processes import pid_running


def normalize_slot(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower() or "default"


def runtime_dir(*, ensure: bool = True) -> Path:
    override = _override_root(ensure=ensure)
    if override:
        path = override / "runtime"
    else:
        path = Path.home() / ".ads-agent" / "runtime"
    if ensure:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _load_sessions(profile: str | None = None) -> list[dict[str, Any]]:
    sessions = []
    for path in sorted(runtime_dir(ensure=False).glob("session-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if profile and payload.get("profile") != profile:
            continue
        if not pid_running(payload.get("pid")):
            continue
        payload["session_file"] = str(path)
        sessions.append(payload)
    return sessions


def list_sessions(profile: str | None = None) -> list[dict[str, Any]]:
    sessions = []
    for payload in _load_sessions(profile):
        public = dict(payload)
        public["has_token"] = bool(public.pop("token", None))
        sessions.append(public)
    return sessions


def select_session(slot: str | None, profile: str) -> dict[str, Any]:
    candidates = _load_sessions(profile)
    if slot:
        normalized_slot = normalize_slot(slot)
        candidates = [item for item in candidates if item.get("slot") == normalized_slot]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError(f"No bridge session found for slot={slot or '*'} profile={profile}")
    raise ValueError(f"Multiple bridge sessions found for profile={profile}; pass --slot")


def _request_session(session: dict[str, Any], command: str, args: dict[str, Any], timeout: float) -> dict[str, Any]:
    payload = {"token": session["token"], "command": command, "args": args}
    with socket.create_connection((session["host"], int(session["port"])), timeout=timeout) as sock:
        sock.sendall(json.dumps(payload).encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    response = json.loads(b"".join(chunks).decode("utf-8"))
    response["session"] = {key: session.get(key) for key in ("slot", "profile", "pid", "port", "started_at", "session_file")}
    return response


def request(command: str, args: dict[str, Any], slot: str | None, profile: str, timeout: float = 15) -> dict[str, Any]:
    return _request_session(select_session(slot, profile), command, args, timeout)


def probe_sessions(profile: str | None = None, timeout: float = 1.0) -> list[dict[str, Any]]:
    results = []
    for session in _load_sessions(profile):
        public = {key: session.get(key) for key in ("slot", "profile", "pid", "port", "started_at", "session_file")}
        try:
            response = _request_session(session, "ping", {}, timeout)
            public.update({"reachable": True, "ok": bool(response.get("ok")), "error": response.get("error")})
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            public.update({"reachable": False, "ok": False, "error": str(exc)})
        results.append(public)
    return results
