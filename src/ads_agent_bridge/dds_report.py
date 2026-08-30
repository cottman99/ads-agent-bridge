"""Typed DDS report creation from an existing ADS dataset."""

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

_SCHEMA = "ads.dds-report/v1"
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")


def validate_dds_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("dds.create requires a structured plan object")
    plan = dict(value)
    allowed = {
        "schema_version",
        "operation_id",
        "workspace",
        "dataset",
        "output_file",
        "instance",
        "page",
        "equations",
        "plots",
    }
    unknown = sorted(set(plan) - allowed)
    if unknown:
        raise ValueError("DDS plan contains unsupported fields: " + ", ".join(unknown))
    required = ("schema_version", "operation_id", "workspace", "dataset", "output_file", "page")
    missing = [name for name in required if not plan.get(name)]
    if missing:
        raise ValueError("DDS plan is missing: " + ", ".join(missing))
    if plan["schema_version"] != _SCHEMA:
        raise ValueError(f"unsupported DDS plan schema: {plan['schema_version']}")
    if not _IDENTIFIER.fullmatch(str(plan["operation_id"])):
        raise ValueError("operation_id must be a simple identifier")
    if not isinstance(plan["page"], str) or len(plan["page"]) > 128:
        raise ValueError("page must be a bounded string")
    equations = plan.get("equations", [])
    plots = plan.get("plots", [])
    if not isinstance(equations, list) or len(equations) > 64:
        raise ValueError("equations must be a list with at most 64 entries")
    if not isinstance(plots, list) or not plots or len(plots) > 32:
        raise ValueError("plots must contain between 1 and 32 entries")
    normalized_equations = []
    for index, item in enumerate(equations):
        if (
            not isinstance(item, dict)
            or set(item) != {"name", "expression"}
            or not _IDENTIFIER.fullmatch(str(item.get("name") or ""))
            or not isinstance(item.get("expression"), str)
            or not item["expression"]
            or len(item["expression"]) > 512
        ):
            raise ValueError(f"equations[{index}] is invalid")
        normalized_equations.append(dict(item))
    normalized_plots = []
    for index, item in enumerate(plots):
        if not isinstance(item, dict) or set(item) != {"name", "traces", "rect"}:
            raise ValueError(f"plots[{index}] is invalid")
        rect = item["rect"]
        traces = item["traces"]
        if (
            not isinstance(item["name"], str)
            or not item["name"]
            or len(item["name"]) > 128
            or not isinstance(traces, list)
            or not traces
            or len(traces) > 32
            or any(not isinstance(trace, str) or not trace or len(trace) > 512 for trace in traces)
            or not isinstance(rect, list)
            or len(rect) != 4
            or any(not isinstance(number, int) or isinstance(number, bool) for number in rect)
            or rect[2] <= 0
            or rect[3] <= 0
        ):
            raise ValueError(f"plots[{index}] is invalid")
        normalized_plots.append(
            {"name": item["name"], "traces": list(traces), "rect": list(rect)}
        )
    plan["equations"] = normalized_equations
    plan["plots"] = normalized_plots
    return plan


def execute_dds_plan(
    value: Any, *, expected_display: str | None = None, timeout: float = 180
) -> dict[str, Any]:
    plan = validate_dds_plan(value)
    actual_display = os.environ.get("DISPLAY")
    if expected_display and actual_display != expected_display:
        raise RuntimeError(
            f"Configured DISPLAY mismatch: expected {expected_display}, got {actual_display}"
        )
    workspace = Path(str(plan["workspace"])).expanduser().resolve()
    dataset = Path(str(plan["dataset"])).expanduser().resolve()
    output = Path(str(plan["output_file"])).expanduser().resolve()
    if not workspace.is_dir():
        raise FileNotFoundError(f"workspace does not exist: {workspace}")
    if not dataset.is_file():
        raise FileNotFoundError(f"dataset does not exist: {dataset}")
    if output.suffix.casefold() != ".dds" or output.parent != workspace:
        raise ValueError("output_file must be a .dds file directly inside workspace")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite DDS output: {output}")
    instance = select_instance(plan.get("instance"))
    if not instance.python_executable:
        raise RuntimeError(f"ADS Python was not discovered for {instance.product_version}")
    plan_path = workspace / f".{output.name}.dds-{uuid.uuid4().hex}.json"
    try:
        plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        worker = files("ads_agent_bridge").joinpath("dds_report_worker.py")
        completed = subprocess.run(
            [instance.python_executable, str(worker), "--plan", str(plan_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_environment(instance.install_root),
            cwd=str(workspace),
            check=False,
        )
        record = _result(completed.stdout or "")
        if completed.returncode or not record or not record.get("ok"):
            detail = (record or {}).get("error") or (completed.stderr or "")[-1000:]
            raise RuntimeError(f"ADS DDS report creation failed: {detail}")
        return {
            "status": "passed",
            "operation_id": plan["operation_id"],
            "dds_created": True,
            "output_file": str(output),
            "readback": record["readback"],
            "artifacts": {"dds": str(output), "dataset": str(dataset)},
        }
    finally:
        plan_path.unlink(missing_ok=True)
