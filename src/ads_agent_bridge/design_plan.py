"""Transactional execution of structured ADS schematic plans."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import uuid
from importlib.resources import files
from pathlib import Path
from typing import Any

from .config import select_instance
from .runtime_environment import ads_runtime_environment

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
_LCV = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]{0,127}:[A-Za-z_][A-Za-z0-9_]{0,127}:schematic"
)
_SCHEMA = "ads.design-plan/v1"
_MAX_OPERATIONS = 256
_PLAN_FIELDS = {
    "schema_version",
    "operation_id",
    "source_workspace",
    "output_workspace",
    "source_fingerprint",
    "instance",
    "design",
    "expected_before",
    "operations",
    "assertions",
}


def _point(value: Any, field: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{field} must contain exactly two coordinates")
    if any(
        not isinstance(item, (int, float)) or isinstance(item, bool) for item in value
    ):
        raise ValueError(f"{field} coordinates must be numbers")
    point = [float(item) for item in value]
    if not all(math.isfinite(item) for item in point):
        raise ValueError(f"{field} coordinates must be finite")
    return point


def validate_design_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("design.apply requires a structured plan object")
    plan = dict(value)
    unknown = sorted(set(plan) - _PLAN_FIELDS)
    if unknown:
        raise ValueError(
            "design plan contains unsupported fields: " + ", ".join(unknown)
        )
    required = (
        "schema_version",
        "operation_id",
        "source_workspace",
        "output_workspace",
        "design",
        "expected_before",
        "assertions",
    )
    missing = [name for name in required if not plan.get(name)]
    if missing:
        raise ValueError("design plan is missing: " + ", ".join(missing))
    if plan["schema_version"] != _SCHEMA:
        raise ValueError(f"unsupported design plan schema: {plan['schema_version']}")
    if not _IDENTIFIER.fullmatch(str(plan["operation_id"])):
        raise ValueError("operation_id must be a simple identifier")
    if not _LCV.fullmatch(str(plan["design"])):
        raise ValueError("design must be a library:cell:schematic identifier")
    fingerprint = plan.get("source_fingerprint")
    if fingerprint is not None and not re.fullmatch(r"[a-f0-9]{64}", str(fingerprint)):
        raise ValueError("source_fingerprint must be a lowercase SHA-256 digest")
    operations = plan.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError("design plan requires at least one operation")
    if len(operations) > _MAX_OPERATIONS:
        raise ValueError(f"design plan exceeds {_MAX_OPERATIONS} operations")

    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, raw in enumerate(operations):
        if not isinstance(raw, dict):
            raise TypeError(f"operations[{index}] must be an object")
        kind = str(raw.get("op") or "")
        if kind == "add_instance":
            unknown = sorted(
                set(raw) - {"op", "name", "item", "at", "angle", "parameters"}
            )
            if unknown:
                raise ValueError(
                    f"operations[{index}] contains unsupported fields: {', '.join(unknown)}"
                )
            name = str(raw.get("name") or "")
            item = raw.get("item")
            if not _IDENTIFIER.fullmatch(name) or name in names:
                raise ValueError(f"operations[{index}].name must be unique and simple")
            if (
                not isinstance(item, list)
                or len(item) != 3
                or not all(_IDENTIFIER.fullmatch(str(part)) for part in item)
            ):
                raise ValueError(
                    f"operations[{index}].item must contain three identifiers"
                )
            parameters = raw.get("parameters") or {}
            if not isinstance(parameters, dict) or any(
                not _IDENTIFIER.fullmatch(str(key))
                or not isinstance(value, str)
                or len(value) > 256
                for key, value in parameters.items()
            ):
                raise ValueError(f"operations[{index}].parameters is invalid")
            entry = {
                "op": kind,
                "name": name,
                "item": [str(part) for part in item],
                "at": _point(raw.get("at"), f"operations[{index}].at"),
                "parameters": dict(parameters),
            }
            if "angle" in raw:
                if not isinstance(raw["angle"], (int, float)) or isinstance(
                    raw["angle"], bool
                ):
                    raise ValueError(f"operations[{index}].angle must be a number")
                angle = float(raw["angle"])
                if not math.isfinite(angle):
                    raise ValueError(f"operations[{index}].angle must be finite")
                entry["angle"] = angle
            normalized.append(entry)
            names.add(name)
            continue
        if kind == "add_wire":
            unknown = sorted(set(raw) - {"op", "points", "label"})
            if unknown:
                raise ValueError(
                    f"operations[{index}] contains unsupported fields: {', '.join(unknown)}"
                )
            points = raw.get("points")
            if not isinstance(points, list) or len(points) < 2:
                raise ValueError(
                    f"operations[{index}].points requires at least two points"
                )
            entry = {
                "op": kind,
                "points": [
                    _point(point, f"operations[{index}].points[{point_index}]")
                    for point_index, point in enumerate(points)
                ],
            }
            if "label" in raw:
                label = str(raw["label"])
                if not label or len(label) > 128:
                    raise ValueError(f"operations[{index}].label is invalid")
                entry["label"] = label
            normalized.append(entry)
            continue
        raise ValueError(f"unsupported design operation: {kind or '<missing>'}")

    expected = plan["expected_before"]
    assertions = plan["assertions"]
    if not isinstance(expected, dict) or not isinstance(assertions, dict):
        raise TypeError("expected_before and assertions must be objects")
    if set(expected) - {"instance_names"}:
        raise ValueError("expected_before contains unsupported fields")
    if set(assertions) - {"instance_names", "parameters", "netlist_contains"}:
        raise ValueError("assertions contains unsupported fields")
    for field, values in (
        ("expected_before.instance_names", expected.get("instance_names", [])),
        ("assertions.instance_names", assertions.get("instance_names", [])),
        ("assertions.netlist_contains", assertions.get("netlist_contains", [])),
    ):
        if not isinstance(values, list) or not all(
            isinstance(item, str) and 0 < len(item) <= 256 for item in values
        ):
            raise ValueError(f"{field} must be a bounded string list")
    parameters = assertions.get("parameters", [])
    if not isinstance(parameters, list) or any(
        not isinstance(item, dict)
        or set(item) != {"instance", "parameter", "value"}
        or not _IDENTIFIER.fullmatch(str(item["instance"]))
        or not _IDENTIFIER.fullmatch(str(item["parameter"]))
        or not isinstance(item["value"], str)
        or len(item["value"]) > 256
        for item in parameters
    ):
        raise ValueError("assertions.parameters must contain exact parameter triples")
    if not (
        assertions.get("instance_names")
        or parameters
        or assertions.get("netlist_contains")
    ):
        raise ValueError("design plan requires at least one fresh-reopen assertion")
    plan["operations"] = normalized
    plan["expected_before"] = expected
    plan["assertions"] = assertions
    return plan


def workspace_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ValueError(f"workspace bundle contains a symbolic link: {path.name}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _environment(install_root: str) -> dict[str, str]:
    return ads_runtime_environment(install_root)


def _result(stdout: str) -> dict[str, Any] | None:
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "ok" in value:
            return value
    return None


def execute_design_plan(
    value: Any, *, expected_display: str | None = None, timeout: float = 180
) -> dict[str, Any]:
    plan = validate_design_plan(value)
    actual_display = os.environ.get("DISPLAY")
    if expected_display and actual_display != expected_display:
        raise RuntimeError(
            f"Configured DISPLAY mismatch: expected {expected_display}, got {actual_display}"
        )
    source = Path(str(plan["source_workspace"])).expanduser().resolve()
    output = Path(str(plan["output_workspace"])).expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"source workspace does not exist: {source}")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output workspace: {output}")
    if source == output or source.parent != output.parent:
        raise ValueError("source and output workspaces must be distinct siblings")
    source_before = workspace_fingerprint(source)
    expected_fingerprint = plan.get("source_fingerprint")
    if expected_fingerprint and expected_fingerprint != source_before:
        raise ValueError("source workspace fingerprint does not match the plan")

    instance = select_instance(plan.get("instance"))
    if not instance.python_executable:
        raise RuntimeError(
            f"ADS Python was not discovered for {instance.product_version}"
        )
    staging = output.parent / f".{output.name}.staging-{uuid.uuid4().hex}"
    plan_path = output.parent / f".{output.name}.plan-{uuid.uuid4().hex}.json"
    try:
        shutil.copytree(source, staging)
        plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        runner = files("ads_agent_bridge").joinpath("structured_design_apply.py")
        completed = subprocess.run(
            [
                instance.python_executable,
                str(runner),
                "--workspace",
                str(staging),
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
            raise RuntimeError(f"ADS structured design apply failed: {detail}")
        source_after = workspace_fingerprint(source)
        if source_after != source_before:
            raise RuntimeError("source workspace changed during design transaction")
        os.replace(staging, output)
        output_fingerprint = workspace_fingerprint(output)
        return {
            "status": "passed",
            "operation_id": plan["operation_id"],
            "source_preserved": True,
            "source_fingerprint": source_before,
            "output_fingerprint": output_fingerprint,
            "output_workspace": output.name,
            "design": plan["design"],
            "fresh_reopen": True,
            "readback": record.get("readback") or {},
        }
    finally:
        plan_path.unlink(missing_ok=True)
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
