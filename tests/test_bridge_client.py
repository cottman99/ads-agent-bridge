import json
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
            }
        ),
        encoding="utf-8",
    )

    public = list_sessions("de")[0]

    assert public["has_token"] is True
    assert "token" not in public
    assert select_session("test", "de")["token"] == "do-not-print-me"
