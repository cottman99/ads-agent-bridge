"""Standalone ADS Python entry point for one empty, reopenable workspace."""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from keysight.ads import de
from keysight.ads.de import db_uu as db


def run(workspace: Path, library: str, cell: str) -> dict[str, object]:
    result: dict[str, object] = {"ok": False, "workspace": str(workspace)}
    try:
        if workspace.exists():
            raise FileExistsError(
                f"Refusing to overwrite an existing workspace: {workspace}"
            )
        workspace.parent.mkdir(parents=True, exist_ok=True)
        de.create_workspace(workspace)
        de.open_workspace(workspace)
        library_path = workspace / library
        de.create_new_library(library, library_path)
        de.active_workspace().add_library(
            library, library_path, de.LibraryMode.NON_SHARED
        )
        design_name = f"{library}:{cell}:schematic"
        design = db.create_schematic(design_name)
        design.save_design()
        result.update({"ok": True, "top_design": design_name})
    except Exception as exc:  # noqa: BLE001 - standalone process reports ADS API failures
        result.update({"error": repr(exc), "traceback": traceback.format_exc()})
    finally:
        if de.workspace_is_open():
            de.close_workspace()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--library", required=True)
    parser.add_argument("--cell", required=True)
    args = parser.parse_args()
    result = run(args.workspace.expanduser().resolve(), args.library, args.cell)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
