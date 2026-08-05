from pathlib import Path

from ads_agent_bridge.discovery import candidate_roots, inspect_root, locate_docs


def make_ads_root(tmp_path: Path, name: str = "ADS2025_Update2") -> Path:
    root = tmp_path / name
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "hpeesofde").write_text("", encoding="ascii")
    (root / "tools" / "python" / "bin").mkdir(parents=True)
    (root / "tools" / "python" / "bin" / "python").write_text("", encoding="ascii")
    (root / "doc" / "ads").mkdir(parents=True)
    (root / "doc" / "ads" / "index.html").write_text("<title>ADS docs</title>", encoding="utf-8")
    (root / "doc" / "python").mkdir(parents=True)
    (root / "doc" / "python" / "index.html").write_text("<title>Python docs</title>", encoding="utf-8")
    return root


def test_inspect_root_discovers_version_docs_and_python(tmp_path: Path) -> None:
    root = make_ads_root(tmp_path)
    instance = inspect_root(root)
    assert instance is not None
    assert instance.year == 2025
    assert instance.update == "2"
    assert instance.support_tier == "stable"
    assert instance.capabilities["embedded_python"] is True
    assert instance.docs_roots["python"] == [str((root / "doc" / "python").resolve())]


def test_locate_docs_supports_linux_doc_python_layout(tmp_path: Path) -> None:
    root = make_ads_root(tmp_path, "ADS2026_Update2.1")
    docs = locate_docs(root)
    assert "ads" in docs
    assert "python" in docs


def test_inspect_root_finds_versioned_linux_ads_python(tmp_path: Path) -> None:
    root = make_ads_root(tmp_path, "ADS2026_Update2.1")
    (root / "tools" / "python" / "bin" / "python").unlink()
    versioned = root / "tools" / "python" / "bin" / "python3.13"
    versioned.write_text("", encoding="ascii")
    instance = inspect_root(root)
    assert instance is not None
    assert instance.python_executable == str(versioned.resolve())


def test_explicit_root_is_authoritative(tmp_path: Path, monkeypatch) -> None:
    explicit = make_ads_root(tmp_path, "ADS2025")
    other = make_ads_root(tmp_path, "ADS2026")
    monkeypatch.setenv("HPEESOF_DIR", str(other))
    assert candidate_roots([explicit]) == [explicit.resolve()]


def test_locate_docs_classifies_nested_ael_and_dds_docs(tmp_path: Path) -> None:
    root = tmp_path / "ADS2026_Update1"
    for domain in ("ael", "dds", "de"):
        html = root / "doc" / "python" / domain / "html"
        html.mkdir(parents=True)
        (html / "index.html").write_text(f"<title>{domain}</title>", encoding="utf-8")
    docs = locate_docs(root)
    assert docs["ael"] == [str((root / "doc" / "python" / "ael" / "html").resolve())]
    assert docs["dds"] == [str((root / "doc" / "python" / "dds" / "html").resolve())]
    assert docs["python"] == [str((root / "doc" / "python" / "de" / "html").resolve())]
