"""SQLite source-of-truth database for the legal knowledge base.

This database - not the vector or keyword index - is the authoritative record.
Schema (aligned to the agreed spec):

    documents        - one row per file (every file, incl. blocked ones)
    document_nodes   - structural graph nodes: clauses/sections, entities, tables
    defined_terms    - '"Term" means ...' definitions, linked to their node
    obligations      - modal ("shall"/"must") statements, linked to their node
    financial_facts  - monetary amounts (value + currency + kind), linked to node
    citations        - one canonical citation per node (doc + clause + status)
    lineage_edges    - version / amendment / shared-party / entity edges
    dates            - notable dates (supporting, for date filtering)
    embeddings       - per-node vector (retrieval aid only; not truth)

Ingest is idempotent per document: re-ingesting replaces that document's rows.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY,
    name           TEXT,
    folder_path    TEXT,
    created_utc    TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    document_id       TEXT PRIMARY KEY,
    transaction_id    TEXT NOT NULL REFERENCES transactions(transaction_id),
    relative_path     TEXT NOT NULL,
    filename          TEXT,
    extension         TEXT,
    doc_kind          TEXT,
    category          TEXT,
    extraction_status TEXT,
    document_status   TEXT,
    status_evidence   TEXT,
    char_count        INTEGER,
    content_hash      TEXT,
    mojibake_flag     INTEGER DEFAULT 0,
    ingested_utc      TEXT
);

CREATE TABLE IF NOT EXISTS document_nodes (
    node_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id    TEXT NOT NULL REFERENCES documents(document_id),
    transaction_id TEXT NOT NULL,
    node_type      TEXT NOT NULL,      -- clause | recital | entity | table
    number         TEXT,
    heading        TEXT,
    level          INTEGER,
    char_start     INTEGER,
    char_end       INTEGER,
    text           TEXT
);

CREATE TABLE IF NOT EXISTS defined_terms (
    term_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    node_id     INTEGER REFERENCES document_nodes(node_id),
    term        TEXT,
    definition  TEXT,
    char_start  INTEGER
);

CREATE TABLE IF NOT EXISTS obligations (
    obligation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id   TEXT NOT NULL REFERENCES documents(document_id),
    node_id       INTEGER REFERENCES document_nodes(node_id),
    party         TEXT,
    modality      TEXT,
    text          TEXT,
    char_start    INTEGER
);

CREATE TABLE IF NOT EXISTS financial_facts (
    fact_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    node_id     INTEGER REFERENCES document_nodes(node_id),
    raw         TEXT,
    amount      REAL,
    currency    TEXT,
    unit        TEXT,
    kind        TEXT,
    context     TEXT,
    char_start  INTEGER
);

CREATE TABLE IF NOT EXISTS citations (
    citation_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id         INTEGER NOT NULL REFERENCES document_nodes(node_id),
    document_id     TEXT NOT NULL REFERENCES documents(document_id),
    transaction_id  TEXT NOT NULL,
    citation_text   TEXT,
    section_ref     TEXT,
    document_status TEXT,
    char_start      INTEGER,
    char_end        INTEGER
);

CREATE TABLE IF NOT EXISTS lineage_edges (
    edge_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT NOT NULL,
    src_type       TEXT,
    src_id         TEXT,
    dst_type       TEXT,
    dst_id         TEXT,
    relation       TEXT,
    evidence       TEXT
);

CREATE TABLE IF NOT EXISTS dates (
    date_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    value       TEXT,
    role        TEXT
);

CREATE TABLE IF NOT EXISTS embeddings (
    embedding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id      INTEGER NOT NULL REFERENCES document_nodes(node_id),
    document_id  TEXT NOT NULL REFERENCES documents(document_id),
    model        TEXT,
    dim          INTEGER,
    vector       BLOB
);

CREATE INDEX IF NOT EXISTS idx_documents_tx ON documents(transaction_id);
CREATE INDEX IF NOT EXISTS idx_nodes_doc ON document_nodes(document_id);
CREATE INDEX IF NOT EXISTS idx_nodes_tx ON document_nodes(transaction_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_doc ON embeddings(document_id);
CREATE INDEX IF NOT EXISTS idx_edges_tx ON lineage_edges(transaction_id);
"""

# Order matters for idempotent delete (children before parents).
_CHILD_TABLES = (
    "embeddings", "citations", "defined_terms", "obligations",
    "financial_facts", "dates", "document_nodes",
)


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def upsert_transaction(conn: sqlite3.Connection, transaction_id: str, name: str,
                       folder_path: str, now_utc: str) -> None:
    conn.execute(
        """INSERT INTO transactions(transaction_id, name, folder_path, created_utc)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(transaction_id) DO UPDATE SET
               name=excluded.name, folder_path=excluded.folder_path""",
        (transaction_id, name, folder_path, now_utc),
    )


def delete_document(conn: sqlite3.Connection, document_id: str) -> None:
    """Remove a document and all child rows so re-ingest is idempotent."""
    for table in _CHILD_TABLES:
        conn.execute(f"DELETE FROM {table} WHERE document_id = ?", (document_id,))
    conn.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))


def clear_transaction_lineage(conn: sqlite3.Connection, transaction_id: str) -> None:
    conn.execute("DELETE FROM lineage_edges WHERE transaction_id = ?", (transaction_id,))


def insert_document(conn: sqlite3.Connection, doc: dict) -> None:
    conn.execute(
        """INSERT INTO documents(
               document_id, transaction_id, relative_path, filename, extension,
               doc_kind, category, extraction_status, document_status, status_evidence,
               char_count, content_hash, mojibake_flag, ingested_utc)
           VALUES (:document_id, :transaction_id, :relative_path, :filename,
                   :extension, :doc_kind, :category, :extraction_status, :document_status,
                   :status_evidence, :char_count, :content_hash, :mojibake_flag,
                   :ingested_utc)""",
        doc,
    )


def insert_node(conn: sqlite3.Connection, document_id: str, transaction_id: str,
                node: dict) -> int:
    cur = conn.execute(
        """INSERT INTO document_nodes(
               document_id, transaction_id, node_type, number, heading, level,
               char_start, char_end, text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (document_id, transaction_id, node["node_type"], node.get("number", ""),
         node.get("heading", ""), node.get("level", 0),
         node.get("char_start", 0), node.get("char_end", 0), node.get("text", "")),
    )
    return int(cur.lastrowid)


def insert_defined_term(conn, document_id, node_id, term) -> None:
    conn.execute(
        "INSERT INTO defined_terms(document_id, node_id, term, definition, char_start) VALUES (?, ?, ?, ?, ?)",
        (document_id, node_id, term["term"], term.get("definition", ""), term.get("char_start", 0)),
    )


def insert_obligation(conn, document_id, node_id, ob) -> None:
    conn.execute(
        """INSERT INTO obligations(document_id, node_id, party, modality, text, char_start)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (document_id, node_id, ob["party"], ob["modality"], ob["text"], ob.get("char_start", 0)),
    )


def insert_financial_fact(conn, document_id, node_id, fact) -> None:
    conn.execute(
        """INSERT INTO financial_facts(document_id, node_id, raw, amount, currency, unit, kind, context, char_start)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (document_id, node_id, fact.get("raw", ""), fact.get("amount"),
         fact.get("currency", ""), fact.get("unit", ""), fact.get("kind", ""),
         fact.get("context", ""), fact.get("char_start", 0)),
    )


def insert_citation(conn, node_id, document_id, transaction_id, cite) -> None:
    conn.execute(
        """INSERT INTO citations(node_id, document_id, transaction_id, citation_text,
               section_ref, document_status, char_start, char_end)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (node_id, document_id, transaction_id, cite["citation_text"],
         cite["section_ref"], cite["document_status"],
         cite.get("char_start", 0), cite.get("char_end", 0)),
    )


def insert_date(conn, document_id, dt) -> None:
    conn.execute(
        "INSERT INTO dates(document_id, value, role) VALUES (?, ?, ?)",
        (document_id, dt["value"], dt.get("role", "")),
    )


def insert_lineage_edge(conn, transaction_id, src_type, src_id, dst_type,
                        dst_id, relation, evidence) -> None:
    conn.execute(
        """INSERT INTO lineage_edges(transaction_id, src_type, src_id, dst_type,
               dst_id, relation, evidence)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (transaction_id, src_type, src_id, dst_type, dst_id, relation, evidence),
    )


def insert_embedding(conn, node_id, document_id, model, dim, vector) -> None:
    conn.execute(
        """INSERT INTO embeddings(node_id, document_id, model, dim, vector)
           VALUES (?, ?, ?, ?, ?)""",
        (node_id, document_id, model, dim, vector),
    )


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    out: dict[str, int] = {}
    for table in ("transactions", "documents", "document_nodes", "defined_terms",
                  "obligations", "financial_facts", "citations", "lineage_edges",
                  "dates", "embeddings"):
        out[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return out
