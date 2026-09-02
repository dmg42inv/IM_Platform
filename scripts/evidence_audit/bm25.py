"""Stage 4 of the evidence coverage audit: a BM25 index over citation-bearing nodes.

Vector search finds text that means something similar. It is poor at exactly the things this
corpus turns on - a fund's legal name, a clause number, a date, a defined term. BM25 is the
complement, and until now it did not exist anywhere in the stack.

The index is built in its own database rather than inside the knowledge base, so the 584 MB
store that was originally ingested is never mutated and the index can be dropped and rebuilt at
will. Each chunk carries the source hash resolved in stage 3, so a search hit resolves to a
specific physical file rather than to a filename that may describe several.

    .\\.venv\\Scripts\\python.exe -m scripts.evidence_audit.bm25 --build
    .\\.venv\\Scripts\\python.exe -m scripts.evidence_audit.bm25 --query "recallable distribution"
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL_KB_DB = REPO_ROOT / "data" / "legal_kb" / "legal_kb.sqlite"
AUDIT_DB = REPO_ROOT / "data" / "evidence" / "audit.sqlite"
BM25_DB = REPO_ROOT / "data" / "evidence" / "bm25.sqlite"

SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS node_search USING fts5(
    heading,
    body,
    node_id UNINDEXED,
    document_id UNINDEXED,
    transaction_id UNINDEXED,
    sha256 UNINDEXED,
    filename UNINDEXED,
    node_type UNINDEXED,
    number UNINDEXED,
    char_start UNINDEXED,
    tokenize = "unicode61 remove_diacritics 2"
);
CREATE TABLE IF NOT EXISTS build_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    built_utc TEXT, nodes_indexed INTEGER, nodes_skipped INTEGER,
    documents INTEGER, with_source_hash INTEGER, seconds REAL
);
"""


def build(batch_size: int, progress_every: int) -> None:
    if not LEGAL_KB_DB.exists():
        raise SystemExit("legal knowledge base not found")

    BM25_DB.parent.mkdir(parents=True, exist_ok=True)
    out = sqlite3.connect(str(BM25_DB))
    out.executescript(SCHEMA)
    out.execute("DELETE FROM node_search")
    out.commit()
    out.execute("PRAGMA journal_mode=WAL")
    out.execute("PRAGMA synchronous=OFF")

    provenance: dict[str, str] = {}
    if AUDIT_DB.exists():
        audit = sqlite3.connect(f"file:{AUDIT_DB}?mode=ro", uri=True)
        try:
            provenance = {r[0]: r[1] for r in audit.execute(
                "SELECT document_id, sha256 FROM kb_document_provenance WHERE sha256 <> ''")}
        except sqlite3.OperationalError:
            provenance = {}
        finally:
            audit.close()
    print(f"  source hashes available for {len(provenance):,} documents", flush=True)

    kb = sqlite3.connect(f"file:{LEGAL_KB_DB}?mode=ro", uri=True)
    kb.row_factory = sqlite3.Row
    filenames = {r["document_id"]: r["filename"] for r in kb.execute(
        "SELECT document_id, filename FROM documents")}

    started = time.time()
    indexed = skipped = 0
    seen_docs: set[str] = set()
    with_hash = 0
    batch: list[tuple] = []

    cursor = kb.execute(
        "SELECT node_id, document_id, transaction_id, node_type, number, heading, char_start, text"
        " FROM document_nodes")
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        for r in rows:
            body = (r["text"] or "").strip()
            if not body:
                skipped += 1
                continue
            sha = provenance.get(r["document_id"], "")
            if sha:
                with_hash += 1
            seen_docs.add(r["document_id"])
            batch.append((r["heading"] or "", body, r["node_id"], r["document_id"],
                          r["transaction_id"] or "", sha, filenames.get(r["document_id"], ""),
                          r["node_type"] or "", str(r["number"] or ""), r["char_start"] or 0))
            indexed += 1
        out.executemany(
            "INSERT INTO node_search (heading, body, node_id, document_id, transaction_id, sha256,"
            " filename, node_type, number, char_start) VALUES (?,?,?,?,?,?,?,?,?,?)", batch)
        batch.clear()
        out.commit()
        if indexed % progress_every < batch_size:
            elapsed = max(time.time() - started, 0.001)
            print(f"    {indexed:>7,} nodes indexed | {skipped:>5,} empty | "
                  f"{indexed/elapsed:6.0f} nodes/s", flush=True)

    print("  optimising the index...", flush=True)
    out.execute("INSERT INTO node_search(node_search) VALUES('optimize')")
    out.commit()
    seconds = time.time() - started
    out.execute(
        "INSERT INTO build_runs (built_utc, nodes_indexed, nodes_skipped, documents,"
        " with_source_hash, seconds) VALUES (datetime('now'),?,?,?,?,?)",
        (indexed, skipped, len(seen_docs), with_hash, seconds))
    out.commit()
    kb.close()
    out.close()

    size = BM25_DB.stat().st_size / 1e6
    print(f"\n  indexed {indexed:,} nodes from {len(seen_docs):,} documents in {seconds:,.0f}s")
    print(f"  {with_hash:,} nodes carry a source hash ({with_hash/max(indexed,1)*100:.1f}%)")
    print(f"  {skipped:,} nodes skipped as empty")
    print(f"  index size {size:,.0f} MB at {BM25_DB}")


_FTS_OPERATORS = ("AND", "OR", "NOT", "NEAR")


def as_fts_query(text: str) -> str:
    """Quote plain search text. Unquoted hyphens and colons are FTS5 operators, so a fund's
    legal name is rejected as a syntax error rather than searched for."""
    stripped = text.strip()
    if not stripped:
        return '""'
    if any(f" {op} " in stripped for op in _FTS_OPERATORS) or '"' in stripped:
        return stripped
    return " ".join('"' + token.replace('"', '""') + '"' for token in stripped.split())


def query(text: str, limit: int) -> None:
    if not BM25_DB.exists():
        raise SystemExit("BM25 index not built yet")
    conn = sqlite3.connect(f"file:{BM25_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    expression = as_fts_query(text)
    try:
        rows = conn.execute(
            "SELECT bm25(node_search) AS score, transaction_id, filename, heading, number,"
            " sha256, node_id, snippet(node_search, 1, '[', ']', ' ... ', 18) AS extract"
            " FROM node_search WHERE node_search MATCH ? ORDER BY score LIMIT ?",
            (expression, limit)).fetchall()
    except sqlite3.OperationalError as exc:
        raise SystemExit(f"query rejected: {exc}")
    if not rows:
        print(f"  no matches for {text!r}")
        return
    print(f"\n  {len(rows)} match(es) for {text!r}\n")
    for r in rows:
        traceable = f"sha {r['sha256'][:12]}" if r["sha256"] else "NO SOURCE HASH"
        print(f"  [{r['score']:7.3f}] {r['transaction_id'] or '?':<24} {traceable}")
        print(f"            {(r['filename'] or '')[:78]}")
        if r["heading"]:
            print(f"            heading: {r['heading'][:70]}")
        print(f"            {r['extract'][:190].replace(chr(10), ' ')}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--query", type=str, default=None)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--progress-every", type=int, default=10000)
    args = parser.parse_args()

    if args.build:
        build(args.batch_size, args.progress_every)
    if args.query:
        query(args.query, args.limit)
    if not args.build and not args.query:
        parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
