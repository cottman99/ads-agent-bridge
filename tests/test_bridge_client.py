import json
import os
from pathlib import Path

from ads_agent_bridge.bridge_client import list_sessions, select_session


def test_session_listing_redacts_transport_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path))
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "session-test-de.json").write_text(
        json.dumps(
            {
                "slot": "test",
                "profile": "de",
                "host": "127.0.0.1",
                "port": 8875,
                "token": "do-not-print-me",
                "pid": os.getpid(),
            }
        ),
        encoding="utf-8",
    )

    public = list_sessions("de")[0]

    assert public["has_token"] is True
    assert "token" not in public
    assert select_session("TEST", "de")["token"] == "do-not-print-me"


def test_slot_selection_uses_server_normalization(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path))
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "session-windows_live_test-de.json").write_text(
        json.dumps(
            {
                "slot": "windows_live_test",
                "profile": "de",
                "host": "127.0.0.1",
                "port": 8875,
                "token": "secret",
                "pid": os.getpid(),
            }
        ),
        encoding="utf-8",
    )

    assert select_session("Windows-Live-Test", "de")["slot"] == "windows_live_test"


def test_stale_sessions_are_hidden(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path))
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "session-stale-de.json").write_text(
        json.dumps(
            {
                "slot": "stale",
                "profile": "de",
                "host": "127.0.0.1",
                "port": 8875,
                "token": "secret",
                "pid": 2_147_483_647,
            }
        ),
        encoding="utf-8",
    )

    assert list_sessions("de") == []


def test_empty_session_listing_is_read_only(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "missing-state"
    monkeypatch.setenv("ADS_AGENT_HOME", str(state))

    assert list_sessions() == []
    assert not state.exists()
