"""Stage 1 of the evidence coverage audit: discover every source file and hash it.

The manifest records only facts about files - path, size, modification time, SHA-256. It does
not classify entity, document type or period; those are derived judgements and belong in a
later stage where the rule that produced them can be recorded alongside the value.

Reading a OneDrive placeholder forces hydration, so hashing a cloud-only file downloads it.
`cloud_state` records what the file was at scan time, which is the only chance to observe it.

The run is resumable: a file already hashed at the same size and modification time is skipped,
so an interrupted run can simply be restarted.

    .\\.venv\\Scripts\\python.exe -m scripts.evidence_audit.manifest --scan
    .\\.venv\\Scripts\\python.exe -m scripts.evidence_audit.manifest --scan --skip-cloud
    .\\.venv\\Scripts\\python.exe -m scripts.evidence_audit.manifest --report
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import os
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "data" / "evidence" / "audit.sqlite"

DEFAULT_ROOTS = [
    Path(r"C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.1 SPPM ###"),
    Path(r"C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.2 Portfolio Management - Monthly"),
]

DOCUMENT_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".xlsm", ".pptx", ".ppt",
    ".msg", ".eml", ".csv", ".txt",
}

SKIP_DIRECTORIES = {".git", "node_modules", "__pycache__", ".venv", "$recycle.bin"}

# OneDrive placeholders carry these; reading such a file triggers a download.
_OFFLINE = 0x1000
_RECALL_ON_OPEN = 0x40000
_RECALL_ON_DATA_ACCESS = 0x400000
_get_attributes = ctypes.windll.kernel32.GetFileAttributesW  # type: ignore[attr-defined]

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    source_id      TEXT PRIMARY KEY,
    full_path      TEXT NOT NULL UNIQUE,
    root           TEXT NOT NULL,
    relative_path  TEXT NOT NULL,
    filename       TEXT NOT NULL,
    extension      TEXT NOT NULL,
    size_bytes     INTEGER,
    modified_utc   TEXT,
    cloud_state    TEXT,
    sha256         TEXT,
    hash_status    TEXT NOT NULL,
    hash_error     TEXT,
    hashed_at      TEXT,
    first_seen_utc TEXT,
    last_scan_utc  TEXT
);
CREATE INDEX IF NOT EXISTS ix_sources_sha ON sources(sha256);
CREATE INDEX IF NOT EXISTS ix_sources_status ON sources(hash_status);
CREATE INDEX IF NOT EXISTS ix_sources_name ON sources(filename);

CREATE TABLE IF NOT EXISTS scan_runs (
    run_id       TEXT PRIMARY KEY,
    started_utc  TEXT,
    finished_utc TEXT,
    roots        TEXT,
    files_seen   INTEGER,
    bytes_hashed INTEGER,
    hashed       INTEGER,
    skipped      INTEGER,
    errors       INTEGER,
    note         TEXT
);
"""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def long_path(path: str) -> str:
    return path if path.startswith("\\\\?\\") else "\\\\?\\" + path


def cloud_state(path: str) -> str:
    attrs = _get_attributes(long_path(path))
    if attrs == -1:
        return "unknown"
    if attrs & (_OFFLINE | _RECALL_ON_OPEN | _RECALL_ON_DATA_ACCESS):
        return "cloud_only"
    return "local"


def sha256_of(path: str, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(long_path(path), "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def source_id_for(path: str) -> str:
    return hashlib.sha256(os.path.normcase(path).encode("utf-8")).hexdigest()[:24]


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    return conn


def walk_documents(roots: list[Path]):
    for root in roots:
        root_str = str(root)
        for dirpath, dirnames, filenames in os.walk(long_path(root_str)):
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRECTORIES]
            for name in filenames:
                if name.startswith("~$") or name.startswith("."):
                    continue
                if os.path.splitext(name)[1].lower() not in DOCUMENT_EXTENSIONS:
                    continue
                full = os.path.join(dirpath, name).replace("\\\\?\\", "", 1)
                yield root_str, full, name


def scan(conn: sqlite3.Connection, roots: list[Path], skip_cloud: bool,
         progress_every: int, limit: int | None) -> dict:
    run_id = uuid.uuid4().hex[:12]
    started = now_utc()
    conn.execute("INSERT INTO scan_runs (run_id, started_utc, roots) VALUES (?,?,?)",
                 (run_id, started, " | ".join(str(r) for r in roots)))
    conn.commit()

    existing = {
        row[0]: (row[1], row[2], row[3])
        for row in conn.execute("SELECT source_id, sha256, size_bytes, modified_utc FROM sources")
    }

    seen = hashed = skipped = errors = 0
    bytes_hashed = 0
    started_at = time.time()

    for root_str, full, name in walk_documents(roots):
        seen += 1
        if limit and seen > limit:
            break
        sid = source_id_for(full)
        try:
            stat = os.stat(long_path(full))
            size = stat.st_size
            modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds")
        except OSError as exc:
            conn.execute(
                "INSERT INTO sources (source_id, full_path, root, relative_path, filename, extension,"
                " hash_status, hash_error, first_seen_utc, last_scan_utc)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(source_id) DO UPDATE SET hash_status='error', hash_error=excluded.hash_error,"
                " last_scan_utc=excluded.last_scan_utc",
                (sid, full, root_str, os.path.relpath(full, root_str), name,
                 os.path.splitext(name)[1].lower(), "error", f"stat: {exc}", now_utc(), now_utc()))
            errors += 1
            continue

        prior = existing.get(sid)
        if prior and prior[0] and prior[1] == size and prior[2] == modified:
            conn.execute("UPDATE sources SET last_scan_utc=? WHERE source_id=?", (now_utc(), sid))
            skipped += 1
        else:
            state = cloud_state(full)
            if skip_cloud and state == "cloud_only":
                digest, status, error = None, "pending_hydration", None
            else:
                try:
                    digest, status, error = sha256_of(full), "hashed", None
                    bytes_hashed += size
                    hashed += 1
                except OSError as exc:
                    digest, status, error = None, "error", f"read: {exc}"
                    errors += 1
            conn.execute(
                "INSERT INTO sources (source_id, full_path, root, relative_path, filename, extension,"
                " size_bytes, modified_utc, cloud_state, sha256, hash_status, hash_error, hashed_at,"
                " first_seen_utc, last_scan_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(source_id) DO UPDATE SET size_bytes=excluded.size_bytes,"
                " modified_utc=excluded.modified_utc, cloud_state=excluded.cloud_state,"
                " sha256=excluded.sha256, hash_status=excluded.hash_status,"
                " hash_error=excluded.hash_error, hashed_at=excluded.hashed_at,"
                " last_scan_utc=excluded.last_scan_utc",
                (sid, full, root_str, os.path.relpath(full, root_str), name,
                 os.path.splitext(name)[1].lower(), size, modified, state, digest, status, error,
                 now_utc() if digest else None, now_utc(), now_utc()))

        if seen % progress_every == 0:
            conn.commit()
            elapsed = max(time.time() - started_at, 0.001)
            print(f"  {seen:>7,} seen | {hashed:>7,} hashed | {skipped:>6,} skipped | "
                  f"{errors:>4,} errors | {bytes_hashed/1e9:6.2f} GB | "
                  f"{bytes_hashed/1e6/elapsed:5.1f} MB/s", flush=True)

    conn.commit()
    conn.execute(
        "UPDATE scan_runs SET finished_utc=?, files_seen=?, bytes_hashed=?, hashed=?, skipped=?,"
        " errors=? WHERE run_id=?",
        (now_utc(), seen, bytes_hashed, hashed, skipped, errors, run_id))
    conn.commit()
    return {"run_id": run_id, "seen": seen, "hashed": hashed, "skipped": skipped,
            "errors": errors, "bytes_hashed": bytes_hashed}


def report(conn: sqlite3.Connection) -> None:
    total, = conn.execute("SELECT COUNT(*) FROM sources").fetchone()
    print(f"\n  files in manifest           {total:>8,}")
    for status, count, size in conn.execute(
            "SELECT hash_status, COUNT(*), COALESCE(SUM(size_bytes),0) FROM sources"
            " GROUP BY 1 ORDER BY 2 DESC"):
        print(f"    {status:<22} {count:>8,}   {size/1e9:6.2f} GB")

    unique, = conn.execute("SELECT COUNT(DISTINCT sha256) FROM sources WHERE sha256 IS NOT NULL").fetchone()
    hashed, = conn.execute("SELECT COUNT(*) FROM sources WHERE sha256 IS NOT NULL").fetchone()
    print(f"\n  hashed files                {hashed:>8,}")
    print(f"  unique after deduplication  {unique:>8,}")
    print(f"  duplicate copies            {hashed - unique:>8,}")

    dupe_bytes, = conn.execute(
        "SELECT COALESCE(SUM(extra),0) FROM (SELECT (COUNT(*)-1)*MIN(size_bytes) AS extra"
        " FROM sources WHERE sha256 IS NOT NULL GROUP BY sha256 HAVING COUNT(*)>1)").fetchone()
    print(f"  space held by duplicates    {dupe_bytes/1e9:>8.2f} GB")

    print("\n  cloud state observed at scan time")
    for state, count in conn.execute(
            "SELECT COALESCE(cloud_state,'n/a'), COUNT(*) FROM sources GROUP BY 1 ORDER BY 2 DESC"):
        print(f"    {state:<22} {count:>8,}")

    print("\n  largest duplicate groups")
    for sha, count, name, size in conn.execute(
            "SELECT sha256, COUNT(*), MIN(filename), MIN(size_bytes) FROM sources"
            " WHERE sha256 IS NOT NULL GROUP BY sha256 HAVING COUNT(*)>1"
            " ORDER BY COUNT(*) DESC LIMIT 8"):
        print(f"    {count:>3} x  {size/1e6:7.1f} MB  {sha[:12]}  {name[:60]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--root", type=Path, action="append", dest="roots")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--skip-cloud", action="store_true",
                        help="Record cloud-only files as pending_hydration instead of downloading them")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--progress-every", type=int, default=500)
    args = parser.parse_args()

    roots = args.roots or DEFAULT_ROOTS
    missing = [r for r in roots if not r.exists()]
    if missing:
        for r in missing:
            print(f"  root not found: {r}", file=sys.stderr)
        return 2

    conn = connect(args.db)
    try:
        if args.scan:
            print(f"Scanning {len(roots)} root(s) into {args.db}")
            result = scan(conn, roots, args.skip_cloud, args.progress_every, args.limit)
            print(f"\nRun {result['run_id']}: {result['seen']:,} seen, {result['hashed']:,} hashed, "
                  f"{result['skipped']:,} unchanged, {result['errors']:,} errors, "
                  f"{result['bytes_hashed']/1e9:.2f} GB read.")
        if args.report or not args.scan:
            report(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
