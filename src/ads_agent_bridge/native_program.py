"""Governed official ADS Python execution inside an owned workspace transaction."""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from importlib.resources import files
from pathlib import Path
from typing import Any

from eda_bridge_runtime import validate_native_program
from eda_bridge_runtime.admission import assert_admission
from eda_bridge_runtime.errors import ExecutionError, error_facts
from eda_bridge_runtime.process_execution import run_owned_process
from eda_bridge_runtime.promotion import promote_paths
from eda_bridge_runtime.retention import retain_stage

from .config import select_instance
from .design_plan import _environment, _result, workspace_fingerprint

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
    plan = validate_native_program(value)
    if plan["mode"] != "background":
        raise ExecutionError(
            "runtime_unsupported",
            "Use a captured ADS context for live programs; ADS has no offline backend",
        )
    if plan["program"]["language"] != "python":
        raise ValueError("ADS native program currently requires official Python")
    scope = plan["scope"]
    if scope["resource_kind"] != "ads-workspace" or len(scope["read_paths"]) != 1:
        raise ValueError("ADS native program requires one ads-workspace read path")
    selectors = scope["selectors"]
    unknown = sorted(set(selectors) - {"instance", "version", "profile"})
    if unknown:
        raise ValueError("ADS native program selectors are unsupported: " + ", ".join(unknown))
    profile = str(selectors.get("profile") or "")
    if profile not in _RUNTIMES or plan["runtime"] != _RUNTIMES[profile]:
        raise ValueError("ADS native program runtime and profile do not match")
    if not selectors.get("version"):
        raise ValueError("ADS native program requires an exact version selector")
    expected_writes = 0 if plan["effect"] == "observe" else 1 + bool(scope["artifacts"])
    if len(scope["write_paths"]) != expected_writes:
        raise ValueError("ADS native program write scope does not match effect and artifacts")
    source = str(Path(scope["read_paths"][0]).expanduser().resolve())
    if plan["effect"] == "mutate" and source not in plan["transaction"]["source_fingerprints"]:
        raise ValueError("ADS staged mutation requires the workspace fingerprint")
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
    admission: dict,
) -> dict[str, Any]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("ADS native program exceeded its total timeout")
    invocation_path.write_text(
        json.dumps(
            {
                "program": program,
                "entrypoint": entrypoint,
                "context": context,
                "max_output_bytes": max_output_bytes,
                "admission": admission,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    worker = files("ads_agent_bridge").joinpath("native_program_worker.py")
    environment = _environment(instance.install_root)
    environment["PYTHONPATH"] = (
        str(Path(str(files("eda_bridge_runtime"))).parent)
        + os.pathsep
        + environment.get("PYTHONPATH", "")
    )
    completed = run_owned_process(
        [
            instance.python_executable,
            str(worker),
            "--invocation",
            str(invocation_path),
        ],
        timeout=remaining,
        env=environment,
        cwd=str(invocation_path.parent),
        max_output_bytes=max_output_bytes + 1048576,
        log_path=str(invocation_path.with_suffix(".log")),
    )
    record = _result(completed.stdout or "")
    if completed.returncode or not record or not record.get("ok"):
        detail = (record or {}).get("error") or (completed.stderr or "")[-1000:]
        raise ExecutionError(
            (record or {}).get("code", "execution_uncertain" if not record else "execution_failed"),
            f"ADS native program failed: {detail}",
            phase=(record or {}).get("phase", "execution"),
            uncertain=not record or bool(record.get("execution_uncertain")),
            evidence={
                **(record or {}).get("evidence", {}),
                "invocation": str(invocation_path),
            },
        )
    result = record.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("ADS governed native program returned no structured result")
    return result


def execute_native_program(
    value: Any,
    *,
    redact_paths: bool = True,
    expected_source_fingerprint: str | None = None,
    admission: dict | None = None,
) -> dict[str, Any]:
    native_started = time.monotonic()
    plan = _validate_ads_plan(value)
    assert_admission(admission or {})
    scope = plan["scope"]
    selectors = scope["selectors"]
    source = Path(scope["read_paths"][0]).expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError("ADS native program source workspace does not exist")
    effect = plan["effect"]
    output = Path(scope["write_paths"][0]).expanduser().resolve() if effect == "mutate" else None
    if output is not None and (output == source or output.parent != source.parent):
        raise ValueError("ADS native program output must be a distinct sibling workspace")
    final_artifacts = (
        Path(scope["write_paths"][1]).expanduser().resolve() if scope["artifacts"] else None
    )
    for target in (output, final_artifacts):
        if target is not None and target.exists():
            raise FileExistsError("ADS native program refuses to overwrite output or artifacts")

    instance = select_instance(selectors.get("instance"))
    if not instance.python_executable:
        raise RuntimeError("ADS Python was not discovered for the selected instance")
    selected_version = str(instance.product_version or instance.year)
    if str(selectors["version"]).strip() not in _instance_version_selectors(instance):
        raise ValueError("ADS native program version selector does not match the installation")

    source_before = workspace_fingerprint(source)
    if expected_source_fingerprint and expected_source_fingerprint != source_before:
        raise ValueError("ADS native program continuation content state does not match")
    expected = plan["transaction"]["source_fingerprints"].get(str(source))
    if expected and expected != source_before:
        raise ValueError("ADS native program source fingerprint does not match")
    parent = output.parent if output is not None else source.parent
    stage_root = parent / f".ads-native-stage-{uuid.uuid4().hex}"
    staged_workspace = stage_root / (output.name if output is not None else source.name)
    staged_artifacts = stage_root / "artifacts"
    invocation = stage_root / "invocation.json"
    deadline = time.monotonic() + plan["limits"]["timeout_seconds"]
    succeeded = False
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
            "mode": "background",
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
            admission=admission,
        )
        program_ms = round((time.monotonic() - program_started) * 1000, 3)
        if workspace_fingerprint(source) != source_before:
            raise RuntimeError("ADS native program changed the source workspace")
        if effect == "observe":
            succeeded = True
            return {
                "status": "passed",
                "program_id": plan["program_id"],
                "effect": effect,
                "runtime": plan["runtime"],
                "mode": "background",
                "execution": "completed",
                "validation": "not_requested",
                "source_preserved": True,
                "source_fingerprint": source_before,
                "program_result": program_result,
                "fresh_process": True,
                "timing": {
                    "staging_ms": staging_ms,
                    "program_ms": program_ms,
                    "native_total_ms": round((time.monotonic() - native_started) * 1000, 3),
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
            admission=admission,
        )
        validation_ms = round((time.monotonic() - validation_started) * 1000, 3)
        if validation_result.get("status") != "passed":
            raise ExecutionError(
                "validation_failed",
                "ADS fresh-process validation did not pass",
                phase="validation",
                evidence={
                    "program_result": program_result,
                    "validation": validation_result,
                },
            )
        for relative in plan["validation"]["required_artifacts"]:
            if not (staged_artifacts / relative).is_file():
                raise RuntimeError(f"ADS native program required artifact is missing: {relative}")
        promotion_started = time.monotonic()
        assert_admission(admission)
        if workspace_fingerprint(source) != source_before:
            raise ExecutionError("target_changed", "Source changed before promotion")
        output_fingerprint = workspace_fingerprint(staged_workspace)
        promote_paths(
            [(staged_workspace, output)]
            + ([(staged_artifacts, final_artifacts)] if final_artifacts is not None else [])
        )
        promotion_ms = round((time.monotonic() - promotion_started) * 1000, 3)
        succeeded = True
        return {
            "status": "passed",
            "program_id": plan["program_id"],
            "effect": effect,
            "runtime": plan["runtime"],
            "mode": "background",
            "execution": "completed",
            "validation": "passed",
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
                "native_total_ms": round((time.monotonic() - native_started) * 1000, 3),
            },
        }
    except Exception as exc:
        retain_stage(stage_root, uncertain=bool(error_facts(exc).get("execution_uncertain")))
        if isinstance(exc, ExecutionError):
            exc.evidence["retained_stage"] = str(stage_root)
            raise
        facts = error_facts(exc)
        raise ExecutionError(
            facts["code"],
            facts["message"],
            phase=facts.get("phase", "execution"),
            uncertain=bool(facts.get("execution_uncertain")),
            evidence={"retained_stage": str(stage_root)},
        ) from exc
    finally:
        if succeeded and stage_root.exists():
            shutil.rmtree(stage_root, ignore_errors=True)
