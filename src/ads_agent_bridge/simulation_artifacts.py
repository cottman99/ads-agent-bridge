"""Filesystem-only helpers shared with the standalone ADS simulation worker."""

from __future__ import annotations

from pathlib import Path


def accept_dataset_artifact(
    output: Path, detected: Path, dataset_name: str | None
) -> Path:
    """Give a simulator-selected dataset a deterministic accepted filename."""

    if not dataset_name:
        return detected
    accepted = output / dataset_name
    if accepted == detected:
        return detected
    if accepted.exists():
        raise FileExistsError(
            f"requested accepted dataset already exists: {accepted.name}"
        )
    detected.replace(accepted)
    return accepted
