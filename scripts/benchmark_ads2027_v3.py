"""Run the corrected ADS 2027 Runtime-MCP versus official-MCP benchmark.

The old v2 runner intentionally remains frozen as historical evidence.  This
runner removes its central confound: the current product arm is the EDA Runtime
MCP, not an Agent exploring and invoking the ads-agent CLI.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ARMS = ("runtime", "official")
AGENTS = ("codex", "pi")
CASES = ("K1", "K3", "K6", "E3")
RUNTIME_TOOLS = (
    "eda_context_resolve",
    "eda_connections_list",
    "eda_connection_reset",
    "eda_capabilities",
    "eda_read",
    "eda_submit",
    "eda_run_plan",
    "eda_run_get",
    "eda_job_status",
    "eda_job_wait",
    "eda_job_events",
)


@dataclass(frozen=True)
class Paths:
    root: Path
    ads_root: Path
    official_mcp: Path
    auth_source: Path
    pi_bin: Path
    pi_node_bin: Path
    pi_auth_source: Path
    pi_official_extension: Path
    contract: Path

    @property
    def runtime_env(self) -> Path:
        return self.root / "envs" / "runtime"

    @property
    def runtime_python(self) -> Path:
        return self.runtime_env / "bin" / "python"

    @property
    def runtime_cli(self) -> Path:
        return self.runtime_env / "bin" / "eda-runtime"

    @property
    def ads_cli(self) -> Path:
        return self.runtime_env / "bin" / "ads-agent"

    @property
    def product_home(self) -> Path:
        return self.root / "product-home"

    @property
    def runtime_home(self) -> Path:
        return self.root / "runtime-home"

    @property
    def runs(self) -> Path:
        return self.root / "runs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "prepare", "run", "summarize"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--ads-root", type=Path, required=True)
    parser.add_argument("--official-mcp", type=Path, required=True)
    parser.add_argument("--official-sha256")
    parser.add_argument("--auth-source", type=Path, required=True)
    parser.add_argument("--pi-bin", type=Path, required=True)
    parser.add_argument("--pi-node-bin", type=Path, required=True)
    parser.add_argument("--pi-auth-source", type=Path, required=True)
    parser.add_argument("--pi-official-extension", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--runtime-version", default="0.1.0a37")
    parser.add_argument("--bridge-version", default="0.1.0a48")
    parser.add_argument("--model", default="gpt-5.6-terra")
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--display", default=":4")
    parser.add_argument("--phase", choices=("calibration", "formal"), default="calibration")
    parser.add_argument("--campaign", default="current")
    parser.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    parser.add_argument("--agents", nargs="+", choices=AGENTS, default=list(AGENTS))
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    parser.add_argument("--repetitions", type=int, default=1)
    return parser.parse_args()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def run_checked(command: list[str], *, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        command, env=env, check=True, text=True, capture_output=True
    ).stdout.strip()


def product_env(paths: Paths, display: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(paths.product_home),
            "XDG_CONFIG_HOME": str(paths.product_home / ".config"),
            "XDG_CACHE_HOME": str(paths.product_home / ".cache"),
            "XDG_DATA_HOME": str(paths.product_home / ".local" / "share"),
            "EDA_RUNTIME_HOME": str(paths.runtime_home),
            "DISPLAY": display,
            "HPEESOF_DIR": str(paths.ads_root),
            "BASH_ENV": "/dev/null",
        }
    )
    return env


def copy_agent_auth(source: Path, destination: Path, agent: str) -> None:
    """Copy credentials without exposing them; normalize Codex OAuth for Pi."""
    if agent == "codex":
        shutil.copy2(source, destination)
        return
    value = json.loads(source.read_text(encoding="utf-8"))
    if "openai-codex" in value:
        normalized = value
    else:
        tokens = value.get("tokens") or {}
        access = tokens.get("access_token")
        refresh = tokens.get("refresh_token")
        if not access or not refresh:
            raise ValueError("Pi auth source has neither Pi nor Codex OAuth credentials")
        try:
            payload = access.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            expires = int(json.loads(base64.urlsafe_b64decode(payload))["exp"] * 1000)
        except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            expires = 0
        normalized = {
            "openai-codex": {
                "type": "oauth",
                "refresh": refresh,
                "access": access,
                "expires": expires,
                "accountId": tokens.get("account_id"),
            }
        }
    destination.write_text(json.dumps(normalized), encoding="utf-8")
    destination.chmod(0o600)


def package_path(paths: Paths, package: str, relative: str) -> Path:
    code = (
        "from importlib.resources import files; "
        f"print(files({package!r}).joinpath({relative!r}))"
    )
    return Path(run_checked([str(paths.runtime_python), "-c", code]))


def preflight(paths: Paths, expected_official_hash: str | None) -> dict[str, Any]:
    actual_hash = digest(paths.official_mcp) if paths.official_mcp.is_file() else None
    checks = {
        "contract_exists": paths.contract.is_file(),
        "ads_root_exists": paths.ads_root.is_dir(),
        "official_mcp_exists": paths.official_mcp.is_file(),
        "official_mcp_sha256": actual_hash,
        "official_identity_matches": not expected_official_hash
        or actual_hash == expected_official_hash,
        "auth_exists": paths.auth_source.is_file(),
        "pi_auth_exists": paths.pi_auth_source.is_file(),
        "pi_binary_exists": paths.pi_bin.is_file(),
        "pi_node_exists": paths.pi_node_bin.is_file(),
        "pi_official_extension_exists": paths.pi_official_extension.is_file(),
        "ads_license_configured": bool(os.environ.get("ADS_LICENSE_FILE")),
        "codex_version": run_checked(["codex", "--version"]),
        "pi_version": run_checked([str(paths.pi_node_bin), str(paths.pi_bin), "--version"]),
    }
    checks["ready"] = all(
        value
        for key, value in checks.items()
        if key not in {"official_mcp_sha256", "codex_version", "pi_version"}
    )
    return checks


def prepare(paths: Paths, *, runtime_version: str, bridge_version: str, display: str) -> dict[str, Any]:
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.product_home.mkdir(parents=True, exist_ok=True)
    paths.runtime_home.mkdir(parents=True, exist_ok=True)
    if not paths.runtime_python.is_file():
        run_checked(["python3.11", "-m", "venv", str(paths.runtime_env)])
    run_checked(
        [
            str(paths.runtime_python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            f"eda-bridge-runtime=={runtime_version}",
            f"ads-agent-bridge=={bridge_version}",
        ]
    )
    env = product_env(paths, display)
    setup = run_checked(
        [
            str(paths.ads_cli),
            "setup",
            "--ads-root",
            str(paths.ads_root),
            "--non-interactive",
            "--skip-skill",
            "--no-background-docs",
        ],
        env=env,
    )
    instances = json.loads(run_checked([str(paths.ads_cli), "instances", "list"], env=env))
    ads_2027 = next(item for item in instances["instances"] if item["product_version"] == "ADS 2027")
    run_checked([str(paths.ads_cli), "docs", "build", "--ads", ads_2027["instance_id"]], env=env)
    registry = paths.runtime_home / "connections.json"
    if registry.exists():
        registry.unlink()
    run_checked(
        [
            str(paths.runtime_cli),
            "connection",
            "set",
            "--registry",
            str(registry),
            "--eda",
            "keysight-ads",
            "--kind",
            "local",
            "ads-benchmark",
            str(paths.ads_cli),
            "runtime",
            "serve",
        ],
        env=env,
    )
    return {
        "runtime_version": run_checked([str(paths.runtime_cli), "--version"], env=env),
        "bridge_version": run_checked(
            [str(paths.runtime_python), "-c", "import importlib.metadata as m;print(m.version('ads-agent-bridge'))"],
            env=env,
        ),
        "ads_instance": ads_2027["instance_id"],
        "registry": json.loads(registry.read_text(encoding="utf-8")),
        "setup_recorded": bool(setup),
    }


def output_schema(case_id: str) -> dict[str, Any]:
    common = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
    }
    if case_id != "E3":
        return {
            **common,
            "properties": {
                "case_id": {"type": "string", "const": case_id},
                "answer": {"type": "string", "minLength": 1},
                "code": {"type": "string"},
                "sources": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["case_id", "answer", "code", "sources"],
        }
    return {
        **common,
        "properties": {
            "case_id": {"type": "string", "const": "E3"},
            "workspace": {"type": "string", "minLength": 1},
            "dataset": {"type": "string", "minLength": 1},
            "simulation_count": {"type": "integer", "const": 1},
            "simulation_completed": {"type": "boolean"},
            "dataset_read_back": {"type": "boolean"},
            "numeric_sample": {"type": "number"},
            "gui_launched": {"type": "boolean"},
            "evidence": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "case_id", "workspace", "dataset", "simulation_count",
            "simulation_completed", "dataset_read_back", "numeric_sample",
            "gui_launched", "evidence",
        ],
    }


def official_config(paths: Paths, display: str, license_value: str) -> str:
    ads = str(paths.ads_root)
    library_path = ":".join(
        (f"{ads}/tools/python/lib", f"{ads}/lib/linux_x86_64", f"{ads}/lib/linux_x86_64/gccrt15")
    )
    return "\n".join(
        (
            '[mcp_servers."ads"]',
            f"command = {json.dumps(str(paths.official_mcp))}",
            "startup_timeout_sec = 30",
            "tool_timeout_sec = 240",
            '[mcp_servers."ads".env]',
            f"HPEESOF_DIR = {json.dumps(ads)}",
            f"DISPLAY = {json.dumps(display)}",
            f"LD_LIBRARY_PATH = {json.dumps(library_path)}",
            f"ADS_LICENSE_FILE = {json.dumps(license_value)}",
            f"PATH = {json.dumps(ads + '/bin:' + ads + '/tools/python/bin:/usr/local/bin:/usr/bin:/bin')}",
            "",
        )
    )


def install_runtime_codex_profile(paths: Paths, agent_home: Path, env: dict[str, str]) -> list[Path]:
    skills_root = agent_home / "skills"
    runtime_skill = package_path(paths, "eda_bridge_runtime", "pi_eda_runtime/skills/eda-runtime-control")
    bridge_skills = package_path(paths, "ads_agent_bridge", "skill_assets")
    selected = []
    for source, name in (
        (runtime_skill, "eda-runtime-control"),
        (bridge_skills / "ads-agent-bridge", "ads-agent-bridge"),
        (bridge_skills / "ads-kb-docs", "ads-kb-docs"),
    ):
        target = skills_root / name
        shutil.copytree(source, target)
        selected.append(target / "SKILL.md")
    run_checked(
        [
            str(paths.runtime_cli), "agent-profile", "codex", "install",
            "--codex-home", str(agent_home), "--profile-name", "eda-runtime",
            "--approve-mutations", "--keep-name", "eda-runtime-control",
            "--keep-name", "ads-agent-bridge", "--keep-name", "ads-kb-docs",
        ],
        env=env,
    )
    profile = agent_home / "eda-runtime.config.toml"
    inherited = {
        key: env[key]
        for key in (
            "EDA_RUNTIME_HOME",
            "HOME",
            "XDG_CONFIG_HOME",
            "XDG_CACHE_HOME",
            "XDG_DATA_HOME",
            "DISPLAY",
            "HPEESOF_DIR",
            "ADS_LICENSE_FILE",
        )
        if env.get(key)
    }
    with profile.open("a", encoding="utf-8") as handle:
        handle.write('[mcp_servers."eda-bridge-runtime".env]\n')
        for key, value in inherited.items():
            handle.write(f"{key} = {json.dumps(value)}\n")
        handle.write("\n")
    return selected


def runtime_pi_assets(paths: Paths) -> tuple[Path, list[Path]]:
    extension = package_path(paths, "eda_bridge_runtime", "pi_eda_runtime")
    bridge_skills = package_path(paths, "ads_agent_bridge", "skill_assets")
    return extension, [
        extension / "skills" / "eda-runtime-control" / "SKILL.md",
        bridge_skills / "ads-agent-bridge" / "SKILL.md",
        bridge_skills / "ads-kb-docs" / "SKILL.md",
    ]


def prompt_for(contract: dict[str, Any], arm: str, case_id: str, work: Path) -> str:
    surface = (
        "Your only product surface is the configured EDA Runtime MCP and the current Runtime/ADS Skills. "
        "Use Runtime MCP tools directly. Do not invoke or discuss ads-agent CLI or the official ADS MCP."
        if arm == "runtime"
        else "Your only product surface is the configured official ADS MCP. Select exact tool names from the tools actually exposed to you; it includes documentation/search and session/Python execution capabilities. Do not invoke or discuss EDA Runtime, ads-agent, or ADS Agent Bridge."
    )
    return "\n\n".join(
        (
            "You are taking part in a controlled ADS 2027 comparison. Solve the engineering request through the assigned current product surface, not through a memorized benchmark recipe.",
            surface,
            "Shell, browser, web, external repositories, prior outputs, and direct process execution are unavailable. Do not perform duplicate work. Calibration and formal runs use fresh directories.",
            "For a knowledge case, call the assigned MCP documentation/search surface and ground the answer in its returned evidence instead of answering from memory. For an execution case, use only the assigned MCP execution surface.",
            "If the assigned execution surface requires an idempotency key, derive a unique key from this RUN_DIRECTORY; never reuse a key from another run.",
            f"RUN_DIRECTORY={work}",
            contract["cases"][case_id]["prompt"].replace("RUN_DIRECTORY", str(work)),
        )
    )


def load_events(path: Path) -> list[dict[str, Any]]:
    events = []
    with path.open(encoding="utf-8-sig", errors="replace") as handle:
        for line in handle:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                events.append(value)
    return events


def parse_answer(text: str) -> dict[str, Any]:
    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", candidate, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1)
    else:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start : end + 1]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def event_facts(events: list[dict[str, Any]], agent: str) -> dict[str, Any]:
    usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    tool_names: list[str] = []
    final_text = ""
    timing_ms: dict[str, list[float]] = {}
    tool_started: dict[str, tuple[float, str]] = {}

    def tool_label(name: str, arguments: Any) -> str:
        operation = arguments.get("operation") if isinstance(arguments, dict) else None
        selected = str(operation or name or "tool").lower()
        return re.sub(r"[^a-z0-9]+", "_", selected).strip("_")[:80] or "tool"

    def record_tool_elapsed(call_id: str, finished_ms: Any) -> None:
        if call_id not in tool_started or not isinstance(finished_ms, (int, float)):
            return
        started_ms, label = tool_started.pop(call_id)
        elapsed = max(0.0, float(finished_ms) - started_ms)
        timing_ms.setdefault(f"tool_{label}_ms", []).append(round(elapsed, 3))

    def collect_timing_object(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if (key.endswith("_ms") or key.endswith("_seconds")) and isinstance(
                    child, (int, float)
                ):
                    timing_ms.setdefault(key, []).append(float(child))
                elif isinstance(child, (dict, list)):
                    collect_timing_object(child)
        elif isinstance(value, list):
            for child in value:
                collect_timing_object(child)

    def collect_runtime_result(value: Any) -> None:
        if not isinstance(value, dict):
            return
        transport = value.get("client_transport_ms")
        if isinstance(transport, (int, float)):
            timing_ms.setdefault("client_transport_ms", []).append(float(transport))
        response = value.get("response")
        if not isinstance(response, dict):
            return

        def find_timing(node: Any) -> None:
            if not isinstance(node, dict):
                return
            if isinstance(node.get("timing"), dict):
                collect_timing_object(node["timing"])
            for key in ("result", "data", "bridge"):
                find_timing(node.get(key))

        find_timing(response)

    for event in events:
        if agent == "codex":
            item = event.get("item") or {}
            call_id = str(item.get("id") or "")
            received_ms = event.get("_benchmark_received_ms")
            if (
                event.get("type") == "item.started"
                and item.get("type") == "mcp_tool_call"
                and isinstance(received_ms, (int, float))
            ):
                tool_started[call_id] = (
                    float(received_ms),
                    tool_label(str(item.get("tool") or item.get("name") or "mcp"), item.get("arguments")),
                )
            if event.get("type") == "item.completed" and item.get("type") == "mcp_tool_call":
                result = item.get("result") or {}
                collect_runtime_result(result.get("structured_content"))
                record_tool_elapsed(call_id, received_ms)
                tool_names.append(str(item.get("name") or item.get("tool") or item.get("server") or "mcp"))
            candidate = event.get("usage")
            if isinstance(candidate, dict):
                for key in usage:
                    if isinstance(candidate.get(key), int):
                        usage[key] = max(usage[key], candidate[key])
        else:
            if event.get("type") == "tool_execution_end":
                result = event.get("result") or {}
                collect_runtime_result((result.get("details") or {}).get("runtime"))
                record_tool_elapsed(
                    str(event.get("toolCallId") or ""),
                    event.get("_benchmark_received_ms"),
                )
                tool_names.append(str(event.get("toolName") or "tool"))
            if event.get("type") == "tool_execution_start":
                received_ms = event.get("_benchmark_received_ms")
                if isinstance(received_ms, (int, float)):
                    tool_started[str(event.get("toolCallId") or "")] = (
                        float(received_ms),
                        tool_label(str(event.get("toolName") or "tool"), event.get("args")),
                    )
            if event.get("type") == "message_end" and (event.get("message") or {}).get("role") == "assistant":
                message = event["message"]
                native = message.get("usage") or {}
                usage["input_tokens"] += int(native.get("input", 0)) + int(native.get("cacheRead", 0))
                usage["cached_input_tokens"] += int(native.get("cacheRead", 0))
                usage["output_tokens"] += int(native.get("output", 0))
                texts = [block.get("text", "") for block in message.get("content", []) if block.get("type") == "text"]
                if texts:
                    final_text = "\n".join(texts)
    return {"usage": usage, "tool_names": tool_names, "timing_ms": timing_ms, "final_text": final_text}


def validate(case_id: str, arm: str, work: Path, answer: dict[str, Any], events: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    combined = f"{answer.get('answer', '')}\n{answer.get('code', '')}".lower()
    actual_tools: list[str] = []
    used_shell = False
    for event in events:
        item = event.get("item") or {}
        if item.get("type") == "mcp_tool_call":
            actual_tools.append(
                str(item.get("name") or item.get("tool") or item.get("server") or "").lower()
            )
        if item.get("type") == "command_execution":
            used_shell = True
        if event.get("type") == "tool_execution_start":
            name = str(event.get("toolName") or "").lower()
            actual_tools.append(name)
            if name == "bash":
                used_shell = True
    if arm == "runtime":
        if any(
            name in {"search_docs", "get_docs", "start_local_session", "execute_python"}
            or name.startswith("mcp__ads__")
            for name in actual_tools
        ):
            errors.append("runtime arm crossed into official MCP")
        if used_shell:
            errors.append("runtime arm used CLI or shell")
    else:
        if any(name.startswith("eda_") or "eda_bridge_runtime" in name for name in actual_tools):
            errors.append("official arm crossed into Runtime MCP")
        if used_shell:
            errors.append("official arm used shell")
    if case_id == "K1":
        if not re.search(
            r"headless|no[- ]gui|without.{0,30}gui|automation mode|ui.{0,30}(unavailable|not available)",
            combined,
        ):
            errors.append("K1 missing no-GUI boundary")
        if "dataset" not in combined or not re.search(r"finite|numeric|sample|read", combined):
            errors.append("K1 missing finite dataset readback")
        if arm == "runtime" and not re.search(r"eda\.(read|submit|run_plan)|runtime mcp|native\.batch|workspace\.create", combined):
            errors.append("K1 did not identify the current Runtime MCP route")
        if arm == "runtime" and "ads-agent quickstart" in combined:
            errors.append("K1 prescribed the superseded CLI route")
        if arm == "official" and not ("start_local_session" in combined and "execute_python" in combined):
            errors.append("K1 did not identify the official MCP route")
    elif case_id == "K3":
        for label, pattern in {"rectangle": r"rectangle|db\.rect", "polygon": r"polygon|db\.polygon", "path": r"path|db\.path"}.items():
            if not re.search(pattern, combined):
                errors.append(f"K3 missing {label}")
        if not re.search(r"add_(rectangle|polygon|path)|db\.(rect|polygon|path)", combined):
            errors.append("K3 lacks recognizable geometry calls")
    elif case_id == "K6":
        answer_text = str(answer.get("answer", ""))
        negative = bool(re.search(r"not established|does not establish|no documented", answer_text, re.IGNORECASE))
        documented_flow = (
            "create_drc_job" in combined and "run_drc_job" in combined
        ) or (
            "dve_create_drc_job" in combined and "dve_job_run_drc" in combined
        )
        affirmative = documented_flow and not negative
        if not affirmative:
            errors.append("K6 contradicts the documented ADS 2027 Python DRC capability")
        if not documented_flow:
            errors.append("K6 lacks the documented DRC API flow")
        if not answer.get("sources"):
            errors.append("K6 lacks source evidence")
        if not re.search(r"verify|verification|fallback|manual|ael|gui", combined):
            errors.append("K6 lacks bounded verification or fallback")
    else:
        root = work.resolve()
        workspace = Path(str(answer.get("workspace", ""))).resolve()
        dataset = Path(str(answer.get("dataset", ""))).resolve()
        if root not in workspace.parents or not workspace.is_dir():
            errors.append("workspace missing or outside run directory")
        if root not in dataset.parents or not dataset.exists():
            errors.append("dataset missing or outside run directory")
        for key, expected in {
            "simulation_count": 1,
            "simulation_completed": True,
            "dataset_read_back": True,
            "gui_launched": False,
        }.items():
            if answer.get(key) != expected:
                errors.append(f"E3 acceptance mismatch: {key}")
        sample = answer.get("numeric_sample")
        if not isinstance(sample, (int, float)) or not math.isfinite(sample):
            errors.append("numeric sample is not finite")
    return errors


def execute_one(
    paths: Paths,
    contract: dict[str, Any],
    *,
    phase: str,
    campaign: str,
    trial: int,
    case_id: str,
    agent: str,
    arm: str,
    model: str,
    reasoning_effort: str,
    display: str,
) -> dict[str, Any]:
    run_dir = paths.runs / phase / campaign / f"trial-{trial:02d}" / case_id / agent / arm
    agent_home = run_dir / f"{agent}-home"
    work = run_dir / "work"
    agent_home.mkdir(parents=True, exist_ok=False)
    work.mkdir(parents=True, exist_ok=False)
    auth = paths.auth_source if agent == "codex" else paths.pi_auth_source
    copy_agent_auth(auth, agent_home / "auth.json", agent)
    schema_path = run_dir / "output-schema.json"
    answer_path = run_dir / "answer.json"
    events_path = run_dir / "events.jsonl"
    stderr_path = run_dir / "stderr.log"
    schema_path.write_text(json.dumps(output_schema(case_id), indent=2), encoding="utf-8")
    env = product_env(paths, display)
    prompt = prompt_for(contract, arm, case_id, work)
    if arm == "runtime" and agent == "codex":
        install_runtime_codex_profile(paths, agent_home, env)
    elif arm == "official" and agent == "codex":
        license_value = env.get("ADS_LICENSE_FILE")
        if not license_value:
            raise RuntimeError("ADS_LICENSE_FILE is required")
        (agent_home / "config.toml").write_text(official_config(paths, display, license_value), encoding="utf-8")

    if agent == "codex":
        env["CODEX_HOME"] = str(agent_home)
        command = [
            "codex", "exec", "--json", "--ephemeral", "--ignore-rules",
            "--skip-git-repo-check", "--model", model,
            "--config", f'model_reasoning_effort="{reasoning_effort}"',
            "--cd", str(work), "--output-schema", str(schema_path),
            "--output-last-message", str(answer_path),
        ]
        if arm == "runtime":
            command.extend(["--profile", "eda-runtime"])
        else:
            command.append("--dangerously-bypass-approvals-and-sandbox")
        command.append(prompt)
    else:
        env["PI_CODING_AGENT_DIR"] = str(agent_home)
        env["PATH"] = str(paths.pi_node_bin.parent) + os.pathsep + env["PATH"]
        command = [
            str(paths.pi_bin), "--mode", "json", "--print", "--no-session",
            "--no-context-files", "--no-extensions", "--no-skills",
            "--no-prompt-templates", "--no-themes", "--no-approve",
            "--provider", "openai-codex", "--model", model,
            "--thinking", reasoning_effort, "--no-builtin-tools",
        ]
        if arm == "runtime":
            extension, skills = runtime_pi_assets(paths)
            env["EDA_RUNTIME_PYTHON"] = str(paths.runtime_python)
            env.pop("EDA_RUNTIME_COMMAND", None)
            command.extend(["--extension", str(extension)])
            for skill in skills:
                command.extend(["--skill", str(skill)])
            command.extend(["--tools", ",".join(("read", *RUNTIME_TOOLS))])
        else:
            ads = str(paths.ads_root)
            env["ADS_MCP_COMMAND"] = str(paths.official_mcp)
            env["LD_LIBRARY_PATH"] = ":".join((f"{ads}/tools/python/lib", f"{ads}/lib/linux_x86_64", f"{ads}/lib/linux_x86_64/gccrt15"))
            env["PATH"] = f"{paths.pi_node_bin.parent}:{ads}/bin:{ads}/tools/python/bin:/usr/local/bin:/usr/bin:/bin"
            command.extend(["--extension", str(paths.pi_official_extension)])
        command.append(
            prompt + "\n\nYour final response must be only one JSON object conforming exactly to this schema:\n"
            + json.dumps(output_schema(case_id), separators=(",", ":"))
        )
    started = time.monotonic()
    with events_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        process = subprocess.Popen(
            command,
            env=env,
            cwd=work,
            text=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=stderr,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                stdout.write(line)
            else:
                event["_benchmark_received_ms"] = round(
                    (time.monotonic() - started) * 1000, 3
                )
                stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
            stdout.flush()
        returncode = process.wait()
    wall_seconds = time.monotonic() - started
    events = load_events(events_path)
    facts = event_facts(events, agent)
    if agent == "codex":
        try:
            answer = json.loads(answer_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            answer = {}
    else:
        answer = parse_answer(facts["final_text"])
        if answer:
            answer_path.write_text(json.dumps(answer, indent=2), encoding="utf-8")
    errors = validate(case_id, arm, work, answer, events) if answer else ["missing or invalid final JSON"]
    usage = facts["usage"]
    record = {
        "schema": "ads-agent-benchmark-run/v3",
        "phase": phase,
        "campaign": campaign,
        "trial": trial,
        "case": case_id,
        "agent": agent,
        "arm": arm,
        "status": "pass" if returncode == 0 and not errors else "fail",
        "returncode": returncode,
        "wall_seconds": round(wall_seconds, 3),
        "usage": usage,
        "total_tokens": usage["input_tokens"] + usage["output_tokens"],
        "tool_names": facts["tool_names"],
        "timing_ms": facts["timing_ms"],
        "validation_errors": errors,
        "answer": answer,
    }
    (run_dir / "result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def schedule(arms: list[str], agents: list[str], cases: list[str], repetitions: int):
    for trial in range(1, repetitions + 1):
        for case_index, case_id in enumerate(cases):
            ordered_arms = arms[(trial + case_index - 1) % len(arms) :] + arms[: (trial + case_index - 1) % len(arms)]
            ordered_agents = agents if (trial + case_index) % 2 else list(reversed(agents))
            for agent in ordered_agents:
                for arm in ordered_arms:
                    yield trial, case_id, agent, arm


def run_suite(paths: Paths, args: argparse.Namespace) -> list[dict[str, Any]]:
    contract = json.loads(paths.contract.read_text(encoding="utf-8"))
    records = []
    for trial, case_id, agent, arm in schedule(list(args.arms), list(args.agents), list(args.cases), args.repetitions):
        record = execute_one(
            paths, contract, phase=args.phase, campaign=args.campaign,
            trial=trial, case_id=case_id,
            agent=agent, arm=arm, model=args.model,
            reasoning_effort=args.reasoning_effort, display=args.display,
        )
        records.append(record)
        print(json.dumps({key: record[key] for key in ("case", "agent", "arm", "status", "wall_seconds", "total_tokens", "validation_errors")}), flush=True)
    return records


def summarize(paths: Paths, phase: str) -> dict[str, Any]:
    records = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((paths.runs / phase).glob("**/result.json"))]
    aggregate = {}
    for agent in AGENTS:
        for arm in ARMS:
            for case_id in CASES:
                selected = [r for r in records if r["agent"] == agent and r["arm"] == arm and r["case"] == case_id]
                aggregate[f"{case_id}:{agent}:{arm}"] = {
                    "runs": len(selected),
                    "passes": sum(r["status"] == "pass" for r in selected),
                    "median_wall_seconds": statistics.median(r["wall_seconds"] for r in selected) if selected else None,
                    "median_total_tokens": statistics.median(r["total_tokens"] for r in selected) if selected else None,
                }
    summary = {"schema": "ads-agent-benchmark-summary/v3", "phase": phase, "aggregate": aggregate, "runs": records}
    output = paths.root / f"{phase}-summary.json"
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    args = parse_args()
    if not 1 <= args.repetitions <= 10:
        raise SystemExit("--repetitions must be between 1 and 10")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", args.campaign):
        raise SystemExit("--campaign must be a bounded filesystem-safe label")
    paths = Paths(
        root=args.root.resolve(), ads_root=args.ads_root.resolve(),
        official_mcp=args.official_mcp.resolve(), auth_source=args.auth_source.resolve(),
        pi_bin=args.pi_bin.resolve(), pi_node_bin=args.pi_node_bin.resolve(),
        pi_auth_source=args.pi_auth_source.resolve(),
        pi_official_extension=args.pi_official_extension.resolve(),
        contract=args.contract.resolve(),
    )
    if args.command == "preflight":
        result = preflight(paths, args.official_sha256)
    elif args.command == "prepare":
        result = prepare(paths, runtime_version=args.runtime_version, bridge_version=args.bridge_version, display=args.display)
    elif args.command == "run":
        records = run_suite(paths, args)
        result = {"runs": len(records), "passes": sum(r["status"] == "pass" for r in records)}
    else:
        result = summarize(paths, args.phase)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
