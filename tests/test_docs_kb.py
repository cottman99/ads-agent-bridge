import json
import os
import sqlite3
from pathlib import Path

import pytest

import ads_agent_bridge.docs_kb as docs_kb
from ads_agent_bridge.docs_kb import (
    _context_excerpt,
    _markdown_record,
    build_full_index,
    ensure_fast_index,
    get_document,
    query,
    status,
)
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
    assert result["results"][0]["source_ref"].startswith("ads-doc:v1:ads-2025-test:python:")
    assert "source_path" not in result["results"][0]
    assert "markdown_path" not in result["results"][0]
    assert result["results"][0]["runtime_verified"] is False
    with pytest.raises(ValueError, match="limit must be between"):
        query(instance, "create_workspace", limit=21)


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
    source_ref = result["results"][0]["source_ref"]
    detail = get_document(instance, source_ref, focus="rare_full_text_token", max_chars=500)
    assert detail["title"] == "rare_full_text_token"
    assert "Version-specific detail" in detail["sections"][0]["excerpt"]
    assert detail["retrieval_mode"] == "enriched_index"
    assert "source_path" not in detail
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
    assert status(instance)["schema_version"] == 4
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
    assert result["coverage"]["path_index"] == "complete"
    assert result["coverage"]["negative_results_are_runtime_proof"] is False


def test_natural_language_domain_word_does_not_silently_filter_corpus(
    tmp_path: Path, monkeypatch
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.html").write_text("<title>ADS documentation</title>", encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(
        "ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache
    )
    instance = AdsInstance(
        instance_id="ads-2027-test",
        install_root=str(tmp_path),
        product_version="ADS 2027",
        year=2027,
        update=None,
        platform="test",
        support_tier="fallback",
        docs_roots={"ads": [str(docs)]},
    )
    ensure_fast_index(instance)
    calls: list[tuple[list[str], list[str]]] = []

    def fake_query_index(
        _db_path: Path,
        terms: list[str],
        _limit: int,
        *,
        require_all: bool,
        domains: list[str],
    ) -> list[dict[str, object]]:
        calls.append((terms, domains))
        if require_all:
            return []
        return [
            {
                "domain": "ads",
                "source_ref": "ads-doc:v1:verification.html",
                "title": "Automating Design Verification using Python",
                "relative_path": "verification.html",
                "_content": "create_drc_job run_drc_job Python",
            }
        ]

    monkeypatch.setattr(docs_kb, "_query_index", fake_query_index)

    result = query(instance, "create_drc_job run_drc_job Python")

    assert result["domains"] == []
    assert result["results"][0]["relative_path"] == "verification.html"
    assert calls
    assert all(domains == [] for _terms, domains in calls)
    assert all("python" in terms for terms, _domains in calls)


def test_fast_index_searches_python_page_prefix_without_full_enrichment(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "Design.html").write_text(
        "<html><head><title>Design</title></head><body><main>"
        f"<p>{'navigation ' * 600}</p>"
        "<p>prefix_only_method(layer_id, points) -&gt; Shape</p></main></body></html>",
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache)
    instance = AdsInstance(
        instance_id="ads-2027-prefix-test",
        install_root=str(tmp_path),
        product_version="ADS 2027",
        year=2027,
        update=None,
        platform="test",
        support_tier="stable",
        docs_roots={"python": [str(docs)]},
    )

    ensure_fast_index(instance)
    result = query(instance, "prefix_only_method", domains=["python"])

    assert result["search_mode"] == "bootstrap_index"
    assert result["results"][0]["title"] == "Design"
    assert "prefix_only_method" in result["results"][0]["snippet"]


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
    assert result["results"][0]["source_kind"] == "api_reference"
    assert result["results"][0]["validation_status"] == "docs_backed_reference"


def test_query_can_explicitly_select_python_domain_and_returns_term_evidence(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs"
    python_docs = docs / "python" / "reference"
    ael_docs = docs / "ael"
    python_docs.mkdir(parents=True)
    ael_docs.mkdir(parents=True)
    (python_docs / "Design.html").write_text(
        "<html><title>Design</title><body><main><h1>Design</h1>"
        "<p>add_rectangle(layer_id, ll_or_box) -&gt; Rect</p>"
        "<p>add_polygon(layer_id, polygon) -&gt; Polygon</p>"
        "</main></body></html>",
        encoding="utf-8",
    )
    (ael_docs / "add_rectangle.html").write_text(
        "<html><title>add_rectangle</title><body><main>AEL add_rectangle command.</main></body></html>",
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache)
    instance = AdsInstance(
        instance_id="ads-2027-domain-test",
        install_root=str(tmp_path),
        product_version="ADS 2027",
        year=2027,
        update=None,
        platform="test",
        support_tier="stable",
        docs_roots={"python": [str(python_docs.parent)], "ael": [str(ael_docs)]},
    )

    build_full_index(instance)
    result = query(instance, "add_rectangle add_polygon", domains=["python"])

    assert result["result_count"] == len(result["results"])
    assert result["domains"] == ["python"]
    assert result["results"][0]["domain"] == "python"
    assert {item["query_term"] for item in result["results"][0]["matched_sections"]} == {
        "add_rectangle",
        "add_polygon",
    }
    serialized = json.dumps(result["results"][0], ensure_ascii=False)
    assert len(serialized) < 2500


def test_exact_title_is_not_excluded_by_unmatched_generic_terms(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs" / "reference"
    docs.mkdir(parents=True)
    (docs / "LayerId.html").write_text(
        "<html><title>LayerId</title><body><main><p>Layer identifier.</p></main></body></html>",
        encoding="utf-8",
    )
    (docs / "GenericObject.html").write_text(
        "<html><title>GenericObject</title><body><main>"
        "LayerId named layer purpose create 2027"
        "</main></body></html>",
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache)
    instance = AdsInstance(
        instance_id="ads-2027-exact-title-test",
        install_root=str(tmp_path),
        product_version="ADS 2027",
        year=2027,
        update=None,
        platform="test",
        support_tier="stable",
        docs_roots={"python": [str(docs.parent)]},
    )

    result = query(instance, "LayerId named layer purpose create 2027", domains=["python"])

    assert result["results"][0]["title"] == "LayerId"


def test_get_document_cleans_on_demand_and_bounds_output(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "symbol.html").write_text(
        "<html><head><title>Symbol</title></head><body><nav>navigation noise</nav><main><h1>Symbol</h1>"
        f"<p>{'intro ' * 200}</p><p>target_symbol(arg: str) -&gt; bool</p><p>{'tail ' * 200}</p>"
        "</main></body></html>",
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache)
    instance = AdsInstance(
        instance_id="ads-2026-get-test",
        install_root=str(tmp_path),
        product_version="ADS 2026 Update 2",
        year=2026,
        update="2",
        platform="test",
        support_tier="stable",
        docs_roots={"python": [str(docs)]},
    )

    result = query(instance, "target_symbol")
    detail = get_document(
        instance,
        result["results"][0]["source_ref"],
        focus="target_symbol signature and examples",
        max_chars=300,
    )

    assert detail["retrieval_mode"] == "on_demand_cleaning"
    excerpt = detail["sections"][0]["excerpt"]
    assert detail["returned_chars"] == sum(
        len(section["excerpt"]) for section in detail["sections"]
    )
    assert [section["query_term"] for section in detail["sections"]] == ["target_symbol"]
    assert "target_symbol(arg: str)" in excerpt
    assert "navigation noise" not in excerpt
    assert len(excerpt) <= 308


def test_ads_function_page_is_typed_as_ael_reference(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs"
    function_dir = docs / "Content" / "drc"
    function_dir.mkdir(parents=True)
    (function_dir / "dve_create_drc_job().html").write_text(
        "<html><title>dve_create_drc_job()</title><body><main><h1>dve_create_drc_job()</h1>"
        "<p>Creates a DRC job for AEL execution.</p></main></body></html>",
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache)
    instance = AdsInstance(
        instance_id="ads-2027-ael-reference-test",
        install_root=str(tmp_path),
        product_version="ADS 2027",
        year=2027,
        update=None,
        platform="test",
        support_tier="stable",
        docs_roots={"ads": [str(docs)]},
    )

    result = query(instance, "dve_create_drc_job", domains=["ads"])

    assert result["results"][0]["source_kind"] == "ael_reference"
    assert result["results"][0]["validation_status"] == "docs_backed_reference"


def test_multi_term_guide_match_keeps_reference_candidates_visible(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs" / "Content" / "drc"
    docs.mkdir(parents=True)
    (docs / "layout_design_rule_check_drc_run.html").write_text(
        "<html><title>Layout DRC guide</title><body><main>Guide.</main></body></html>",
        encoding="utf-8",
    )
    (docs / "dve_create_drc_job().html").write_text(
        "<html><title>dve_create_drc_job()</title><body><main>AEL reference.</main></body></html>",
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache)
    instance = AdsInstance(
        instance_id="ads-2027-hybrid-rank-test",
        install_root=str(tmp_path),
        product_version="ADS 2027",
        year=2027,
        update=None,
        platform="test",
        support_tier="stable",
        docs_roots={"ads": [str(docs.parents[1])]},
    )

    result = query(instance, "layout design rule check DRC run", limit=4, domains=["ads"])

    assert result["search_mode"] == "bootstrap_index_hybrid"
    assert result["results"][0]["source_kind"] == "guide"
    assert any(row["source_kind"] == "ael_reference" for row in result["results"][:3])


def test_multi_term_query_preserves_uncovered_title_topics(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "layout.html").write_text(
        "<html><title>Layout</title><body>ADS 2027 Python API execute layout DRC design rule check</body></html>",
        encoding="utf-8",
    )
    (docs / "drc.html").write_text(
        "<html><title>Using the Design Rule Checker DRC</title><body>layout guide</body></html>",
        encoding="utf-8",
    )
    (docs / "python-dve.html").write_text(
        "<html><title>Automating Design Verification using Python</title>"
        "<body>create_drc_job run_drc_job</body></html>",
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache)
    instance = AdsInstance(
        instance_id="ads-2027-topic-coverage-test",
        install_root=str(tmp_path),
        product_version="ADS 2027",
        year=2027,
        update=None,
        platform="test",
        support_tier="stable",
        docs_roots={"ads": [str(docs)]},
    )
    build_full_index(instance)

    result = query(instance, "ADS 2027 Python API execute layout DRC design rule check", limit=10)

    assert result["search_mode"] == "bootstrap_index_hybrid"
    assert "Automating Design Verification using Python" in {
        row["title"] for row in result["results"]
    }


def test_longer_exact_symbol_title_beats_generic_exact_title(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs" / "reference" / "_autosummary"
    docs.mkdir(parents=True)
    shared = "named layer purpose technology lookup"
    (docs / "Layer.html").write_text(
        f"<html><title>Layer</title><body><main>LayerId {shared}</main></body></html>",
        encoding="utf-8",
    )
    (docs / "LayerId.html").write_text(
        f"<html><title>LayerId</title><body><main>Layer {shared}</main></body></html>",
        encoding="utf-8",
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ads_agent_bridge.docs_kb.docs_cache", lambda _instance_id, **_kwargs: cache)
    instance = AdsInstance(
        instance_id="ads-2027-exact-symbol-rank-test",
        install_root=str(tmp_path),
        product_version="ADS 2027",
        year=2027,
        update=None,
        platform="test",
        support_tier="stable",
        docs_roots={"python": [str(docs.parents[1])]},
    )

    result = query(instance, "LayerId named layer purpose technology lookup", limit=6, domains=["python"])

    assert result["results"][0]["title"] == "LayerId"


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
