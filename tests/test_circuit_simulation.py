from pathlib import Path

import pytest

from ads_agent_bridge import circuit_simulation


def _plan(tmp_path: Path) -> dict:
    return {
        "schema_version": "ads.circuit-simulation/v1",
        "operation_id": "run_ac",
        "workspace": str(tmp_path / "source_wrk"),
        "design": "Demo_lib:Main:schematic",
        "output_directory": str(tmp_path / "results"),
        "assertions": {
            "minimum_rows": 5,
            "required_columns": ["freq", "Vout"],
            "finite_columns": ["freq", "Vout"],
        },
    }


def test_simulation_plan_is_typed_and_bounded(tmp_path: Path):
    plan = circuit_simulation.validate_simulation_plan(_plan(tmp_path))
    assert plan["assertions"]["minimum_rows"] == 5


def test_simulation_plan_rejects_unregistered_fields(tmp_path: Path):
    plan = _plan(tmp_path)
    plan["python"] = "print('escape')"
    with pytest.raises(ValueError, match="unsupported fields"):
        circuit_simulation.validate_simulation_plan(plan)


def test_simulation_refuses_existing_output(tmp_path: Path, monkeypatch):
    plan = _plan(tmp_path)
    Path(plan["workspace"]).mkdir()
    Path(plan["output_directory"]).mkdir()
    monkeypatch.delenv("DISPLAY", raising=False)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        circuit_simulation.execute_simulation_plan(plan)
