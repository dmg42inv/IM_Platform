"""Verify the grounded domicile candidates against the legal knowledge base.

For each entry in company_domicile_legal.json we locate its cited source
document in legal_kb.sqlite and check whether the recorded `domicile_phrase`
(and the domicile term itself) actually appears in that document's text. This
turns "candidate" rows into either:
  - phrase_verified : the cited phrase is present verbatim in the cited doc
  - term_only       : the phrase isn't verbatim but the jurisdiction term appears
  - phrase_not_found: neither found in that doc (needs manual review)
  - doc_not_found   : the cited source file isn't in the KB

Read-only. Writes a worksheet to data/outputs/Domicile_Verification.md and .json.

Run: python -m scripts.tracker2.verify_domiciles
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

DOM = Path("data/source_of_truth/company_domicile_legal.json")
DB = Path("data/legal_kb/legal_kb.sqlite")
OUT_MD = Path("data/outputs/Domicile_Verification.md")
OUT_JSON = Path("data/outputs/Domicile_Verification.json")


def _src_filename(source: str) -> str:
    return (source or "").split(" (legal doc")[0].strip()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# Markers that mean the matched sentence is about a third party (auditor / law
# firm / registry), not the portfolio company itself.
_THIRD_PARTY = (
    "pricewaterhousecoopers", "pwc", "arendt & medernach", "ernst & young",
    "deloitte", "kpmg", "registered with the luxembourg bar", "macandrews & forbes",
)
_PLACEHOLDER = ("[full company name]", "[number]", "[date]", "[\u2022]", "[name]")
# Generic words to drop when deriving a company's distinctive name tokens.
_STOP = {
    "inc", "inc.", "ltd", "ltd.", "llc", "lp", "l.p.", "plc", "holding", "holdings",
    "fund", "capital", "the", "and", "co", "co.", "corporation", "limited", "ventures",
    "technologies", "systems", "group", "strategic", "co-invest", "gp", "com", "scsp",
    "i", "ii", "iii", "1", "fund", "holding", "inc", "llc",
}


def _name_tokens(company_key: str) -> list[str]:
    raw = re.sub(r"[(),.]", " ", company_key.lower())
    return [w for w in raw.split() if w not in _STOP and len(w) >= 3]


def _evidence_quality(company_key: str, evidence: str) -> str:
    ev = (evidence or "").lower()
    if not ev:
        return "none"
    # Third-party / placeholder context is checked FIRST: if the domicile phrase
    # sits next to an auditor, law firm or a template blank, the company name
    # also appearing in the window does not make it self-evidence.
    if any(p in ev for p in _PLACEHOLDER):
        return "template_placeholder"
    if any(m in ev for m in _THIRD_PARTY):
        return "third_party_context"
    tokens = _name_tokens(company_key)
    if any(tok in ev for tok in tokens):
        return "self_named"
    return "context_unclear"


def _find_doc(con: sqlite3.Connection, filename: str) -> tuple | None:
    rows = con.execute(
        "select document_id, filename, relative_path from documents where filename = ?",
        (filename,),
    ).fetchall()
    if rows:
        return rows[0]
    target = _norm(filename)
    if not target:
        return None
    for did, fn, rel in con.execute(
        "select document_id, filename, relative_path from documents"
    ):
        if _norm(fn) == target:
            return did, fn, rel
    return None


def _search(con: sqlite3.Connection, document_id: int, needle: str) -> str | None:
    if not needle:
        return None
    nl = needle.lower()
    for (txt,) in con.execute(
        "select text from document_nodes where document_id = ?", (document_id,)
    ):
        if txt and nl in txt.lower():
            i = txt.lower().find(nl)
            return re.sub(r"\s+", " ", txt[max(0, i - 70):i + len(needle) + 70]).strip()
    return None


def main() -> None:
    dom = json.loads(DOM.read_text(encoding="utf-8"))
    con = sqlite3.connect(str(DB))
    results = []
    tally = {"phrase_verified": 0, "term_only": 0, "phrase_not_found": 0, "doc_not_found": 0}

    for key, e in dom.items():
        if key.startswith("_"):
            continue
        if e.get("domicile_status") == "confirmed" or e.get("listed_status_grounded") and "domicile" not in e:
            continue
        filename = _src_filename(e.get("domicile_source", ""))
        phrase = (e.get("domicile_phrase") or "").strip()
        domicile = e.get("domicile", "")
        doc = _find_doc(con, filename)
        status, snippet = "doc_not_found", ""
        if doc:
            did = doc[0]
            hit = _search(con, did, phrase)
            if hit:
                status, snippet = "phrase_verified", hit
            else:
                term = domicile.split(" (")[0]
                hit = _search(con, did, term)
                if hit:
                    status, snippet = "term_only", hit
                else:
                    status = "phrase_not_found"
        tally[status] += 1
        quality = _evidence_quality(key, snippet)
        confidence = (
            "high" if status == "phrase_verified" and quality == "self_named"
            else "low" if quality in ("third_party_context", "template_placeholder", "none")
            else "medium"
        )
        results.append({
            "company": key, "domicile": domicile, "source_file": filename,
            "phrase": phrase, "status": status, "evidence": snippet,
            "evidence_quality": quality, "confidence": confidence,
            "n_candidates": len(e.get("domicile_candidates", [])),
        })

    order = {"phrase_verified": 0, "term_only": 1, "phrase_not_found": 2, "doc_not_found": 3}
    conf_order = {"high": 0, "medium": 1, "low": 2}
    results.sort(key=lambda r: (conf_order[r["confidence"]], order[r["status"]], r["company"]))
    n_high = sum(1 for r in results if r["confidence"] == "high")
    n_med = sum(1 for r in results if r["confidence"] == "medium")
    n_low = sum(1 for r in results if r["confidence"] == "low")

    lines = [
        "# Domicile Verification Worksheet",
        "",
        f"Generated {date.today().isoformat()}. Each grounded domicile candidate checked "
        "against its cited document in the legal knowledge base (legal_kb.sqlite). The cited "
        "phrase being present is necessary but NOT sufficient - we also check the matched "
        "sentence names the company itself (self_named) rather than an auditor / law firm / "
        "template placeholder.",
        "",
        "## Summary",
        "",
        f"- **high** confidence (phrase verbatim AND names the company): **{n_high}**",
        f"- **medium** confidence (phrase/term found, context unclear): **{n_med}**",
        f"- **low** confidence (matched a third party / placeholder - REVIEW): **{n_low}**",
        "",
        f"Phrase-match tally: phrase_verified={tally['phrase_verified']}, "
        f"term_only={tally['term_only']}, phrase_not_found={tally['phrase_not_found']}, "
        f"doc_not_found={tally['doc_not_found']}.",
        "",
        "Only **high** rows are safe to promote to domicile_status=confirmed on a glance. "
        "**low** rows are likely false positives (the phrase describes someone else).",
        "",
        "| Confidence | Company | Domicile | Quality | Evidence (from cited doc) | Source file |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        ev = (r["evidence"] or "").replace("|", "\\|")
        if len(ev) > 150:
            ev = ev[:147] + "..."
        lines.append(
            f"| {r['confidence']} | {r['company']} | {r['domicile']} | "
            f"{r['evidence_quality']} | {ev} | {r['source_file']} |"
        )

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Checked {len(results)} domiciles against the KB.")
    print(f"  confidence: high={n_high}  medium={n_med}  low={n_low}")
    print("  " + "  ".join(f"{k}={v}" for k, v in tally.items()))
    print(f"Wrote {OUT_MD}\nWrote {OUT_JSON}")

    if "--promote" in sys.argv:
        promoted = 0
        for r in results:
            if r["confidence"] != "high":
                continue
            entry = dom.get(r["company"])
            if not entry:
                continue
            entry["domicile_status"] = "confirmed"
            entry["domicile_evidence"] = r["evidence"]
            entry["domicile_evidence_source"] = f"{r['source_file']} (legal_kb.sqlite)"
            promoted += 1
        DOM.write_text(json.dumps(dom, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Promoted {promoted} high-confidence domiciles to domicile_status=confirmed.")


if __name__ == "__main__":
    main()
