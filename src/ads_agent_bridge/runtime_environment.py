"""Platform-aware environment for ADS bundled Python processes."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path


def ads_runtime_environment(
    install_root: str | Path,
    *,
    environment: Mapping[str, str] | None = None,
    platform_name: str | None = None,
) -> dict[str, str]:
    """Build one shared ADS Python environment for every public execution lane."""
    result = dict(os.environ if environment is None else environment)
    root = Path(install_root)
    result["HPEESOF_DIR"] = str(root)
    result["PATH"] = str(root / "bin") + os.pathsep + result.get("PATH", "")
    if (platform_name or sys.platform).casefold().startswith("linux"):
        libraries = [
            root / "bin" / "plugins" / "pde_core",
            root / "tools" / "python" / "lib",
            root / "tools" / "python" / "lib64",
            root / "lib" / "linux_x86_64",
            root / "lib" / "linux_x86",
        ]
        values = [str(path) for path in libraries]
        if result.get("LD_LIBRARY_PATH"):
            values.append(result["LD_LIBRARY_PATH"])
        result["LD_LIBRARY_PATH"] = os.pathsep.join(values)
    return result
