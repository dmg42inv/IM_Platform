"""Generate DGML graphs from the knowledge-base database.

DGML (Directed Graph Markup Language) opens directly in Visual Studio and the
VS Code DGML viewer. Two views are produced:

    transaction graph - documents + cross-document entities + amendment/version
                        lineage edges; each document labelled with its clause /
                        definition / obligation counts
    document graph    - one document's internal structure: clauses, defined
                        terms, obligations and named entities

Nodes and edges are read from the SQLite source of truth, so the visual graph
always reflects the authoritative data.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from xml.sax.saxutils import escape

DGML_NS = "http://schemas.microsoft.com/vs/2009/dgml"

CATEGORIES = {
    "Document": "#FF4E79A7",
    "Entity": "#FF59A14F",
    "Clause": "#FFF28E2B",
    "Recital": "#FFEDC948",
    "Definition": "#FFB07AA1",
    "Obligation": "#FFE15759",
    "Table": "#FF76B7B2",
}


def _node(node_id: str, label: str, category: str, extra: dict | None = None) -> str:
    attrs = f'Id="{escape(node_id, {chr(34): "&quot;"})}" Label="{escape(label, {chr(34): "&quot;"})}" Category="{category}"'
    for key, value in (extra or {}).items():
        attrs += f' {key}="{escape(str(value), {chr(34): "&quot;"})}"'
    return f"    <Node {attrs} />"


def _link(source: str, target: str, category: str, label: str = "") -> str:
    attrs = f'Source="{escape(source, {chr(34): "&quot;"})}" Target="{escape(target, {chr(34): "&quot;"})}" Category="{category}"'
    if label:
        attrs += f' Label="{escape(label, {chr(34): "&quot;"})}"'
    return f"    <Link {attrs} />"


def _wrap(nodes: list[str], links: list[str]) -> str:
    cats = "\n".join(
        f'    <Category Id="{name}" Background="{color}" />'
        for name, color in CATEGORIES.items()
    )
    return (
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<DirectedGraph xmlns="{DGML_NS}">\n'
        f'  <Nodes>\n' + "\n".join(nodes) + "\n  </Nodes>\n"
        f'  <Links>\n' + "\n".join(links) + "\n  </Links>\n"
        f'  <Categories>\n' + cats + "\n  </Categories>\n"
        f"</DirectedGraph>\n"
    )


def transaction_graph(conn: sqlite3.Connection, transaction_id: str,
                      min_entity_docs: int = 2) -> str:
    docs = conn.execute(
        """SELECT document_id, filename, doc_kind, document_status
           FROM documents WHERE transaction_id = ? AND extraction_status = 'extracted_text'""",
        (transaction_id,),
    ).fetchall()

    def count(table: str, document_id: str) -> int:
        return int(conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE document_id = ?", (document_id,)
        ).fetchone()[0])

    nodes: list[str] = []
    links: list[str] = []
    for document_id, filename, doc_kind, status in docs:
        clauses = int(conn.execute(
            "SELECT COUNT(*) FROM document_nodes WHERE document_id=? AND node_type IN ('clause','recital')",
            (document_id,)).fetchone()[0])
        defs = count("defined_terms", document_id)
        obs = count("obligations", document_id)
        facts = count("financial_facts", document_id)
        label = f"{filename}\n[{doc_kind} | {status}]\nclauses {clauses} · defs {defs} · obl {obs} · $ {facts}"
        nodes.append(_node(f"doc:{document_id}", label, "Document",
                           {"Kind": doc_kind, "Status": status}))

    # Cross-document entities (graph hubs).
    entity_rows = conn.execute(
        """SELECT text, COUNT(DISTINCT document_id) AS n
           FROM document_nodes
           WHERE transaction_id = ? AND node_type = 'entity' AND length(text) > 0
           GROUP BY lower(text) HAVING n >= ? ORDER BY n DESC LIMIT 60""",
        (transaction_id, min_entity_docs),
    ).fetchall()
    for name, _n in entity_rows:
        nodes.append(_node(f"entity:{name.lower()}", name, "Entity"))

    # Lineage edges.
    for src_type, src_id, dst_type, dst_id, relation in conn.execute(
        "SELECT src_type, src_id, dst_type, dst_id, relation FROM lineage_edges WHERE transaction_id = ?",
        (transaction_id,),
    ).fetchall():
        if src_type == "document" and dst_type == "document":
            links.append(_link(f"doc:{src_id}", f"doc:{dst_id}", "Amends", relation))
        elif src_type == "entity" and dst_type == "document":
            node_key = f"entity:{src_id.lower()}"
            if any(node_key in n for n in nodes):
                links.append(_link(node_key, f"doc:{dst_id}", "PartyOf", "party_of"))

    if not nodes:
        nodes.append(_node("empty", "No readable documents", "Document"))
    return _wrap(nodes, links)


def document_graph(conn: sqlite3.Connection, document_id: str, max_nodes: int = 400) -> str:
    row = conn.execute(
        "SELECT filename, doc_kind, document_status FROM documents WHERE document_id = ?",
        (document_id,)).fetchone()
    if not row:
        raise ValueError(f"Unknown document_id: {document_id}")
    filename, doc_kind, status = row
    nodes = [_node(f"doc:{document_id}", f"{filename}\n[{doc_kind} | {status}]", "Document")]
    links: list[str] = []

    clause_rows = conn.execute(
        """SELECT node_id, node_type, number, heading FROM document_nodes
           WHERE document_id = ? AND node_type IN ('clause','recital') ORDER BY char_start LIMIT ?""",
        (document_id, max_nodes)).fetchall()
    for node_id, node_type, number, heading in clause_rows:
        label = (number + " " + (heading or "")).strip() or "(clause)"
        cat = "Recital" if node_type == "recital" else "Clause"
        nodes.append(_node(f"node:{node_id}", label[:80], cat))
        links.append(_link(f"doc:{document_id}", f"node:{node_id}", "Contains"))

    for term_id, term, node_id in conn.execute(
        "SELECT term_id, term, node_id FROM defined_terms WHERE document_id = ? LIMIT ?",
        (document_id, max_nodes)).fetchall():
        nodes.append(_node(f"def:{term_id}", term[:60], "Definition"))
        parent = f"node:{node_id}" if node_id else f"doc:{document_id}"
        links.append(_link(parent, f"def:{term_id}", "Defines"))

    for ob_id, party, modality, node_id in conn.execute(
        "SELECT obligation_id, party, modality, node_id FROM obligations WHERE document_id = ? LIMIT ?",
        (document_id, max_nodes)).fetchall():
        nodes.append(_node(f"obl:{ob_id}", f"{party}: {modality}"[:60], "Obligation"))
        parent = f"node:{node_id}" if node_id else f"doc:{document_id}"
        links.append(_link(parent, f"obl:{ob_id}", "Obliges"))

    return _wrap(nodes, links)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate DGML graphs from the legal KB.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--transaction", type=str, default=None,
                        help="Build the transaction-level graph for this vehicle.")
    parser.add_argument("--document", type=str, default=None,
                        help="Build the internal graph for this document_id.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    conn = sqlite3.connect(str(args.db))
    try:
        if args.document:
            xml = document_graph(conn, args.document)
        elif args.transaction:
            xml = transaction_graph(conn, args.transaction)
        else:
            raise SystemExit("Provide --transaction or --document.")
    finally:
        conn.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(xml, encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
