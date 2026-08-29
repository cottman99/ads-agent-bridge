"""ADS-Python worker for one validated structured schematic plan."""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

import keysight.ads.de as de
from keysight.ads.de import db_uu as db


def _instance_names(design) -> list[str]:
    return sorted(str(instance.name) for instance in design.instances)


def run(workspace: Path, plan: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {"ok": False}
    try:
        de.open_workspace(workspace)
        design = db.open_design(str(plan["design"]), de.db.DesignMode.WRITE)
        before = _instance_names(design)
        expected_before = list(
            (plan.get("expected_before") or {}).get("instance_names", [])
        )
        if before != sorted(expected_before):
            raise RuntimeError(
                f"expected_before mismatch: expected {sorted(expected_before)!r}, got {before!r}"
            )
        with de.db.Transaction(
            design, "EDA Bridge structured design apply"
        ) as transaction:
            for operation in plan["operations"]:
                if operation["op"] == "add_instance":
                    kwargs = {"name": operation["name"]}
                    if "angle" in operation:
                        kwargs["angle"] = operation["angle"]
                    instance = design.add_instance(
                        tuple(operation["item"]), tuple(operation["at"]), **kwargs
                    )
                    for name, value in operation.get("parameters", {}).items():
                        instance.parameters[name].value = value
                else:
                    wire = design.add_wire(
                        [tuple(point) for point in operation["points"]]
                    )
                    if operation.get("label"):
                        wire.add_wire_label(operation["label"])
            transaction.commit()
        design.save_design()
        de.close_workspace()

        de.open_workspace(workspace)
        design = db.open_design(str(plan["design"]), de.db.DesignMode.READ_ONLY)
        names = _instance_names(design)
        assertions = plan.get("assertions") or {}
        expected_names = sorted(assertions.get("instance_names", []))
        if expected_names and names != expected_names:
            raise RuntimeError(
                f"fresh-reopen instance mismatch: expected {expected_names!r}, got {names!r}"
            )
        parameter_values: list[dict[str, str]] = []
        for expected in assertions.get("parameters", []):
            actual = str(
                design.instances[expected["instance"]]
                .parameters[expected["parameter"]]
                .value
            )
            if actual != expected["value"]:
                raise RuntimeError(
                    f"fresh-reopen parameter mismatch for {expected['instance']}.{expected['parameter']}"
                )
            parameter_values.append({**expected, "actual": actual})
        netlist = design.generate_netlist()
        for needle in assertions.get("netlist_contains", []):
            if needle not in netlist:
                raise RuntimeError(
                    f"fresh-reopen netlist is missing required text: {needle}"
                )
        result.update(
            {
                "ok": True,
                "readback": {
                    "instance_count": len(names),
                    "instance_names": names,
                    "parameters": parameter_values,
                    "netlist_lines": len(netlist.splitlines()),
                    "assertion_count": len(expected_names)
                    + len(parameter_values)
                    + len(assertions.get("netlist_contains", [])),
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
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    result = run(args.workspace.expanduser().resolve(), plan)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
