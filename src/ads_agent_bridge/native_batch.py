"""Governed official ADS Python execution inside an owned workspace transaction."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from importlib.resources import files
from pathlib import Path
from typing import Any

from eda_bridge_runtime import validate_native_batch, validate_python_program_policy

from .config import select_instance
from .design_plan import _environment, _result, workspace_fingerprint

_ALLOWED_IMPORTS = (
    "keysight.ads.dataset",
    "keysight.ads.de",
    "keysight.ads.dds",
    "keysight.edatoolbox",
    "json",
    "math",
)
_RUNTIMES = {"de": "ads.python.de", "dds": "ads.python.dds"}


def _instance_version_selectors(instance: Any) -> set[str]:
    """Return stable version spellings that identify one selected installation."""
    values = {str(instance.year)} if instance.year else set()
    product_version = str(instance.product_version or "").strip()
    if product_version:
        values.add(product_version)
        if product_version.lower().startswith("ads "):
            values.add(product_version[4:].strip())
    return values


def _validate_ads_plan(value: Any) -> dict[str, Any]:
    plan = validate_native_batch(value)
    if plan["program"]["language"] != "python":
        raise ValueError("ADS native batch currently requires official Python")
    scope = plan["scope"]
    if scope["resource_kind"] != "ads-workspace" or len(scope["read_paths"]) != 1:
        raise ValueError("ADS native batch requires one ads-workspace read path")
    selectors = scope["selectors"]
    unknown = sorted(set(selectors) - {"instance", "version", "profile"})
    if unknown:
        raise ValueError(
            "ADS native batch selectors are unsupported: " + ", ".join(unknown)
        )
    profile = str(selectors.get("profile") or "")
    if profile not in _RUNTIMES or plan["runtime"] != _RUNTIMES[profile]:
        raise ValueError("ADS native batch runtime and profile do not match")
    if not selectors.get("version"):
        raise ValueError("ADS native batch requires an exact version selector")
    expected_writes = 0 if plan["effect"] == "observe" else 1 + bool(scope["artifacts"])
    if len(scope["write_paths"]) != expected_writes:
        raise ValueError(
            "ADS native batch write scope does not match effect and artifacts"
        )
    source = str(Path(scope["read_paths"][0]).expanduser().resolve())
    if (
        plan["effect"] == "staged_mutation"
        and source not in plan["transaction"]["source_fingerprints"]
    ):
        raise ValueError("ADS staged mutation requires the workspace fingerprint")
    validate_python_program_policy(
        plan["program"]["source"], allowed_import_prefixes=_ALLOWED_IMPORTS
    )
    if plan["validation"]["program"]:
        validate_python_program_policy(
            plan["validation"]["program"]["source"],
            allowed_import_prefixes=_ALLOWED_IMPORTS,
        )
    return plan


def _run_program(
    *,
    instance,
    program: dict[str, str],
    entrypoint: str,
    context: dict[str, Any],
    invocation_path: Path,
    deadline: float,
    max_output_bytes: int,
) -> dict[str, Any]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("ADS native batch exceeded its total timeout")
    invocation_path.write_text(
        json.dumps(
            {
                "program": program,
                "entrypoint": entrypoint,
                "context": context,
                "max_output_bytes": max_output_bytes,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    worker = files("ads_agent_bridge").joinpath("native_batch_worker.py")
    completed = subprocess.run(
        [
            instance.python_executable,
            str(worker),
            "--invocation",
            str(invocation_path),
        ],
        capture_output=True,
        text=True,
        timeout=remaining,
        env=_environment(instance.install_root),
        cwd=str(invocation_path.parent),
        check=False,
    )
    record = _result(completed.stdout or "")
    if completed.returncode or not record or not record.get("ok"):
        detail = (record or {}).get("error") or (completed.stderr or "")[-1000:]
        raise RuntimeError(f"ADS governed native batch failed: {detail}")
    result = record.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("ADS governed native batch returned no structured result")
    return result


def execute_native_batch(
    value: Any,
    *,
    redact_paths: bool = True,
    expected_source_fingerprint: str | None = None,
) -> dict[str, Any]:
    native_started = time.monotonic()
    plan = _validate_ads_plan(value)
    scope = plan["scope"]
    selectors = scope["selectors"]
    source = Path(scope["read_paths"][0]).expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError("ADS native batch source workspace does not exist")
    effect = plan["effect"]
    output = (
        Path(scope["write_paths"][0]).expanduser().resolve()
        if effect == "staged_mutation"
        else None
    )
    if output is not None and (output == source or output.parent != source.parent):
        raise ValueError("ADS native batch output must be a distinct sibling workspace")
    final_artifacts = (
        Path(scope["write_paths"][1]).expanduser().resolve()
        if scope["artifacts"]
        else None
    )
    for target in (output, final_artifacts):
        if target is not None and target.exists():
            raise FileExistsError(
                "ADS native batch refuses to overwrite output or artifacts"
            )

    instance = select_instance(selectors.get("instance"))
    if not instance.python_executable:
        raise RuntimeError("ADS Python was not discovered for the selected instance")
    selected_version = str(instance.product_version or instance.year)
    if str(selectors["version"]).strip() not in _instance_version_selectors(instance):
        raise ValueError(
            "ADS native batch version selector does not match the installation"
        )

    source_before = workspace_fingerprint(source)
    if expected_source_fingerprint and expected_source_fingerprint != source_before:
        raise ValueError("ADS native batch continuation content state does not match")
    expected = plan["transaction"]["source_fingerprints"].get(str(source))
    if expected and expected != source_before:
        raise ValueError("ADS native batch source fingerprint does not match")
    parent = output.parent if output is not None else source.parent
    stage_root = parent / f".ads-native-stage-{uuid.uuid4().hex}"
    staged_workspace = stage_root / (output.name if output is not None else source.name)
    staged_artifacts = stage_root / "artifacts"
    invocation = stage_root / "invocation.json"
    deadline = time.monotonic() + plan["limits"]["timeout_seconds"]
    try:
        staging_started = time.monotonic()
        shutil.copytree(source, staged_workspace)
        if scope["artifacts"]:
            staged_artifacts.mkdir()
        staging_ms = round((time.monotonic() - staging_started) * 1000, 3)
        context = {
            "workspace": str(staged_workspace),
            "profile": str(selectors["profile"]),
            "version": selected_version,
            "artifact_root": str(staged_artifacts),
            "effect": effect,
        }
        program_started = time.monotonic()
        program_result = _run_program(
            instance=instance,
            program=plan["program"],
            entrypoint="run",
            context=context,
            invocation_path=invocation,
            deadline=deadline,
            max_output_bytes=plan["limits"]["max_output_bytes"],
        )
        program_ms = round((time.monotonic() - program_started) * 1000, 3)
        if workspace_fingerprint(source) != source_before:
            raise RuntimeError("ADS native batch changed the source workspace")
        if effect == "observe":
            return {
                "status": "passed",
                "batch_id": plan["batch_id"],
                "effect": effect,
                "runtime": plan["runtime"],
                "source_preserved": True,
                "source_fingerprint": source_before,
                "program_result": program_result,
                "fresh_process": True,
                "timing": {
                    "staging_ms": staging_ms,
                    "program_ms": program_ms,
                    "native_total_ms": round(
                        (time.monotonic() - native_started) * 1000, 3
                    ),
                },
            }

        validation_started = time.monotonic()
        validation_result = _run_program(
            instance=instance,
            program=plan["validation"]["program"],
            entrypoint="validate",
            context=context,
            invocation_path=invocation,
            deadline=deadline,
            max_output_bytes=plan["limits"]["max_output_bytes"],
        )
        validation_ms = round((time.monotonic() - validation_started) * 1000, 3)
        if validation_result.get("status") != "passed":
            raise RuntimeError("ADS native batch fresh-process validation did not pass")
        for relative in plan["validation"]["required_artifacts"]:
            if not (staged_artifacts / relative).is_file():
                raise RuntimeError(
                    f"ADS native batch required artifact is missing: {relative}"
                )
        promotion_started = time.monotonic()
        output_fingerprint = workspace_fingerprint(staged_workspace)
        os.replace(staged_workspace, output)
        if final_artifacts is not None:
            os.replace(staged_artifacts, final_artifacts)
        promotion_ms = round((time.monotonic() - promotion_started) * 1000, 3)
        return {
            "status": "passed",
            "batch_id": plan["batch_id"],
            "effect": effect,
            "runtime": plan["runtime"],
            "source_preserved": True,
            "source_fingerprint": source_before,
            "output_fingerprint": output_fingerprint,
            "output_workspace": output.name if redact_paths else str(output),
            "program_result": program_result,
            "validation_result": validation_result,
            "fresh_process": True,
            "artifacts": scope["artifacts"],
            "timing": {
                "staging_ms": staging_ms,
                "program_ms": program_ms,
                "validation_ms": validation_ms,
                "promotion_ms": promotion_ms,
                "native_total_ms": round(
                    (time.monotonic() - native_started) * 1000, 3
                ),
            },
        }
    finally:
        if stage_root.exists():
            shutil.rmtree(stage_root, ignore_errors=True)
