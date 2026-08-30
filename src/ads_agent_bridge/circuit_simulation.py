"""Typed ADS circuit simulation and dataset acceptance."""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from importlib.resources import files
from pathlib import Path
from typing import Any

from .config import select_instance
from .design_plan import _environment, _result

_SCHEMA = "ads.circuit-simulation/v1"
_LCV = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]{0,127}:[A-Za-z_][A-Za-z0-9_]{0,127}:schematic"
)


def validate_simulation_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("circuit.simulate requires a structured plan object")
    plan = dict(value)
    allowed = {
        "schema_version",
        "operation_id",
        "workspace",
        "design",
        "output_directory",
        "instance",
        "assertions",
    }
    unknown = sorted(set(plan) - allowed)
    if unknown:
        raise ValueError("simulation plan contains unsupported fields: " + ", ".join(unknown))
    required = ("schema_version", "operation_id", "workspace", "design", "output_directory", "assertions")
    missing = [name for name in required if not plan.get(name)]
    if missing:
        raise ValueError("simulation plan is missing: " + ", ".join(missing))
    if plan["schema_version"] != _SCHEMA:
        raise ValueError(f"unsupported simulation plan schema: {plan['schema_version']}")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", str(plan["operation_id"])):
        raise ValueError("operation_id must be a simple identifier")
    if not _LCV.fullmatch(str(plan["design"])):
        raise ValueError("design must be a library:cell:schematic identifier")
    assertions = plan["assertions"]
    if not isinstance(assertions, dict):
        raise TypeError("assertions must be an object")
    if set(assertions) - {"minimum_rows", "required_columns", "finite_columns"}:
        raise ValueError("simulation assertions contain unsupported fields")
    minimum_rows = assertions.get("minimum_rows", 1)
    if not isinstance(minimum_rows, int) or isinstance(minimum_rows, bool) or minimum_rows < 1:
        raise ValueError("assertions.minimum_rows must be a positive integer")
    for field in ("required_columns", "finite_columns"):
        values = assertions.get(field, [])
        if not isinstance(values, list) or any(
            not isinstance(item, str) or not item or len(item) > 256 for item in values
        ):
            raise ValueError(f"assertions.{field} must be a bounded string list")
    if not assertions.get("required_columns"):
        raise ValueError("simulation requires at least one required dataset column")
    plan["assertions"] = {
        "minimum_rows": minimum_rows,
        "required_columns": list(assertions.get("required_columns", [])),
        "finite_columns": list(assertions.get("finite_columns", [])),
    }
    return plan


def execute_simulation_plan(
    value: Any, *, expected_display: str | None = None, timeout: float = 600
) -> dict[str, Any]:
    plan = validate_simulation_plan(value)
    actual_display = os.environ.get("DISPLAY")
    if expected_display and actual_display != expected_display:
        raise RuntimeError(
            f"Configured DISPLAY mismatch: expected {expected_display}, got {actual_display}"
        )
    workspace = Path(str(plan["workspace"])).expanduser().resolve()
    output = Path(str(plan["output_directory"])).expanduser().resolve()
    if not workspace.is_dir():
        raise FileNotFoundError(f"workspace does not exist: {workspace}")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite simulation output: {output}")
    instance = select_instance(plan.get("instance"))
    if not instance.python_executable:
        raise RuntimeError(f"ADS Python was not discovered for {instance.product_version}")
    plan_path = output.parent / f".{output.name}.simulation-{uuid.uuid4().hex}.json"
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        worker = files("ads_agent_bridge").joinpath("circuit_simulation_worker.py")
        completed = subprocess.run(
            [
                instance.python_executable,
                str(worker),
                "--plan",
                str(plan_path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_environment(instance.install_root),
            cwd=str(output.parent),
            check=False,
        )
        record = _result(completed.stdout or "")
        if completed.returncode or not record or not record.get("ok"):
            detail = (record or {}).get("error") or (completed.stderr or "")[-1000:]
            raise RuntimeError(f"ADS circuit simulation failed: {detail}")
        return {
            "status": "passed",
            "operation_id": plan["operation_id"],
            "workspace": str(workspace),
            "design": plan["design"],
            "output_directory": str(output),
            "simulation_completed": True,
            "dataset_read_back": True,
            "readback": record["readback"],
            "artifacts": record["artifacts"],
        }
    finally:
        plan_path.unlink(missing_ok=True)

