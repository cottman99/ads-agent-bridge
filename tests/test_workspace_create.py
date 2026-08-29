import json
import subprocess
from types import SimpleNamespace

import pytest

from ads_agent_bridge import workspace_create


def test_create_workspace_refuses_display_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("DISPLAY", ":4.0")
    with pytest.raises(RuntimeError, match="DISPLAY mismatch"):
        workspace_create.create_workspace(
            workspace=tmp_path / "demo_wrk",
            library="Demo_lib",
            cell="Main",
            instance_id=None,
            slot="u2",
            profile="de",
            connection_id="ads-display4",
            expected_display=":5.0",
            timeout=30,
        )


def test_create_workspace_returns_opaque_context(tmp_path, monkeypatch):
    monkeypatch.setenv("DISPLAY", ":4.0")
    instance = SimpleNamespace(
        python_executable="/opt/ads/python",
        product_version="2026 Update 2",
        install_root="/opt/ads",
        instance_id="ads2026u2",
    )
    monkeypatch.setattr(workspace_create, "select_instance", lambda _value: instance)
    monkeypatch.setattr(workspace_create, "runtime_dir", lambda: tmp_path / "runtime")

    def fake_run(command, **_kwargs):
        workspace = command[command.index("--workspace") + 1]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "workspace": workspace,
                    "top_design": "Demo_lib:Main:schematic",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(workspace_create.subprocess, "run", fake_run)
    result = workspace_create.create_workspace(
        workspace=tmp_path / "demo_wrk",
        library="Demo_lib",
        cell="Main",
        instance_id=None,
        slot="u2",
        profile="de",
        connection_id="ads-display4",
        expected_display=":4.0",
        timeout=30,
    )

    from eda_bridge_runtime import EDAContext

    decoded = EDAContext.decode(result["eda_context"])
    assert decoded.locator == {
        "connection_id": "ads-display4",
        "context_id": result["context_id"],
        "profile": "de",
        "slot": "u2",
    }
    assert "workspace" not in decoded.locator
    record = workspace_create.resolve_context(result["context_id"])
    assert record["target"]["workspace"].endswith("demo_wrk")


def test_create_workspace_removes_its_partial_output_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("DISPLAY", ":4.0")
    instance = SimpleNamespace(
        python_executable="/opt/ads/python",
        product_version="2026 Update 2",
        install_root="/opt/ads",
        instance_id="ads2026u2",
    )
    monkeypatch.setattr(workspace_create, "select_instance", lambda _value: instance)
    target = tmp_path / "partial_wrk"

    def fake_run(command, **_kwargs):
        target.mkdir()
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="failed")

    monkeypatch.setattr(workspace_create.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="workspace creation failed"):
        workspace_create.create_workspace(
            workspace=target,
            library="Demo_lib",
            cell="Main",
            instance_id=None,
            slot="u2",
            profile="de",
            connection_id="ads-display4",
            expected_display=":4.0",
            timeout=30,
        )
    assert not target.exists()
