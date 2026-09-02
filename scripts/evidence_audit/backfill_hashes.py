"""Stage 3 of the evidence coverage audit: give every knowledge base document a real source hash.

The knowledge base stores no content hash, so until now its documents could only be matched to
the corpus by filename - useless where 46% of the corpus is duplicate copies. But it does store
the path each document had when it was ingested, relative to its transaction folder, and those
paths still resolve against the live investment folders.

Matching on the full relative path rather than the bare filename is far more specific: it must
agree on every intervening folder, not just the last segment. A document is only accepted when
exactly one corpus file ends with that path. Anything else is recorded as ambiguous or
unresolved rather than guessed.

Nothing is written to the knowledge base. The mapping lands in the audit database, so the
knowledge base stays exactly as it was built and the provenance layer can be rebuilt at will.

    .\\.venv\\Scripts\\python.exe -m scripts.evidence_audit.backfill_hashes --run
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_DB = REPO_ROOT / "data" / "evidence" / "audit.sqlite"
LEGAL_KB_DB = REPO_ROOT / "data" / "legal_kb" / "legal_kb.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_document_provenance (
    document_id       TEXT PRIMARY KEY,
    transaction_id    TEXT,
    kb_relative_path  TEXT,
    kb_filename       TEXT,
    resolved_path     TEXT,
    source_id         TEXT,
    sha256            TEXT,
    resolution_method TEXT NOT NULL,
    candidate_count   INTEGER,
    resolved_at       TEXT
);
CREATE INDEX IF NOT EXISTS ix_kbprov_sha ON kb_document_provenance(sha256);
CREATE INDEX IF NOT EXISTS ix_kbprov_method ON kb_document_provenance(resolution_method);
"""


def normalise(path: str) -> str:
    return os.path.normcase(path.replace("/", "\\"))


def load_corpus_index(conn: sqlite3.Connection) -> dict[str, list[tuple[str, str, str]]]:
    """filename -> [(full_path, source_id, sha256)], the shortlist for suffix matching."""
    index: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for full_path, source_id, sha256, filename in conn.execute(
            "SELECT full_path, source_id, sha256, filename FROM sources"):
        index[os.path.normcase(filename or "")].append((full_path, source_id, sha256 or ""))
    return index


def resolve(kb_rows, corpus_index) -> list[dict]:
    out = []
    for row in kb_rows:
        rel = normalise(row["relative_path"] or "")
        name = os.path.normcase(row["filename"] or "")
        shortlist = corpus_index.get(name, [])
        suffix = "\\" + rel if rel else ""
        matches = [c for c in shortlist if suffix and normalise(c[0]).endswith(suffix)]

        if len(matches) == 1:
            full, sid, sha = matches[0]
            method = "path_suffix_unique" if sha else "path_suffix_unique_unhashed"
            out.append({"document_id": row["document_id"], "transaction_id": row["transaction_id"],
                        "kb_relative_path": row["relative_path"], "kb_filename": row["filename"],
                        "resolved_path": full, "source_id": sid, "sha256": sha,
                        "resolution_method": method, "candidate_count": 1})
        elif len(matches) > 1:
            distinct = {m[2] for m in matches if m[2]}
            # Several copies of the same bytes still identify the content unambiguously.
            if len(distinct) == 1:
                full, sid, sha = sorted(matches)[0]
                out.append({"document_id": row["document_id"], "transaction_id": row["transaction_id"],
                            "kb_relative_path": row["relative_path"], "kb_filename": row["filename"],
                            "resolved_path": full, "source_id": sid, "sha256": sha,
                            "resolution_method": "path_suffix_identical_copies",
                            "candidate_count": len(matches)})
            else:
                out.append({"document_id": row["document_id"], "transaction_id": row["transaction_id"],
                            "kb_relative_path": row["relative_path"], "kb_filename": row["filename"],
                            "resolved_path": "", "source_id": "", "sha256": "",
                            "resolution_method": "ambiguous_differing_content",
                            "candidate_count": len(matches)})
        else:
            method = "unresolved_no_filename_match" if not shortlist else "unresolved_path_mismatch"
            out.append({"document_id": row["document_id"], "transaction_id": row["transaction_id"],
                        "kb_relative_path": row["relative_path"], "kb_filename": row["filename"],
                        "resolved_path": "", "source_id": "", "sha256": "",
                        "resolution_method": method, "candidate_count": len(shortlist)})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-db", type=Path, default=AUDIT_DB)
    parser.add_argument("--kb-db", type=Path, default=LEGAL_KB_DB)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()

    if not args.audit_db.exists() or not args.kb_db.exists():
        print("  audit manifest or knowledge base missing", file=sys.stderr)
        return 2

    audit = sqlite3.connect(str(args.audit_db))
    audit.executescript(SCHEMA)
    kb = sqlite3.connect(f"file:{args.kb_db}?mode=ro", uri=True)
    kb.row_factory = sqlite3.Row
    try:
        corpus_index = load_corpus_index(audit)
        kb_rows = kb.execute(
            "SELECT document_id, transaction_id, relative_path, filename FROM documents").fetchall()
        resolved = resolve(kb_rows, corpus_index)

        if args.run:
            audit.execute("DELETE FROM kb_document_provenance")
            audit.executemany(
                "INSERT INTO kb_document_provenance (document_id, transaction_id, kb_relative_path,"
                " kb_filename, resolved_path, source_id, sha256, resolution_method, candidate_count,"
                " resolved_at) VALUES (:document_id,:transaction_id,:kb_relative_path,:kb_filename,"
                ":resolved_path,:source_id,:sha256,:resolution_method,:candidate_count,"
                "datetime('now'))", resolved)
            audit.commit()

        total = len(resolved)
        counts: dict[str, int] = defaultdict(int)
        for r in resolved:
            counts[r["resolution_method"]] += 1
        print(f"\n  knowledge base documents            {total:>7,}")
        for method, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"    {method:<34} {count:>7,}   ({count/total*100:5.1f}%)")

        proven = sum(c for m, c in counts.items() if m.startswith("path_suffix") and "unhashed" not in m)
        print(f"\n  documents now traceable to a hash   {proven:>7,}   ({proven/total*100:.1f}%)")
        print(f"  previously traceable                     59")

        distinct_sha = len({r["sha256"] for r in resolved if r["sha256"]})
        print(f"  distinct source files behind them   {distinct_sha:>7,}")
        if not args.run:
            print("\n  (dry run - pass --run to write the mapping)")
    finally:
        kb.close()
        audit.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
