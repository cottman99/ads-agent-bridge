"""Isolated ADS Python runner; execution semantics come from Runtime."""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from types import SimpleNamespace

from eda_bridge_runtime.admission import assert_admission
from eda_bridge_runtime.errors import error_facts
from eda_bridge_runtime.python_execution import execute_python


def execute(invocation: dict) -> dict:
    de = None
    try:
        assert_admission(invocation["admission"])
        from keysight.ads import ael, de
        from keysight.ads.de import db_uu as db

        api = SimpleNamespace(de=de, db=db, ael=ael)
        if invocation["context"]["profile"] == "dds":
            from keysight.ads import dds

            api.dds = dds
        result = execute_python(
            invocation["program"],
            api,
            invocation["context"],
            entrypoint=invocation["entrypoint"],
            max_output_bytes=invocation["max_output_bytes"],
        )
        return {"ok": True, "result": result}
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            **error_facts(exc),
            "traceback": traceback.format_exc(),
        }
    finally:
        if de is not None and de.workspace_is_open():
            de.close_workspace()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--invocation", type=Path, required=True)
    args = parser.parse_args()
    result = execute(json.loads(args.invocation.read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
