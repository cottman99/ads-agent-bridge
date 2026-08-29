"""Transactional execution and bounded validation of generated Momentum inputs."""

from __future__ import annotations

import hashlib
import math
import os
import re
import signal
import shutil
import subprocess
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

from .config import select_instance
from .design_plan import workspace_fingerprint
from .runtime_environment import ads_runtime_environment

_PROJECT = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_PORTS = re.compile(r"^CONSTANT\s+NBR_OF_PORTS\s+(\d+)\s*$")
_FREQUENCIES = re.compile(r"^VAR\s+freq\s+MAG\s+(\d+)\s*$", re.IGNORECASE)
_DATA = re.compile(r"^DATA\s+(\S+)\s+RI\s*$", re.IGNORECASE)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wrapper(install_root: str) -> list[str]:
    binary_root = Path(install_root) / "bin"
    candidates = [
        binary_root / "adsMomWrapper",
        binary_root / "adsMomWrapper.exe",
        binary_root / "adsMomWrapper.bat",
        binary_root / "adsMomWrapper.cmd",
    ]
    selected = next(
        (candidate for candidate in candidates if candidate.is_file()), None
    )
    if selected is None:
        raise FileNotFoundError(
            "ADS Momentum wrapper was not found in the selected installation"
        )
    if selected.suffix.casefold() in {".bat", ".cmd"}:
        command_processor = os.environ.get("COMSPEC") or shutil.which("cmd.exe")
        if not command_processor:
            raise RuntimeError(
                "Windows command processor was not found for ADS Momentum"
            )
        return [command_processor, "/d", "/s", "/c", str(selected)]
    return [str(selected)]


def _float_pair(value: str) -> complex:
    parts = [item.strip() for item in value.split(",")]
    if len(parts) != 2:
        raise ValueError("Momentum CITI RI data must contain exactly two values")
    real, imaginary = (float(item) for item in parts)
    if not math.isfinite(real) or not math.isfinite(imaginary):
        raise ValueError("Momentum CITI contains a non-finite S-parameter value")
    return complex(real, imaginary)


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Stop the wrapper and every solver process it started."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
        return
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def _run_momentum_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    popen_options: dict[str, Any] = {}
    if os.name == "nt":
        popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_options["start_new_session"] = True
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **popen_options,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()
        raise RuntimeError(
            f"ADS Momentum timed out after {timeout:g} seconds; solver process tree stopped"
        ) from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def inspect_citi(path: str | Path) -> dict[str, Any]:
    """Return finite two-port-or-greater facts without depending on parser version quirks."""
    source = Path(path)
    lines = [line.strip() for line in source.read_text(encoding="utf-8").splitlines()]
    if not lines or not lines[0].startswith("CITIFILE"):
        raise ValueError("Momentum result is not a CITI file")
    port_match = next(
        (_PORTS.match(line) for line in lines if _PORTS.match(line)), None
    )
    frequency_match = next(
        (_FREQUENCIES.match(line) for line in lines if _FREQUENCIES.match(line)), None
    )
    if port_match is None or frequency_match is None:
        raise ValueError("Momentum CITI is missing port or frequency metadata")
    port_count = int(port_match.group(1))
    frequency_count = int(frequency_match.group(1))
    if port_count < 1 or frequency_count < 1:
        raise ValueError("Momentum CITI declares an empty result")

    data_names = [match.group(1) for line in lines if (match := _DATA.match(line))]
    try:
        list_start = lines.index("VAR_LIST_BEGIN") + 1
        list_end = lines.index("VAR_LIST_END", list_start)
    except ValueError as exc:
        raise ValueError("Momentum CITI is missing its frequency list") from exc
    frequencies = [float(value) for value in lines[list_start:list_end] if value]
    if len(frequencies) != frequency_count or not all(
        math.isfinite(value) for value in frequencies
    ):
        raise ValueError("Momentum CITI frequency list does not match its declaration")

    blocks: list[list[complex]] = []
    cursor = list_end + 1
    while cursor < len(lines):
        if lines[cursor] != "BEGIN":
            cursor += 1
            continue
        cursor += 1
        values: list[complex] = []
        while cursor < len(lines) and lines[cursor] != "END":
            if lines[cursor]:
                values.append(_float_pair(lines[cursor]))
            cursor += 1
        if cursor >= len(lines):
            raise ValueError("Momentum CITI contains an unterminated data block")
        blocks.append(values)
        cursor += 1
    if len(blocks) < len(data_names):
        raise ValueError("Momentum CITI has fewer data blocks than declarations")
    data = dict(zip(data_names, blocks, strict=False))
    required = [
        f"S[{row},{column}]"
        for row in range(1, port_count + 1)
        for column in range(1, port_count + 1)
    ]
    missing = [name for name in required if name not in data]
    if missing:
        raise ValueError("Momentum CITI is missing S-parameters: " + ", ".join(missing))
    if any(len(data[name]) != frequency_count for name in required):
        raise ValueError(
            "Momentum CITI S-parameter length does not match its frequency list"
        )

    indices = sorted({0, frequency_count // 2, frequency_count - 1})
    samples = {}
    for name in required:
        samples[name] = [
            {
                "frequency_hz": frequencies[index],
                "real": data[name][index].real,
                "imag": data[name][index].imag,
                "magnitude": abs(data[name][index]),
            }
            for index in indices
        ]
    return {
        "port_count": port_count,
        "frequency_count": frequency_count,
        "frequency_hz": {"start": min(frequencies), "stop": max(frequencies)},
        "s_parameters": samples,
    }


def run_generated_momentum(
    *,
    source_directory: str | Path,
    output_directory: str | Path,
    project: str,
    instance_id: str | None = None,
    expected_display: str | None = None,
    source_fingerprint: str | None = None,
    timeout: float = 600,
) -> dict[str, Any]:
    """Run one generated Momentum bundle on a non-overwriting transactional copy."""
    if not _PROJECT.fullmatch(project):
        raise ValueError("Momentum project basename must be a simple identifier")
    if not 1 <= timeout <= 3600:
        raise ValueError("Momentum timeout must be between 1 and 3600 seconds")
    actual_display = os.environ.get("DISPLAY")
    if expected_display and actual_display != expected_display:
        raise RuntimeError(
            f"Configured DISPLAY mismatch: expected {expected_display}, got {actual_display}"
        )
    source = Path(source_directory).expanduser().resolve()
    output = Path(output_directory).expanduser().resolve()
    if not source.is_dir() or not (source / project).is_file():
        raise FileNotFoundError(
            "Momentum source directory is missing its generated project input"
        )
    if output.exists():
        raise FileExistsError(f"refusing to overwrite Momentum output: {output}")
    if source == output or source.parent != output.parent:
        raise ValueError(
            "Momentum source and output directories must be distinct siblings"
        )
    source_before = workspace_fingerprint(source)
    if source_fingerprint and source_fingerprint != source_before:
        raise ValueError("Momentum source fingerprint does not match the request")

    instance = select_instance(instance_id)
    staging = output.parent / f".{output.name}.staging-{uuid.uuid4().hex}"
    try:
        shutil.copytree(source, staging)
        for suffix in ("cti", "afs", "sta"):
            (staging / f"{project}.{suffix}").unlink(missing_ok=True)
        completed = _run_momentum_command(
            [*_wrapper(instance.install_root), "-O", "-3D", project, project],
            cwd=staging,
            env=ads_runtime_environment(instance.install_root),
            timeout=timeout,
        )
        log = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        (staging / "momentum-runtime.log").write_text(log, encoding="utf-8")
        if completed.returncode != 0 or "S-parameter simulation finished" not in log:
            raise RuntimeError(
                "ADS Momentum did not complete S-parameter generation: " + log[-1000:]
            )
        artifacts = {}
        for suffix in ("cti", "afs", "sta"):
            artifact = staging / f"{project}.{suffix}"
            if not artifact.is_file() or artifact.stat().st_size == 0:
                raise RuntimeError(f"ADS Momentum did not create {artifact.name}")
            artifacts[artifact.name] = {
                "bytes": artifact.stat().st_size,
                "sha256": _file_sha256(artifact),
            }
        citi = inspect_citi(staging / f"{project}.cti")
        source_after = workspace_fingerprint(source)
        if source_after != source_before:
            raise RuntimeError("Momentum source directory changed during execution")
        os.replace(staging, output)
        return {
            "status": "passed",
            "source_preserved": True,
            "source_fingerprint": source_before,
            "output_fingerprint": workspace_fingerprint(output),
            "project": project,
            "artifacts": artifacts,
            "result": citi,
            "warnings": {
                "log_error_markers": log.count("--- ERROR"),
                "dataset_export_failed": "Could not create dataset" in log,
            },
        }
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
