from pathlib import Path

from ads_agent_bridge.docs_kb import build_full_index, ensure_fast_index, query, status
from ads_agent_bridge.models import AdsInstance


def test_fast_index_and_query(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "workspace.html").write_text(
        "<html><head><title>Create Workspace</title></head><body><h1>create_workspace</h1><p>Open and create an ADS workspace.</p></body></html>",
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache)
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


def test_full_index_writes_private_markdown_and_enriches_query(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "installed-docs"
    docs.mkdir()
    (docs / "api.html").write_text(
        "<html><head><title>Hidden API</title></head><body><h1>rare_full_text_token</h1><p>Version-specific detail.</p></body></html>",
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache)
    instance = AdsInstance(
        instance_id="ads-2026-u1-test",
        install_root=str(tmp_path),
        product_version="ADS 2026 Update 1",
        year=2026,
        update="1",
        platform="test",
        support_tier="stable",
        docs_roots={"python": [str(docs)]},
    )

    built = build_full_index(instance)
    result = query(instance, "rare_full_text_token")

    assert built["status"] == "ready"
    assert built["enriched_file_count"] == 1
    markdown_path = Path(result["results"][0]["markdown_path"])
    assert markdown_path.is_file()
    assert "rare_full_text_token" in markdown_path.read_text(encoding="utf-8")
    assert status(instance)["enrichment_status"] == "ready"
