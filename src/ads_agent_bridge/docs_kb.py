from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .models import AdsInstance
from .paths import docs_cache


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


def ensure_fast_index(instance: AdsInstance, force: bool = False) -> dict[str, object]:
    cache = docs_cache(instance.instance_id)
    db_path = cache / "fast-index.sqlite"
    manifest_path = cache / "manifest.json"
    current_fingerprint, file_count = fingerprint(instance)
    if not file_count:
        raise ValueError(f"No local HTML documentation found for {instance.product_version}.")
    if not force and db_path.is_file() and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("fingerprint") == current_fingerprint:
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
                        "INSERT OR REPLACE INTO pages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (domain, str(root), relative, path.stem, relative, stat.st_mtime_ns, stat.st_size, 0),
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
        "schema_version": 1,
        "instance_id": instance.instance_id,
        "product_version": instance.product_version,
        "fingerprint": current_fingerprint,
        "source_file_count": file_count,
        "indexed_file_count": indexed,
        "enriched_file_count": 0,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**manifest, "status": "ready", "reused": False, "db_path": str(db_path)}


def status(instance: AdsInstance) -> dict[str, object]:
    cache = docs_cache(instance.instance_id, ensure=False)
    manifest_path = cache / "manifest.json"
    db_path = cache / "fast-index.sqlite"
    if not manifest_path.is_file() or not db_path.is_file():
        return {"instance_id": instance.instance_id, "status": "missing"}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {**payload, "status": "ready", "db_path": str(db_path)}


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
    sql = f"SELECT domain, source_root, relative_path, title, substr(content, 1, 500) AS snippet FROM pages WHERE {where} LIMIT ?"
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
