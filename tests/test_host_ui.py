from __future__ import annotations

from pathlib import Path

import pytest

from ads_agent_bridge import host_ui


def _waiting_session() -> dict:
    return {
        "slot": "candidate",
        "state": "waiting-for-host-ui",
        "managed_session_id": "owned-nonce",
        "workspace": "/tmp/Probe_wrk",
        "display": ":4",
        "host_ui": {
            "xauthority": "/tmp/test.Xauthority",
            "candidate_processes": [
                {"pid": 41, "process_name": "hpeesofde"},
                {"pid": 42, "process_name": "aglmpsel_exe"},
            ]
        },
    }


def _window() -> dict:
    return {
        "window_id": "0x2a",
        "pid": 42,
        "title": "Product Selection",
        "class_name": "aglmpsel_exe.aglmpsel_exe",
        "visible": True,
        "enabled": True,
        "geometry": {"x": 10, "y": 20, "width": 600, "height": 320},
        "coordinate_space": "x11-client-pixels",
    }


def _prepare(monkeypatch) -> None:
    monkeypatch.setattr(host_ui, "_platform_name", lambda: "posix")
    monkeypatch.setattr(host_ui, "session_status", lambda _slot: {"sessions": [_waiting_session()]})
    monkeypatch.setattr(host_ui, "_linux_candidate_windows", lambda _display, _pids, _auth: [_window()])


def test_snapshot_binds_nonce_process_window_and_image(monkeypatch, tmp_path: Path) -> None:
    _prepare(monkeypatch)
    captured = []

    def fake_capture(display_name, xauthority, target, path):
        captured.append((display_name, xauthority, target["window_id"], path))
        path.write_bytes(b"png")

    monkeypatch.setattr(host_ui, "_linux_capture", fake_capture)
    image = tmp_path / "target.png"

    payload = host_ui.snapshot("candidate", image_out=image)

    assert payload["status"] == "ready"
    assert payload["managed_session_id"] == "owned-nonce"
    assert payload["candidate_pids"] == [41, 42]
    assert len(payload["windows"][0]["fingerprint"]) == 64
    assert payload["windows"][0]["coordinate_space"] == "x11-client-pixels"
    assert payload["selected"]["window_id"] == "0x2a"
    assert captured == [(":4", "/tmp/test.Xauthority", "0x2a", image.resolve())]


def test_action_rejects_changed_fingerprint(monkeypatch) -> None:
    _prepare(monkeypatch)

    with pytest.raises(host_ui.HostUiError, match="fingerprint changed"):
        host_ui.action(
            "candidate",
            window_id="0x2a",
            fingerprint="stale",
            operation="click",
            x=10,
            y=10,
            risk="medium",
            authorization="workflow-policy",
            reason="Select the explicitly configured license",
        )


def test_action_rechecks_bounds_and_authorization(monkeypatch) -> None:
    _prepare(monkeypatch)
    current = host_ui.snapshot("candidate")
    fingerprint = current["windows"][0]["fingerprint"]

    with pytest.raises(host_ui.HostUiError, match="insufficient"):
        host_ui.action(
            "candidate",
            window_id="0x2a",
            fingerprint=fingerprint,
            operation="click",
            x=10,
            y=10,
            risk="medium",
            authorization="automatic",
            reason="Select the explicitly configured license",
        )
    with pytest.raises(host_ui.HostUiError, match="outside"):
        host_ui.action(
            "candidate",
            window_id="0x2a",
            fingerprint=fingerprint,
            operation="click",
            x=600,
            y=10,
            risk="medium",
            authorization="workflow-policy",
            reason="Select the explicitly configured license",
        )


def test_action_executes_one_verified_linux_click(monkeypatch) -> None:
    _prepare(monkeypatch)
    current = host_ui.snapshot("candidate")
    fingerprint = current["windows"][0]["fingerprint"]
    calls = []
    monkeypatch.setattr(
        host_ui,
        "_linux_click",
        lambda display, auth, target, x, y: calls.append((display, auth, target, x, y)),
    )
    monkeypatch.setattr(host_ui.time, "sleep", lambda _seconds: None)

    payload = host_ui.action(
        "candidate",
        window_id="0x2a",
        fingerprint=fingerprint,
        operation="click",
        x=100,
        y=94,
        risk="medium",
        authorization="workflow-policy",
        reason="Select the explicitly configured license",
    )

    assert payload["status"] == "accepted"
    assert payload["point"] == {"x": 100, "y": 94}
    assert len(calls) == 1
    assert calls[0][0] == ":4"
    assert calls[0][1] == "/tmp/test.Xauthority"
    assert calls[0][2]["window_id"] == "0x2a"
    assert calls[0][2]["fingerprint"] == fingerprint
    assert calls[0][3:] == (100, 94)
