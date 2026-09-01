from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _runner():
    path = Path(__file__).parents[1] / "scripts" / "benchmark_ads2027_v3.py"
    spec = importlib.util.spec_from_file_location("benchmark_ads2027_v3", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v3_contract_compares_mcp_surfaces_without_legacy_cli():
    root = Path(__file__).parents[1]
    contract = json.loads(
        (root / "docs" / "benchmarks" / "ads2027-v3-contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(contract["arms"]) == {"runtime", "official"}
    assert "EDA Runtime MCP" in contract["arms"]["runtime"]["surface"]
    assert "ads-agent CLI task execution" in contract["arms"]["runtime"]["forbidden"]
    assert contract["cases"]["E3"]["common_acceptance"]["simulation_count"] == 1


def test_schedule_is_serial_and_counterbalanced():
    runner = _runner()
    observed = list(
        runner.schedule(["runtime", "official"], ["codex", "pi"], ["K1"], 2)
    )
    assert len(observed) == 8
    assert [row[3] for row in observed[:2]] == ["runtime", "official"]
    assert [row[3] for row in observed[4:6]] == ["official", "runtime"]


def test_run_campaign_has_an_isolated_directory_component():
    runner = _runner()
    assert "campaign" in runner.execute_one.__annotations__


def test_runtime_validation_rejects_cli_and_official_surface(tmp_path: Path):
    runner = _runner()
    answer = {
        "case_id": "K1",
        "answer": "Use Runtime MCP eda.submit with native.batch in no-GUI mode and read a finite dataset sample.",
        "code": "",
        "sources": [],
    }
    events = [
        {"item": {"type": "command_execution", "command": "ads-agent quickstart"}},
        {"item": {"type": "mcp_tool_call", "name": "mcp__ads__start_local_session"}},
    ]
    errors = runner.validate("K1", "runtime", tmp_path, answer, events)
    assert "runtime arm crossed into official MCP" in errors
    assert "runtime arm used CLI or shell" in errors


def test_prompt_requires_run_unique_idempotency_key(tmp_path: Path):
    runner = _runner()
    contract = json.loads(
        (
            Path(__file__).parents[1]
            / "docs"
            / "benchmarks"
            / "ads2027-v3-contract.json"
        ).read_text(encoding="utf-8")
    )
    prompt = runner.prompt_for(contract, "runtime", "E3", tmp_path)
    assert "derive a unique key from this RUN_DIRECTORY" in prompt


def test_validation_ignores_surface_names_in_prompt_and_checks_actual_tools(
    tmp_path: Path,
):
    runner = _runner()
    answer = {
        "case_id": "K1",
        "answer": "Use Runtime MCP native.batch in automation mode and read a finite dataset sample.",
        "code": "",
        "sources": [],
    }
    events = [
        {"type": "message_start", "prompt": "Do not invoke ads-agent CLI or official MCP"},
        {"type": "tool_execution_start", "toolName": "eda_read"},
    ]
    assert runner.validate("K1", "runtime", tmp_path, answer, events) == []


def test_codex_oauth_is_normalized_for_pi_without_changing_source(tmp_path: Path):
    runner = _runner()
    source = tmp_path / "codex-auth.json"
    destination = tmp_path / "pi-auth.json"
    payload = {"exp": 2_000_000_000}
    encoded = __import__("base64").urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    original = {
        "tokens": {
            "access_token": f"x.{encoded}.x",
            "refresh_token": "refresh",
            "account_id": "account",
        }
    }
    source.write_text(json.dumps(original), encoding="utf-8")
    runner.copy_agent_auth(source, destination, "pi")
    normalized = json.loads(destination.read_text(encoding="utf-8"))["openai-codex"]
    assert normalized == {
        "type": "oauth",
        "refresh": "refresh",
        "access": f"x.{encoded}.x",
        "expires": 2_000_000_000_000,
        "accountId": "account",
    }
    assert json.loads(source.read_text(encoding="utf-8")) == original


def test_execution_validation_requires_real_artifacts_and_one_simulation(
    tmp_path: Path,
):
    runner = _runner()
    workspace = tmp_path / "work" / "demo_wrk"
    dataset = workspace / "data" / "accepted.ds"
    dataset.mkdir(parents=True)
    answer = {
        "case_id": "E3",
        "workspace": str(workspace),
        "dataset": str(dataset),
        "simulation_count": 1,
        "simulation_completed": True,
        "dataset_read_back": True,
        "numeric_sample": 0.5,
        "gui_launched": False,
        "evidence": ["dataset opened"],
    }
    assert runner.validate("E3", "official", tmp_path / "work", answer, []) == []
    answer["simulation_count"] = 2
    assert "E3 acceptance mismatch: simulation_count" in runner.validate(
        "E3", "official", tmp_path / "work", answer, []
    )
