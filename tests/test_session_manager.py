from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ads_agent_bridge.models import AdsInstance
from ads_agent_bridge import session_manager


def make_instance(tmp_path: Path) -> AdsInstance:
    root = tmp_path / "ADS2026_Update2"
    executable = root / "bin" / ("ads.exe" if session_manager.os.name == "nt" else "ads")
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="ascii")
    return AdsInstance(
        instance_id="ads-2026-u2-test",
        install_root=str(root),
        product_version="ADS 2026 Update 2",
        year=2026,
        update="2",
        platform="test",
        support_tier="stable",
        executable=str(executable),
    )


def make_workspace(tmp_path: Path, name: str = "Demo_wrk") -> Path:
    workspace = tmp_path / name
    workspace.mkdir()
    (workspace / "lib.defs").write_text("", encoding="ascii")
    (workspace / "cds.lib").write_text("", encoding="ascii")
    return workspace


def test_launch_dry_run_binds_argument_and_cwd_to_workspace(tmp_path: Path, monkeypatch) -> None:
    instance = make_instance(tmp_path)
    workspace = make_workspace(tmp_path)
    monkeypatch.setattr(session_manager, "select_instance", lambda _: instance)
    monkeypatch.setattr(session_manager, "_live_bridge", lambda _: None)
    monkeypatch.setattr(session_manager, "_live_slot_records", lambda _: [])

    payload = session_manager.launch(None, workspace, display=":4", dry_run=True)

    assert payload["status"] == "planned"
    assert payload["plan"]["workspace"] == str(workspace.resolve())
    assert payload["plan"]["working_directory"] == str(workspace.resolve())
    assert payload["plan"]["command"] == [instance.executable, str(workspace.resolve())]


def test_launch_records_nonce_bound_ownership_only_after_verification(tmp_path: Path, monkeypatch) -> None:
    instance = make_instance(tmp_path)
    workspace = make_workspace(tmp_path)
    state = tmp_path / "state"
    calls = {}

    class FakeProcess:
        pid = 1234

    def fake_popen(command, **kwargs):
        calls["command"] = command
        calls["kwargs"] = kwargs
        return FakeProcess()

    bridge = {
        "slot": "ads_2026_u2_test",
        "profile": "de",
        "pid": 4321,
        "started_at": "2026-08-06T00:00:00+00:00",
        "managed_session_id": "owned-nonce",
    }
    monkeypatch.setenv("ADS_AGENT_HOME", str(state))
    monkeypatch.setattr(session_manager, "select_instance", lambda _: instance)
    monkeypatch.setattr(session_manager, "_live_bridge", lambda _: None)
    monkeypatch.setattr(session_manager, "_live_slot_records", lambda _: [])
    monkeypatch.setattr(session_manager.uuid, "uuid4", lambda: SimpleNamespace(hex="owned-nonce"))
    monkeypatch.setattr(session_manager.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(session_manager, "_wait_for_bridge", lambda *_: bridge)
    monkeypatch.setattr(
        session_manager,
        "_verified_workspace",
        lambda *_: {"ok": True, "expected": str(workspace), "actual": str(workspace)},
    )
    monkeypatch.setattr(
        session_manager,
        "request",
        lambda *_args, **_kwargs: {
            "ok": True,
            "result": {"workspace_is_open": True, "workspace": str(workspace), "ui": {"modal_blocking": False}},
        },
    )

    payload = session_manager.launch(None, workspace, display=":4")
    record = session_manager._managed_record("ads_2026_u2_test")

    assert payload["status"] == "ready"
    assert payload["ownership"] == "agent-owned"
    assert calls["kwargs"]["cwd"] == str(workspace.resolve())
    assert calls["kwargs"]["env"]["ADS_AGENT_MANAGED_SESSION_ID"] == "owned-nonce"
    assert calls["kwargs"]["env"]["ADS_AGENT_INSTANCE_ID"] == instance.instance_id
    assert calls["kwargs"]["env"]["DISPLAY"] == ":4"
    assert calls["kwargs"]["stdin"] == session_manager.subprocess.DEVNULL
    assert calls["kwargs"]["stderr"] == session_manager.subprocess.STDOUT
    assert calls["kwargs"]["stdout"].closed is True
    assert record is not None
    assert record["managed_session_id"] == "owned-nonce"
    assert record["ads_pid"] == 4321


def test_reuse_refuses_different_workspace_without_closing_it(tmp_path: Path, monkeypatch) -> None:
    instance = make_instance(tmp_path)
    requested = make_workspace(tmp_path, "Requested_wrk")
    other = make_workspace(tmp_path, "Other_wrk")
    monkeypatch.setattr(session_manager, "select_instance", lambda _: instance)
    monkeypatch.setattr(session_manager, "_live_bridge", lambda _: {"slot": "test", "pid": 10})
    monkeypatch.setattr(
        session_manager,
        "request",
        lambda *_args, **_kwargs: {
            "ok": True,
            "result": {
                "hpeesof_dir": instance.install_root,
                "workspace_is_open": True,
                "workspace": str(other),
            },
        },
    )

    with pytest.raises(session_manager.SessionError, match="different workspace"):
        session_manager.launch(None, requested, slot="test", display=":4", reuse_existing=True)


def test_reuse_refuses_bridge_from_different_ads_installation(tmp_path: Path, monkeypatch) -> None:
    instance = make_instance(tmp_path)
    workspace = make_workspace(tmp_path)
    different_root = tmp_path / "ADS2025"
    calls = []
    monkeypatch.setattr(session_manager, "select_instance", lambda _: instance)
    monkeypatch.setattr(session_manager, "_live_bridge", lambda _: {"slot": "test", "pid": 10})

    def fake_request(command, *_args, **_kwargs):
        calls.append(command)
        return {
            "ok": True,
            "result": {
                "hpeesof_dir": str(different_root),
                "workspace_is_open": False,
            },
        }

    monkeypatch.setattr(session_manager, "request", fake_request)

    with pytest.raises(session_manager.SessionError, match="different or unverifiable ADS installation"):
        session_manager.launch(None, workspace, slot="test", display=":4", reuse_existing=True)

    assert calls == ["status"]


def test_shutdown_refuses_session_without_matching_ownership(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(session_manager, "_managed_record", lambda _: None)
    monkeypatch.setattr(session_manager, "_live_bridge", lambda _: {"slot": "test", "pid": 20})
    monkeypatch.setattr(
        session_manager,
        "_session_summary",
        lambda *_: {"slot": "test", "ownership": "user-owned", "modal": {}},
    )

    with pytest.raises(session_manager.SessionError, match="Refusing to close"):
        session_manager.shutdown("test")


def test_shutdown_refuses_active_modal_without_sending_exit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    managed = {"managed_session_id": "owned", "ads_pid": 30, "slot": "test"}
    monkeypatch.setattr(session_manager, "_managed_record", lambda _: managed)
    monkeypatch.setattr(session_manager, "_live_bridge", lambda _: {"slot": "test", "pid": 30})
    monkeypatch.setattr(
        session_manager,
        "_session_summary",
        lambda *_: {
            "slot": "test",
            "ownership": "agent-owned",
            "modal": {"modal_blocking": True, "title": "Save changes?"},
        },
    )
    monkeypatch.setattr(
        session_manager,
        "request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not request shutdown")),
    )

    with pytest.raises(session_manager.SessionError, match="modal dialog"):
        session_manager.shutdown("test")


def test_shutdown_removes_record_after_native_safe_exit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    managed = {"managed_session_id": "owned", "ads_pid": 40, "slot": "test"}
    bridges = iter(({"slot": "test", "pid": 40}, None))
    monkeypatch.setattr(session_manager, "_managed_record", lambda _: managed)
    monkeypatch.setattr(session_manager, "_live_bridge", lambda _: next(bridges))
    monkeypatch.setattr(
        session_manager,
        "_session_summary",
        lambda *_: {"slot": "test", "ownership": "agent-owned", "modal": {"modal_blocking": False}},
    )
    monkeypatch.setattr(
        session_manager,
        "request",
        lambda *_args, **_kwargs: {"ok": True, "result": {"accepted": True}},
    )
    monkeypatch.setattr(session_manager, "pid_running", lambda _: False)
    monkeypatch.setattr(session_manager, "_remove_managed_record", lambda *_: True)
    monkeypatch.setattr(session_manager, "_cleanup_stale_bridge_records", lambda *_: ["de.json", "dds.json"])
    monkeypatch.setattr(session_manager, "_live_slot_records", lambda _: [])

    payload = session_manager.shutdown("test", wait_seconds=1)

    assert payload["status"] == "exited"
    assert payload["record_removed"] is True
    assert payload["stale_bridge_records_removed"] == ["de.json", "dds.json"]


def test_stale_bridge_cleanup_requires_dead_owned_slot_records(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    runtime = session_manager.runtime_dir()
    records = {
        "session-test-de.json": {"slot": "test", "profile": "de", "pid": 11, "managed_session_id": "owned"},
        "session-test-dds.json": {"slot": "test", "profile": "dds", "pid": 12, "managed_session_id": None},
        "session-test-other.json": {"slot": "test", "profile": "other", "pid": 13, "managed_session_id": "someone-else"},
        "session-live-de.json": {"slot": "live", "profile": "de", "pid": 14, "managed_session_id": "owned"},
    }
    for name, payload in records.items():
        session_manager._write_json(runtime / name, payload)
    monkeypatch.setattr(session_manager, "pid_running", lambda pid: pid == 14)

    removed = session_manager._cleanup_stale_bridge_records("test", "owned")

    assert {Path(path).name for path in removed} == {"session-test-de.json", "session-test-dds.json"}
    assert (runtime / "session-test-other.json").is_file()
    assert (runtime / "session-live-de.json").is_file()


def test_live_slot_records_include_all_profiles_and_block_partial_slot_claim(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    runtime = session_manager.runtime_dir()
    instance = make_instance(tmp_path)
    workspace = make_workspace(tmp_path)
    session_manager._write_json(
        runtime / "session-partial-dds.json",
        {"slot": "partial", "profile": "dds", "pid": 51},
    )
    monkeypatch.setattr(session_manager, "pid_running", lambda pid: pid == 51)
    monkeypatch.setattr(session_manager, "select_instance", lambda _: instance)
    monkeypatch.setattr(session_manager, "_live_bridge", lambda _: None)

    assert session_manager._live_slot_records("partial") == [
        {"profile": "dds", "pid": 51, "session_file": str(runtime / "session-partial-dds.json")}
    ]
    with pytest.raises(session_manager.SessionError, match="partially occupied"):
        session_manager.launch(None, workspace, slot="partial", display=":4")


def test_status_reports_stale_managed_record_without_claiming_live_ownership(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    session_manager._write_json(
        session_manager._managed_path("old"),
        {"managed_session_id": "old-id", "slot": "old", "ads_pid": 2_147_483_647, "workspace": "old"},
    )
    monkeypatch.setattr(session_manager, "list_sessions", lambda _: [])

    payload = session_manager.status("old")

    assert payload["sessions"][0]["state"] == "orphaned"
    assert payload["sessions"][0]["ownership"] == "orphaned-record"


def test_launch_timeout_preserves_recoverable_starting_record(tmp_path: Path, monkeypatch) -> None:
    instance = make_instance(tmp_path)
    workspace = make_workspace(tmp_path)
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(session_manager, "select_instance", lambda _: instance)
    monkeypatch.setattr(session_manager, "_live_bridge", lambda _: None)
    monkeypatch.setattr(session_manager, "_live_slot_records", lambda _: [])
    monkeypatch.setattr(session_manager.uuid, "uuid4", lambda: SimpleNamespace(hex="starting-nonce"))
    def fake_popen(*_args, **kwargs):
        kwargs["stdout"].write(b"waiting for license\n")
        return SimpleNamespace(pid=1234)

    monkeypatch.setattr(session_manager.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        session_manager,
        "_wait_for_bridge",
        lambda *_: (_ for _ in ()).throw(session_manager.SessionError("bridge timeout")),
    )
    monkeypatch.setattr(session_manager, "pid_running", lambda pid: pid == 1234)

    payload = session_manager.launch(None, workspace, display=":4")
    record = session_manager._managed_record("ads_2026_u2_test")

    assert payload["status"] == "starting"
    assert payload["session"]["state"] == "starting"
    assert payload["session"]["log_path"].endswith("managed-session-ads_2026_u2_test.log")
    assert "waiting for license" in payload["diagnostics"]["log_tail"]
    assert record is not None
    assert record["state"] == "starting"
    assert record["launcher_pid"] == 1234
    assert record["ads_pid"] is None


def test_status_adopts_nonce_bound_linux_ads_process_after_wrapper_exit(monkeypatch) -> None:
    managed = {
        "state": "starting",
        "managed_session_id": "owned-nonce",
        "slot": "blind-slot",
        "launcher_pid": 1234,
        "ads_pid": None,
        "workspace": "/tmp/BlindStart_wrk",
        "display": ":4",
    }
    monkeypatch.setattr(
        session_manager,
        "managed_ads_processes",
        lambda *_: [
            {"pid": 4321, "process_name": "hpeesofde", "role": "design-environment"},
            {"pid": 4320, "process_name": "hpeesofemx", "role": "ads-runtime"},
        ],
    )
    monkeypatch.setattr(
        session_manager,
        "managed_host_processes",
        lambda *_: [
            {
                "pid": 4330,
                "parent_pid": 4321,
                "process_name": "aglmpsel_exe",
                "role": "managed-child",
            }
        ],
    )
    monkeypatch.setattr(session_manager, "pid_running", lambda pid: pid == 4321)

    summary = session_manager._session_summary("blind-slot", None, managed)

    assert summary["state"] == "waiting-for-host-ui"
    assert summary["ownership"] == "agent-owned-unverified"
    assert summary["ads_pid"] == 4321
    assert summary["host_ui"]["phase"] == "pre-bridge"
    assert summary["host_ui"]["display"] == ":4"
    assert summary["host_ui"]["candidate_processes"][0]["process_name"] == "aglmpsel_exe"
    assert "must not guess a license choice" in summary["host_ui"]["action_policy"]


def test_explicit_host_ui_wait_state_does_not_depend_on_wrapper_exit(monkeypatch) -> None:
    managed = {
        "state": "waiting-for-host-ui",
        "managed_session_id": "owned-nonce",
        "slot": "blind-slot",
        "launcher_pid": 1234,
        "ads_pid": 4321,
        "workspace": "/tmp/BlindStart_wrk",
        "display": ":4",
    }
    monkeypatch.setattr(
        session_manager,
        "managed_ads_processes",
        lambda *_: [{"pid": 4321, "process_name": "hpeesofde", "role": "design-environment"}],
    )
    monkeypatch.setattr(session_manager, "pid_running", lambda pid: pid in {1234, 4321})

    summary = session_manager._session_summary("blind-slot", None, managed)

    assert summary["state"] == "waiting-for-host-ui"
    assert summary["launcher_pid"] == 1234
    assert summary["ads_pid"] == 4321


def test_launch_refuses_duplicate_when_wrapper_exited_but_nonce_bound_ads_is_alive(
    tmp_path: Path, monkeypatch
) -> None:
    instance = make_instance(tmp_path)
    workspace = make_workspace(tmp_path)
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    session_manager._write_json(
        session_manager._managed_path("blind-slot"),
        {
            "state": "starting",
            "managed_session_id": "owned-nonce",
            "slot": "blind-slot",
            "launcher_pid": 1234,
            "ads_pid": None,
        },
    )
    monkeypatch.setattr(session_manager, "select_instance", lambda _: instance)
    monkeypatch.setattr(session_manager, "_live_bridge", lambda _: None)
    monkeypatch.setattr(
        session_manager,
        "managed_ads_processes",
        lambda *_: [{"pid": 4321, "process_name": "hpeesofde", "role": "design-environment"}],
    )
    monkeypatch.setattr(session_manager, "pid_running", lambda pid: pid == 4321)

    with pytest.raises(session_manager.SessionError, match="already has a managed ADS launch"):
        session_manager.launch(None, workspace, slot="blind-slot", display=":4")


def test_provisional_record_adopts_only_matching_bridge_nonce() -> None:
    record = {"managed_session_id": "nonce", "slot": "test", "ads_pid": None}

    assert session_manager._identity_matches(
        record,
        {"managed_session_id": "nonce", "slot": "test", "pid": 44},
    )
    assert not session_manager._identity_matches(
        record,
        {"managed_session_id": "different", "slot": "test", "pid": 44},
    )


def test_session_summary_reports_unknown_modal_as_user_resolvable_blockage(monkeypatch) -> None:
    bridge = {"managed_session_id": "nonce", "slot": "test", "pid": 44}
    record = {"managed_session_id": "nonce", "slot": "test", "ads_pid": 44}
    monkeypatch.setattr(
        session_manager,
        "request",
        lambda *_args, **_kwargs: {
            "ok": True,
            "result": {
                "workspace_is_open": True,
                "workspace": "Demo_wrk",
                "ui": {"modal_blocking": True, "title": "Unexpected dialog"},
            },
        },
    )

    summary = session_manager._session_summary("test", bridge, record)

    assert summary["state"] == "blocked-by-dialog"
    assert summary["ownership"] == "agent-owned"
    assert "exact fingerprint and button ID" in summary["next_actions"][1]


def test_remove_managed_record_requires_identity_and_really_unlinks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    path = session_manager._managed_path("test")
    session_manager._write_json(path, {"managed_session_id": "owned", "slot": "test"})

    assert session_manager._remove_managed_record("test", "other") is False
    assert path.is_file()
    assert session_manager._remove_managed_record("test", "owned") is True
    assert not path.exists()


def test_slot_operation_lock_rejects_overlapping_lifecycle_action(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))

    with session_manager._slot_operation_lock("test"):
        with pytest.raises(session_manager.SessionError, match="already in progress"):
            with session_manager._slot_operation_lock("test"):
                pass


def test_shutdown_reports_native_prompt_as_awaiting_user_action(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ADS_AGENT_HOME", str(tmp_path / "state"))
    managed = {"managed_session_id": "owned", "ads_pid": 40, "slot": "test"}
    bridge = {"managed_session_id": "owned", "slot": "test", "pid": 40}
    monotonic = iter((0.0, 0.0, 1.0))
    monkeypatch.setattr(session_manager, "_managed_record", lambda _: managed)
    monkeypatch.setattr(session_manager, "_live_bridge", lambda _: bridge)
    monkeypatch.setattr(
        session_manager,
        "_session_summary",
        lambda *_: {"slot": "test", "ownership": "agent-owned", "modal": {"modal_blocking": False}},
    )
    monkeypatch.setattr(
        session_manager,
        "request",
        lambda *_args, **_kwargs: {"ok": True, "result": {"accepted": True, "state": "scheduled"}},
    )
    monkeypatch.setattr(session_manager, "pid_running", lambda _: True)
    monkeypatch.setattr(session_manager, "_live_slot_records", lambda _: [])
    monkeypatch.setattr(
        session_manager,
        "_bridge_status",
        lambda *_: {
            "ok": True,
            "result": {
                "shutdown": {"state": "prompting"},
                "ui": {"modal_blocking": True, "title": "Save changes?"},
            },
        },
    )
    monkeypatch.setattr(session_manager.time, "monotonic", lambda: next(monotonic))
    monkeypatch.setattr(session_manager.time, "sleep", lambda _: None)

    payload = session_manager.shutdown("test", wait_seconds=0.5)

    assert payload["status"] == "awaiting-user-action"
    assert payload["record_retained"] is True
    assert payload["shutdown"]["state"] == "prompting"
    assert "no controls were clicked" in payload["warning"]


def test_disconnect_never_closes_ads() -> None:
    payload = session_manager.disconnect("Example Slot")
    assert payload["status"] == "disconnected"
    assert payload["ads_left_running"] is True
    assert payload["slot"] == "example_slot"
