from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ARMS = ("bridge_a29", "bridge_a48", "official")
AGENTS = ("codex", "pi")
KNOWLEDGE_CASES = ("K1", "K3", "K6")
ALL_CASES = (*KNOWLEDGE_CASES, "E3")
BRIDGE_VERSIONS = {"bridge_a29": "0.1.0a29", "bridge_a48": "0.1.0a48"}
OFFICIAL_SHA256 = "b68afcc4e904fae576a3c139898f877261fe9266a5235313ec46d48a2d0e4783"


@dataclass(frozen=True)
class Paths:
    root: Path
    ads_root: Path
    official_mcp: Path
    auth_source: Path
    contract: Path
    pi_bin: Path
    pi_node_bin: Path
    pi_auth_source: Path
    pi_extension: Path

    @property
    def envs(self) -> Path:
        return self.root / "envs"

    @property
    def product_homes(self) -> Path:
        return self.root / "product-homes"

    @property
    def runs(self) -> Path:
        return self.root / "runs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("preflight", "prepare", "run", "revalidate", "summarize")
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--ads-root", type=Path, required=True)
    parser.add_argument("--official-mcp", type=Path, required=True)
    parser.add_argument("--auth-source", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--pi-bin", type=Path, required=True)
    parser.add_argument("--pi-node-bin", type=Path, required=True)
    parser.add_argument("--pi-auth-source", type=Path, required=True)
    parser.add_argument("--pi-extension", type=Path, required=True)
    parser.add_argument(
        "--phase", choices=("calibration", "formal"), default="calibration"
    )
    parser.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    parser.add_argument("--agents", nargs="+", choices=AGENTS, default=list(AGENTS))
    parser.add_argument(
        "--cases", nargs="+", choices=ALL_CASES, default=list(ALL_CASES)
    )
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--model", default="gpt-5.6-terra")
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--display", default=":4")
    return parser.parse_args()


def run_checked(command: list[str], *, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command, env=env, check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def base_env(paths: Paths, *, home: Path, display: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "DISPLAY": display,
            "HPEESOF_DIR": str(paths.ads_root),
        }
    )
    return env


def env_python(paths: Paths, arm: str) -> Path:
    return paths.envs / arm / "bin" / "python"


def env_ads_agent(paths: Paths, arm: str) -> Path:
    return paths.envs / arm / "bin" / "ads-agent"


def preflight(paths: Paths) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "contract_exists": paths.contract.is_file(),
        "auth_exists": paths.auth_source.is_file(),
        "ads_root_exists": paths.ads_root.is_dir(),
        "official_mcp_exists": paths.official_mcp.is_file(),
        "official_mcp_sha256": sha256(paths.official_mcp)
        if paths.official_mcp.is_file()
        else None,
        "codex_version": run_checked(["codex", "--version"]),
        "pi_version": run_checked(
            [str(paths.pi_node_bin), str(paths.pi_bin), "--version"]
        ),
        "pi_node_exists": paths.pi_node_bin.is_file(),
        "pi_auth_exists": paths.pi_auth_source.is_file(),
        "pi_extension_exists": paths.pi_extension.is_file(),
        "ads_license_configured": bool(os.environ.get("ADS_LICENSE_FILE")),
    }
    checks["official_mcp_identity_matches"] = (
        checks["official_mcp_sha256"] == OFFICIAL_SHA256
    )
    checks["ready"] = all(
        (
            checks["contract_exists"],
            checks["auth_exists"],
            checks["ads_root_exists"],
            checks["official_mcp_identity_matches"],
            checks["codex_version"] == "codex-cli 0.145.0",
            checks["pi_version"] == "0.84.4",
            checks["pi_node_exists"],
            checks["pi_auth_exists"],
            checks["pi_extension_exists"],
            checks["ads_license_configured"],
        )
    )
    return checks


def prepare(paths: Paths, display: str) -> dict[str, Any]:
    paths.envs.mkdir(parents=True, exist_ok=True)
    paths.product_homes.mkdir(parents=True, exist_ok=True)
    prepared: dict[str, Any] = {}
    for arm, version in BRIDGE_VERSIONS.items():
        venv = paths.envs / arm
        home = paths.product_homes / arm
        home.mkdir(parents=True, exist_ok=True)
        if not env_python(paths, arm).is_file():
            run_checked(["python3.11", "-m", "venv", str(venv)])
        run_checked(
            [
                str(env_python(paths, arm)),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                f"ads-agent-bridge=={version}",
            ]
        )
        env = base_env(paths, home=home, display=display)
        run_checked(
            [
                str(env_ads_agent(paths, arm)),
                "setup",
                "--ads-root",
                str(paths.ads_root),
                "--non-interactive",
                "--skip-skill",
                "--no-background-docs",
            ],
            env=env,
        )
        instances = json.loads(
            run_checked([str(env_ads_agent(paths, arm)), "instances", "list"], env=env)
        )
        ads_2027 = next(
            item
            for item in instances["instances"]
            if item["product_version"] == "ADS 2027"
        )
        run_checked(
            [
                str(env_ads_agent(paths, arm)),
                "docs",
                "build",
                "--ads",
                ads_2027["instance_id"],
            ],
            env=env,
        )
        prepared[arm] = {
            "version": run_checked(
                [str(env_ads_agent(paths, arm)), "--version"], env=env
            ),
            "instance_id": ads_2027["instance_id"],
            "python_sha256": sha256(env_python(paths, arm)),
        }
    return prepared


def output_schema(case_id: str) -> dict[str, Any]:
    common = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
    }
    if case_id in KNOWLEDGE_CASES:
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
            "running_automation": {"type": "boolean"},
            "is_pde_app": {"type": "boolean"},
            "simulation_completed": {"type": "boolean"},
            "dataset_read_back": {"type": "boolean"},
            "numeric_sample": {"type": "number"},
            "gui_launched": {"type": "boolean"},
        },
        "required": [
            "case_id",
            "workspace",
            "dataset",
            "running_automation",
            "is_pde_app",
            "simulation_completed",
            "dataset_read_back",
            "numeric_sample",
            "gui_launched",
        ],
    }


def counterbalanced_order(trial: int, case_index: int) -> tuple[str, ...]:
    rotation = (trial + case_index - 2) % len(ARMS)
    return ARMS[rotation:] + ARMS[:rotation]


def install_skills(
    paths: Paths,
    arm: str,
    agent_home: Path,
    env: dict[str, str],
    case_id: str,
    agent: str,
) -> list[Path]:
    if arm == "bridge_a29":
        skill_kind = "docs"
    elif case_id == "K1":
        skill_kind = "all"
    elif case_id in {"K3", "K6"}:
        skill_kind = "docs"
    else:
        skill_kind = "bridge"
    run_checked(
        [
            str(env_ads_agent(paths, arm)),
            "skill",
            "install",
            skill_kind,
            "--target",
            "codex" if agent == "codex" else "agents",
            "--root",
            str(agent_home / "skills"),
            "--force",
        ],
        env=env,
    )
    return sorted((agent_home / "skills").glob("**/SKILL.md"))


def official_config(paths: Paths, display: str, license_value: str) -> str:
    ads = str(paths.ads_root)
    library_path = ":".join(
        (
            f"{ads}/tools/python/lib",
            f"{ads}/lib/linux_x86_64",
            f"{ads}/lib/linux_x86_64/gccrt15",
        )
    )
    return "\n".join(
        (
            "[mcp_servers.ads]",
            f"command = {json.dumps(str(paths.official_mcp))}",
            "startup_timeout_sec = 30",
            "tool_timeout_sec = 180",
            "[mcp_servers.ads.env]",
            f"HPEESOF_DIR = {json.dumps(ads)}",
            f"DISPLAY = {json.dumps(display)}",
            f"LD_LIBRARY_PATH = {json.dumps(library_path)}",
            f"ADS_LICENSE_FILE = {json.dumps(license_value)}",
            f'PATH = {json.dumps(ads + "/bin:" + ads + "/tools/python/bin:/usr/local/bin:/usr/bin:/bin")}',
            "",
        )
    )


def prompt_for(contract: dict[str, Any], arm: str, case_id: str, run_dir: Path) -> str:
    case = contract["cases"][case_id]
    if arm.startswith("bridge"):
        lane = (
            "Your only product surface is the installed ads-agent Bridge and the one packaged Skill "
            "provided in this fresh Codex home. Do not call or inspect the official ADS MCP."
        )
    else:
        lane = (
            "Your only product surface is the configured official ADS MCP. Use its documentation tools "
            "for knowledge cases and start_local_session plus execute_python for E3. Do not call, inspect, "
            "or mention ads-agent or ADS Agent Bridge."
        )
    return "\n\n".join(
        (
            "You are taking part in a controlled ADS 2027 benchmark. Follow the assigned surface exactly.",
            lane,
            "Web access, external repositories, earlier run outputs, and direct shell invocation of ADS Python or hpeesofsim are forbidden. Ordinary shell use is allowed only to inspect the assigned empty run directory or invoke ads-agent in a Bridge arm.",
            f"RUN_DIRECTORY={run_dir}",
            case["prompt"].replace("RUN_DIRECTORY", str(run_dir)),
        )
    )


def parse_jsonl(path: Path) -> tuple[dict[str, int], int, list[str]]:
    usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    tool_events = 0
    event_types: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = str(event.get("type", ""))
            event_types.append(event_type)
            if "tool" in event_type or event_type in {"item.started", "item.completed"}:
                item = event.get("item", {})
                if item.get("type") in {"command_execution", "mcp_tool_call"}:
                    tool_events += 1
            candidate = event.get("usage")
            if isinstance(candidate, dict):
                for key in usage:
                    if isinstance(candidate.get(key), int):
                        usage[key] = max(usage[key], candidate[key])
    return usage, tool_events, event_types


def parse_pi_jsonl(path: Path) -> tuple[dict[str, int], int, list[str], str]:
    usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    tool_events = 0
    event_types: list[str] = []
    final_text = ""
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = str(event.get("type", ""))
            event_types.append(event_type)
            if event_type == "tool_execution_start":
                tool_events += 1
            if event_type != "message_end":
                continue
            message = event.get("message", {})
            if message.get("role") != "assistant":
                continue
            native_usage = message.get("usage", {})
            usage["input_tokens"] += int(native_usage.get("input", 0)) + int(
                native_usage.get("cacheRead", 0)
            )
            usage["cached_input_tokens"] += int(native_usage.get("cacheRead", 0))
            usage["output_tokens"] += int(native_usage.get("output", 0))
            texts = [
                block.get("text", "")
                for block in message.get("content", [])
                if block.get("type") == "text"
            ]
            if texts:
                final_text = "\n".join(texts)
    return usage, tool_events, event_types, final_text


def parse_answer_text(text: str) -> dict[str, Any]:
    candidate = text.strip()
    fenced = re.search(
        r"```(?:json)?\s*(\{.*\})\s*```", candidate, re.DOTALL | re.IGNORECASE
    )
    if fenced:
        candidate = fenced.group(1)
    else:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def validate(
    case_id: str,
    arm: str,
    run_dir: Path,
    answer: dict[str, Any],
    jsonl: Path,
    agent: str,
) -> list[str]:
    errors: list[str] = []
    combined = (answer.get("answer", "") + "\n" + answer.get("code", "")).lower()
    if case_id == "K1":
        if not re.search(
            r"headless|no[- ]gui|without.{0,40}gui|not.{0,40}gui", combined
        ):
            errors.append("K1 missing headless")
        if (
            "dataset" not in combined
            and not re.search(r"numeric[- ]result", combined)
            and not (
                "finite" in combined and re.search(r"read|readback|读取|回读", combined)
            )
        ):
            errors.append("K1 missing dataset or equivalent finite-result readback")
        if arm.startswith("bridge") and not (
            "ads-agent quickstart" in combined
            or re.search(r"ads-agent examples run\s+headless-minimal-ac", combined)
        ):
            errors.append(
                "K1 Bridge arm did not select the maintained disposable headless route"
            )
        if arm == "official" and not (
            "start_local_session" in combined and "execute_python" in combined
        ):
            errors.append(
                "K1 official arm did not select start_local_session plus execute_python"
            )
    elif case_id == "K3":
        shape_patterns = {
            "rectangle": r"rectangle|\brect\b|db\.rect",
            "polygon": r"polygon|db\.polygon",
            "path": r"path|db\.path",
        }
        for shape, pattern in shape_patterns.items():
            if not re.search(pattern, combined):
                errors.append(f"K3 missing {shape}")
        if not re.search(
            r"(add_(rectangle|polygon|path)|db\.(rect|polygon|path))", combined
        ):
            errors.append("K3 lacks recognizable documented geometry calls")
    elif case_id == "K6":
        if "create_drc_job" in combined and not re.search(
            r"(unverified|not verified|not documented|no documented|not (?:been )?established|do not treat.{0,80}runnable|未验证|未建立)",
            combined,
        ):
            errors.append(
                "K6 presents create_drc_job without an explicit unverified boundary"
            )
        if not re.search(
            r"(not documented|no documented|not (?:been )?established|could not verify|not verified|unverified|未验证|未建立|未找到)",
            combined,
        ):
            errors.append("K6 lacks the required documented-capability boundary")
        if not re.search(
            r"(fallback|manual|ael|gui|verification|verify|回退|验证)", combined
        ):
            errors.append("K6 lacks a verification step or fallback")
    else:
        workspace = Path(answer.get("workspace", "")).resolve()
        dataset = Path(answer.get("dataset", "")).resolve()
        root = run_dir.resolve()
        if root not in workspace.parents:
            errors.append("workspace escaped the assigned run directory")
        if root not in dataset.parents:
            errors.append("dataset escaped the assigned run directory")
        if not workspace.is_dir():
            errors.append("workspace does not exist")
        if not dataset.exists():
            errors.append("dataset does not exist")
        expected = {
            "running_automation": True,
            "is_pde_app": False,
            "simulation_completed": True,
            "dataset_read_back": True,
            "gui_launched": False,
        }
        for key, value in expected.items():
            if answer.get(key) is not value:
                errors.append(f"E3 acceptance mismatch: {key}")
        sample = answer.get("numeric_sample")
        if not isinstance(sample, (int, float)) or not (
            -sys.float_info.max < sample < sys.float_info.max
        ):
            errors.append("numeric sample is not finite")
    tool_payloads: list[str] = []
    shell_commands: list[str] = []
    with jsonl.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item", {})
            if item.get("type") in {"command_execution", "mcp_tool_call"}:
                tool_payloads.append(json.dumps(item).lower())
            if item.get("type") == "command_execution" and isinstance(
                item.get("command"), str
            ):
                shell_commands.append(item["command"].lower())
            if agent == "pi" and event.get("type") == "tool_execution_start":
                tool_payloads.append(json.dumps(event).lower())
                if event.get("toolName") == "bash" and isinstance(
                    event.get("args"), dict
                ):
                    command = event["args"].get("command")
                    if isinstance(command, str):
                        shell_commands.append(command.lower())
    tool_text = "\n".join(tool_payloads)
    if arm == "official" and re.search(r"ads-agent|ads_agent_bridge", tool_text):
        errors.append("official arm crossed into the Bridge surface")
    if arm.startswith("bridge") and "ads-mcp" in tool_text:
        errors.append("Bridge arm crossed into the official MCP surface")

    def mutating_k1_invocation(command: str) -> bool:
        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = []
        script = tokens[2] if len(tokens) >= 3 and tokens[1] == "-lc" else command
        for segment in re.split(r"&&|\|\||;", script):
            if (
                re.match(
                    r"\s*ads-agent\s+(quickstart|examples\s+run\s+headless-minimal-ac)(?:\s|$)",
                    segment,
                )
                and "--help" not in segment
            ):
                return True
        return False

    if case_id == "K1" and any(
        mutating_k1_invocation(command) for command in shell_commands
    ):
        errors.append("K1 executed quickstart instead of remaining knowledge-only")
    return errors


def execute_one(
    paths: Paths,
    contract: dict[str, Any],
    agent: str,
    arm: str,
    case_id: str,
    trial: int,
    phase: str,
    model: str,
    reasoning_effort: str,
    display: str,
) -> dict[str, Any]:
    run_dir = paths.runs / phase / agent / f"trial-{trial:02d}" / case_id / arm
    agent_home = run_dir / f"{agent}-home"
    work = run_dir / "work"
    agent_home.mkdir(parents=True, exist_ok=False)
    work.mkdir(parents=True, exist_ok=False)
    auth_source = paths.auth_source if agent == "codex" else paths.pi_auth_source
    shutil.copy2(auth_source, agent_home / "auth.json")
    (agent_home / ".case-class").write_text(
        contract["cases"][case_id]["class"], encoding="utf-8"
    )
    schema_path = run_dir / "output-schema.json"
    schema_path.write_text(
        json.dumps(output_schema(case_id), indent=2), encoding="utf-8"
    )
    answer_path = run_dir / "answer.json"
    jsonl_path = run_dir / "events.jsonl"
    stderr_path = run_dir / "stderr.log"

    product_home = (
        paths.product_homes / arm if arm.startswith("bridge") else run_dir / "home"
    )
    product_home.mkdir(parents=True, exist_ok=True)
    env = base_env(paths, home=product_home, display=display)
    env["BASH_ENV"] = "/dev/null"
    skill_paths: list[Path] = []
    if arm.startswith("bridge"):
        skill_paths = install_skills(paths, arm, agent_home, env, case_id, agent)
        env["PATH"] = (
            str(paths.envs / arm / "bin") + os.pathsep + "/usr/local/bin:/usr/bin:/bin"
        )
    else:
        (run_dir / "home").mkdir(parents=True, exist_ok=True)
        license_value = env.get("ADS_LICENSE_FILE")
        if not license_value:
            raise RuntimeError("ADS_LICENSE_FILE is required for the official MCP arm")
        if agent == "codex":
            (agent_home / "config.toml").write_text(
                official_config(paths, display, license_value), encoding="utf-8"
            )
        else:
            ads = str(paths.ads_root)
            env["ADS_MCP_COMMAND"] = str(paths.official_mcp)
            env["LD_LIBRARY_PATH"] = ":".join(
                (
                    f"{ads}/tools/python/lib",
                    f"{ads}/lib/linux_x86_64",
                    f"{ads}/lib/linux_x86_64/gccrt15",
                )
            )
            env["PATH"] = (
                f"{ads}/bin:{ads}/tools/python/bin:/usr/local/bin:/usr/bin:/bin"
            )

    benchmark_prompt = prompt_for(contract, arm, case_id, work)
    if agent == "codex":
        env["CODEX_HOME"] = str(agent_home)
        command = [
            "codex",
            "exec",
            "--json",
            "--ephemeral",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
            "--model",
            model,
            "--config",
            f'model_reasoning_effort="{reasoning_effort}"',
            "--cd",
            str(work),
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(answer_path),
            benchmark_prompt,
        ]
    else:
        env["PI_CODING_AGENT_DIR"] = str(agent_home)
        env["PATH"] = str(paths.pi_node_bin.parent) + os.pathsep + env["PATH"]
        command = [
            str(paths.pi_bin),
            "--mode",
            "json",
            "--print",
            "--no-session",
            "--no-context-files",
            "--no-extensions",
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
            "--no-approve",
            "--provider",
            "openai-codex",
            "--model",
            model,
            "--thinking",
            reasoning_effort,
        ]
        if arm == "official":
            command.extend(
                ("--no-builtin-tools", "--extension", str(paths.pi_extension))
            )
        else:
            command.extend(("--tools", "read,bash"))
            for skill_path in skill_paths:
                command.extend(("--skill", str(skill_path)))
        command.append(
            benchmark_prompt
            + "\n\nYour final response must be only one JSON object conforming exactly to this schema:\n"
            + json.dumps(output_schema(case_id), separators=(",", ":"))
        )
    started = time.monotonic()
    with (
        jsonl_path.open("w", encoding="utf-8") as stdout,
        stderr_path.open("w", encoding="utf-8") as stderr,
    ):
        result = subprocess.run(
            command,
            env=env,
            text=True,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            cwd=work,
        )
    wall_seconds = time.monotonic() - started
    if agent == "codex":
        try:
            answer = json.loads(answer_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            answer = {}
        usage, tool_events, event_types = parse_jsonl(jsonl_path)
    else:
        usage, tool_events, event_types, final_text = parse_pi_jsonl(jsonl_path)
        answer = parse_answer_text(final_text)
        if answer:
            answer_path.write_text(json.dumps(answer, indent=2), encoding="utf-8")
    errors = (
        validate(case_id, arm, work, answer, jsonl_path, agent)
        if answer
        else ["missing or invalid final JSON"]
    )
    record = {
        "schema": "ads-agent-benchmark-run/v2",
        "phase": phase,
        "trial": trial,
        "agent": agent,
        "case": case_id,
        "arm": arm,
        "status": "pass" if result.returncode == 0 and not errors else "fail",
        "returncode": result.returncode,
        "wall_seconds": round(wall_seconds, 3),
        "usage": usage,
        "total_tokens": usage["input_tokens"] + usage["output_tokens"],
        "uncached_input_tokens": max(
            0, usage["input_tokens"] - usage["cached_input_tokens"]
        ),
        "tool_events": tool_events,
        "event_types": sorted(set(event_types)),
        "validation_errors": errors,
        "answer": answer,
    }
    (run_dir / "result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def run_suite(paths: Paths, args: argparse.Namespace) -> list[dict[str, Any]]:
    contract = json.loads(paths.contract.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    for trial in range(1, args.repetitions + 1):
        for case_index, case_id in enumerate(args.cases):
            order = [
                arm
                for arm in counterbalanced_order(trial, case_index)
                if arm in args.arms
            ]
            agent_order = (
                args.agents if (trial + case_index) % 2 else list(reversed(args.agents))
            )
            for agent in agent_order:
                for arm in order:
                    records.append(
                        execute_one(
                            paths,
                            contract,
                            agent,
                            arm,
                            case_id,
                            trial,
                            args.phase,
                            args.model,
                            args.reasoning_effort,
                            args.display,
                        )
                    )
                    print(
                        json.dumps(
                            {
                                key: records[-1][key]
                                for key in (
                                    "case",
                                    "agent",
                                    "arm",
                                    "status",
                                    "wall_seconds",
                                    "total_tokens",
                                    "validation_errors",
                                )
                            }
                        ),
                        flush=True,
                    )
    return records


def revalidate(paths: Paths, phase: str) -> dict[str, int]:
    checked = 0
    changed = 0
    for result_path in sorted((paths.runs / phase).glob("**/result.json")):
        record = json.loads(result_path.read_text(encoding="utf-8"))
        run_dir = result_path.parent
        answer = record.get("answer", {})
        errors = (
            validate(
                record["case"],
                record["arm"],
                run_dir / "work",
                answer,
                run_dir / "events.jsonl",
                record.get("agent", "codex"),
            )
            if answer
            else ["missing or invalid final JSON"]
        )
        status = "pass" if record.get("returncode") == 0 and not errors else "fail"
        checked += 1
        if errors != record.get("validation_errors") or status != record.get("status"):
            record.setdefault(
                "initial_validation_errors", record.get("validation_errors", [])
            )
            record["validation_errors"] = errors
            record["status"] = status
            record["revalidated"] = True
            result_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
            changed += 1
    return {"checked": checked, "changed": changed}


def summarize(paths: Paths, phase: str) -> dict[str, Any]:
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((paths.runs / phase).glob("**/result.json"))
    ]
    aggregate: dict[str, Any] = {}
    for agent in AGENTS:
        for arm in ARMS:
            arm_records = [
                record
                for record in records
                if record.get("agent", "codex") == agent and record["arm"] == arm
            ]
            aggregate[f"{agent}:{arm}"] = {
                "runs": len(arm_records),
                "passes": sum(record["status"] == "pass" for record in arm_records),
                "total_tokens": sum(record["total_tokens"] for record in arm_records),
                "median_wall_seconds": statistics.median(
                    record["wall_seconds"] for record in arm_records
                )
                if arm_records
                else None,
                "isolation_violations": sum(
                    any(
                        "surface" in error or "escaped" in error
                        for error in record["validation_errors"]
                    )
                    for record in arm_records
                ),
            }
    summary = {
        "schema": "ads-agent-benchmark-summary/v2",
        "phase": phase,
        "aggregate": aggregate,
        "runs": records,
    }
    output = paths.root / f"{phase}-summary.json"
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    args = parse_args()
    paths = Paths(
        root=args.root.resolve(),
        ads_root=args.ads_root.resolve(),
        official_mcp=args.official_mcp.resolve(),
        auth_source=args.auth_source.resolve(),
        contract=args.contract.resolve(),
        pi_bin=args.pi_bin.resolve(),
        pi_node_bin=args.pi_node_bin.resolve(),
        pi_auth_source=args.pi_auth_source.resolve(),
        pi_extension=args.pi_extension.resolve(),
    )
    result: Any
    if args.command == "preflight":
        result = preflight(paths)
    elif args.command == "prepare":
        result = prepare(paths, args.display)
    elif args.command == "run":
        records = run_suite(paths, args)
        result = {
            "runs": len(records),
            "passes": sum(record["status"] == "pass" for record in records),
            "failures": sum(record["status"] != "pass" for record in records),
        }
    elif args.command == "revalidate":
        result = revalidate(paths, args.phase)
    else:
        result = summarize(paths, args.phase)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
