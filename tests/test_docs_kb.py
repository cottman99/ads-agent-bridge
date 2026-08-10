import json
import os
import sqlite3
from pathlib import Path

from ads_agent_bridge.docs_kb import _context_excerpt, _markdown_record, build_full_index, ensure_fast_index, query, status
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


def test_query_rebuilds_stale_index_schema(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "workspace.html").write_text(
        "<html><head><title>Workspace</title></head><body><main>workspace</main></body></html>",
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache)
    instance = AdsInstance(
        instance_id="ads-2027-stale-schema-test",
        install_root=str(tmp_path),
        product_version="ADS 2027",
        year=2027,
        update=None,
        platform="test",
        support_tier="stable",
        docs_roots={"python": [str(docs)]},
    )
    ensure_fast_index(instance)
    manifest_path = cache / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = 2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert status(instance)["status"] == "stale"
    result = query(instance, "workspace")

    assert result["results"][0]["relative_path"] == "workspace.html"
    assert status(instance)["schema_version"] == 3
    assert status(instance)["status"] == "ready"


def test_multi_term_query_does_not_return_domain_only_match(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "workspace.html").write_text("<html><title>Workspace</title></html>", encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache)
    instance = AdsInstance(
        instance_id="ads-2026-test",
        install_root=str(tmp_path),
        product_version="ADS 2026",
        year=2026,
        update=None,
        platform="test",
        support_tier="stable",
        docs_roots={"python": [str(docs)]},
    )
    ensure_fast_index(instance)
    fallback_calls = []
    monkeypatch.setattr("ads_agent_bridge.docs_kb._query_source_fallback", lambda *_args, **_kwargs: fallback_calls.append(1) or [])

    result = query(instance, "python term_that_is_not_indexed")

    assert result["search_mode"] == "source_fallback_bounded"
    assert result["results"] == []
    assert fallback_calls == [1]
    assert result["enrichment_status"] == "not_started"


def test_sphinx_main_content_excludes_navigation_and_private_glyphs(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    page = docs / "Design.html"
    page.write_text(
        """
        <html><head><title>Design — ADS 2027 documentation</title></head><body>
          <nav>Global navigation and theme controls</nav>
          <div id="ks-content">
            <div class="wy-breadcrumbs">Python API / Design</div>
            <h1>Design<a class="headerlink">\uf0c1</a></h1>
            <p>Use <code>add_rectangle</code> to add geometry.</p>
            <div class="rst-footer-buttons">Previous Next</div>
          </div>
          <footer>Privacy Terms Feedback</footer>
        </body></html>
        """,
        encoding="utf-8",
    )

    title, markdown = _markdown_record("python", docs, page)

    assert title == "Design"
    assert markdown.count("# Design") == 1
    assert "add_rectangle" in markdown
    assert "Global navigation" not in markdown
    assert "Previous Next" not in markdown
    assert "Privacy Terms Feedback" not in markdown
    assert "\uf0c1" not in markdown
    assert len(markdown) < 500


def test_visible_h1_replaces_dds_product_build_title(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    page = docs / "index.html"
    page.write_text(
        "<html><head><title>Index — DDS Python Documentation Advanced Design System 2027 (650) documentation</title>"
        "</head><body><main><h1>Index</h1><p>DDS API landing page.</p></main></body></html>",
        encoding="utf-8",
    )

    title, markdown = _markdown_record("dds", docs, page)

    assert title == "Index"
    assert markdown.count("# Index") == 1
    assert "Advanced Design System" not in markdown


def test_visible_h1_replaces_dataset_package_title(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    page = docs / "api.html"
    page.write_text(
        "<html><head><title>API Reference — keysight-ads-dataset Advanced Design System 2027 (650) documentation</title>"
        "</head><body><main><h1>API Reference</h1><p>Dataset package symbols.</p></main></body></html>",
        encoding="utf-8",
    )

    title, markdown = _markdown_record("python", docs, page)

    assert title == "API Reference"
    assert markdown.count("# API Reference") == 1
    assert "keysight-ads-dataset Advanced Design System" not in markdown


def test_heading_only_page_does_not_repeat_canonical_title(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    page = docs / "heading-only.html"
    page.write_text(
        "<html><head><title>Branded browser title</title></head>"
        "<body><main><h1>Schematic - Differential Impedance</h1></main></body></html>",
        encoding="utf-8",
    )

    title, markdown = _markdown_record("ads", docs, page)

    assert title == "Schematic - Differential Impedance"
    assert markdown.count("# Schematic - Differential Impedance") == 1
    assert markdown.rstrip().endswith(f"Source: `{page}`")


def test_madcap_main_content_excludes_account_chrome_and_build_metadata(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    page = docs / "drc.html"
    page.write_text(
        """
        <html><head><title>Run Design Rule Check</title></head><body>
          <header>Skip to Main Content Account Settings Logout</header>
          <main id="mc-main-content">
            <h1>Run Design Rule Check</h1>
            <p>Open the layout and run DRC with the configured rules.</p>
            <div id="buildmetadata">product_logo.png ADS 2027 Build time 10:00</div>
          </main>
          <footer>Contact Privacy Terms</footer>
        </body></html>
        """,
        encoding="utf-8",
    )

    title, markdown = _markdown_record("manual", docs, page)

    assert title == "Run Design Rule Check"
    assert markdown.count("# Run Design Rule Check") == 1
    assert "run DRC" in markdown
    assert "Account Settings" not in markdown
    assert "product_logo.png" not in markdown
    assert "Build time" not in markdown
    assert "Contact Privacy Terms" not in markdown


def test_query_snippet_is_centered_on_late_match(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "late.html").write_text(
        "<html><head><title>Late Match</title></head><body><main><h1>Late Match</h1>"
        f"<p>{'introductory material ' * 100}</p>"
        "<p>Call needle_method after opening the design.</p></main></body></html>",
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache)
    instance = AdsInstance(
        instance_id="ads-2027-snippet-test",
        install_root=str(tmp_path),
        product_version="ADS 2027",
        year=2027,
        update=None,
        platform="test",
        support_tier="stable",
        docs_roots={"python": [str(docs)]},
    )

    build_full_index(instance)
    result = query(instance, "needle_method")

    assert "needle_method" in result["results"][0]["snippet"]
    assert len(result["results"][0]["snippet"]) <= 808


def test_context_excerpt_preserves_python_indentation() -> None:
    markdown = (
        "# Example\n\nSource: `example.html`\n\n"
        "    def create_layout(enabled: bool) -> None:\n"
        "        if enabled:\n"
        "            design = create_layout()\n"
    )

    excerpt = _context_excerpt(markdown, ["create_layout"])

    assert "    def create_layout" in excerpt
    assert "        if enabled:" in excerpt
    assert "            design = create_layout()" in excerpt


def test_context_excerpt_prefers_signature_over_summary_table() -> None:
    markdown = (
        "# Design\n\nSource: `design.html`\n\n"
        "`add_rectangle`() | Add a rectangle.\n"
        + ("unrelated documentation text\n" * 80)
        + "add_rectangle(layer_id: LayerId, ll_or_box: ScaledBox) -> Rect\n"
        "Add a rectangle on the given layer and return it.\n"
    )

    excerpt = _context_excerpt(markdown, ["add_rectangle"])

    assert "layer_id: LayerId" in excerpt
    assert "ll_or_box: ScaledBox" in excerpt

    multi_term_excerpt = _context_excerpt(markdown, ["add", "rectangle"])
    assert "layer_id: LayerId" in multi_term_excerpt


def test_query_prefers_reference_page_over_generic_page(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs"
    reference = docs / "python" / "reference"
    examples = docs / "python" / "examples"
    reference.mkdir(parents=True)
    examples.mkdir(parents=True)
    (docs / "geometry.html").write_text(
        "<html><title>Geometry Guide</title><body><main><p>add_rectangle overview</p></main></body></html>",
        encoding="utf-8",
    )
    (reference / "add_rectangle.html").write_text(
        "<html><title>add_rectangle</title><body><main><h1>add_rectangle</h1><p>Reference signature.</p></main></body></html>",
        encoding="utf-8",
    )
    (examples / "rectangle.html").write_text(
        "<html><title>Rectangle Example</title><body><main><p>add_rectangle example.</p></main></body></html>",
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache)
    instance = AdsInstance(
        instance_id="ads-2027-rank-test",
        install_root=str(tmp_path),
        product_version="ADS 2027",
        year=2027,
        update=None,
        platform="test",
        support_tier="stable",
        docs_roots={"python": [str(docs)]},
    )

    build_full_index(instance)
    result = query(instance, "add_rectangle")

    assert result["results"][0]["relative_path"] == "python/reference/add_rectangle.html"


def test_status_reports_committed_background_progress(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    for index in range(3):
        (docs / f"page-{index}.html").write_text(
            f"<html><title>Page {index}</title><body><main>content {index}</main></body></html>",
            encoding="utf-8",
        )
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache)
    instance = AdsInstance(
        instance_id="ads-2026-progress-test",
        install_root=str(tmp_path),
        product_version="ADS 2026 Update 2",
        year=2026,
        update="2",
        platform="test",
        support_tier="stable",
        docs_roots={"python": [str(docs)]},
    )
    built = ensure_fast_index(instance)
    with sqlite3.connect(built["db_path"]) as connection:
        connection.execute("UPDATE pages SET enriched = 1 WHERE relative_path IN ('page-0.html', 'page-1.html')")
        connection.commit()
    (cache / "build-state.json").write_text(
        json.dumps({"status": "running", "pid": os.getpid()}),
        encoding="utf-8",
    )
    monkeypatch.setattr("ads_agent_bridge.docs_kb.pid_running", lambda _pid: True)

    result = status(instance)

    assert result["status"] == "ready"
    assert result["enrichment_status"] == "running"
    assert result["enriched_file_count"] == 2
    assert result["source_file_count"] == 3
    assert result["background_build"]["enriched_file_count"] == 2
