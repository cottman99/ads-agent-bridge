from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
from pathlib import Path
from typing import Iterable

from .compatibility import support_tier
from .models import AdsInstance


VERSION_PATTERN = re.compile(
    r"ADS[_ -]?(?P<year>20\d{2})(?:[_ .-]*(?:Update|U)[_ .-]?(?P<update>\d+(?:\.\d+)?))?",
    re.IGNORECASE,
)


def _unique_existing(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue
        key = os.path.normcase(str(resolved))
        if resolved.is_dir() and key not in seen:
            seen.add(key)
            result.append(resolved)
    return result


def candidate_roots(explicit: Iterable[Path] = (), search_roots: Iterable[Path] = ()) -> list[Path]:
    explicit_roots = list(explicit)
    if explicit_roots:
        return _unique_existing(explicit_roots)

    direct: list[Path] = []
    for name in ("HPEESOF_DIR", "ADS_ROOT"):
        value = os.environ.get(name)
        if value:
            direct.append(Path(value))

    for executable_name in ("hpeesofde", "hpeesofde.exe", "hpeesofemx", "hpeesofemx.exe", "ads"):
        found = shutil.which(executable_name)
        if found:
            executable = Path(found).resolve()
            direct.append(executable.parent.parent if executable.parent.name.lower() == "bin" else executable.parent)

    system = platform.system().lower()
    parents = list(search_roots)
    if system == "windows":
        for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
            value = os.environ.get(env_name)
            if value:
                parents.append(Path(value) / "Keysight")
        parents.append(Path("C:/Keysight"))
    else:
        parents.extend([Path("/opt/Keysight"), Path("/usr/local/Keysight"), Path.home() / "Keysight"])

    for parent in _unique_existing(parents):
        direct.append(parent)
        try:
            direct.extend(child for child in parent.iterdir() if child.is_dir() and "ads" in child.name.lower())
        except OSError:
            continue
    return _unique_existing(direct)


def _find_first(root: Path, relatives: Iterable[str]) -> Path | None:
    for relative in relatives:
        candidate = root / relative
        if candidate.is_file():
            return candidate.resolve()
    return None


def _find_python(root: Path) -> Path | None:
    exact = _find_first(
        root,
        ("tools/python/python.exe", "tools/python/bin/python", "tools/python/python", "bin/python.exe", "bin/python"),
    )
    if exact:
        return exact
    python_bin = root / "tools" / "python" / "bin"
    if python_bin.is_dir():
        for candidate in sorted(python_bin.glob("python3*"), reverse=True):
            if candidate.is_file() and not candidate.name.endswith("-config") and re.fullmatch(r"python3(?:\.\d+)?", candidate.name):
                return candidate.resolve()
    return None


def _html_root(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        return next(path.rglob("*.html"), None) is not None
    except OSError:
        return False


def locate_docs(root: Path) -> dict[str, list[str]]:
    candidates = {
        "ads": [root / "doc" / "ads", root / "doc" / "ads_html", root / "docs" / "ads", root / "help" / "ads"],
        "python": [
            root / "doc" / "python_api",
            root / "de" / "python" / "docs" / "html",
            root / "de" / "python" / "docs",
        ],
        "dds": [root / "dds" / "python" / "docs" / "html", root / "dds" / "python" / "docs"],
    }
    found: dict[str, list[str]] = {}
    seen: set[str] = set()
    for domain, paths in candidates.items():
        matches = []
        for path in paths:
            if not _html_root(path):
                continue
            key = os.path.normcase(str(path.resolve()))
            if key not in seen:
                seen.add(key)
                matches.append(str(path.resolve()))
        if matches:
            found[domain] = matches

    python_parent = root / "doc" / "python"
    python_children_found = False
    if python_parent.is_dir():
        for child in sorted(python_parent.iterdir()):
            if not child.is_dir():
                continue
            candidate = child / "html" if _html_root(child / "html") else child
            if not _html_root(candidate):
                continue
            python_children_found = True
            domain = "dds" if child.name.lower() == "dds" else "ael" if child.name.lower() == "ael" else "python"
            key = os.path.normcase(str(candidate.resolve()))
            if key not in seen:
                seen.add(key)
                found.setdefault(domain, []).append(str(candidate.resolve()))
        if not python_children_found and _html_root(python_parent):
            key = os.path.normcase(str(python_parent.resolve()))
            if key not in seen:
                seen.add(key)
                found.setdefault("python", []).append(str(python_parent.resolve()))

    ads_root = root / "doc" / "ads"
    if ads_root.is_dir():
        for path in ads_root.glob("Content/*/pythonapi"):
            if _html_root(path):
                key = os.path.normcase(str(path.resolve()))
                if key not in seen:
                    seen.add(key)
                    found.setdefault("python", []).append(str(path.resolve()))
    return found


def parse_version(root: Path) -> tuple[int | None, str | None, str]:
    texts = [root.name]
    for name in ("version.txt", "product.version", "VERSION"):
        path = root / name
        if path.is_file():
            try:
                texts.append(path.read_text(encoding="utf-8", errors="ignore")[:500])
            except OSError:
                pass
    for text in texts:
        match = VERSION_PATTERN.search(text)
        if match:
            year = int(match.group("year"))
            update = match.group("update")
            label = f"ADS {year}" + (f" Update {update}" if update else "")
            return year, update, label
    return None, None, root.name


def inspect_root(root: Path) -> AdsInstance | None:
    executable = _find_first(
        root,
        ("bin/hpeesofde.exe", "bin/hpeesofde", "bin/hpeesofemx.exe", "bin/hpeesofemx", "hpeesofde.exe", "hpeesofde"),
    )
    python_executable = _find_python(root)
    docs_roots = locate_docs(root)
    if not executable and not python_executable and not docs_roots:
        return None
    year, update, label = parse_version(root)
    root_hash = hashlib.sha256(os.path.normcase(str(root.resolve())).encode("utf-8")).hexdigest()[:8]
    version_slug = f"ads-{year}" if year else "ads-unknown"
    if update:
        version_slug += f"-u{update.replace('.', '-') }"
    capabilities: dict[str, str | bool] = {
        "local_docs": bool(docs_roots),
        "embedded_python": python_executable is not None,
        "de_docs": bool(docs_roots.get("python")),
        "dds_docs": bool(docs_roots.get("dds")),
    }
    if year is not None:
        capabilities["de_python_generation"] = "available" if year >= 2023 else "unavailable"
        capabilities["python_addon_generation"] = "available" if year >= 2025 or (year == 2024 and float(update or 0) >= 2) else "unavailable"
        capabilities["dds_python_generation"] = "available" if year >= 2026 else "preview" if year == 2025 else "unavailable"
    return AdsInstance(
        instance_id=f"{version_slug}-{root_hash}",
        install_root=str(root.resolve()),
        product_version=label,
        year=year,
        update=update,
        platform=platform.system() or "unknown",
        support_tier=support_tier(year, update),
        executable=str(executable) if executable else None,
        python_executable=str(python_executable) if python_executable else None,
        docs_roots=docs_roots,
        capabilities=capabilities,
    )


def discover(explicit: Iterable[Path] = (), search_roots: Iterable[Path] = ()) -> list[AdsInstance]:
    instances: list[AdsInstance] = []
    seen: set[str] = set()
    for candidate in candidate_roots(explicit, search_roots):
        instance = inspect_root(candidate)
        if instance and instance.instance_id not in seen:
            seen.add(instance.instance_id)
            instances.append(instance)
    return sorted(instances, key=lambda item: (item.year or 0, item.update or "", item.install_root), reverse=True)
