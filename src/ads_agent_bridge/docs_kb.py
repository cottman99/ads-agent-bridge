from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import html2text
from bs4 import BeautifulSoup

from .models import AdsInstance
from .paths import docs_cache
from .processes import pid_running


INDEX_SCHEMA_VERSION = 4
BATCH_SIZE = 100
SOURCE_FALLBACK_MAX_FILES = 200
SOURCE_FALLBACK_MAX_BYTES = 64 * 1024
SOURCE_FALLBACK_MAX_SECONDS = 1.0
MAIN_CONTENT_SELECTORS = ("#ks-content", "#mc-main-content", "main", '[role="main"]', "article")
DOCUMENT_DOMAINS = {"ads", "ael", "python", "dds"}
MAX_QUERY_MATCHES = 6
MAX_QUERY_RESULTS = 20
MAX_GET_CHARS = 12_000
QUERY_SNIPPET_CHARS = 360
QUERY_MATCHED_SECTIONS_CHARS = 720
BOOTSTRAP_PREFIX_BYTES = 64 * 1024
BOOTSTRAP_TEXT_CHARS = 12_000


def _source_ref(instance: AdsInstance, domain: str, root: Path | str, relative_path: str) -> str:
    identity = f"{os.path.normcase(str(Path(root).resolve()))}\0{relative_path}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"ads-doc:v1:{instance.instance_id}:{domain}:{digest}"


def _source_evidence(domain: str, relative_path: str) -> tuple[str, str]:
    path = relative_path.casefold().replace("\\", "/")
    name = Path(path).name
    if name in {"genindex.html", "search.html", "index.html"}:
        return "index", "discovery_only"
    if "/examples/" in path or "/example/" in path:
        return "official_example", "docs_backed_example"
    if "/reference/" in path or "/_autosummary/" in path:
        return "api_reference", "docs_backed_reference"
    if domain == "ael" or ("(" in name and ")" in name):
        return "ael_reference", "docs_backed_reference"
    return "guide", "docs_backed_unverified"


def _iter_html(instance: AdsInstance) -> Iterator[tuple[str, Path, Path]]:
    seen: set[str] = set()
    for domain, roots in instance.docs_roots.items():
        for root_text in roots:
            root = Path(root_text)
            if not root.is_dir():
                continue
            for path in root.rglob("*.html"):
                key = os.path.normcase(str(path.resolve()))
                if key not in seen:
                    seen.add(key)
                    yield domain, root, path


def fingerprint(instance: AdsInstance) -> tuple[str, int]:
    digest = hashlib.sha256(instance.install_root.encode("utf-8"))
    count = 0
    for domain, root, path in _iter_html(instance):
        try:
            stat = path.stat()
        except OSError:
            continue
        relative = path.relative_to(root).as_posix()
        digest.update(f"{domain}\0{root}\0{relative}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode("utf-8"))
        count += 1
    return digest.hexdigest(), count


def _plain_fragment(value: str) -> str:
    value = re.sub(r"[\ue000-\uf8ff\ufeff]", "", value)
    value = re.sub(r"<[^>]*$", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return " ".join(html.unescape(value).split())


def _strip_product_branding(title: str) -> str:
    return re.sub(r"\s+[—–-]\s+.*?\s+documentation\s*$", "", title, flags=re.IGNORECASE).strip()


def _page_record(domain: str, root: Path, path: Path) -> tuple[str, str, str, str, str, int, int]:
    # The bootstrap index must become useful quickly even for a large ADS help
    # corpus. Read a bounded prefix instead of parsing every complete page.
    with path.open("rb") as stream:
        raw = stream.read(BOOTSTRAP_PREFIX_BYTES).decode("utf-8", errors="ignore")
    title_match = re.search(r"(?is)<title\b[^>]*>(.*?)</title>", raw)
    title = _strip_product_branding(_plain_fragment(title_match.group(1))) if title_match else path.stem
    heading_matches = re.findall(r"(?is)<h[1-4]\b[^>]*>(.*?)</h[1-4]>", raw)[:30]
    headings = " | ".join(_plain_fragment(item) for item in heading_matches)
    text = f"{path.stem} {_plain_fragment(raw)[:BOOTSTRAP_TEXT_CHARS]}"
    stat = path.stat()
    return domain, str(root), path.relative_to(root).as_posix(), title, headings + " " + text, stat.st_mtime_ns, stat.st_size


def _normalized_title(soup: BeautifulSoup, path: Path, content=None) -> str:
    # The visible page heading is the canonical document title. ADS Sphinx
    # packages append product/build branding to <title>, which is useful in a
    # browser tab but becomes duplicated retrieval noise in Markdown.
    first_heading = content.find("h1") if content is not None else None
    if first_heading is not None:
        heading = " ".join(first_heading.get_text(" ", strip=True).split())
        if heading:
            return heading
    title = " ".join((soup.title.get_text(" ", strip=True) if soup.title else path.stem).split())
    title = _strip_product_branding(title)
    return title or path.stem


def _main_content(soup: BeautifulSoup):
    content = next((node for selector in MAIN_CONTENT_SELECTORS if (node := soup.select_one(selector))), None)
    if content is None:
        content = soup.body or soup
    removable = content.select(
        "script, style, noscript, template, nav, aside, form, header, footer, "
        "#buildmetadata, a.headerlink, .rst-footer-buttons, .wy-breadcrumbs"
    )
    for node in reversed(removable):
        node.decompose()
    return content


def _clean_markdown(markdown: str, title: str) -> str:
    markdown = re.sub(r"[\ue000-\uf8ff\ufeff]", "", markdown).strip()
    markdown = re.sub(r"[ \t]+\n", "\n", markdown)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    first_heading = re.match(r"^#\s+([^\n]+)(?:\n+|$)", markdown)
    if first_heading and _plain_fragment(first_heading.group(1)).casefold() == title.casefold():
        markdown = markdown[first_heading.end() :].lstrip()
    return markdown


def _markdown_record(domain: str, root: Path, path: Path) -> tuple[str, str]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    content = _main_content(soup)
    title = _normalized_title(soup, path, content)
    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.ignore_images = True
    converter.ignore_emphasis = False
    converter.ignore_links = False
    converter.skip_internal_links = True
    markdown = _clean_markdown(converter.handle(str(content)), title)
    header = f"# {title}\n\nSource: `{path}`\n\n"
    return title, header + markdown + ("\n" if markdown else "")


def _markdown_path(cache: Path, root: Path, relative_path: str) -> Path:
    root_id = hashlib.sha256(os.path.normcase(str(root.resolve())).encode("utf-8")).hexdigest()[:12]
    relative = Path(relative_path)
    return cache / "markdown" / root_id / relative.with_suffix(".md")


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _load_manifest(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def ensure_fast_index(instance: AdsInstance, force: bool = False) -> dict[str, object]:
    cache = docs_cache(instance.instance_id)
    db_path = cache / "fast-index.sqlite"
    manifest_path = cache / "manifest.json"
    current_fingerprint, file_count = fingerprint(instance)
    if not file_count:
        raise ValueError(f"No local HTML documentation found for {instance.product_version}.")
    if not force and db_path.is_file() and manifest_path.is_file():
        manifest = _load_manifest(manifest_path) or {}
        if manifest.get("schema_version") == INDEX_SCHEMA_VERSION and manifest.get("fingerprint") == current_fingerprint:
            return {**manifest, "status": "ready", "reused": True, "db_path": str(db_path)}

    fd, temporary_name = tempfile.mkstemp(prefix=".fast-index.", suffix=".sqlite", dir=cache)
    os.close(fd)
    temporary = Path(temporary_name)
    indexed = 0
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(temporary)
        try:
            connection.executescript(
                """
                CREATE TABLE pages (
                    domain TEXT NOT NULL,
                    source_root TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    size INTEGER NOT NULL,
                    enriched INTEGER NOT NULL DEFAULT 0,
                    markdown_path TEXT NOT NULL DEFAULT '',
                    UNIQUE(source_root, relative_path)
                );
                CREATE INDEX pages_domain ON pages(domain);
                """
            )
            for domain, root, path in _iter_html(instance):
                try:
                    if domain in {"python", "ael", "dds"}:
                        record = _page_record(domain, root, path)
                    else:
                        stat = path.stat()
                        relative = path.relative_to(root).as_posix()
                        record = (domain, str(root), relative, path.stem, relative, stat.st_mtime_ns, stat.st_size)
                    connection.execute(
                        "INSERT OR REPLACE INTO pages "
                        "(domain, source_root, relative_path, source_ref, title, content, mtime_ns, size, enriched, markdown_path) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            record[0],
                            record[1],
                            record[2],
                            _source_ref(instance, record[0], record[1], record[2]),
                            record[3],
                            record[4],
                            record[5],
                            record[6],
                            0,
                            "",
                        ),
                    )
                    indexed += 1
                except (OSError, UnicodeError):
                    continue
            connection.commit()
        finally:
            connection.close()
            connection = None
        os.replace(temporary, db_path)
    finally:
        if connection is not None:
            connection.close()
        if temporary.exists():
            temporary.unlink()

    manifest = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "instance_id": instance.instance_id,
        "product_version": instance.product_version,
        "fingerprint": current_fingerprint,
        "source_file_count": file_count,
        "indexed_file_count": indexed,
        "enriched_file_count": 0,
        "enrichment_status": "not_started",
        "enrichment_error_count": 0,
        "markdown_root": str(cache / "markdown"),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_manifest(manifest_path, manifest)
    return {**manifest, "status": "ready", "reused": False, "db_path": str(db_path)}


def build_full_index(instance: AdsInstance, *, force: bool = False, max_pages: int | None = None) -> dict[str, object]:
    state = ensure_fast_index(instance)
    cache = docs_cache(instance.instance_id)
    db_path = Path(str(state["db_path"]))
    manifest_path = cache / "manifest.json"
    errors: list[dict[str, str]] = []
    converted = 0
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        where = "" if force else " WHERE enriched = 0"
        limit = "" if max_pages is None else f" LIMIT {max(0, int(max_pages))}"
        rows = connection.execute(
            "SELECT domain, source_root, relative_path FROM pages" + where + " ORDER BY source_root, relative_path" + limit
        ).fetchall()
        for row in rows:
            root = Path(row["source_root"])
            source = root / row["relative_path"]
            try:
                title, markdown = _markdown_record(row["domain"], root, source)
                output = _markdown_path(cache, root, row["relative_path"])
                _atomic_write_text(output, markdown)
                connection.execute(
                    "UPDATE pages SET title = ?, content = ?, enriched = 1, markdown_path = ? "
                    "WHERE source_root = ? AND relative_path = ?",
                    (title, markdown, str(output), str(root), row["relative_path"]),
                )
                converted += 1
                if converted % BATCH_SIZE == 0:
                    connection.commit()
            except (OSError, UnicodeError, ValueError) as exc:
                errors.append({"source_path": str(source), "error": str(exc)})
        connection.commit()
        enriched = int(connection.execute("SELECT count(*) FROM pages WHERE enriched = 1").fetchone()[0])
        total = int(connection.execute("SELECT count(*) FROM pages").fetchone()[0])

    manifest = _load_manifest(manifest_path) or {}
    complete = enriched == total and not errors
    manifest.update(
        {
            "enriched_file_count": enriched,
            "enrichment_status": "ready" if complete else "partial",
            "enrichment_error_count": len(errors),
            "enrichment_updated_at": datetime.now(timezone.utc).isoformat(),
            "markdown_root": str(cache / "markdown"),
        }
    )
    _write_manifest(manifest_path, manifest)
    build_state_path = cache / "build-state.json"
    build_state = _load_manifest(build_state_path) or {}
    if int(build_state.get("pid") or 0) == os.getpid():
        build_state.update(
            {
                "status": "completed" if complete else "partial",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "enriched_file_count": enriched,
                "source_file_count": total,
                "error_count": len(errors),
            }
        )
        _write_manifest(build_state_path, build_state)
    return {
        **manifest,
        "status": "ready" if complete else "partial",
        "converted_this_run": converted,
        "errors": errors[:20],
        "db_path": str(db_path),
    }


def _database_progress(db_path: Path) -> tuple[int, int] | None:
    try:
        with sqlite3.connect(db_path, timeout=0.25) as connection:
            row = connection.execute(
                "SELECT count(*), sum(CASE WHEN enriched = 1 THEN 1 ELSE 0 END) FROM pages"
            ).fetchone()
    except (OSError, sqlite3.Error):
        return None
    return (int(row[1] or 0), int(row[0] or 0)) if row else None


def start_background_build(instance: AdsInstance, *, force: bool = False) -> dict[str, object]:
    ensure_fast_index(instance)
    cache = docs_cache(instance.instance_id)
    state_path = cache / "build-state.json"
    previous = _load_manifest(state_path) or {}
    previous_pid = int(previous.get("pid") or 0)
    if pid_running(previous_pid):
        return {**previous, "status": "running", "reused": True}
    log_path = cache / "build.log"
    command = [sys.executable, "-m", "ads_agent_bridge", "docs", "build", "--ads", instance.instance_id]
    if force:
        command.append("--force")
    creationflags = 0
    kwargs: dict[str, object] = {"cwd": str(cache)}
    if os.name == "nt":
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True
    with log_path.open("ab") as log:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **kwargs)
    payload = {
        "schema_version": 1,
        "status": "running",
        "pid": process.pid,
        "instance_id": instance.instance_id,
        "command": command,
        "log_path": str(log_path),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "reused": False,
    }
    _write_manifest(state_path, payload)
    return payload


def status(instance: AdsInstance) -> dict[str, object]:
    cache = docs_cache(instance.instance_id, ensure=False)
    manifest_path = cache / "manifest.json"
    db_path = cache / "fast-index.sqlite"
    if not manifest_path.is_file() or not db_path.is_file():
        return {"instance_id": instance.instance_id, "status": "missing"}
    payload = _load_manifest(manifest_path) or {}
    if payload.get("schema_version") != INDEX_SCHEMA_VERSION:
        return {
            **payload,
            "status": "stale",
            "stale_reason": "schema_version",
            "db_path": str(db_path),
            "background_build": None,
        }
    build_state = _load_manifest(cache / "build-state.json") or {}
    if build_state and build_state.get("status") == "running" and not pid_running(int(build_state.get("pid") or 0)):
        updated_at = str(payload.get("enrichment_updated_at") or "")
        started_at = str(build_state.get("started_at") or "")
        if updated_at and updated_at >= started_at:
            build_state["status"] = "completed" if payload.get("enrichment_status") == "ready" else "partial"
        else:
            build_state["status"] = "interrupted"
    if build_state.get("status") == "running":
        progress = _database_progress(db_path)
        if progress is not None:
            enriched, total = progress
            payload["enriched_file_count"] = enriched
            payload["source_file_count"] = total
            payload["enrichment_status"] = "running"
            build_state["enriched_file_count"] = enriched
            build_state["source_file_count"] = total
    return {**payload, "status": "ready", "db_path": str(db_path), "background_build": build_state or None}


def _document_body(content: str) -> str:
    body = re.sub(r"\A# [^\n]+\n\nSource: `[^\n]+`\n\n", "", content, count=1)
    body = "\n".join(line.rstrip() for line in body.splitlines())
    return re.sub(r"\n{3,}", "\n\n", body).strip("\n")


def _context_excerpt(content: str, terms: list[str], *, width: int = 800) -> str:
    body = _document_body(content)
    if len(body) <= width:
        return body
    lowered = body.lower()
    phrase = " ".join(terms)
    positions = {match.start() for term in terms for match in re.finditer(re.escape(term), lowered)}
    if phrase:
        positions.update(match.start() for match in re.finditer(re.escape(phrase), lowered))
    positions = sorted(positions)
    if not positions:
        return body[:width].rstrip() + " …"
    best_position = positions[0]
    best_score = -1
    for position in positions:
        start = max(0, position - width // 3)
        end = min(len(body), start + width)
        window = lowered[start:end]
        line_start = body.rfind("\n", 0, position) + 1
        line_end = body.find("\n", position)
        line_end = len(body) if line_end < 0 else line_end
        line = body[line_start:line_end]
        stripped = line.lstrip()
        offset = position - line_start
        matched_term = next((term for term in terms if lowered.startswith(term, position)), "")
        after_match = line[offset + len(matched_term) :].lstrip() if matched_term else ""
        score = 100 * sum(term in window for term in set(terms))
        score += 30 if stripped.startswith(("#", "def ", "class ")) else 0
        score += 20 if "|" not in line else -20
        score += 15 if offset <= len(line) - len(stripped) + 4 else 0
        score += 10 if after_match.startswith("(") else 0
        score -= 15 if "`" in line else 0
        if score > best_score:
            best_position, best_score = position, score
    start = max(0, best_position - width // 3)
    end = min(len(body), start + width)
    if end - start < width:
        start = max(0, end - width)
    if start:
        next_line = body.find("\n", start, best_position)
        if next_line >= 0:
            start = next_line + 1
    if end < len(body):
        previous_line = body.rfind("\n", best_position, end)
        if previous_line > best_position:
            end = previous_line
    excerpt = body[start:end].strip("\n")
    return ("…\n\n" if start else "") + excerpt + ("\n\n…" if end < len(body) else "")


def _matched_sections(content: str, terms: list[str], *, width: int = 500) -> list[dict[str, str]]:
    lowered = _document_body(content).casefold()
    matches: list[dict[str, str]] = []
    seen: set[str] = set()
    for term in terms:
        normalized = term.casefold()
        if normalized in seen or normalized not in lowered:
            continue
        seen.add(normalized)
        matches.append({"query_term": term, "excerpt": _context_excerpt(content, [normalized], width=width)})
        if len(matches) >= MAX_QUERY_MATCHES:
            break
    return matches


def _focus_terms(text: str | None) -> list[str]:
    terms = [term.casefold() for term in re.findall(r"[\w.:-]+", text or "", flags=re.UNICODE) if len(term) > 1]
    symbol_terms = [term for term in terms if any(marker in term for marker in ("_", ".", ":"))]
    return list(dict.fromkeys(symbol_terms or terms))


def _decorate_result(row: dict[str, object], terms: list[str]) -> dict[str, object]:
    content = str(row.pop("_content", ""))
    source_kind, validation_status = _source_evidence(str(row["domain"]), str(row["relative_path"]))
    row.pop("source_root", None)
    row.pop("markdown_path", None)
    row["source_kind"] = source_kind
    row["validation_status"] = validation_status
    row["runtime_verified"] = False
    matched_term_count = min(
        MAX_QUERY_MATCHES,
        len({term.casefold() for term in terms if term.casefold() in content.casefold()}),
    )
    section_width = max(120, QUERY_MATCHED_SECTIONS_CHARS // max(1, matched_term_count))
    matches = _matched_sections(content, terms, width=section_width)
    if matches:
        row["matched_sections"] = matches
    return row


def _is_reference_result(row: dict[str, object]) -> bool:
    source_kind, _ = _source_evidence(str(row["domain"]), str(row["relative_path"]))
    return source_kind in {"api_reference", "official_example", "ael_reference"}


def _merge_reference_candidates(
    strict_rows: list[dict[str, object]],
    relaxed_rows: list[dict[str, object]],
    limit: int,
) -> tuple[list[dict[str, object]], bool]:
    if not strict_rows or limit < 2:
        return strict_rows, False
    reference_quota = min(3, limit // 2)
    existing_references = sum(_is_reference_result(row) for row in strict_rows[:limit])
    needed = max(0, reference_quota - existing_references)
    existing_refs = {str(row["source_ref"]) for row in strict_rows}
    supplements = [
        row
        for row in relaxed_rows
        if _is_reference_result(row) and str(row["source_ref"]) not in existing_refs
    ][:needed]
    if not supplements:
        return strict_rows[:limit], False
    ordered = [strict_rows[0], *supplements, *strict_rows[1:], *relaxed_rows]
    merged: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in ordered:
        source_ref = str(row["source_ref"])
        if source_ref in seen:
            continue
        seen.add(source_ref)
        merged.append(row)
        if len(merged) >= limit:
            break
    return merged, True


def _query_index(
    db_path: Path,
    terms: list[str],
    limit: int,
    *,
    require_all: bool,
    domains: list[str],
) -> list[dict[str, object]]:
    title = "lower(title)"
    relative_path = "lower(relative_path)"
    content = "lower(content)"
    searchable = "lower(title || ' ' || relative_path || ' ' || content)"
    score_parts: list[str] = []
    score_params: list[str] = []
    for term in terms:
        exact_title_weight = 60 + min(len(term), 40)
        score_parts.extend(
            [
                f"CASE WHEN {title} = ? THEN {exact_title_weight} ELSE 0 END",
                f"CASE WHEN instr({title}, ?) > 0 THEN 8 ELSE 0 END",
                f"CASE WHEN instr({relative_path}, ?) > 0 THEN 5 ELSE 0 END",
                f"CASE WHEN instr({content}, ?) > 0 THEN 1 ELSE 0 END",
            ]
        )
        score_params.extend([term, term, term, term])
    score_parts.append(
        "CASE WHEN lower(relative_path) LIKE '%/reference/%' "
        "OR lower(relative_path) LIKE '%/_autosummary/%' THEN 3 "
        "WHEN lower(relative_path) LIKE '%/examples/%' THEN 2 ELSE 0 END"
    )
    operator = " AND " if require_all else " OR "
    term_where = operator.join(f"instr({searchable}, ?) > 0" for _ in terms)
    where_params = list(terms)
    if require_all and len(terms) > 1:
        exact_title_where = " OR ".join(f"{title} = ?" for _ in terms)
        term_where = f"({term_where}) OR ({exact_title_where})"
        where_params.extend(terms)
    domain_where = f"lower(domain) IN ({', '.join('?' for _ in domains)})" if domains else ""
    where = f"({term_where}) AND {domain_where}" if domain_where else term_where
    sql = (
        "SELECT domain, source_root, relative_path, source_ref, title, markdown_path, content AS _content, "
        f"({' + '.join(score_parts)}) AS relevance FROM pages WHERE {where} "
        "ORDER BY relevance DESC, title, relative_path LIMIT ?"
    )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = [dict(row) for row in connection.execute(sql, [*score_params, *where_params, *domains, limit])]
        for row in rows:
            row["snippet"] = _context_excerpt(str(row["_content"]), terms, width=QUERY_SNIPPET_CHARS)
            row.pop("relevance", None)
    return rows


def query(
    instance: AdsInstance,
    text: str,
    limit: int = 10,
    *,
    domains: list[str] | None = None,
) -> dict[str, object]:
    if limit < 1 or limit > MAX_QUERY_RESULTS:
        raise ValueError(f"limit must be between 1 and {MAX_QUERY_RESULTS}.")
    state = status(instance)
    if state.get("status") != "ready":
        state = ensure_fast_index(instance)
    db_path = Path(str(state["db_path"]))
    terms = [term.lower() for term in re.findall(r"[\w.:-]+", text, flags=re.UNICODE) if len(term) > 1]
    if not terms:
        raise ValueError("Query must contain at least one searchable term.")
    explicit_domains = [domain.casefold() for domain in (domains or [])]
    invalid_domains = sorted(set(explicit_domains) - DOCUMENT_DOMAINS)
    if invalid_domains:
        raise ValueError(f"Unsupported documentation domain: {', '.join(invalid_domains)}")
    implicit_domains = list(dict.fromkeys(term for term in terms if term in DOCUMENT_DOMAINS))
    selected_domains = list(dict.fromkeys(explicit_domains or (implicit_domains if len(implicit_domains) == 1 else [])))
    search_terms = [term for term in terms if term not in DOCUMENT_DOMAINS]
    if not search_terms:
        search_terms = terms
        selected_domains = explicit_domains
    rows = _query_index(db_path, search_terms, limit, require_all=True, domains=selected_domains)
    search_mode = "bootstrap_index"
    if len(search_terms) > 1:
        relaxed_rows = _query_index(
            db_path,
            search_terms,
            max(MAX_QUERY_RESULTS, limit * 4),
            require_all=False,
            domains=selected_domains,
        )
        if rows:
            rows, supplemented = _merge_reference_candidates(rows, relaxed_rows, limit)
            if supplemented:
                search_mode = "bootstrap_index_hybrid"
        else:
            rows = relaxed_rows[:limit]
            if rows:
                search_mode = "bootstrap_index_relaxed"
    if not rows:
        rows = _query_source_fallback(instance, search_terms, limit, domains=selected_domains)
        search_mode = "source_fallback_bounded"
    rows = [_decorate_result(row, search_terms) for row in rows]
    return {
        "instance_id": instance.instance_id,
        "product_version": instance.product_version,
        "query": text,
        "domains": selected_domains,
        "search_mode": search_mode,
        "enrichment_status": state.get("enrichment_status", "not_started"),
        "coverage": {
            "path_index": "complete",
            "content_index": (
                "complete"
                if state.get("enrichment_status") == "ready"
                else "api_prefixes_plus_bounded_fallback"
            ),
            "negative_results_are_runtime_proof": False,
        },
        "evidence_boundary": "Version-matched local documentation evidence; not runtime verification.",
        "next_action": "Use docs get <source_ref> --focus <symbol-or-topic> only when returned excerpts are insufficient.",
        "results": rows,
    }


def get_document(
    instance: AdsInstance,
    source_ref: str,
    *,
    focus: str | None = None,
    max_chars: int = 4000,
) -> dict[str, object]:
    if max_chars < 200 or max_chars > MAX_GET_CHARS:
        raise ValueError(f"max_chars must be between 200 and {MAX_GET_CHARS}.")
    state = status(instance)
    if state.get("status") != "ready":
        state = ensure_fast_index(instance)
    db_path = Path(str(state["db_path"]))
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        stored = connection.execute(
            "SELECT domain, source_root, relative_path, source_ref, title, content, enriched "
            "FROM pages WHERE source_ref = ?",
            (source_ref,),
        ).fetchone()
    if stored is None:
        raise ValueError(f"Unknown documentation source_ref for {instance.instance_id}: {source_ref}")
    row = dict(stored)
    retrieval_mode = "enriched_index"
    if not row["enriched"]:
        root = Path(str(row["source_root"]))
        source = root / str(row["relative_path"])
        title, content = _markdown_record(str(row["domain"]), root, source)
        row["title"] = title
        row["content"] = content
        retrieval_mode = "on_demand_cleaning"
    terms = _focus_terms(focus)
    sections: list[dict[str, str]] = []
    excerpt: str | None = None
    if terms:
        section_width = max(200, min(2000, max_chars // len(terms)))
        sections = _matched_sections(str(row["content"]), terms, width=section_width)
        matched_terms = {section["query_term"] for section in sections}
        title_text = str(row["title"]).casefold()
        for term in terms:
            if term not in matched_terms and term in title_text:
                sections.append(
                    {"query_term": term, "excerpt": _context_excerpt(str(row["content"]), [], width=section_width)}
                )
    else:
        excerpt = _context_excerpt(str(row["content"]), [], width=max_chars)
    source_kind, validation_status = _source_evidence(str(row["domain"]), str(row["relative_path"]))
    return {
        "instance_id": instance.instance_id,
        "product_version": instance.product_version,
        "source_ref": row["source_ref"],
        "domain": row["domain"],
        "title": row["title"],
        "relative_path": row["relative_path"],
        "source_kind": source_kind,
        "validation_status": validation_status,
        "runtime_verified": False,
        "focus": focus,
        "retrieval_mode": retrieval_mode,
        **({"sections": sections} if terms else {"excerpt": excerpt}),
        "content_hash": hashlib.sha256(_document_body(str(row["content"])).encode("utf-8")).hexdigest(),
        "evidence_boundary": "Version-matched local documentation evidence; not runtime verification.",
    }


def _query_source_fallback(
    instance: AdsInstance,
    terms: list[str],
    limit: int,
    *,
    domains: list[str] | None = None,
) -> list[dict[str, object]]:
    encoded_terms = [term.encode("utf-8", errors="ignore") for term in terms]
    results: list[dict[str, object]] = []
    started = time.monotonic()
    scanned = 0
    for domain, root, path in _iter_html(instance):
        if domains and domain.lower() not in domains:
            continue
        if scanned >= SOURCE_FALLBACK_MAX_FILES or time.monotonic() - started >= SOURCE_FALLBACK_MAX_SECONDS:
            break
        scanned += 1
        try:
            with path.open("rb") as stream:
                raw = stream.read(SOURCE_FALLBACK_MAX_BYTES)
        except OSError:
            continue
        lowered = raw.lower()
        if not all(term in lowered for term in encoded_terms):
            continue
        record = _page_record(domain, root, path)
        results.append(
            {
                "domain": record[0],
                "source_root": str(root),
                "relative_path": record[2],
                "source_ref": _source_ref(instance, record[0], root, record[2]),
                "title": record[3],
                "snippet": _context_excerpt(record[4], terms, width=QUERY_SNIPPET_CHARS),
                "_content": record[4],
            }
        )
        if len(results) >= limit:
            break
    return results
