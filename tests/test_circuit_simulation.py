from pathlib import Path

import pytest

from ads_agent_bridge import circuit_simulation
from ads_agent_bridge.simulation_artifacts import accept_dataset_artifact


def _plan(tmp_path: Path) -> dict:
    return {
        "schema_version": "ads.circuit-simulation/v1",
        "operation_id": "run_ac",
        "workspace": str(tmp_path / "source_wrk"),
        "design": "Demo_lib:Main:schematic",
        "output_directory": str(tmp_path / "results"),
        "dataset_name": "accepted.ds",
        "assertions": {
            "minimum_rows": 5,
            "required_columns": ["freq", "Vout"],
            "finite_columns": ["freq", "Vout"],
        },
    }


def test_simulation_plan_is_typed_and_bounded(tmp_path: Path):
    plan = circuit_simulation.validate_simulation_plan(_plan(tmp_path))
    assert plan["assertions"]["minimum_rows"] == 5
    assert plan["dataset_name"] == "accepted.ds"


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


@pytest.mark.parametrize(
    "name", ["../escape.ds", "nested/result.ds", "result.txt", "a b.ds"]
)
def test_simulation_plan_rejects_unsafe_dataset_name(tmp_path: Path, name: str):
    plan = _plan(tmp_path)
    plan["dataset_name"] = name
    with pytest.raises(ValueError, match="simple .ds filename"):
        circuit_simulation.validate_simulation_plan(plan)


def test_simulation_accepts_dataset_under_requested_stable_name(tmp_path: Path):
    output = tmp_path / "results"
    output.mkdir()
    detected = output / "simulator-selected.ds"
    detected.write_bytes(b"native dataset")

    accepted = accept_dataset_artifact(output, detected, "accepted.ds")

    assert accepted == output / "accepted.ds"
    assert accepted.read_bytes() == b"native dataset"
    assert not detected.exists()


def test_simulation_dataset_acceptance_refuses_overwrite(tmp_path: Path):
    output = tmp_path / "results"
    output.mkdir()
    detected = output / "simulator-selected.ds"
    detected.write_bytes(b"new")
    (output / "accepted.ds").write_bytes(b"existing")

    with pytest.raises(FileExistsError, match="already exists"):
        accept_dataset_artifact(output, detected, "accepted.ds")

    assert detected.read_bytes() == b"new"
