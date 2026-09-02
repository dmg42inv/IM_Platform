"""Stage 2 of the evidence coverage audit: reconcile every source file against every layer.

Layers, in the order a fact must survive to be usable:

    discovered -> extracted -> nodes -> retrieval index -> structured facts

A file that stops between two layers is a coverage gap and must carry a reason. "Extracted but
not indexed" with no explanation fails the audit.

Joining is the weak point and is reported rather than hidden. The legal knowledge base stores no
content hash, so its documents can only be matched on filename, which is ambiguous wherever the
corpus holds several files of the same name. Every matched row records how it was matched and
whether that match was unique. The portfolio database does store SHA-256, so those rows join
exactly and are labelled as such.

    .\\.venv\\Scripts\\python.exe -m scripts.evidence_audit.coverage --report
    .\\.venv\\Scripts\\python.exe -m scripts.evidence_audit.coverage --export
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_DB = REPO_ROOT / "data" / "evidence" / "audit.sqlite"
LEGAL_KB_DB = REPO_ROOT / "data" / "legal_kb" / "legal_kb.sqlite"
PORTFOLIO_DB = REPO_ROOT / "data" / "portfolio" / "portfolio.sqlite"
OUT_DIR = REPO_ROOT / "data" / "evidence" / "audit_outputs"


def read_only(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_manifest(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT source_id, full_path, root, relative_path, filename, extension, size_bytes,"
        " modified_utc, cloud_state, sha256, hash_status, hash_error FROM sources").fetchall()


def load_legal_kb() -> dict:
    """Per-document layer counts from the legal knowledge base, keyed by lower-cased filename."""
    if not LEGAL_KB_DB.exists():
        return {}
    conn = read_only(LEGAL_KB_DB)
    try:
        nodes = {r["document_id"]: r["n"] for r in conn.execute(
            "SELECT document_id, COUNT(*) n FROM document_nodes GROUP BY 1")}
        vectors = {r["document_id"]: r["n"] for r in conn.execute(
            "SELECT document_id, COUNT(*) n FROM embeddings GROUP BY 1")}
        facts: dict[str, int] = defaultdict(int)
        for table in ("financial_facts", "citations", "dates", "defined_terms", "obligations"):
            try:
                for r in conn.execute(f"SELECT document_id, COUNT(*) n FROM {table} GROUP BY 1"):
                    facts[r["document_id"]] += r["n"]
            except sqlite3.OperationalError:
                continue
        edges: dict[str, int] = defaultdict(int)
        try:
            for r in conn.execute("SELECT document_id, COUNT(*) n FROM lineage_edges GROUP BY 1"):
                edges[r["document_id"]] += r["n"]
        except sqlite3.OperationalError:
            pass

        by_name: dict[str, list[dict]] = defaultdict(list)
        by_doc_id: dict[str, dict] = {}
        for r in conn.execute(
                "SELECT document_id, transaction_id, filename, relative_path, extraction_status,"
                " char_count, content_hash FROM documents"):
            doc_id = r["document_id"]
            entry = {
                "document_id": doc_id,
                "transaction_id": r["transaction_id"],
                "relative_path": r["relative_path"],
                "extraction_status": r["extraction_status"],
                "char_count": r["char_count"] or 0,
                "content_hash": r["content_hash"] or "",
                "nodes": nodes.get(doc_id, 0),
                "vectors": vectors.get(doc_id, 0),
                "facts": facts.get(doc_id, 0),
                "graph_edges": edges.get(doc_id, 0),
            }
            by_name[(r["filename"] or "").lower()].append(entry)
            by_doc_id[doc_id] = entry
        return by_name, by_doc_id
    finally:
        conn.close()


def load_provenance(audit_db: Path) -> dict[str, str]:
    """sha256 -> knowledge base document_id, from the stage 3 backfill."""
    conn = read_only(audit_db)
    try:
        return {r["sha256"]: r["document_id"] for r in conn.execute(
            "SELECT sha256, document_id FROM kb_document_provenance WHERE sha256 <> ''")}
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


def load_portfolio_by_hash() -> dict[str, dict]:
    """The portfolio database records SHA-256, so these join exactly."""
    if not PORTFOLIO_DB.exists():
        return {}
    conn = read_only(PORTFOLIO_DB)
    try:
        holdings = {r["doc_id"]: r["n"] for r in conn.execute(
            "SELECT doc_id, COUNT(*) n FROM fund_holdings GROUP BY 1")}
        out = {}
        for r in conn.execute("SELECT doc_id, fund, as_of_date, file_name, sha256 FROM fund_documents"):
            if r["sha256"]:
                out[r["sha256"]] = {"fund": r["fund"], "as_of_date": r["as_of_date"],
                                    "structured_rows": holdings.get(r["doc_id"], 0)}
        for r in conn.execute("SELECT fund, as_of_date, file_name, sha256 FROM fund_capital_accounts"
                              " WHERE sha256 IS NOT NULL"):
            entry = out.setdefault(r["sha256"], {"fund": r["fund"], "as_of_date": r["as_of_date"],
                                                 "structured_rows": 0})
            entry["structured_rows"] += 1
        return out
    finally:
        conn.close()


def fts_chunk_count() -> int:
    if not LEGAL_KB_DB.exists():
        return 0
    conn = read_only(LEGAL_KB_DB)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE '%fts%'")]
        total = 0
        for name in names:
            total += conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        return total
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def build_rows(manifest, kb_by_name, kb_by_doc_id, sha_to_doc, portfolio_by_hash) -> list[dict]:
    name_counts: dict[str, int] = defaultdict(int)
    for row in manifest:
        name_counts[(row["filename"] or "").lower()] += 1

    rows = []
    for src in manifest:
        name = (src["filename"] or "").lower()
        sha = src["sha256"] or ""
        kb = kb_by_doc_id.get(sha_to_doc.get(sha, "")) if sha else None

        if kb is not None:
            match_method, ambiguity = "sha256_resolved", ""
        else:
            kb_matches = kb_by_name.get(name, [])
            corpus_copies = name_counts[name]
            if not kb_matches:
                match_method, ambiguity = "none", ""
            elif len(kb_matches) == 1 and corpus_copies == 1:
                match_method, ambiguity, kb = "filename_unique", "", kb_matches[0]
            else:
                match_method = "filename_ambiguous"
                ambiguity = f"{corpus_copies} corpus copies, {len(kb_matches)} kb rows of this name"
                kb = kb_matches[0]

        pf = portfolio_by_hash.get(src["sha256"] or "")

        extracted = bool(kb and kb["char_count"] > 0)
        rows.append({
            "source_id": src["source_id"],
            "full_path": src["full_path"],
            "filename": src["filename"],
            "extension": src["extension"],
            "size_bytes": src["size_bytes"],
            "modified_utc": src["modified_utc"],
            "cloud_state": src["cloud_state"],
            "sha256": src["sha256"] or "",
            "hash_status": src["hash_status"],
            "discovered": 1,
            "kb_match_method": match_method,
            "kb_match_ambiguity": ambiguity,
            "kb_document_id": kb["document_id"] if kb else "",
            "kb_transaction_id": kb["transaction_id"] if kb else "",
            "extraction_status": kb["extraction_status"] if kb else "not_in_kb",
            "char_count": kb["char_count"] if kb else 0,
            "extracted": int(extracted),
            "node_count": kb["nodes"] if kb else 0,
            "fts_chunks": 0,
            "vector_nodes": kb["vectors"] if kb else 0,
            "graph_edges": kb["graph_edges"] if kb else 0,
            "kb_fact_count": kb["facts"] if kb else 0,
            "portfolio_exact_hash_match": int(pf is not None),
            "portfolio_fund": pf["fund"] if pf else "",
            "portfolio_as_of": pf["as_of_date"] if pf else "",
            "portfolio_structured_rows": pf["structured_rows"] if pf else 0,
            "stop_reason": stop_reason(src, kb, extracted),
        })
    return rows


def stop_reason(src, kb, extracted: bool) -> str:
    if src["hash_status"] == "error":
        return f"unreadable: {src['hash_error']}"
    if src["hash_status"] == "pending_hydration":
        return "cloud-only at scan, not hydrated"
    if kb is None:
        return "discovered but never presented to the knowledge base"
    if not extracted:
        return f"in knowledge base but no text extracted ({kb['extraction_status']})"
    if kb["nodes"] == 0:
        return "text extracted but no structural nodes built"
    if kb["vectors"] == 0:
        return "nodes built but not embedded"
    return "reached vector index; no BM25 index exists"


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0].keys()) if rows else [])
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summarise(rows: list[dict], fts_total: int) -> None:
    n = len(rows)
    hashed = sum(1 for r in rows if r["sha256"])
    unique = len({r["sha256"] for r in rows if r["sha256"]})
    in_kb = sum(1 for r in rows if r["kb_match_method"] != "none")
    resolved = sum(1 for r in rows if r["kb_match_method"] == "sha256_resolved")
    ambiguous = sum(1 for r in rows if r["kb_match_method"] == "filename_ambiguous")
    extracted = sum(r["extracted"] for r in rows)
    noded = sum(1 for r in rows if r["node_count"] > 0)
    vectored = sum(1 for r in rows if r["vector_nodes"] > 0)
    facted = sum(1 for r in rows if r["kb_fact_count"] > 0)
    exact = sum(r["portfolio_exact_hash_match"] for r in rows)

    print("\n  EVIDENCE COVERAGE")
    print(f"    discovered in corpus                {n:>8,}")
    print(f"    hashed                              {hashed:>8,}")
    print(f"    unique after SHA-256 deduplication  {unique:>8,}")
    print(f"    present in knowledge base           {in_kb:>8,}   ({in_kb/n*100:5.1f}% of corpus)")
    print(f"      resolved by source hash           {resolved:>8,}   <- provenance proven")
    print(f"      matched only by filename          {ambiguous:>8,}   <- provenance not proven")
    print(f"    text extracted                      {extracted:>8,}   ({extracted/n*100:5.1f}%)")
    print(f"    structural nodes built              {noded:>8,}")
    print(f"    embedded for vector search          {vectored:>8,}")
    print(f"    BM25 / FTS chunks                   {fts_total:>8,}")
    print(f"    structured facts extracted          {facted:>8,}")
    print(f"    exact hash match to portfolio DB    {exact:>8,}")

    print("\n  WHERE FILES STOP")
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r["stop_reason"].split(":")[0]] += 1
    for reason, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"    {count:>8,}  {reason}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-db", type=Path, default=AUDIT_DB)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    if not args.audit_db.exists():
        print(f"  manifest not found at {args.audit_db}; run the manifest scan first", file=sys.stderr)
        return 2

    conn = read_only(args.audit_db)
    try:
        manifest = load_manifest(conn)
    finally:
        conn.close()
    if not manifest:
        print("  manifest is empty", file=sys.stderr)
        return 2

    rows = build_rows(manifest, *load_legal_kb(), load_provenance(args.audit_db),
                      load_portfolio_by_hash())
    fts_total = fts_chunk_count()
    summarise(rows, fts_total)

    if args.export:
        out = args.out
        write_csv(out / "corpus_manifest.csv", rows, [
            "source_id", "full_path", "filename", "extension", "size_bytes", "modified_utc",
            "cloud_state", "sha256", "hash_status"])
        write_csv(out / "evidence_coverage_matrix.csv", rows)
        unresolved = [r for r in rows if r["stop_reason"] != "reached vector index; no BM25 index exists"]
        write_csv(out / "unresolved_documents.csv", unresolved)

        groups: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            if r["sha256"]:
                groups[r["sha256"]].append(r)
        dupes = []
        for sha, items in groups.items():
            if len(items) > 1:
                keep = min(items, key=lambda x: x["full_path"])
                for item in items:
                    dupes.append({"sha256": sha, "copies": len(items), "full_path": item["full_path"],
                                  "size_bytes": item["size_bytes"],
                                  "duplicate_of": "" if item is keep else keep["full_path"]})
        write_csv(out / "duplicate_documents.csv", dupes,
                  ["sha256", "copies", "full_path", "size_bytes", "duplicate_of"])
        print(f"\n  wrote 4 files to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
