"""ADS-Python worker for a validated circuit simulation plan."""

from __future__ import annotations

import argparse
import json
import math
import time
import traceback
from pathlib import Path

import keysight.ads.dataset as dataset
import keysight.ads.de as de
from keysight.ads.de import db_uu as db
from keysight.edatoolbox import ads

try:
    from .simulation_artifacts import accept_dataset_artifact
except ImportError:  # Executed by ADS Python as a standalone file.
    from simulation_artifacts import accept_dataset_artifact


def _finite(value) -> bool:
    if isinstance(value, complex):
        return math.isfinite(value.real) and math.isfinite(value.imag)
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def run(plan: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {"ok": False}
    try:
        workspace = Path(str(plan["workspace"])).resolve()
        output = Path(str(plan["output_directory"])).resolve()
        de.open_workspace(workspace)
        design = db.open_design(str(plan["design"]), de.db.DesignMode.READ_ONLY)
        netlist = design.generate_netlist()
        de.close_workspace()
        output.mkdir(parents=False)
        netlist_path = output / "simulation.net"
        netlist_path.write_text(netlist, encoding="utf-8")
        started = time.monotonic()
        run_result = ads.CircuitSimulator().run_netlist(netlist, output_dir=str(output))
        datasets = sorted(
            output.glob("*.ds"), key=lambda item: item.stat().st_mtime, reverse=True
        )
        if not datasets:
            raise RuntimeError("simulation completed without a dataset")
        dataset_path = accept_dataset_artifact(
            output,
            datasets[0],
            str(plan["dataset_name"]) if plan.get("dataset_name") else None,
        )
        assertions = plan["assertions"]
        frames = []
        with dataset.open(dataset_path) as data:
            for varblock in data.varblock_names:
                frame = data[varblock].to_dataframe().reset_index()
                frames.append((str(varblock), frame))
        if not frames:
            raise RuntimeError("dataset contains no variable blocks")
        selected_name, selected = max(frames, key=lambda item: len(item[1]))
        columns = [str(column) for column in selected.columns]
        rows = int(len(selected))
        missing = [
            name for name in assertions["required_columns"] if name not in columns
        ]
        if missing:
            raise RuntimeError(
                "dataset is missing required columns: " + ", ".join(missing)
            )
        if rows < assertions["minimum_rows"]:
            raise RuntimeError(
                f"dataset has {rows} rows; expected at least {assertions['minimum_rows']}"
            )
        nonfinite = []
        for name in assertions["finite_columns"]:
            if name not in columns or not all(
                _finite(value) for value in selected[name]
            ):
                nonfinite.append(name)
        if nonfinite:
            raise RuntimeError(
                "dataset has non-finite columns: " + ", ".join(nonfinite)
            )
        csv_path = output / "dataset.csv"
        selected.to_csv(csv_path, index=False)
        result.update(
            {
                "ok": True,
                "readback": {
                    "varblock": selected_name,
                    "varblocks": [name for name, _frame in frames],
                    "rows": rows,
                    "columns": columns,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "run_result": repr(run_result),
                },
                "artifacts": {
                    "netlist": str(netlist_path),
                    "dataset": str(dataset_path),
                    "csv": str(csv_path),
                },
            }
        )
    except Exception as exc:
        result.update({"error": repr(exc), "traceback": traceback.format_exc()})
    finally:
        if de.workspace_is_open():
            de.close_workspace()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    result = run(plan)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
