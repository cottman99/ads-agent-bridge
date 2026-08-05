from __future__ import annotations

from .models import AdsInstance


def support_tier(year: int | None, update: str | None) -> str:
    if year is None:
        return "unknown"
    if year >= 2025:
        return "stable"
    if year == 2024:
        try:
            update_number = float(update or "0")
        except ValueError:
            update_number = 0
        return "preview" if update_number >= 2 else "experimental"
    if year == 2023 and update and update.startswith("2"):
        return "experimental"
    return "unsupported"


def explain(instance: AdsInstance) -> dict[str, object]:
    capabilities = instance.capabilities
    ready = sorted(key for key, value in capabilities.items() if value is True or value == "available")
    unavailable = sorted(key for key, value in capabilities.items() if value is False or value == "unavailable")
    notes: list[str] = []
    if instance.support_tier == "stable":
        notes.append("Stable support target. Individual features still require runtime capability probes.")
    elif instance.support_tier == "preview":
        notes.append("Preview support: ADS Python APIs in this generation were still evolving.")
    elif instance.support_tier == "experimental":
        notes.append("Experimental support: installation and docs are usable, but live automation may need a legacy adapter.")
    else:
        notes.append("No live bridge support promise for this ADS generation.")
    return {
        "instance_id": instance.instance_id,
        "product_version": instance.product_version,
        "support": instance.support_tier,
        "ready_by_probe": ready,
        "unavailable_by_probe": unavailable,
        "notes": notes,
    }
