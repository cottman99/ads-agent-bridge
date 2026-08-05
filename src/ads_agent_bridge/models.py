from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AdsInstance:
    instance_id: str
    install_root: str
    product_version: str
    year: int | None
    update: str | None
    platform: str
    support_tier: str
    executable: str | None = None
    python_executable: str | None = None
    docs_roots: dict[str, list[str]] = field(default_factory=dict)
    capabilities: dict[str, str | bool] = field(default_factory=dict)

    @property
    def root(self) -> Path:
        return Path(self.install_root)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AdsInstance":
        return cls(**payload)
