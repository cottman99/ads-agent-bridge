"""Create a DDS file and validate an ADS dataset through an equation.

Set ``WORKSPACE`` and ``DATASET`` in the DDS bridge namespace before running.
The final stdout line is a JSON acceptance record. This intentionally avoids
adding a plot, because raw complex data can open an interactive chooser.
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path

from keysight.ads import dds


def json_safe(value):
    if isinstance(value, complex):
        return {"real": value.real, "imag": value.imag}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    return repr(value)


def main() -> dict:
    record = {"ok": False}
    try:
        workspace = Path(globals()["WORKSPACE"]).resolve()
        dataset_path = Path(globals()["DATASET"]).resolve()
        if not dataset_path.is_file():
            raise FileNotFoundError(dataset_path)
        dds.init_dds_path(workspace)
        dds_file = dds.new_dds_file(dataset_path, workspace)
        dds_file.add_dataset_alias("minimal_ac", str(dataset_path))
        page = dds_file.pages[0]
        page.name = "Minimal AC dataset"
        equation = page.add_equation("node_voltage", "R1_v")
        values = equation.variable.to_dataframe().values.tolist()
        dds_name = "minimal_ac_readback.dds"
        dds_path = workspace / dds_name
        dds_file.save(dds_name, workspace)
        record.update(
            {
                "ok": equation.status == "Valid" and len(values) > 0 and dds_path.is_file(),
                "workspace": str(workspace),
                "dataset_path": str(dataset_path),
                "dds_path": str(dds_path),
                "dds_exists": dds_path.is_file(),
                "equation": equation.expression,
                "equation_status": equation.status,
                "row_count": len(values),
                "values_preview": json_safe(values[:3]),
                "dataset_aliases": dict(dds_file.dataset_aliases),
                "is_dds_app": bool(dds.is_dds_app()),
            }
        )
    except Exception as exc:
        record.update({"error": repr(exc), "traceback": traceback.format_exc()})
    return record


print(json.dumps(main(), ensure_ascii=False))
