"""Source-only descriptions from the selected ADS installation."""

from pathlib import Path

from eda_bridge_runtime.source_symbols import describe_symbols


def describe(instance, query, limit=6):
    base = Path(instance.install_root) / "tools" / "python"
    roots = [base / "packages" / "keysight", base / "Lib" / "site-packages" / "keysight"]
    roots.extend(base.glob("lib/python*/site-packages/keysight"))
    return describe_symbols(roots, query, version=instance.product_version, limit=limit)
