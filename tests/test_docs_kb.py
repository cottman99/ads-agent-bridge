from pathlib import Path

from ads_agent_bridge.docs_kb import ensure_fast_index, query
from ads_agent_bridge.models import AdsInstance


def test_fast_index_and_query(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "workspace.html").write_text(
        "<html><head><title>Create Workspace</title></head><body><h1>create_workspace</h1><p>Open and create an ADS workspace.</p></body></html>",
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id: cache)
    cache.mkdir()
    instance = AdsInstance(
        instance_id="ads-2025-test",
        install_root=str(tmp_path),
        product_version="ADS 2025",
        year=2025,
        update=None,
        platform="test",
        support_tier="stable",
        docs_roots={"python": [str(docs)]},
    )
    built = ensure_fast_index(instance)
    assert built["indexed_file_count"] == 1
    assert built["reused"] is False
    assert ensure_fast_index(instance)["reused"] is True
    result = query(instance, "create_workspace")
    assert result["results"][0]["title"] == "Create Workspace"
    assert result["results"][0]["source_path"].endswith("workspace.html")
