from pathlib import Path

from ads_agent_bridge.examples import list_examples, run_example
from test_discovery import make_ads_root


def test_public_catalog_contains_exactly_five_examples() -> None:
    payload = list_examples()

    assert payload["count"] == 5
    assert [item["name"] for item in payload["examples"]] == [
        "discover-installations",
        "headless-minimal-ac",
        "live-de-context",
        "dds-dataset-readback",
        "bounded-ael-workspace",
    ]
    assert all(item["evidence"] for item in payload["examples"])
    assert all(item["requires"] for item in payload["examples"])


def test_discovery_example_is_read_only_and_version_specific(tmp_path: Path) -> None:
    root = make_ads_root(tmp_path / "install", "ADS2025_Update2")

    payload, code = run_example("discover-installations", ads_roots=[root])

    assert code == 0
    assert payload["status"] == "passed"
    assert payload["read_only"] is True
    assert payload["instances"][0]["product_version"] == "ADS 2025 Update 2"
