"""Standalone ADS Python quickstart: create, simulate, and read a tiny AC design."""

from __future__ import annotations

import argparse
import json
import shutil
import time
import traceback
from pathlib import Path

import keysight.ads.dataset as dataset
import keysight.ads.de as de
from keysight.ads.de import db_uu as db
from keysight.edatoolbox import ads


def summarize_dataset(path: Path) -> dict[str, object]:
    with dataset.open(path) as data:
        result: dict[str, object] = {"dataset_path": str(path), "varblocks": list(data.varblock_names)}
        if "AC1.AC" in data.varblock_names:
            frame = data["AC1.AC"].to_dataframe().reset_index()
            result["columns"] = [str(column) for column in frame.columns]
            result["rows"] = int(len(frame))
            if "freq" in frame.columns and len(frame):
                result["freq_first_last"] = [float(frame["freq"].iloc[0]), float(frame["freq"].iloc[-1])]
        return result


def run(workspace: Path) -> dict[str, object]:
    record: dict[str, object] = {"ok": False, "workspace": str(workspace)}
    try:
        running_automation = bool(de.running_automation())
        is_pde_app = bool(de.is_pde_app())
        record["execution_context"] = {
            "running_automation": running_automation,
            "is_pde_app": is_pde_app,
        }
        if not running_automation or is_pde_app:
            raise RuntimeError(
                "Quickstart requires external ADS automation "
                f"(running_automation={running_automation}, is_pde_app={is_pde_app})."
            )
        if workspace.exists():
            raise RuntimeError(f"Refusing to overwrite an existing quickstart workspace: {workspace}")
        workspace.parent.mkdir(parents=True, exist_ok=True)
        de.create_workspace(workspace)
        de.open_workspace(workspace)

        library_path = workspace / "AgentBridgeExamples_lib"
        de.create_new_library("AgentBridgeExamples_lib", library_path)
        de.active_workspace().add_library("AgentBridgeExamples_lib", library_path, de.LibraryMode.NON_SHARED)
        design = db.create_schematic("AgentBridgeExamples_lib:MinimalAC:schematic")
        design.add_instance(("ads_sources", "V_AC", "symbol"), (-2, 0), name="SRC1", angle=-90)
        resistor = design.add_instance(("ads_rflib", "R", "symbol"), (0, 0), name="R1")
        resistor.parameters["R"].value = "3.0 kOhm"
        capacitor = design.add_instance(("ads_rflib", "C", "symbol"), (2, 0), name="C1", angle=-90)
        capacitor.parameters["C"].value = "1.0 uF"
        design.add_instance(("ads_rflib", "GROUND", "symbol"), (-2, -1), name="G1", angle=-90)
        design.add_instance(("ads_rflib", "GROUND", "symbol"), (2, -1), name="G2", angle=-90)
        design.add_wire([(-2.0, 0.0), (0.0, 0.0)])
        wire = design.add_wire([(1.0, 0.0), (2.0, 0.0)])
        wire.add_wire_label("R1_v")
        controller = design.add_instance(("ads_simulation", "AC", "symbol"), (-4, 1), name="AC1")
        controller.parameters["Start"].value = "1.0 Hz"
        controller.parameters["Stop"].value = "1.0 MHz"
        controller.parameters["Dec"].value = "5"
        controller.parameters["Step"].value = ""
        design.save_design()

        netlist = design.generate_netlist()
        netlist_dir = workspace / "agent-output" / "netlists"
        netlist_dir.mkdir(parents=True, exist_ok=True)
        netlist_path = netlist_dir / "MinimalAC.net"
        netlist_path.write_text(netlist, encoding="utf-8")
        output_dir = workspace / "agent-output" / "minimal-ac"
        output_dir.mkdir(parents=True)

        started = time.monotonic()
        result = ads.CircuitSimulator().run_netlist(netlist, output_dir=str(output_dir))
        datasets = sorted(output_dir.glob("*.ds"), key=lambda item: item.stat().st_mtime, reverse=True)
        dataset_path = datasets[0] if datasets else output_dir / "cell.ds"
        summary = summarize_dataset(dataset_path) if dataset_path.exists() else {}
        record.update(summary)
        record.update(
            {
                "ok": dataset_path.exists() and summary.get("rows", 0) >= 5 and "R1_v" in summary.get("columns", []),
                "top_design": "AgentBridgeExamples_lib:MinimalAC:schematic",
                "netlist_path": str(netlist_path),
                "netlist_lines": len(netlist.splitlines()),
                "run_result": repr(result),
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "dataset_exists": dataset_path.exists(),
            }
        )
    except Exception as exc:
        record.update({"error": repr(exc), "traceback": traceback.format_exc()})
    finally:
        if de.workspace_is_open():
            de.close_workspace()
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.workspace.expanduser().resolve())
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
