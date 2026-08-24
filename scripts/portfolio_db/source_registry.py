"""Registry of source-of-truth files, so every ingested figure is traceable.

Each source file (monthly tracker, cashflow workbook, descriptive/domicile
reference, legal-KB database, ...) is recorded once with a SHA-256 content
hash, size and modified time. Data rows elsewhere in the database carry the
returned `source_id`, so any number shown in the app can be traced back to the
exact file - and the hash lets us prove the file has not changed since ingest.
Nothing is estimated; this is the audit backbone for the "never approximate"
reporting rule.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

SOURCES_DDL = """
CREATE TABLE IF NOT EXISTS sources (
    source_id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT,
    path TEXT UNIQUE,
    filename TEXT,
    month_id TEXT,
    version TEXT,
    sha256 TEXT,
    size_bytes INTEGER,
    source_mtime TEXT,
    ingested_at TEXT
);
"""


def ensure_sources_table(conn: sqlite3.Connection) -> None:
    conn.execute(SOURCES_DDL)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def register_source(
    conn: sqlite3.Connection,
    path: Path,
    kind: str,
    *,
    hash_path: Path | None = None,
    month_id: str | None = None,
    version: str | None = None,
) -> tuple[int, str]:
    """Upsert a source file (keyed by its original path); return (source_id, status).

    `status` is 'new' (path not seen before), 'changed' (content hash differs
    from what we last ingested) or 'unchanged'. `path` is the authoritative
    location recorded for provenance; `hash_path` (if given) is the file
    actually read - e.g. a local copy of a cloud file - whose bytes are hashed.
    They are byte-identical, so the hash still proves the ingested content.
    """
    path = Path(path)
    to_hash = Path(hash_path) if hash_path is not None else path
    stat = to_hash.stat()
    digest = sha256_of(to_hash)
    now = datetime.now().isoformat(timespec="seconds")
    existing = conn.execute("SELECT sha256 FROM sources WHERE path = ?", (str(path),)).fetchone()
    if existing is None:
        status = "new"
    elif existing[0] != digest:
        status = "changed"
    else:
        status = "unchanged"
    conn.execute(
        """INSERT INTO sources
           (kind, path, filename, month_id, version, sha256, size_bytes,
            source_mtime, ingested_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(path) DO UPDATE SET
             kind=excluded.kind, filename=excluded.filename,
             month_id=excluded.month_id, version=excluded.version,
             sha256=excluded.sha256, size_bytes=excluded.size_bytes,
             source_mtime=excluded.source_mtime, ingested_at=excluded.ingested_at""",
        (kind, str(path), path.name, month_id, version, digest, stat.st_size,
         datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"), now),
    )
    row = conn.execute("SELECT source_id FROM sources WHERE path = ?", (str(path),)).fetchone()
    return int(row[0]), status


def register_reference_sources(conn: sqlite3.Connection, repo_root: Path) -> int:
    """Register the other source-of-truth artefacts in the repo (descriptive
    facts, grounded domicile, cashflow source, legal-KB DB) so the registry is
    a complete inventory. Returns the count registered."""
    candidates = [
        ("descriptive_facts", repo_root / "data/source_of_truth/company_descriptive_facts.json"),
        ("domicile_legal", repo_root / "data/source_of_truth/company_domicile_legal.json"),
        ("cashflow_source", repo_root / "data/source_of_truth/Cashflow_SourceOfTruth_2026-07-31.xlsx"),
        ("snapshot_history", repo_root / "data/source_of_truth/Portfolio_Snapshot_History.xlsx"),
        ("legal_kb_db", repo_root / "data/legal_kb/legal_kb.sqlite"),
    ]
    count = 0
    for kind, path in candidates:
        if path.exists():
            register_source(conn, path, kind)  # returns (id, status); status unused here
            count += 1
    return count
