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
        page_plans = plan.get("pages") or [
            {
                "name": plan["page"],
                "equations": plan.get("equations", []),
                "plots": plan["plots"],
            }
        ]
        page_records = []
        for index, page_plan in enumerate(page_plans):
            page = (
                dds_file.pages[0]
                if index == 0
                else dds_file.new_page(page_plan["name"])
            )
            page.name = str(page_plan["name"])
            equation_status = {}
            for item in page_plan.get("equations", []):
                equation = page.add_equation(item["name"], item["expression"])
                equation_status[item["name"]] = equation.status
                if equation.status != "Valid":
                    raise RuntimeError(
                        f"DDS equation {item['name']} is not valid: {equation.status}"
                    )
            plot_records = []
            for item in page_plan["plots"]:
                left, top, width, height = item["rect"]
                location = dds.Rect(left=left, top=top, width=width, height=height)
                kind = item.get("kind", "rectangular")
                if kind == "polar":
                    page.add_polar_plot(location, item["traces"], item["name"])
                else:
                    page.add_plot(location, item["traces"], item["name"])
                plot_records.append({"name": str(item["name"]), "kind": kind})
            page_records.append(
                {
                    "page": page.name,
                    "equations": equation_status,
                    "plots": plot_records,
                }
            )
        dds_file.save(output.name, workspace)
        if not output.is_file():
            raise RuntimeError("DDS save returned without the requested output file")
        reopened = dds.open_dds_file(output)
        expected_pages = [str(item["name"]) for item in page_plans]
        reopened_pages = [str(item.name) for item in reopened.pages]
        if reopened_pages != expected_pages:
            raise RuntimeError(f"fresh-reopen DDS pages mismatch: {reopened_pages!r}")
        readback = {
            "pages": page_records,
            "page_count": len(page_records),
            "dataset_aliases": dict(dds_file.dataset_aliases),
            "fresh_reopen": True,
        }
        if plan.get("schema_version") == "ads.dds-report/v1":
            readback.update(
                {
                    "page": page_records[0]["page"],
                    "equations": page_records[0]["equations"],
                    "plots": [item["name"] for item in page_records[0]["plots"]],
                }
            )
        result.update(
            {
                "ok": True,
                "readback": readback,
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
