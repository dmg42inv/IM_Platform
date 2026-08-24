"""Grounded extraction of a company's domicile / jurisdiction of incorporation.

Domiciliation is a legal fact and must come from the original documents
(charter / articles / certificate of incorporation / agreement recitals), not
from the tracker. This module finds incorporation language verbatim in the
knowledge base and returns candidate jurisdictions with their citation, so the
value shown on a company profile is source-grounded and analyst-confirmable.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from pathlib import Path

# Canonical jurisdictions we normalise noisy captures onto.
_KNOWN_JURISDICTIONS = [
    "England and Wales", "England & Wales", "Scotland", "Northern Ireland",
    "United Kingdom", "State of Delaware", "Delaware", "Nevada", "California",
    "New York", "Cayman Islands", "British Virgin Islands", "Bermuda", "Jersey",
    "Guernsey", "Luxembourg", "Grand Duchy of Luxembourg", "Ireland",
    "Netherlands", "Singapore", "Hong Kong", "Abu Dhabi Global Market", "ADGM",
    "Dubai International Financial Centre", "DIFC", "United Arab Emirates",
    "Switzerland", "Germany", "France", "Canada", "Australia", "Mauritius",
    "Kazakhstan", "Israel", "State of Israel", "Massachusetts", "Texas",
    "Washington", "Wyoming", "Colorado", "Florida", "Virginia", "Illinois",
    "New Jersey", "Maryland", "China", "People's Republic of China", "PRC",
    "Japan", "South Korea", "India", "Saudi Arabia", "Qatar", "Bahrain",
    "Spain", "Italy", "Sweden", "Denmark", "Norway", "Finland", "Estonia",
    "Abu Dhabi",
]
# Collapse variants onto one canonical label.
_CANON = {
    "england & wales": "England and Wales",
    "england and wales": "England and Wales",
    "state of delaware": "Delaware",
    "state of israel": "Israel",
    "grand duchy of luxembourg": "Luxembourg",
    "people's republic of china": "China",
    "prc": "China",
    "adgm": "Abu Dhabi Global Market (ADGM)",
    "abu dhabi global market": "Abu Dhabi Global Market (ADGM)",
    "difc": "Dubai International Financial Centre (DIFC)",
    "dubai international financial centre": "Dubai International Financial Centre (DIFC)",
}
_KNOWN_LOWER = {j.lower(): j for j in _KNOWN_JURISDICTIONS}
# Longest-first so "England and Wales" wins over "England".
_KNOWN_ALT = "|".join(
    re.escape(j) for j in sorted(_KNOWN_JURISDICTIONS, key=len, reverse=True)
)

# Incorporation context immediately preceding a jurisdiction. Deliberately
# limited to incorporation verbs - NOT bare "laws of" / "a company" /
# "corporation", which also appear in governing-law clauses and prose and were
# mis-tagging governing law (e.g. "laws of the State of California") as domicile.
_CONTEXT = (
    r"(?:re-?incorporated|incorporated|incorporation|"
    r"re-?organi[sz]ed|organi[sz]ed|formed|constituted|chartered|"
    r"re-?domicil\w*|domicil\w*|registered|existing)"
)
# A known jurisdiction appearing shortly after incorporation context.
_KNOWN_NEAR = re.compile(
    rf"{_CONTEXT}[^.\n]{{0,40}}?\b(?P<jur>{_KNOWN_ALT})\b", re.IGNORECASE)
# Adjective form: "a Delaware corporation", "a Cayman Islands company".
_ADJ = re.compile(
    rf"\b(?:a|an)\s+(?P<jur>{_KNOWN_ALT})\s+"
    r"(?:corporation|company|limited|llc|entity|fund|soci[eé]t[eé])\b",
    re.IGNORECASE)

# Demonym adjective form: "an Israeli company", "a British company". These name
# a country only via nationality, so they are handled explicitly.
_DEMONYM = {
    "israeli": "Israel", "british": "United Kingdom", "english": "England and Wales",
    "dutch": "Netherlands", "swiss": "Switzerland", "german": "Germany",
    "french": "France", "japanese": "Japan", "chinese": "China",
    "caymanian": "Cayman Islands", "emirati": "United Arab Emirates",
    "singaporean": "Singapore", "irish": "Ireland", "canadian": "Canada",
    "australian": "Australia", "spanish": "Spain", "italian": "Italy",
    "swedish": "Sweden", "korean": "South Korea", "indian": "India",
}
_DEMONYM_ALT = "|".join(sorted(_DEMONYM, key=len, reverse=True))
_DEMONYM_ADJ = re.compile(
    rf"\b(?:a|an)\s+(?P<dem>{_DEMONYM_ALT})\s+"
    r"(?:corporation|company|limited|private\s+company|public\s+company|"
    r"entity|fund|start-?up)\b",
    re.IGNORECASE)

# Generic fallback for jurisdictions not in the known list. Captures a full
# Title-Case place name (up to 4 extra words, allowing "of"/"and" connectors)
# so multi-word jurisdictions aren't truncated (e.g. "Abu Dhabi Global Market",
# "United States").
_JUR = r"(?P<jur>[A-Z][A-Za-z.&']+(?:\s+(?:of\s+|and\s+)?[A-Z][A-Za-z.&']+){0,4})"
_FALLBACK = [
    re.compile(rf"incorporated\s+(?:in|under\s+the\s+laws\s+of)\s+(?:the\s+)?(?:State\s+of\s+)?{_JUR}\b"),
    re.compile(rf"organi[sz]ed\s+(?:and\s+existing\s+)?under\s+the\s+laws\s+of\s+(?:the\s+)?(?:State\s+of\s+)?{_JUR}\b"),
    re.compile(rf"domiciled\s+in\s+(?:the\s+)?{_JUR}\b"),
]
# Generic-fallback captures that are prose or partial, not a place of incorporation.
_FALLBACK_STOP = {
    "shareholders", "shareholder", "company", "the company", "purchaser",
    "seller", "connection", "accordance", "respect", "addition", "order",
    "default", "escrow", "trust", "witness", "good", "full", "behalf",
    "favour", "favor", "lieu", "part", "consideration", "exchange", "form",
    "name", "case", "event", "writing", "person", "entity", "jurisdiction",
    "abu", "united", "new", "state", "republic", "grand", "virgin", "british",
}
# Any of these tokens appearing in a fallback capture means it is prose/an
# instrument, not a place of incorporation.
_BAD_TOKENS = {
    "register", "registrar", "shareholders", "shareholder", "company",
    "agreement", "corporation", "partnership", "act", "ordinance", "law",
    "laws", "section", "article", "schedule", "exhibit", "name", "office",
    "principal", "board", "holder", "holders", "members", "director",
    "states", "america",
}
# Stop-words that indicate the capture ran into following prose, not a place.
_BAD_TAIL = re.compile(r"\b(with|having|and|under|pursuant|whose|the|a|an|as)\b", re.IGNORECASE)


def _canon(raw: str) -> str:
    low = re.sub(r"\s+", " ", raw).strip(" .,;:").lower()
    if low in _CANON:
        return _CANON[low]
    if low in _KNOWN_LOWER:
        return _KNOWN_LOWER[low]
    return raw.strip(" .,;:")


def _normalise_jurisdiction(raw: str) -> str:
    text = re.sub(r"\s+", " ", raw).strip(" .,;:")
    low = text.lower()
    if low in _CANON:
        return _CANON[low]
    if low in _KNOWN_LOWER:
        return _KNOWN_LOWER[low]
    for known_low, known in _KNOWN_LOWER.items():
        if known_low in low:
            return _canon(known)
    m = _BAD_TAIL.search(text)
    if m and m.start() > 0:
        text = text[:m.start()].strip(" .,;:")
    return text


def extract_domicile_candidates(text: str) -> list[dict]:
    """Return [{jurisdiction, phrase, char_start, verb_context}] found verbatim.

    `verb_context` marks authoritative incorporation-verb phrasing ("incorporated
    in X", "organized under the laws of X") versus a bare adjective/demonym form
    ("a X corporation", "an Israeli company"), which is weaker because the same
    form is also used for third parties and street addresses.
    """
    out: list[dict] = []
    seen: set[int] = set()

    def add(jur: str, match: re.Match, verb: bool) -> None:
        jur = _canon(jur)
        if not jur or len(jur) < 3 or match.start() in seen:
            return
        before = (match.string[max(0, match.start() - 18):match.start()]).lower()
        after = (match.string[match.end():match.end() + 24]).lower()
        # Negations ("formed outside the ...") and securities/tax boilerplate
        # ("registered under the ... Securities Act") are not a place of domicile.
        if any(w in before for w in ("outside", "non-", "not ", "other than")):
            return
        if any(w in after for w in ("securities act", "federal", " person", "tax", "gaap", "dollar")):
            return
        seen.add(match.start())
        out.append({
            "jurisdiction": jur,
            "phrase": re.sub(r"\s+", " ", match.group(0)).strip(),
            "char_start": match.start(),
            "verb_context": verb,
        })

    for m in _KNOWN_NEAR.finditer(text or ""):
        add(m.group("jur"), m, True)
    for m in _ADJ.finditer(text or ""):
        add(m.group("jur"), m, False)
    for m in _DEMONYM_ADJ.finditer(text or ""):
        add(_DEMONYM[m.group("dem").lower()], m, False)
    # Generic fallback rescues jurisdictions the known-list scan missed, but only
    # when no authoritative verb-context match was already found in this node.
    if not any(c["verb_context"] for c in out):
        for pattern in _FALLBACK:
            for m in pattern.finditer(text or ""):
                jur = _normalise_jurisdiction(m.group("jur"))
                low = jur.strip().lower()
                if (jur and len(jur) >= 3 and m.start() not in seen
                        and low not in _FALLBACK_STOP
                        and not (set(low.split()) & _BAD_TOKENS)):
                    seen.add(m.start())
                    out.append({"jurisdiction": jur,
                                "phrase": re.sub(r"\s+", " ", m.group(0)).strip(),
                                "char_start": m.start(),
                                "verb_context": True})
    return out


def find_domicile(db_path: Path, transaction_id: str, limit_nodes: int = 4000) -> dict:
    """Best-grounded domicile for a transaction, with its citation.

    A verbatim "incorporated in X" / charter statement (strong) always outranks
    any number of bare adjective/address mentions (weak); weak evidence is used
    only when no strong statement exists. Within a tier, more frequent and more
    authoritative (charter/constitutional) attestations win.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """SELECT n.node_id, n.text, d.relative_path, d.filename, d.doc_kind,
                      d.document_status, c.citation_text
               FROM document_nodes n
               JOIN documents d ON d.document_id = n.document_id
               LEFT JOIN citations c ON c.node_id = n.node_id
               WHERE d.transaction_id = ? AND n.node_type IN ('clause','recital')
                 AND length(n.text) > 0
               LIMIT ?""",
            (transaction_id, limit_nodes),
        ).fetchall()
    finally:
        conn.close()

    strong_tally: Counter = Counter()
    weak_tally: Counter = Counter()
    evidence: dict[str, dict] = {}
    for node_id, text, rel, filename, kind, status, citation in rows:
        authoritative = kind in ("charter", "constitutional_document")
        doc_weight = 3 if authoritative else 1
        for cand in extract_domicile_candidates(text):
            jur = cand["jurisdiction"]
            known = jur.lower() in _KNOWN_LOWER or jur in _CANON.values()
            score = doc_weight + (2 if known else 0) + (3 if cand["verb_context"] else 0)
            strong = cand["verb_context"] or authoritative
            (strong_tally if strong else weak_tally)[jur] += score
            # Prefer to cite an authoritative verb-context attestation.
            better = cand["verb_context"] and not evidence.get(jur, {}).get("verb_context")
            if jur not in evidence or better:
                evidence[jur] = {
                    "jurisdiction": jur,
                    "phrase": cand["phrase"],
                    "citation": citation or f"{filename}",
                    "document": rel,
                    "doc_kind": kind,
                    "document_status": status,
                    "verb_context": cand["verb_context"],
                }

    tally = strong_tally if strong_tally else weak_tally
    if not tally:
        return {"jurisdiction": None, "status": "not_found",
                "note": "No incorporation language found in the documents.",
                "candidates": []}

    ranked = tally.most_common()
    best_jur = ranked[0][0]
    result = dict(evidence[best_jur])
    result["status"] = "candidate"  # requires analyst confirmation before 'confirmed'
    result["support_count"] = ranked[0][1]
    result["evidence_strength"] = "strong" if strong_tally else "weak"
    result["candidates"] = [
        {"jurisdiction": j, "score": s, "citation": evidence[j]["citation"]}
        for j, s in ranked[:5]
    ]
    return result


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Extract grounded domicile for a transaction.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--transaction", type=str, required=True)
    args = parser.parse_args()
    print(json.dumps(find_domicile(args.db, args.transaction), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
