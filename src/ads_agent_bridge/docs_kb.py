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
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import html2text
from bs4 import BeautifulSoup

from .models import AdsInstance
from .paths import docs_cache


INDEX_SCHEMA_VERSION = 2
BATCH_SIZE = 100


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
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return " ".join(html.unescape(value).split())


def _page_record(domain: str, root: Path, path: Path) -> tuple[str, str, str, str, str, int, int]:
    # The bootstrap index must become useful quickly even for a large ADS help
    # corpus. Read a bounded prefix instead of parsing every complete page.
    with path.open("rb") as stream:
        raw = stream.read(32 * 1024).decode("utf-8", errors="ignore")
    title_match = re.search(r"(?is)<title\b[^>]*>(.*?)</title>", raw)
    title = _plain_fragment(title_match.group(1)) if title_match else path.stem
    heading_matches = re.findall(r"(?is)<h[1-4]\b[^>]*>(.*?)</h[1-4]>", raw)[:30]
    headings = " | ".join(_plain_fragment(item) for item in heading_matches)
    text = f"{path.stem} {_plain_fragment(raw)[:4000]}"
    stat = path.stat()
    return domain, str(root), path.relative_to(root).as_posix(), title, headings + " " + text, stat.st_mtime_ns, stat.st_size


def _markdown_record(domain: str, root: Path, path: Path) -> tuple[str, str]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    title = " ".join((soup.title.get_text(" ", strip=True) if soup.title else path.stem).split())
    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.ignore_images = True
    converter.ignore_emphasis = False
    converter.ignore_links = False
    converter.skip_internal_links = True
    markdown = converter.handle(raw).strip()
    header = f"# {title}\n\nSource: `{path}`\n\n"
    return title, header + markdown + "\n"


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
                    stat = path.stat()
                    relative = path.relative_to(root).as_posix()
                    connection.execute(
                        "INSERT OR REPLACE INTO pages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (domain, str(root), relative, path.stem, relative, stat.st_mtime_ns, stat.st_size, 0, ""),
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


def _pid_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    return True


def start_background_build(instance: AdsInstance, *, force: bool = False) -> dict[str, object]:
    ensure_fast_index(instance)
    cache = docs_cache(instance.instance_id)
    state_path = cache / "build-state.json"
    previous = _load_manifest(state_path) or {}
    previous_pid = int(previous.get("pid") or 0)
    if _pid_running(previous_pid):
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
    build_state = _load_manifest(cache / "build-state.json") or {}
    if build_state and build_state.get("status") == "running" and not _pid_running(int(build_state.get("pid") or 0)):
        updated_at = str(payload.get("enrichment_updated_at") or "")
        started_at = str(build_state.get("started_at") or "")
        if updated_at and updated_at >= started_at:
            build_state["status"] = "completed" if payload.get("enrichment_status") == "ready" else "partial"
        else:
            build_state["status"] = "interrupted"
    return {**payload, "status": "ready", "db_path": str(db_path), "background_build": build_state or None}


def query(instance: AdsInstance, text: str, limit: int = 10) -> dict[str, object]:
    state = status(instance)
    if state.get("status") != "ready":
        state = ensure_fast_index(instance)
    db_path = Path(str(state["db_path"]))
    terms = [term.lower() for term in re.findall(r"[\w.:-]+", text, flags=re.UNICODE) if len(term) > 1]
    if not terms:
        raise ValueError("Query must contain at least one searchable term.")
    where = " AND ".join("lower(title || ' ' || content) LIKE ?" for _ in terms)
    params = [f"%{term}%" for term in terms]
    sql = (
        "SELECT domain, source_root, relative_path, title, markdown_path, "
        f"substr(content, 1, 500) AS snippet FROM pages WHERE {where} LIMIT ?"
    )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = [dict(row) for row in connection.execute(sql, [*params, limit])]
    search_mode = "bootstrap_index"
    if not rows:
        rows = _query_source_fallback(instance, terms, limit)
        search_mode = "source_fallback"
    for row in rows:
        source_root = row.pop("source_root", None)
        if source_root:
            row["source_path"] = str(Path(source_root) / row["relative_path"])
        if not row.get("markdown_path"):
            row.pop("markdown_path", None)
    return {
        "instance_id": instance.instance_id,
        "product_version": instance.product_version,
        "query": text,
        "search_mode": search_mode,
        "results": rows,
    }


def _query_source_fallback(instance: AdsInstance, terms: list[str], limit: int) -> list[dict[str, object]]:
    encoded_terms = [term.encode("utf-8", errors="ignore") for term in terms]
    results: list[dict[str, object]] = []
    for domain, root, path in _iter_html(instance):
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        lowered = raw.lower()
        if not all(term in lowered for term in encoded_terms):
            continue
        record = _page_record(domain, root, path)
        results.append(
            {
                "domain": record[0],
                "relative_path": record[2],
                "title": record[3],
                "snippet": record[4][:500],
                "source_path": str(path),
            }
        )
        if len(results) >= limit:
            break
    return results
