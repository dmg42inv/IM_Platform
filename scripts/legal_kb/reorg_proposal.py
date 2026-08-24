"""Propose a clean, logical folder placement for each document in a transaction.

Reads the knowledge base (document kind + original path + content) and assigns
each file to one bucket of a refined, de-duplicated taxonomy. This is a
READ-ONLY proposal: it moves nothing. It writes a manifest (CSV) and prints a
summary so the reorganisation can be reviewed before any files are touched.

Usage:
    python -m scripts.legal_kb.reorg_proposal --db data/legal_kb/legal_kb.sqlite --transaction ont
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

# Refined taxonomy (fixes the duplicate 08 and the vague catch-all).
BUCKETS = [
    "01_Investment_Thesis_and_Memos",
    "02_Due_Diligence",
    "03_Board_and_IC",
    "04_Legal_and_Closing",
    "05_Capitalization_and_Securities",
    "06_Cashflows_and_Funding",
    "07_Monitoring_and_Financials",
    "08_Valuation",
    "09_Corporate_Actions_and_AGM",
    "10_Exit_and_Public_Markets",
    "11_Correspondence_and_Other",
]

# doc_kind (content inference from the KB) -> bucket. Strong signal.
KIND_TO_BUCKET = {
    "investment_memo": "01_Investment_Thesis_and_Memos",
    "investment_note": "01_Investment_Thesis_and_Memos",
    "due_diligence": "02_Due_Diligence",
    "board_resolution": "03_Board_and_IC",
    "resolution": "03_Board_and_IC",
    "shareholder_document": "03_Board_and_IC",
    "term_sheet": "04_Legal_and_Closing",
    "subscription_agreement": "04_Legal_and_Closing",
    "share_purchase_agreement": "04_Legal_and_Closing",
    "stock_purchase_agreement": "04_Legal_and_Closing",
    "purchase_agreement": "04_Legal_and_Closing",
    "shareholders_agreement": "04_Legal_and_Closing",
    "investors_rights_agreement": "04_Legal_and_Closing",
    "side_letter": "04_Legal_and_Closing",
    "charter": "04_Legal_and_Closing",
    "constitutional_document": "04_Legal_and_Closing",
    "closing_document": "04_Legal_and_Closing",
    "amendment": "04_Legal_and_Closing",
    "convertible_instrument": "04_Legal_and_Closing",
    "cap_table": "05_Capitalization_and_Securities",
    "warrant": "05_Capitalization_and_Securities",
    "payment_instruction": "06_Cashflows_and_Funding",
    "capital_call": "06_Cashflows_and_Funding",
    "financial_statement": "07_Monitoring_and_Financials",
    "financial_model": "07_Monitoring_and_Financials",
    "valuation_support": "08_Valuation",
    "capital_account_statement": "08_Valuation",
    "public_filing": "10_Exit_and_Public_Markets",
}

# Keyword signals in the original path/filename -> bucket. Order = priority.
PATH_RULES = [
    ("prospectus", "10_Exit_and_Public_Markets"),
    ("pre-emption", "10_Exit_and_Public_Markets"),
    ("pre emption", "10_Exit_and_Public_Markets"),
    ("ipo", "10_Exit_and_Public_Markets"),
    ("listing", "10_Exit_and_Public_Markets"),
    ("admission", "10_Exit_and_Public_Markets"),
    ("public market", "10_Exit_and_Public_Markets"),
    ("lock-up", "10_Exit_and_Public_Markets"),
    ("lockup", "10_Exit_and_Public_Markets"),
    ("agm", "09_Corporate_Actions_and_AGM"),
    ("annual general meeting", "09_Corporate_Actions_and_AGM"),
    ("corporate action", "09_Corporate_Actions_and_AGM"),
    ("milestone", "09_Corporate_Actions_and_AGM"),
    ("due diligence", "02_Due_Diligence"),
    ("data room", "02_Due_Diligence"),
    ("cap table", "05_Capitalization_and_Securities"),
    ("captable", "05_Capitalization_and_Securities"),
    ("share certificate", "05_Capitalization_and_Securities"),
    ("nominee", "05_Capitalization_and_Securities"),
    ("warrant", "05_Capitalization_and_Securities"),
    ("payment direction", "06_Cashflows_and_Funding"),
    ("capital call", "06_Cashflows_and_Funding"),
    ("drawdown", "06_Cashflows_and_Funding"),
    ("distribution", "06_Cashflows_and_Funding"),
    ("funding", "06_Cashflows_and_Funding"),
    ("valuation", "08_Valuation"),
    ("capital account", "08_Valuation"),
    ("nav", "08_Valuation"),
    ("monitoring", "07_Monitoring_and_Financials"),
    ("financial statement", "07_Monitoring_and_Financials"),
    ("annual report", "07_Monitoring_and_Financials"),
    ("interim report", "07_Monitoring_and_Financials"),
    ("resolution", "03_Board_and_IC"),
    ("board", "03_Board_and_IC"),
    ("investment committee", "03_Board_and_IC"),
    ("transaction closure", "04_Legal_and_Closing"),
    ("closing", "04_Legal_and_Closing"),
    ("term sheet", "04_Legal_and_Closing"),
    ("subscription", "04_Legal_and_Closing"),
    ("framework agreement", "04_Legal_and_Closing"),
    ("agreement", "04_Legal_and_Closing"),
    ("articles", "04_Legal_and_Closing"),
    ("deed", "04_Legal_and_Closing"),
    ("investment summary", "01_Investment_Thesis_and_Memos"),
    ("investment memo", "01_Investment_Thesis_and_Memos"),
    ("presentation", "01_Investment_Thesis_and_Memos"),
    (" ir ", "01_Investment_Thesis_and_Memos"),
    ("return analysis", "01_Investment_Thesis_and_Memos"),
]

# Content signals (checked only when kind + path are inconclusive).
TEXT_RULES = [
    ("in witness whereof", "04_Legal_and_Closing"),
    ("subscription agreement", "04_Legal_and_Closing"),
    ("shareholders' agreement", "04_Legal_and_Closing"),
    ("capitalisation table", "05_Capitalization_and_Securities"),
    ("fully diluted", "05_Capitalization_and_Securities"),
    ("capital account statement", "08_Valuation"),
    ("fair value", "08_Valuation"),
    ("balance sheet", "07_Monitoring_and_Financials"),
    ("income statement", "07_Monitoring_and_Financials"),
    ("cash flow statement", "07_Monitoring_and_Financials"),
    ("initial public offering", "10_Exit_and_Public_Markets"),
    ("admission to trading", "10_Exit_and_Public_Markets"),
    ("resolved that", "03_Board_and_IC"),
    ("board of directors", "03_Board_and_IC"),
    ("due diligence", "02_Due_Diligence"),
]


def classify(doc_kind: str, filename: str, relative_path: str, sample_text: str) -> tuple[str, str]:
    """Placement driven by what the document IS (filename/content/kind), with
    the original folder only as a weak last hint - so we fix the source mess
    rather than re-encode it."""
    low_name = (filename or "").lower()
    # 1. The filename is the strongest, least-polluted type signal.
    for kw, bucket in PATH_RULES:
        if kw in low_name:
            return bucket, f"name:'{kw.strip()}'"
    # 2. Content-inferred kind from the KB.
    if doc_kind and doc_kind in KIND_TO_BUCKET:
        return KIND_TO_BUCKET[doc_kind], f"kind:{doc_kind}"
    # 3. Actual text content.
    low_text = (sample_text or "").lower()
    for kw, bucket in TEXT_RULES:
        if kw in low_text:
            return bucket, f"content:'{kw}'"
    # 4. Original folder path - weak hint only (may carry source mis-filing).
    low_path = (relative_path or "").lower()
    for kw, bucket in PATH_RULES:
        if kw in low_path:
            return bucket, f"folder-hint:'{kw.strip()}'"
    return "11_Correspondence_and_Other", "default"


def build_proposal(db_path: Path, transaction_id: str) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    try:
        docs = conn.execute(
            """SELECT document_id, relative_path, filename, doc_kind, extraction_status
               FROM documents WHERE transaction_id = ? ORDER BY relative_path""",
            (transaction_id,),
        ).fetchall()
        rows: list[dict] = []
        for document_id, rel, filename, kind, status in docs:
            r = conn.execute(
                "SELECT text FROM document_nodes WHERE document_id = ? ORDER BY char_start LIMIT 1",
                (document_id,)).fetchone()
            sample = ((r[0] if r else "") or "")[:1500]
            bucket, reason = classify(kind, filename, rel, sample)
            rows.append({
                "filename": filename,
                "original_path": rel,
                "doc_kind": kind,
                "extraction_status": status,
                "proposed_bucket": bucket,
                "reason": reason,
            })
        return rows
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Propose a clean folder placement per document (read-only).")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--transaction", type=str, required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    rows = build_proposal(args.db, args.transaction)
    out = args.out or Path(f"data/outputs/{args.transaction}_reorg_proposal.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=["filename", "original_path", "doc_kind",
                                               "extraction_status", "proposed_bucket", "reason"])
        w.writeheader()
        w.writerows(rows)

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["proposed_bucket"]] = counts.get(r["proposed_bucket"], 0) + 1
    print(f"Proposed placement for '{args.transaction}' - {len(rows)} files")
    print(f"Manifest: {out}\n")
    for b in BUCKETS:
        if counts.get(b):
            print(f"  {counts[b]:4}  {b}")
    other = counts.get("11_Correspondence_and_Other", 0)
    print(f"\n(catch-all '11_Correspondence_and_Other': {other} = {100*other/max(1,len(rows)):.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
