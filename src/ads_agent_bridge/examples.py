from __future__ import annotations

from pathlib import Path
from typing import Any

from .bridge_client import request
from .discovery import discover
from .onboarding import quickstart


EXAMPLES: tuple[dict[str, Any], ...] = (
    {
        "name": "discover-installations",
        "title": "Discover and choose an ADS installation",
        "lane": "local",
        "state_change": "none",
        "support": "stable",
        "requires": ["a local ADS installation"],
        "evidence": ["instance_id", "product_version", "support_tier", "docs_roots", "capabilities"],
    },
    {
        "name": "headless-minimal-ac",
        "title": "Create, simulate, and read back a minimal AC circuit",
        "lane": "headless",
        "state_change": "creates a new disposable workspace",
        "support": "stable on ADS 2025+ after runtime gates pass",
        "requires": ["a configured ADS instance", "ADS Python", "a license", "DISPLAY on Linux"],
        "evidence": ["workspace_creation", "circuit_simulation", "dataset_readback"],
    },
    {
        "name": "live-de-context",
        "title": "Read the active Design Environment workspace context",
        "lane": "live-de",
        "state_change": "none",
        "support": "stable on ADS 2025+ after bridge connection passes",
        "requires": ["ADS DE running with the bridge add-on", "an open workspace"],
        "evidence": ["profile", "slot", "pid", "workspace", "running_automation", "is_pde_app"],
    },
    {
        "name": "dds-dataset-readback",
        "title": "Create a DDS file and validate a dataset equation",
        "lane": "live-dds",
        "state_change": "creates ads_agent_dds_readback.dds in the chosen workspace",
        "support": "version-gated; DDS Python is probed at runtime",
        "requires": ["ADS DDS running with the bridge add-on", "an ADS dataset", "a writable disposable workspace"],
        "evidence": ["dds_path", "equation_status", "row_count", "dataset_aliases"],
    },
    {
        "name": "bounded-ael-workspace",
        "title": "Call a fixed read-only AEL workspace function",
        "lane": "live-de-ael",
        "state_change": "none",
        "support": "hybrid boundary; fixed allowlisted call only",
        "requires": ["ADS DE running with the bridge add-on", "an open workspace"],
        "evidence": ["function", "workspace_path", "bounded", "unsafe_python_enabled"],
    },
)


def list_examples() -> dict[str, Any]:
    return {"status": "ready", "count": len(EXAMPLES), "examples": list(EXAMPLES)}


def show_example(name: str) -> dict[str, Any]:
    for item in EXAMPLES:
        if item["name"] == name:
            return {"status": "ready", "example": item}
    raise ValueError(f"Unknown example: {name}. Run `ads-agent examples list`.")


def run_example(
    name: str,
    *,
    instance_id: str | None = None,
    ads_roots: list[Path] | None = None,
    search_roots: list[Path] | None = None,
    workspace: Path | None = None,
    dataset: Path | None = None,
    slot: str | None = None,
    timeout: float = 300,
    config_dir: Path | None = None,
) -> tuple[dict[str, Any], int]:
    metadata = show_example(name)["example"]
    if name == "discover-installations":
        found = discover(ads_roots or [], search_roots or [])
        payload = {
            "status": "passed" if found else "failed",
            "example": metadata,
            "read_only": True,
            "instances": [item.to_dict() for item in found],
        }
        return payload, 0 if found else 2
    if name == "headless-minimal-ac":
        payload, code = quickstart(instance_id, workspace, timeout, config_dir)
        return {"example": metadata, **payload}, code
    if name == "live-de-context":
        response = request("status", {}, slot, "de", timeout=min(timeout, 30))
        result = response.get("result") if response.get("ok") else None
        accepted = isinstance(result, dict) and result.get("profile") == "de" and result.get("workspace_is_open") is True
        return {
            "status": "passed" if accepted else "failed",
            "example": metadata,
            "bridge": response,
            "stop_reason": None if accepted else "A live DE bridge with an open workspace is required.",
        }, 0 if accepted else 2
    if name == "dds-dataset-readback":
        if workspace is None or dataset is None:
            raise ValueError("dds-dataset-readback requires --workspace and --dataset")
        response = request(
            "dds_readback",
            {"workspace": str(workspace.expanduser().resolve()), "dataset": str(dataset.expanduser().resolve())},
            slot,
            "dds",
            timeout=min(timeout, 120),
        )
        result = response.get("result") if response.get("ok") else None
        accepted = isinstance(result, dict) and bool(result.get("ok"))
        return {
            "status": "passed" if accepted else "failed",
            "example": metadata,
            "bridge": response,
        }, 0 if accepted else 2
    if name == "bounded-ael-workspace":
        response = request("ael_workspace_path", {}, slot, "de", timeout=min(timeout, 30))
        result = response.get("result") if response.get("ok") else None
        accepted = isinstance(result, dict) and bool(result.get("workspace_path")) and result.get("bounded") is True
        return {
            "status": "passed" if accepted else "failed",
            "example": metadata,
            "bridge": response,
            "stop_reason": None if accepted else "The fixed AEL call requires an open DE workspace.",
        }, 0 if accepted else 2
    raise ValueError(f"Unknown example: {name}")
