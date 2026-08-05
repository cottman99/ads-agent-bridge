from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def local_digests(dist_dir: Path) -> dict[str, str]:
    paths = sorted([*dist_dir.glob("*.whl"), *dist_dir.glob("*.tar.gz")])
    if not paths:
        raise ValueError(f"No wheel or source distribution found in {dist_dir}")
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def compare_digests(local: dict[str, str], payload: dict[str, object]) -> dict[str, object]:
    remote = {
        str(item["filename"]): str(item["digests"]["sha256"])
        for item in payload.get("urls", [])
        if isinstance(item, dict) and isinstance(item.get("digests"), dict)
    }
    missing = sorted(set(local) - set(remote))
    mismatched = {
        name: {"local": digest, "pypi": remote[name]}
        for name, digest in local.items()
        if name in remote and remote[name] != digest
    }
    return {"ok": not missing and not mismatched, "local": local, "pypi": remote, "missing": missing, "mismatched": mismatched}


def fetch_payload(project: str, version: str, timeout: float) -> dict[str, object]:
    project_part = urllib.parse.quote(project, safe="")
    version_part = urllib.parse.quote(version, safe="")
    url = f"https://pypi.org/pypi/{project_part}/{version_part}/json"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify that PyPI received the exact CI-built distributions.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()

    local = local_digests(args.dist_dir)
    last_error = None
    for attempt in range(1, args.attempts + 1):
        try:
            result = compare_digests(local, fetch_payload(args.project, args.version, args.timeout))
        except (OSError, ValueError, urllib.error.HTTPError, urllib.error.URLError) as exc:
            last_error = str(exc)
        else:
            if result["ok"]:
                print(json.dumps({"attempt": attempt, **result}, indent=2))
                return 0
            last_error = json.dumps(result, sort_keys=True)
        if attempt < args.attempts:
            time.sleep(args.interval)
    raise SystemExit(f"PyPI artifact verification failed after {args.attempts} attempts: {last_error}")


if __name__ == "__main__":
    raise SystemExit(main())
