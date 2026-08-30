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

_SCHEMA_V1 = "ads.dds-report/v1"
_SCHEMA_V2 = "ads.dds-report/v2"
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")


def _validate_equations(value: Any, path: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 64:
        raise ValueError(f"{path} must be a list with at most 64 entries")
    normalized = []
    for index, item in enumerate(value):
        if (
            not isinstance(item, dict)
            or set(item) != {"name", "expression"}
            or not _IDENTIFIER.fullmatch(str(item.get("name") or ""))
            or not isinstance(item.get("expression"), str)
            or not item["expression"]
            or len(item["expression"]) > 512
        ):
            raise ValueError(f"{path}[{index}] is invalid")
        normalized.append(dict(item))
    return normalized


def _validate_plots(value: Any, path: str, *, typed: bool) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > 32:
        raise ValueError(f"{path} must contain between 1 and 32 entries")
    normalized = []
    expected = (
        {"kind", "name", "traces", "rect"} if typed else {"name", "traces", "rect"}
    )
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != expected:
            raise ValueError(f"{path}[{index}] is invalid")
        rect = item["rect"]
        traces = item["traces"]
        kind = item.get("kind", "rectangular")
        if (
            kind not in {"rectangular", "polar"}
            or not isinstance(item["name"], str)
            or not item["name"]
            or len(item["name"]) > 128
            or not isinstance(traces, list)
            or not traces
            or len(traces) > 32
            or any(
                not isinstance(trace, str) or not trace or len(trace) > 512
                for trace in traces
            )
            or not isinstance(rect, list)
            or len(rect) != 4
            or any(
                not isinstance(number, int) or isinstance(number, bool)
                for number in rect
            )
            or rect[2] <= 0
            or rect[3] <= 0
        ):
            raise ValueError(f"{path}[{index}] is invalid")
        normalized_item = {
            "name": item["name"],
            "traces": list(traces),
            "rect": list(rect),
        }
        if typed:
            normalized_item["kind"] = kind
        normalized.append(normalized_item)
    return normalized


def validate_dds_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("dds.create requires a structured plan object")
    plan = dict(value)
    schema = plan.get("schema_version")
    common = {
        "schema_version",
        "operation_id",
        "workspace",
        "dataset",
        "output_file",
        "instance",
    }
    legacy = {
        "page",
        "equations",
        "plots",
    }
    allowed = common | (legacy if schema == _SCHEMA_V1 else {"pages"})
    unknown = sorted(set(plan) - allowed)
    if unknown:
        raise ValueError("DDS plan contains unsupported fields: " + ", ".join(unknown))
    required = ("schema_version", "operation_id", "workspace", "dataset", "output_file")
    missing = [name for name in required if not plan.get(name)]
    if missing:
        raise ValueError("DDS plan is missing: " + ", ".join(missing))
    if schema not in {_SCHEMA_V1, _SCHEMA_V2}:
        raise ValueError(f"unsupported DDS plan schema: {plan['schema_version']}")
    if not _IDENTIFIER.fullmatch(str(plan["operation_id"])):
        raise ValueError("operation_id must be a simple identifier")
    if schema == _SCHEMA_V1:
        if (
            not isinstance(plan.get("page"), str)
            or not plan["page"]
            or len(plan["page"]) > 128
        ):
            raise ValueError("page must be a bounded string")
        plan["equations"] = _validate_equations(plan.get("equations", []), "equations")
        plan["plots"] = _validate_plots(plan.get("plots", []), "plots", typed=False)
        return plan

    pages = plan.get("pages")
    if not isinstance(pages, list) or not pages or len(pages) > 16:
        raise ValueError("pages must contain between 1 and 16 entries")
    normalized_pages = []
    names = set()
    for index, page in enumerate(pages):
        if not isinstance(page, dict) or set(page) - {"name", "equations", "plots"}:
            raise ValueError(f"pages[{index}] is invalid")
        name = page.get("name")
        if not isinstance(name, str) or not name or len(name) > 128 or name in names:
            raise ValueError(f"pages[{index}].name is invalid or duplicated")
        names.add(name)
        normalized_pages.append(
            {
                "name": name,
                "equations": _validate_equations(
                    page.get("equations", []), f"pages[{index}].equations"
                ),
                "plots": _validate_plots(
                    page.get("plots", []), f"pages[{index}].plots", typed=True
                ),
            }
        )
    plan["pages"] = normalized_pages
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
        raise RuntimeError(
            f"ADS Python was not discovered for {instance.product_version}"
        )
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
