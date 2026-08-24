"""Answer verification and numerical grounding middleware.

Implements the mandatory, hidden validation step between retrieval and final
rendering (PRD 19.7). It does not converse with the user; given the retrieved
payload it:

    1. scans the primary clause and graph context for overriding / conditional
       legal language and elevates any governing clause;
    2. grounds every number / percentage / date to a verbatim source token
       (or an explicit calculation from proven figures), suppressing anything
       that cannot be proven as [UNVERIFIED_NUMBER];
    3. emits a machine-parseable validation state
       (PASSED | OVERRIDDEN | FAILED_UNVERIFIED_DATA) that hard-gates rendering.

The database remains the source of truth; this layer never invents facts. When
a downstream generator (LLM) is added, its output MUST pass through
`validate_answer` before being shown to a user.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

# --- Override / exception language ------------------------------------------

_OVERRIDE_PATTERNS = [
    re.compile(r"notwithstanding\s+anything\s+to\s+the\s+contrary", re.IGNORECASE),
    re.compile(r"\bnotwithstanding\b", re.IGNORECASE),
    re.compile(r"subject\s+to\s+(?:the\s+)?(?:section|clause|article|paragraph)\s*[0-9IVXA-Z.\-]+", re.IGNORECASE),
    re.compile(r"except\s+as\s+(?:otherwise\s+)?(?:provided|set\s+out|expressly\s+stated)", re.IGNORECASE),
    re.compile(r"unless\s+(?:expressly\s+)?(?:stated|provided|agreed)\s+otherwise", re.IGNORECASE),
    re.compile(r"provided\s+(?:always\s+)?that\b", re.IGNORECASE),
    re.compile(r"save\s+as\s+(?:otherwise\s+)?provided", re.IGNORECASE),
]

# --- Figures (numbers / percentages / currency / dates) ---------------------

_MONTHS = ("January|February|March|April|May|June|July|August|September|October|"
           "November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec")
_FIGURE_PATTERNS = [
    re.compile(r"[$\u00a3\u20ac]\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?\s?(?:million|billion|bn|m|k)?", re.IGNORECASE),
    re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s?(?:million|billion|bn|m|k)\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:\.\d+)?\s?%"),
    re.compile(r"\b\d+(?:\.\d+)?x\b"),
    re.compile(rf"\b\d{{1,2}}\s+(?:{_MONTHS})\.?\s+\d{{4}}\b"),
    re.compile(rf"\b(?:{_MONTHS})\.?\s+\d{{1,2}},?\s+\d{{4}}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"),
]


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


@dataclass
class ValidationResult:
    validation_status: str = "PASSED"
    override_detected: bool = False
    governing_clauses: list[str] = field(default_factory=list)
    numerical_grounding_verified: bool = True
    figures_found: list[str] = field(default_factory=list)
    unverified_figures: list[str] = field(default_factory=list)
    calculation_notes: str = "None"
    synthesized_response: str = ""

    def to_dict(self) -> dict:
        return {
            "validation_status": self.validation_status,
            "override_detected": self.override_detected,
            "governing_clauses": self.governing_clauses,
            "numerical_grounding_verified": self.numerical_grounding_verified,
            "verified_extracted_data": {
                "figures_found": self.figures_found,
                "unverified_figures": self.unverified_figures,
                "calculation_notes": self.calculation_notes,
            },
            "synthesized_response": self.synthesized_response,
        }


def scan_overrides(nodes: list[dict]) -> tuple[bool, list[str], list[str]]:
    """Return (override_detected, governing_clause_refs, evidence_snippets)."""
    governing: list[str] = []
    evidence: list[str] = []
    for node in nodes:
        text = node.get("text", "") or ""
        for pattern in _OVERRIDE_PATTERNS:
            m = pattern.search(text)
            if m:
                ref = node.get("section") or node.get("section_ref") or node.get("citation") or "(clause)"
                if ref not in governing:
                    governing.append(ref)
                snippet = _normalise(text[max(0, m.start() - 40):m.end() + 80])
                evidence.append(snippet)
                break
    return (len(governing) > 0, governing, evidence)


def extract_figures(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for pattern in _FIGURE_PATTERNS:
        for m in pattern.finditer(text or ""):
            value = _normalise(m.group(0))
            key = value.lower()
            if value and key not in seen:
                seen.add(key)
                found.append(value)
    return found


def verify_figures(figures: list[str], source_texts: list[str]) -> tuple[list[str], list[str]]:
    """A figure is grounded only if it appears verbatim in the source text."""
    corpus = _normalise(" \n ".join(source_texts)).lower()
    compact = corpus.replace(" ", "")
    verified: list[str] = []
    unverified: list[str] = []
    for fig in figures:
        norm = fig.lower()
        if norm in corpus or norm.replace(" ", "") in compact:
            verified.append(fig)
        else:
            unverified.append(fig)
    return verified, unverified


def validate_answer(user_query: str, primary_clause: dict,
                    graph_context: list[dict], candidate_answer: str | None = None) -> ValidationResult:
    """Run the full verification protocol and build the validation payload."""
    context_nodes = [primary_clause, *graph_context]
    source_texts = [n.get("text", "") for n in context_nodes]

    override_detected, governing, evidence = scan_overrides(context_nodes)

    # Figures come from the candidate answer if given, else from the cited text.
    if candidate_answer is not None:
        figures = extract_figures(candidate_answer)
    else:
        figures = extract_figures(primary_clause.get("text", ""))
    verified, unverified = verify_figures(figures, source_texts)

    if unverified:
        status = "FAILED_UNVERIFIED_DATA"
    elif override_detected:
        status = "OVERRIDDEN"
    else:
        status = "PASSED"

    citation = primary_clause.get("citation", "") or primary_clause.get("section_ref", "")
    body = _normalise(primary_clause.get("text", ""))[:600]
    parts = [f"[{citation}] {body}"] if citation or body else []
    if override_detected:
        parts.append(f"Governing/conditional language detected in: {', '.join(governing)}. "
                     f"The primary rule is conditional on this.")
    if verified:
        parts.append(f"Grounded figures: {', '.join(verified)}.")
    if unverified:
        parts.append(f"Suppressed unverified figures: {', '.join('[UNVERIFIED_NUMBER]' for _ in unverified)}.")
    synthesized = " ".join(parts)

    return ValidationResult(
        validation_status=status,
        override_detected=override_detected,
        governing_clauses=governing,
        numerical_grounding_verified=(not unverified),
        figures_found=verified,
        unverified_figures=unverified,
        calculation_notes="None",
        synthesized_response=synthesized,
    )


def _graph_context_for(conn: sqlite3.Connection, node: dict, limit: int = 6) -> list[dict]:
    """Pull cross-reference context: defined terms and sibling clauses in the doc."""
    document_id = node.get("document_id")
    if not document_id:
        return []
    rows = conn.execute(
        """SELECT dt.term, dt.definition, n.number, n.heading
           FROM defined_terms dt LEFT JOIN document_nodes n ON n.node_id = dt.node_id
           WHERE dt.document_id = ? AND length(dt.definition) > 0 LIMIT ?""",
        (document_id, limit),
    ).fetchall()
    context: list[dict] = []
    for term, definition, number, heading in rows:
        context.append({
            "text": f'"{term}" means {definition}',
            "section": number or heading or "definitions",
            "citation": f'definition of "{term}"',
            "document_id": document_id,
        })
    return context


def answer(db_path: Path, user_query: str, top_k: int = 5, **query_kwargs) -> dict:
    """End-to-end: hybrid retrieve -> build graph context -> verify -> payload."""
    if __package__:
        from . import query as query_mod
    else:  # pragma: no cover
        import query as query_mod

    results = query_mod.search(db_path, user_query, top_k=top_k, **query_kwargs)
    if not results:
        return {"validation_status": "FAILED_UNVERIFIED_DATA",
                "reason": "No cited evidence retrieved.", "results": []}

    conn = sqlite3.connect(str(db_path))
    try:
        # Rehydrate full node text for the top hit (snippet is truncated).
        top = results[0]
        primary = dict(top)
        primary["text"] = _node_text(conn, top) or top.get("snippet", "")
        primary["document_id"] = _document_id(conn, top)
        graph_context = _graph_context_for(conn, primary)
    finally:
        conn.close()

    verdict = validate_answer(user_query, primary, graph_context)
    payload = verdict.to_dict()
    payload["primary_citation"] = top.get("citation")
    payload["candidates"] = results
    return payload


def _node_text(conn: sqlite3.Connection, hit: dict) -> str | None:
    row = conn.execute(
        """SELECT n.text FROM document_nodes n JOIN documents d ON d.document_id = n.document_id
           WHERE d.relative_path = ? AND (n.number = ? OR n.heading = ?) LIMIT 1""",
        (hit.get("document"), hit.get("section"), hit.get("section")),
    ).fetchone()
    return row[0] if row else None


def _document_id(conn: sqlite3.Connection, hit: dict) -> str | None:
    row = conn.execute(
        "SELECT document_id FROM documents WHERE relative_path = ? AND transaction_id = ? LIMIT 1",
        (hit.get("document"), hit.get("transaction")),
    ).fetchone()
    return row[0] if row else None


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Grounded, verified answer over the legal KB.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--transaction", type=str, default=None)
    parser.add_argument("--status", type=str, default=None)
    args = parser.parse_args()

    payload = answer(args.db, args.query, top_k=args.top_k,
                     transaction=args.transaction, status=args.status)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
