"""Isolated ADS-Python worker for one governed official program."""

from __future__ import annotations

import argparse
import builtins
import json
import traceback
from pathlib import Path
from types import SimpleNamespace

import keysight.ads.de as de
from keysight.ads.de import db_uu as db

_ALLOWED_IMPORTS = (
    "keysight.ads.dataset",
    "keysight.ads.de",
    "keysight.ads.dds",
    "keysight.edatoolbox",
    "json",
    "math",
)
_SAFE_BUILTINS = {
    name: getattr(builtins, name)
    for name in (
        "Exception",
        "RuntimeError",
        "ValueError",
        "abs",
        "all",
        "any",
        "bool",
        "complex",
        "dict",
        "dir",
        "enumerate",
        "float",
        "getattr",
        "hasattr",
        "int",
        "isinstance",
        "len",
        "list",
        "max",
        "min",
        "range",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "repr",
        "zip",
    )
}


def _controlled_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or not any(
        name == prefix or name.startswith(prefix + ".") for prefix in _ALLOWED_IMPORTS
    ):
        raise ImportError(f"native batch import is outside the ADS runtime: {name}")
    return builtins.__import__(name, globals, locals, fromlist, level)


def execute(invocation: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {"ok": False}
    try:
        program = invocation["program"]
        entrypoint = str(invocation["entrypoint"])
        source = str(program["source"])
        namespace = {
            "__builtins__": {**_SAFE_BUILTINS, "__import__": _controlled_import}
        }
        exec(compile(source, "<ads-native-batch>", "exec"), namespace, namespace)
        function = namespace.get(entrypoint)
        if not callable(function):
            raise ValueError(f"native batch did not define callable {entrypoint}")
        value = function(SimpleNamespace(de=de, db=db), dict(invocation["context"]))
        if not isinstance(value, dict):
            raise TypeError(f"native batch {entrypoint} must return an object")
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, allow_nan=False
        ).encode("utf-8")
        if len(encoded) > int(invocation["max_output_bytes"]):
            raise ValueError("native batch result exceeds max_output_bytes")
        result.update({"ok": True, "result": value})
    except Exception as exc:
        result.update({"error": repr(exc), "traceback": traceback.format_exc()})
    finally:
        if de.workspace_is_open():
            de.close_workspace()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--invocation", type=Path, required=True)
    args = parser.parse_args()
    invocation = json.loads(args.invocation.read_text(encoding="utf-8"))
    result = execute(invocation)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
