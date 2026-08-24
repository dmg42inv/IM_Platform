"""Finalise the clean sandbox: give every deal a self-contained knowledge index.

For each transaction it writes, into <clean deal>/00_Knowledge_Base/:
    <Name>.dgml   - the deal's DGML visual graph (documents + entities +
                    amendment/version lineage), openable in Visual Studio / VS Code
    README.txt    - node/citation/embedding counts + how to query the central KB

The heavy KB (vectors, full graph) stays in the single central database; this
just attaches a lightweight, self-describing index to each clean folder.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

if __package__:
    from . import dgml_export
    from .apply_reorg import NAME_MAP, long_path
else:  # pragma: no cover
    import dgml_export
    from apply_reorg import NAME_MAP, long_path


def _count(conn, sql, tid):
    return int(conn.execute(sql, (tid,)).fetchone()[0])


def finalize(db_path: Path, dest_base: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    txns = conn.execute("SELECT transaction_id, folder_path FROM transactions").fetchall()
    results = []
    for tid, folder_path in txns:
        category = "1_Funds" if "1_F_U_N_D" in folder_path else "0_Equity"
        name = NAME_MAP.get(tid, tid)
        kb_dir = dest_base / category / name / "00_Knowledge_Base"
        os.makedirs(long_path(str(kb_dir)), exist_ok=True)

        xml = dgml_export.transaction_graph(conn, tid)
        dgml_path = kb_dir / f"{name}.dgml"
        with open(long_path(str(dgml_path)), "w", encoding="utf-8") as h:
            h.write(xml)

        docs = _count(conn, "SELECT COUNT(*) FROM documents WHERE transaction_id=?", tid)
        readable = _count(conn, "SELECT COUNT(*) FROM documents WHERE transaction_id=? AND extraction_status='extracted_text'", tid)
        nodes = _count(conn, "SELECT COUNT(*) FROM document_nodes WHERE transaction_id=?", tid)
        cites = _count(conn, "SELECT COUNT(*) FROM citations WHERE transaction_id=?", tid)
        edges = _count(conn, "SELECT COUNT(*) FROM lineage_edges WHERE transaction_id=?", tid)
        emb = int(conn.execute(
            "SELECT COUNT(*) FROM embeddings e JOIN documents d ON d.document_id=e.document_id WHERE d.transaction_id=?",
            (tid,)).fetchone()[0])

        readme = (
            f"KNOWLEDGE BASE INDEX - {name}\n"
            f"{'='*50}\n\n"
            f"Documents      : {docs} ({readable} fully read)\n"
            f"Graph nodes    : {nodes}\n"
            f"Citations      : {cites}\n"
            f"Lineage edges  : {edges}\n"
            f"Embeddings     : {emb}\n\n"
            f"Visual graph   : {name}.dgml (open in Visual Studio / VS Code DGML viewer)\n\n"
            f"The full searchable knowledge base (all deals) lives in the central database:\n"
            f"    data/legal_kb/legal_kb.sqlite\n\n"
            f"Ask a grounded, cited question about this deal:\n"
            f'    python -m scripts.legal_kb.query --db data/legal_kb/legal_kb.sqlite '
            f'--transaction {tid} --query "your question"\n'
        )
        with open(long_path(str(kb_dir / "README.txt")), "w", encoding="utf-8") as h:
            h.write(readme)

        results.append({"name": name, "dgml": str(dgml_path.name), "nodes": nodes, "embeddings": emb})
        print(f"[ok]   {name:34} dgml + README  (nodes={nodes}, emb={emb})")

    conn.close()
    return {"deals": len(results), "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Attach a self-contained KB index to each clean deal folder.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--dest-base", type=Path, required=True)
    args = parser.parse_args()
    import json
    print(json.dumps(finalize(args.db, args.dest_base), indent=2)[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
