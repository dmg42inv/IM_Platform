"""Hybrid, citation-grade retrieval over the legal knowledge base.

Pipeline (per the agreed query design):
    1. retrieve candidate nodes (clauses / recitals / tables)
    2. filter by metadata: vehicle (transaction), document status, doc kind, year
    3. rank by a hybrid score = BM25 (keyword) fused with vector (semantic)
    4. answer only from cited nodes - each result carries its citation row

Vector search uses sentence-transformers embeddings with FAISS when available
(falls back to a NumPy inner product, which is identical for normalised
vectors). The SQLite database remains the source of truth; scores only rank.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

import numpy as np

if __package__:
    from . import embeddings as embeddings_mod
else:  # pragma: no cover
    import embeddings as embeddings_mod

try:
    import faiss  # type: ignore
    _HAVE_FAISS = True
except Exception:  # pragma: no cover
    _HAVE_FAISS = False

try:
    from rank_bm25 import BM25Okapi
    _HAVE_BM25 = True
except Exception:  # pragma: no cover
    _HAVE_BM25 = False

_TOKEN = re.compile(r"[A-Za-z0-9$%.]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def _minmax(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    lo, hi = float(values.min()), float(values.max())
    if hi - lo < 1e-12:
        return np.zeros_like(values)
    return (values - lo) / (hi - lo)


def _candidate_nodes(conn: sqlite3.Connection, filters: dict) -> list[dict]:
    sql = [
        "SELECT n.node_id, n.node_type, n.number, n.heading, n.text,",
        "       d.document_id, d.relative_path, d.filename, d.doc_kind,",
        "       d.document_status, d.transaction_id, d.category, d.clean_path,",
        "       c.citation_text, c.section_ref",
        "FROM document_nodes n",
        "JOIN documents d ON d.document_id = n.document_id",
        "LEFT JOIN citations c ON c.node_id = n.node_id",
        "WHERE n.node_type IN ('clause','recital','table')",
        "  AND length(n.text) > 0",
    ]
    params: list = []
    if filters.get("transaction"):
        sql.append("AND d.transaction_id = ?")
        params.append(filters["transaction"])
    if filters.get("status"):
        sql.append("AND d.document_status = ?")
        params.append(filters["status"])
    if filters.get("doc_kind"):
        sql.append("AND d.doc_kind = ?")
        params.append(filters["doc_kind"])
    if filters.get("category"):
        sql.append("AND d.category = ?")
        params.append(filters["category"])
    if filters.get("year"):
        sql.append(
            "AND d.document_id IN (SELECT document_id FROM dates WHERE value LIKE ?)")
        params.append(f"%{filters['year']}%")
    rows = conn.execute(" ".join(sql), params).fetchall()
    cols = ["node_id", "node_type", "number", "heading", "text", "document_id",
            "relative_path", "filename", "doc_kind", "document_status",
            "transaction_id", "category", "clean_path", "citation_text", "section_ref"]
    return [dict(zip(cols, r)) for r in rows]


def _vector_scores(conn: sqlite3.Connection, node_ids: list[int],
                   query_vec: np.ndarray) -> dict[int, float]:
    if not node_ids:
        return {}
    placeholders = ",".join("?" * len(node_ids))
    rows = conn.execute(
        f"SELECT node_id, vector FROM embeddings WHERE node_id IN ({placeholders})",
        node_ids,
    ).fetchall()
    if not rows:
        return {}
    matrix = np.stack([embeddings_mod.from_bytes(r[1]) for r in rows]).astype(np.float32)
    ids = [r[0] for r in rows]
    if _HAVE_FAISS:
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        sims, idxs = index.search(query_vec.reshape(1, -1).astype(np.float32), len(ids))
        sims, idxs = sims[0], idxs[0]
    else:
        sims_all = matrix @ query_vec
        idxs = np.argsort(-sims_all)
        sims = sims_all[idxs]
    best: dict[int, float] = {}
    for sim, idx in zip(sims, idxs):
        node_id = ids[int(idx)]
        if node_id not in best or sim > best[node_id]:
            best[node_id] = float(sim)
    return best


def search(db_path: Path, question: str, top_k: int = 8, alpha: float = 0.6,
           transaction: str | None = None, status: str | None = None,
           doc_kind: str | None = None, year: str | None = None,
           category: str | None = None, model_name: str | None = None) -> list[dict]:
    """alpha weights the semantic (vector) score; (1-alpha) weights BM25."""
    model_name = model_name or embeddings_mod.DEFAULT_MODEL
    filters = {"transaction": transaction, "status": status,
               "doc_kind": doc_kind, "year": year, "category": category}
    conn = sqlite3.connect(str(db_path))
    try:
        candidates = _candidate_nodes(conn, filters)
        if not candidates:
            return []
        node_ids = [c["node_id"] for c in candidates]

        # Keyword score (BM25).
        query_tokens = _tokenize(question)
        if _HAVE_BM25:
            bm25 = BM25Okapi([_tokenize(c["text"]) for c in candidates])
            bm25_scores = np.asarray(bm25.get_scores(query_tokens), dtype=np.float32)
        else:
            bm25_scores = np.zeros(len(candidates), dtype=np.float32)

        # Semantic score (vector).
        query_vec = embeddings_mod.embed_query(question, model_name=model_name)
        vec_map = _vector_scores(conn, node_ids, query_vec)
        vec_scores = np.asarray([vec_map.get(nid, 0.0) for nid in node_ids], dtype=np.float32)

        hybrid = alpha * _minmax(vec_scores) + (1.0 - alpha) * _minmax(bm25_scores)
        order = np.argsort(-hybrid)[:]

        results: list[dict] = []
        seen_content: set[tuple[str, str]] = set()
        for i in order:
            c = candidates[int(i)]
            snippet = " ".join((c["text"] or "").split())[:320]
            # De-duplicate identical documents copied to multiple archive paths.
            dedup_key = (c["filename"], (c["text"] or "")[:400])
            if dedup_key in seen_content:
                continue
            seen_content.add(dedup_key)
            results.append({
                "hybrid_score": round(float(hybrid[i]), 4),
                "vector_score": round(float(vec_scores[i]), 4),
                "bm25_score": round(float(bm25_scores[i]), 4),
                "transaction": c["transaction_id"],
                "category": c["category"],
                "document": c["relative_path"],
                "clean_path": c["clean_path"],
                "filename": c["filename"],
                "doc_kind": c["doc_kind"],
                "document_status": c["document_status"],
                "node_type": c["node_type"],
                "section": c["section_ref"] or c["number"] or c["heading"],
                "citation": c["citation_text"],
                "snippet": snippet,
            })
            if len(results) >= top_k:
                break
        return results
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Hybrid citation-grade query over the legal KB.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--alpha", type=float, default=0.6,
                        help="Weight on semantic score (1-alpha on BM25).")
    parser.add_argument("--transaction", type=str, default=None, help="Vehicle / deal filter.")
    parser.add_argument("--status", type=str, default=None, help="Document status filter.")
    parser.add_argument("--doc-kind", type=str, default=None)
    parser.add_argument("--category", type=str, default=None, help="Curated SR category filter (e.g. 03_Closing_and_Legal).")
    parser.add_argument("--year", type=str, default=None)
    parser.add_argument("--model", type=str, default=None)
    args = parser.parse_args()

    results = search(args.db, args.query, args.top_k, args.alpha, args.transaction,
                     args.status, args.doc_kind, args.year, args.category, args.model)
    print(json.dumps({
        "query": args.query,
        "engine": {"faiss": _HAVE_FAISS, "bm25": _HAVE_BM25, "alpha": args.alpha},
        "results": results,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
