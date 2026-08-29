import json
import subprocess
from types import SimpleNamespace

import pytest

from ads_agent_bridge import design_plan


def plan(source, output):
    return {
        "schema_version": "ads.design-plan/v1",
        "operation_id": "eval_plan",
        "source_workspace": str(source),
        "output_workspace": str(output),
        "design": "Demo_lib:Main:schematic",
        "expected_before": {"instance_names": []},
        "operations": [
            {
                "op": "add_instance",
                "item": ["ads_rflib", "R", "symbol"],
                "at": [0, 0],
                "name": "R1",
                "parameters": {"R": "50 Ohm"},
            },
            {"op": "add_wire", "points": [[0, 0], [1, 0]], "label": "OUT"},
        ],
        "assertions": {
            "instance_names": ["R1"],
            "parameters": [{"instance": "R1", "parameter": "R", "value": "50 Ohm"}],
            "netlist_contains": ["R1"],
        },
    }


def test_validate_design_plan_rejects_raw_or_unknown_operations(tmp_path):
    value = plan(tmp_path / "source", tmp_path / "output")
    value["operations"] = [{"op": "python", "code": "print('unsafe')"}]
    with pytest.raises(ValueError, match="unsupported design operation"):
        design_plan.validate_design_plan(value)


def test_execute_design_plan_preserves_source_and_promotes_verified_copy(
    tmp_path, monkeypatch
):
    source = tmp_path / "source_wrk"
    output = tmp_path / "output_wrk"
    source.mkdir()
    (source / "workspace.ads").write_text("source", encoding="utf-8")
    instance = SimpleNamespace(
        python_executable="/opt/ads/python",
        product_version="2026 Update 2",
        install_root="/opt/ads",
    )
    monkeypatch.setattr(design_plan, "select_instance", lambda _value: instance)
    before = design_plan.workspace_fingerprint(source)

    def fake_run(command, **_kwargs):
        staged = command[command.index("--workspace") + 1]
        assert staged != str(source)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "readback": {
                        "instance_count": 1,
                        "instance_names": ["R1"],
                        "assertion_count": 3,
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(design_plan.subprocess, "run", fake_run)
    result = design_plan.execute_design_plan(plan(source, output))

    assert result["status"] == "passed"
    assert result["source_preserved"] is True
    assert result["fresh_reopen"] is True
    assert output.is_dir()
    assert design_plan.workspace_fingerprint(source) == before


def test_execute_design_plan_removes_staging_on_failure(tmp_path, monkeypatch):
    source = tmp_path / "source_wrk"
    output = tmp_path / "output_wrk"
    source.mkdir()
    (source / "workspace.ads").write_text("source", encoding="utf-8")
    instance = SimpleNamespace(
        python_executable="/opt/ads/python",
        product_version="2026 Update 2",
        install_root="/opt/ads",
    )
    monkeypatch.setattr(design_plan, "select_instance", lambda _value: instance)
    monkeypatch.setattr(
        design_plan.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 1, stdout=json.dumps({"ok": False, "error": "failed"}), stderr=""
        ),
    )

    with pytest.raises(RuntimeError, match="structured design apply failed"):
        design_plan.execute_design_plan(plan(source, output))
    assert not output.exists()
    assert not list(tmp_path.glob(".output_wrk.staging-*"))
