"""Enrich the knowledge base with each document's clean (reorganised) path.

The KB was indexed from the original archive paths; the reorg produced a clean
foldered layout. This adds a `clean_path` to every document so citations can be
shown against the new structure (e.g. '0_Equity/Oxford Nanopore/
10_Exit_and_Public_Markets/ONT IPO Prospectus.pdf'). Pure metadata - no
re-extraction, the graph/vectors/BM25 are unchanged.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

if __package__:
    from .apply_reorg import NAME_MAP
    from .reorg_proposal import build_proposal
else:  # pragma: no cover
    from apply_reorg import NAME_MAP
    from reorg_proposal import build_proposal


def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})"))


def reindex(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    if not _has_column(conn, "documents", "clean_path"):
        conn.execute("ALTER TABLE documents ADD COLUMN clean_path TEXT")

    txns = conn.execute("SELECT transaction_id, folder_path FROM transactions").fetchall()
    updated = 0
    for tid, folder_path in txns:
        category = "1_Funds" if "1_F_U_N_D" in folder_path else "0_Equity"
        name = NAME_MAP.get(tid, tid)
        for r in build_proposal(db_path, tid):
            rel = r["original_path"]
            if "__unzipped" in rel.lower():
                clean = f"{category}/{name}/(inside archive) {rel}"
            else:
                clean = f"{category}/{name}/{r['proposed_bucket']}/{r['filename']}"
            conn.execute(
                "UPDATE documents SET clean_path = ? WHERE transaction_id = ? AND relative_path = ?",
                (clean, tid, rel))
            updated += 1
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM documents WHERE clean_path IS NOT NULL").fetchone()[0]
    conn.close()
    return {"updated": updated, "documents_with_clean_path": total}


def main() -> int:
    parser = argparse.ArgumentParser(description="Add clean reorganised paths to the KB documents.")
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    import json
    print(json.dumps(reindex(args.db), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
