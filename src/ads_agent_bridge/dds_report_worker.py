"""ADS-Python worker for a validated DDS report plan."""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from keysight.ads import dds


def run(plan: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {"ok": False}
    try:
        workspace = Path(str(plan["workspace"])).resolve()
        dataset = Path(str(plan["dataset"])).resolve()
        output = Path(str(plan["output_file"])).resolve()
        dds.init_dds_path(workspace)
        dds_file = dds.new_dds_file(dataset, workspace)
        dds_file.add_dataset_alias("agent_dataset", str(dataset))
        page = dds_file.pages[0]
        page.name = str(plan["page"])
        equation_status = {}
        for item in plan.get("equations", []):
            equation = page.add_equation(item["name"], item["expression"])
            equation_status[item["name"]] = equation.status
            if equation.status != "Valid":
                raise RuntimeError(f"DDS equation {item['name']} is not valid: {equation.status}")
        plot_names = []
        for item in plan["plots"]:
            left, top, width, height = item["rect"]
            page.add_plot(
                dds.Rect(left=left, top=top, width=width, height=height),
                item["traces"],
                item["name"],
            )
            plot_names.append(str(item["name"]))
        dds_file.save(output.name, workspace)
        if not output.is_file():
            raise RuntimeError("DDS save returned without the requested output file")
        reopened = dds.open_dds_file(output)
        reopened_page = reopened.pages[0]
        if str(reopened_page.name) != str(plan["page"]):
            raise RuntimeError(
                f"fresh-reopen DDS page mismatch: {reopened_page.name!r}"
            )
        result.update(
            {
                "ok": True,
                "readback": {
                    "page": page.name,
                    "equations": equation_status,
                    "plots": plot_names,
                    "dataset_aliases": dict(dds_file.dataset_aliases),
                    "fresh_reopen": True,
                },
            }
        )
    except Exception as exc:
        result.update({"error": repr(exc), "traceback": traceback.format_exc()})
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
