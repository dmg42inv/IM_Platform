"""Driver: build the citation-grade knowledge base for one investment folder.

Consumes the extraction outputs already on disk (extraction_status.csv and
extracted_text/*.txt from build_extraction_coverage.py) and populates the
SQLite source-of-truth database:

  every file            -> documents row (all-files rule)
  readable file text    -> cleaned, parsed into document_nodes (clauses,
                           entities, tables), with defined_terms, obligations,
                           financial_facts and dates linked to their node,
                           one citation per retrievable node, and per-node
                           embeddings for semantic search
  per transaction       -> lineage_edges (version/amendment + party links)

Usage:
    python -m scripts.legal_kb.build_kb --folder "<...>/ONT/SR"
    python -m scripts.legal_kb.build_kb --folder "<...>/ONT/SR" --no-embeddings
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from . import metadata_db, structural_parser, text_cleanup
else:  # pragma: no cover
    import metadata_db
    import structural_parser
    import text_cleanup


DOC_TYPE_RULES = [
    ("term sheet", "term_sheet"), ("cap table", "cap_table"), ("captable", "cap_table"),
    ("subscription", "subscription_agreement"), ("share purchase", "share_purchase_agreement"),
    ("stock purchase", "stock_purchase_agreement"), ("purchase agreement", "purchase_agreement"),
    ("shareholders agreement", "shareholders_agreement"), ("shareholder", "shareholder_document"),
    ("board resolution", "board_resolution"), ("resolution", "resolution"),
    ("investors rights", "investors_rights_agreement"), ("side letter", "side_letter"),
    ("warrant", "warrant"), ("convertible", "convertible_instrument"), ("charter", "charter"),
    ("certificate of incorporation", "charter"), ("articles", "constitutional_document"),
    ("valuation", "valuation_support"), ("financial", "financial_statement"),
    ("audited", "financial_statement"), ("cashflow", "financial_model"),
    ("due diligence", "due_diligence"), ("memo", "investment_memo"),
    ("investment note", "investment_note"), ("prospectus", "public_filing"),
    ("closing", "closing_document"), ("payment direction", "payment_instruction"),
    ("capital account", "capital_account_statement"), ("drawdown", "capital_call"),
    ("capital call", "capital_call"), ("amendment", "amendment"), ("amended", "amendment"),
]

# Map an original archive folder/path to the curated SR taxonomy (01-10).
# Order matters: earlier, more specific rules win.
CATEGORY_RULES = [
    ("due diligence", "10_Due_Diligence"),
    ("valuation", "08_Valuation_Support"),
    ("exit", "08_Exit_and_Public_Markets"),
    ("public market", "08_Exit_and_Public_Markets"),
    ("ipo", "08_Exit_and_Public_Markets"),
    ("listing", "08_Exit_and_Public_Markets"),
    ("monitoring", "07_Monitoring_and_Financials"),
    ("financial", "07_Monitoring_and_Financials"),
    ("quarterly", "07_Monitoring_and_Financials"),
    ("annual report", "07_Monitoring_and_Financials"),
    ("milestone", "06_Milestones_and_Corporate_Actions"),
    ("corporate action", "06_Milestones_and_Corporate_Actions"),
    ("cashflow", "05_Cashflows_and_Funding"),
    ("capital call", "05_Cashflows_and_Funding"),
    ("drawdown", "05_Cashflows_and_Funding"),
    ("funding", "05_Cashflows_and_Funding"),
    ("payment", "05_Cashflows_and_Funding"),
    ("distribution", "05_Cashflows_and_Funding"),
    ("cap table", "04_Capitalization_and_Securities"),
    ("captable", "04_Capitalization_and_Securities"),
    ("capitalization", "04_Capitalization_and_Securities"),
    ("securities", "04_Capitalization_and_Securities"),
    ("share certificate", "04_Capitalization_and_Securities"),
    ("warrant", "04_Capitalization_and_Securities"),
    ("transaction closure", "03_Closing_and_Legal"),
    ("closing", "03_Closing_and_Legal"),
    ("legal", "03_Closing_and_Legal"),
    ("term sheet", "03_Closing_and_Legal"),
    ("subscription", "03_Closing_and_Legal"),
    ("agreement", "03_Closing_and_Legal"),
    ("board", "02_Board_and_Investment_Committee"),
    ("investment committee", "02_Board_and_Investment_Committee"),
    ("analysis", "09_Analysis"),
]


def categorize(relative_path: str) -> str:
    """Best-effort mapping of an archive file to the curated SR taxonomy."""
    lowered = relative_path.lower()
    for keyword, category in CATEGORY_RULES:
        if keyword in lowered:
            return category
    return "01_Primary_Source_Documents"


EMBED_WINDOW = 1200
EMBED_OVERLAP = 150
SECTION_TEXT_CAP = 20000
EMBEDDABLE = {"clause", "recital", "table"}
_VERSION_TOKENS = re.compile(
    r"\b(v\d+(?:\.\d+)?|version\s*\d+|draft|final|execution|executed|conformed|"
    r"amendment(?:\s*no\.?\s*\d+)?|amended(?:\s+and\s+restated)?|restated|"
    r"clean|revised|rev\d*)\b",
    re.IGNORECASE,
)


def long_path(path: Path) -> str:
    resolved = str(path.resolve(strict=False))
    return resolved if resolved.startswith("\\\\?\\") else "\\\\?\\" + resolved


def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return slug or "item"


def infer_doc_kind(relative_path: str) -> str:
    lowered = relative_path.lower()
    for keyword, kind in DOC_TYPE_RULES:
        if keyword in lowered:
            return kind
    return "unclassified_document"


def find_sandbox_root(folder: Path) -> Path:
    for parent in [folder, *folder.parents]:
        if parent.name == "AF" or (parent / "README_COVERAGE.md").exists():
            return parent
    return folder


def document_id_for(transaction_id: str, relative_path: str) -> str:
    digest = hashlib.sha1(f"{transaction_id}/{relative_path}".encode("utf-8")).hexdigest()
    return f"{transaction_id}__{digest[:16]}"


def load_rows(intel_root: Path) -> list[dict]:
    status_csv = intel_root / "extraction_status.csv"
    if not status_csv.exists():
        raise FileNotFoundError(
            f"Missing extraction_status.csv: {status_csv}. Run build_extraction_coverage.py first."
        )
    with status_csv.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def window_text(text: str) -> list[str]:
    text = text.strip()
    if len(text) <= EMBED_WINDOW:
        return [text] if text else []
    out: list[str] = []
    step = max(1, EMBED_WINDOW - EMBED_OVERLAP)
    for start in range(0, len(text), step):
        piece = text[start:start + EMBED_WINDOW]
        if piece.strip():
            out.append(piece)
    return out


def _normalise_base_name(filename: str) -> str:
    stem = Path(filename).stem.lower()
    stem = _VERSION_TOKENS.sub(" ", stem)
    stem = re.sub(r"\b\d{1,2}[.\-/ ]\d{1,2}[.\-/ ]\d{2,4}\b", " ", stem)  # dates
    stem = re.sub(r"[^a-z0-9]+", " ", stem)
    return re.sub(r"\s+", " ", stem).strip()


def _version_rank(filename: str) -> int:
    low = filename.lower()
    rank = 0
    if re.search(r"\bdraft\b", low):
        rank = 1
    if re.search(r"\brevised|rev\d|conformed|clean\b", low):
        rank = 2
    m = re.search(r"\bv(\d+)", low)
    if m:
        rank = max(rank, 2 + int(m.group(1)))
    if re.search(r"\bfinal|execution|executed\b", low):
        rank = max(rank, 50)
    if re.search(r"amended\s+and\s+restated|restated", low):
        rank = max(rank, 60)
    m2 = re.search(r"amendment\s*(?:no\.?\s*)?(\d+)", low)
    if m2:
        rank = max(rank, 70 + int(m2.group(1)))
    return rank


def build_lineage(conn, transaction_id: str) -> int:
    metadata_db.clear_transaction_lineage(conn, transaction_id)
    docs = conn.execute(
        "SELECT document_id, filename, doc_kind FROM documents WHERE transaction_id = ?"
        " AND extraction_status = 'extracted_text'",
        (transaction_id,),
    ).fetchall()
    edges = 0

    # Version / amendment edges: group by normalised base name.
    groups: dict[str, list[tuple[str, str]]] = {}
    for document_id, filename, _kind in docs:
        groups.setdefault(_normalise_base_name(filename), []).append((document_id, filename))
    for base, members in groups.items():
        if not base or len(members) < 2:
            continue
        members.sort(key=lambda m: _version_rank(m[1]))
        for earlier, later in zip(members, members[1:]):
            relation = "amends" if "amend" in later[1].lower() else "version_of"
            metadata_db.insert_lineage_edge(
                conn, transaction_id, "document", later[0], "document", earlier[0],
                relation, f"{later[1]} -> {earlier[1]}")
            edges += 1

    # Party links: entity node -> document it appears in (deduped per name).
    entities = conn.execute(
        "SELECT DISTINCT text, document_id FROM document_nodes "
        "WHERE transaction_id = ? AND node_type = 'entity'",
        (transaction_id,),
    ).fetchall()
    seen: set[tuple[str, str]] = set()
    for name, document_id in entities:
        key = (name.lower(), document_id)
        if name and key not in seen:
            seen.add(key)
            metadata_db.insert_lineage_edge(
                conn, transaction_id, "entity", name, "document", document_id,
                "party_of", "")
            edges += 1
    return edges


def build(folder: Path, db_path: Path, with_embeddings: bool, model_name: str) -> dict:
    intel_root = folder / "00_Index" / "Document_Intelligence"
    text_root = intel_root / "extracted_text"
    rows = load_rows(intel_root)

    transaction_name = folder.parent.name
    transaction_id = slugify(transaction_name)
    now_utc = datetime.now(timezone.utc).isoformat()

    conn = metadata_db.connect(db_path)
    metadata_db.upsert_transaction(conn, transaction_id, transaction_name, str(folder), now_utc)

    embed_model = None
    if with_embeddings:
        from . import embeddings as embeddings_mod
        embed_model = embeddings_mod

    stats = {"documents": 0, "readable": 0, "nodes": 0, "financial_facts": 0,
             "embedded_windows": 0, "mojibake_docs": 0}

    for row in rows:
        relative = row["relative_path"]
        status = row.get("status", "")
        document_id = document_id_for(transaction_id, relative)
        metadata_db.delete_document(conn, document_id)

        readable = status == "extracted_text"
        text = ""
        if readable:
            text_file = text_root / (relative + ".txt")
            if os.path.exists(long_path(text_file)):
                with open(long_path(text_file), "r", encoding="utf-8", errors="replace") as handle:
                    text = handle.read()
            else:
                readable = False

        mojibake = 0
        parsed = structural_parser.ParsedDocument()
        if readable and text.strip():
            mojibake = text_cleanup.mojibake_score(text)
            text = text_cleanup.clean(text)
            parsed = structural_parser.parse_document(text)

        metadata_db.insert_document(conn, {
            "document_id": document_id,
            "transaction_id": transaction_id,
            "relative_path": relative,
            "filename": Path(relative).name,
            "extension": (row.get("extension") or Path(relative).suffix).lower(),
            "doc_kind": infer_doc_kind(relative),
            "category": categorize(relative),
            "extraction_status": status,
            "document_status": parsed.document_status,
            "status_evidence": parsed.status_evidence,
            "char_count": len(text),
            "content_hash": row.get("content_hash", "") or row.get("sha256", ""),
            "mojibake_flag": 1 if mojibake else 0,
            "ingested_utc": now_utc,
        })
        stats["documents"] += 1
        if mojibake:
            stats["mojibake_docs"] += 1
        if not (readable and text.strip()):
            continue
        stats["readable"] += 1

        # Clause / recital nodes (retrievable, position-indexed for linking).
        clause_starts: list[int] = []
        clause_ids: list[int] = []
        embed_batch: list[tuple[int, str]] = []
        for sec in parsed.sections:
            node_type = "recital" if sec.number == "RECITALS" else "clause"
            sec_text = sec.text[:SECTION_TEXT_CAP]
            node_id = metadata_db.insert_node(conn, document_id, transaction_id, {
                "node_type": node_type, "number": sec.number, "heading": sec.heading,
                "level": sec.level, "char_start": sec.char_start,
                "char_end": sec.char_end, "text": sec_text,
            })
            stats["nodes"] += 1
            clause_starts.append(sec.char_start)
            clause_ids.append(node_id)
            section_ref = sec.number or sec.heading or "(whole document)"
            metadata_db.insert_citation(conn, node_id, document_id, transaction_id, {
                "citation_text": f"{Path(relative).name} \u00a7 {section_ref} [status: {parsed.document_status}]",
                "section_ref": section_ref, "document_status": parsed.document_status,
                "char_start": sec.char_start, "char_end": sec.char_end,
            })
            for window in window_text(sec_text):
                embed_batch.append((node_id, window))

        def node_for(pos: int) -> int | None:
            if not clause_starts:
                return None
            idx = bisect.bisect_right(clause_starts, pos) - 1
            return clause_ids[idx] if idx >= 0 else clause_ids[0]

        # Entity nodes.
        for party in parsed.parties:
            metadata_db.insert_node(conn, document_id, transaction_id, {
                "node_type": "entity", "number": "", "heading": party.get("role", ""),
                "level": 0, "char_start": 0, "char_end": 0, "text": party["name"],
            })
            stats["nodes"] += 1

        # Table nodes (embeddable; carry the financial grids).
        for tbl in parsed.tables:
            tnode = metadata_db.insert_node(conn, document_id, transaction_id, {
                "node_type": "table", "number": "", "heading": "table",
                "level": 0, "char_start": tbl["char_start"], "char_end": tbl["char_end"],
                "text": tbl["text"][:SECTION_TEXT_CAP],
            })
            stats["nodes"] += 1
            metadata_db.insert_citation(conn, tnode, document_id, transaction_id, {
                "citation_text": f"{Path(relative).name} \u00a7 table@{tbl['char_start']} [status: {parsed.document_status}]",
                "section_ref": f"table@{tbl['char_start']}", "document_status": parsed.document_status,
                "char_start": tbl["char_start"], "char_end": tbl["char_end"],
            })
            for window in window_text(tbl["text"][:SECTION_TEXT_CAP]):
                embed_batch.append((tnode, window))

        # Linked extractions.
        for term in parsed.defined_terms:
            metadata_db.insert_defined_term(conn, document_id, node_for(term.get("char_start", 0)), term)
        for ob in parsed.obligations:
            metadata_db.insert_obligation(conn, document_id, node_for(ob.get("char_start", 0)), ob)
        for fact in parsed.financial_facts:
            metadata_db.insert_financial_fact(conn, document_id, node_for(fact.get("char_start", 0)), fact)
            stats["financial_facts"] += 1
        for dt in parsed.dates:
            metadata_db.insert_date(conn, document_id, dt)

        if with_embeddings and embed_model is not None and embed_batch:
            vectors = embed_model.embed_texts([t for _, t in embed_batch], model_name=model_name)
            for (node_id, _), vector in zip(embed_batch, vectors):
                metadata_db.insert_embedding(conn, node_id, document_id, model_name,
                                             int(vector.shape[0]), embed_model.to_bytes(vector))
                stats["embedded_windows"] += 1

    edges = build_lineage(conn, transaction_id)
    stats["lineage_edges"] = edges

    conn.commit()
    db_counts = metadata_db.counts(conn)
    conn.close()
    return {"transaction_id": transaction_id, "db_path": str(db_path),
            "folder_stats": stats, "db_counts": db_counts}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the citation-grade legal KB for one folder.")
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=None,
                        help="SQLite DB path. Default: <sandbox_root>/legal_kb/legal_kb.sqlite")
    parser.add_argument("--no-embeddings", action="store_true")
    parser.add_argument("--model", type=str, default=None)
    args = parser.parse_args()

    from . import embeddings as embeddings_mod
    model_name = args.model or embeddings_mod.DEFAULT_MODEL
    db_path = args.db or (find_sandbox_root(args.folder) / "legal_kb" / "legal_kb.sqlite")
    result = build(args.folder, db_path, not args.no_embeddings, model_name)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
