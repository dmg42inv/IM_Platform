"""Parse a cleaned legal/financial document into structured elements.

Extracts, from plain extracted text, the structure needed for citation-grade
retrieval and reporting:

    parties         - named counterparties (with entity-type + role heuristics)
    dates           - execution / effective / notable dates
    defined_terms   - '"Term" means ...' style definitions
    sections        - numbered clauses / articles / headings, with char offsets
    obligations     - modal ("shall"/"must"/"agrees to") statements per section
    tables          - blocks of tabular numeric rows
    document_status - draft / executed / superseded / unknown (heuristic)

This is deterministic, offline heuristic parsing. It is intentionally
conservative: it captures real structure where the text supports it and
degrades gracefully (whole-document single section) where it does not. Every
element carries character offsets so the DB can produce exact citations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# --- Section / clause heading detection -------------------------------------

# "1.", "1.1", "1.2.3" followed by a heading or clause text.
_NUM_SECTION = re.compile(
    r"^\s*(?P<num>\d{1,2}(?:\.\d{1,3}){0,4})\.?\s+(?P<head>[^\n]{1,160})$",
    re.MULTILINE,
)
# "ARTICLE V", "SECTION 4", "CLAUSE 12".
_WORD_SECTION = re.compile(
    r"^\s*(?P<kind>ARTICLE|SECTION|CLAUSE|SCHEDULE|EXHIBIT|ANNEX|APPENDIX)\s+"
    r"(?P<num>[IVXLCDM]+|\d{1,3}[A-Z]?)\b[.:\-\s]*(?P<head>[^\n]{0,160})$",
    re.MULTILINE | re.IGNORECASE,
)
# All-caps heading line (e.g. "DEFINITIONS AND INTERPRETATION").
_CAPS_SECTION = re.compile(
    r"^\s*(?P<head>[A-Z][A-Z0-9 ,&/'\-]{4,70})\s*$",
    re.MULTILINE,
)
# Recital markers.
_RECITAL = re.compile(r"\b(WHEREAS|NOW,?\s+THEREFORE|RECITALS?)\b", re.IGNORECASE)

# --- Defined terms -----------------------------------------------------------

_DEFINED_TERM = re.compile(
    r'[\u201c"](?P<term>[A-Z][A-Za-z0-9 &/\-\.]{1,60})[\u201d"]\s*'
    r'(?:\((?:the|each|an?)\s+[\u201c"][^\u201d"]+[\u201d"]\)\s*)?'
    r'(?:shall\s+mean|means|shall\s+have\s+the\s+meaning|refers\s+to)\b'
    r'(?P<def>[^\n]{0,300})',
)
_PARENTHETICAL_TERM = re.compile(
    r'\((?:the|each|an?|collectively,?)\s+[\u201c"](?P<term>[A-Z][A-Za-z0-9 &/\-\.]{1,60})[\u201d"]\)',
)

# --- Parties / entities ------------------------------------------------------

_ENTITY_SUFFIX = re.compile(
    r"\b([A-Z][A-Za-z0-9&.,'\- ]{2,80}?"
    r"(?:Limited|Ltd\.?|LLC|L\.L\.C\.|Inc\.?|Incorporated|Corp\.?|Corporation|"
    r"PLC|plc|LLP|LP|L\.P\.|S\.C\.S\.?|S\.A\.?|S\.\u00e0 r\.l\.|GmbH|AG|"
    r"Pte\.?\s?Ltd\.?|Holdings?|Partners|Capital|Ventures|Fund(?:\s+[IVX]+)?))\b",
)
_PARTY_INTRO = re.compile(
    r"\b(?:by\s+and\s+between|between|among)\b(?P<body>.{0,400}?)"
    r"(?:\bWHEREAS\b|\bNOW\b|\brecitals?\b|\.\s*$)",
    re.IGNORECASE | re.DOTALL,
)

# --- Dates -------------------------------------------------------------------

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
_DATE_PATTERNS = [
    re.compile(rf"\b(\d{{1,2}}\s+(?:{_MONTHS})\.?\s+\d{{4}})\b"),
    re.compile(rf"\b((?:{_MONTHS})\.?\s+\d{{1,2}},?\s+\d{{4}})\b"),
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
    re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b"),
]
_DATED_AS_OF = re.compile(
    rf"\bdated(?:\s+as\s+of)?\s+(?P<date>\d{{1,2}}\s+(?:{_MONTHS})\.?\s+\d{{4}}|"
    rf"(?:{_MONTHS})\.?\s+\d{{1,2}},?\s+\d{{4}})",
    re.IGNORECASE,
)

# --- Obligations -------------------------------------------------------------

_OBLIGATION = re.compile(
    r"(?P<subject>[A-Z][A-Za-z0-9&.,'\- ]{2,70}?)\s+"
    r"(?P<modal>shall(?:\s+not)?|must(?:\s+not)?|agrees?\s+to|undertakes?\s+to|"
    r"will(?:\s+not)?|is\s+required\s+to|covenants?\s+to)\s+"
    r"(?P<body>[^\n\.]{5,220})",
)

# --- Financial facts ---------------------------------------------------------

_MAGNITUDE = {
    "k": 1_000, "thousand": 1_000,
    "m": 1_000_000, "mm": 1_000_000, "mn": 1_000_000, "million": 1_000_000,
    "bn": 1_000_000_000, "b": 1_000_000_000, "billion": 1_000_000_000,
}
_CURRENCY_SYMBOL = {"$": "USD", "\u00a3": "GBP", "\u20ac": "EUR"}
_CURRENCY_CODE = re.compile(r"\b(USD|GBP|EUR|US\$|CHF|JPY|AED|SGD)\b", re.IGNORECASE)
_MONEY = re.compile(
    r"(?P<sym>[$\u00a3\u20ac])?\s?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<mag>million|billion|thousand|bn|mm|mn|[mkb])?"
    r"(?:\s?(?P<code>USD|GBP|EUR|US\$|dollars?|pounds?|euros?))?",
    re.IGNORECASE,
)
_FACT_KIND_RULES = [
    ("commitment", "commitment"), ("committed", "commitment"),
    ("invested", "invested"), ("investment", "invested"),
    ("paid-in", "paid_in"), ("paid in", "paid_in"), ("drawn", "paid_in"),
    ("valuation", "valuation"), ("fair value", "fair_value"), ("nav", "nav"),
    ("net asset value", "nav"), ("carrying value", "carrying_value"),
    ("per share", "price_per_share"), ("share price", "price_per_share"),
    ("purchase price", "purchase_price"), ("consideration", "consideration"),
    ("distribution", "distribution"), ("proceeds", "proceeds"),
    ("management fee", "fee"), ("carried interest", "carry"), ("fee", "fee"),
    ("raising", "round_size"), ("round", "round_size"),
]

# --- Tables ------------------------------------------------------------------

_TABLE_ROW = re.compile(r"^.*?(?:\s{2,}|\t).*?\d[\d,.\-%$\u00a3\u20ac]*\s*$")
_NUMERIC_TOKEN = re.compile(r"[\d][\d,.\-%$\u00a3\u20ac]*")

# --- Status ------------------------------------------------------------------

_EXECUTED_MARKERS = re.compile(
    r"\b(IN\s+WITNESS\s+WHEREOF|duly\s+executed|executed\s+as\s+a\s+deed|"
    r"signature\s+page|/s/|SIGNED\s+by|for\s+and\s+on\s+behalf\s+of)\b",
    re.IGNORECASE,
)
_DRAFT_MARKERS = re.compile(
    r"\b(DRAFT|SUBJECT\s+TO\s+CONTRACT|FOR\s+DISCUSSION\s+PURPOSES|"
    r"WITHOUT\s+PREJUDICE|NOT\s+FOR\s+EXECUTION)\b",
    re.IGNORECASE,
)


@dataclass
class Section:
    number: str
    heading: str
    level: int
    char_start: int
    char_end: int
    text: str


@dataclass
class ParsedDocument:
    parties: list[dict] = field(default_factory=list)
    dates: list[dict] = field(default_factory=list)
    defined_terms: list[dict] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    obligations: list[dict] = field(default_factory=list)
    financial_facts: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    document_status: str = "unknown"
    status_evidence: str = ""


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out


def _detect_status(text: str) -> tuple[str, str]:
    exec_match = _EXECUTED_MARKERS.search(text)
    draft_match = _DRAFT_MARKERS.search(text)
    if draft_match and not exec_match:
        return "draft", draft_match.group(0)
    if exec_match:
        return "executed", exec_match.group(0)
    return "unknown", ""


def _find_sections(text: str) -> list[Section]:
    """Locate section headings and slice the document into sections."""
    boundaries: list[tuple[int, str, str, int]] = []  # (start, number, heading, level)

    for match in _WORD_SECTION.finditer(text):
        num = f"{match.group('kind').upper()} {match.group('num')}".strip()
        head = (match.group("head") or "").strip(" .:-")
        boundaries.append((match.start(), num, head, 1))

    for match in _NUM_SECTION.finditer(text):
        num = match.group("num")
        head = match.group("head").strip(" .:-")
        # Skip lines that are clearly prose or table rows, not headings.
        if len(_NUMERIC_TOKEN.findall(head)) >= 3:
            continue
        level = num.count(".") + 1
        boundaries.append((match.start(), num, head, level))

    for match in _RECITAL.finditer(text):
        boundaries.append((match.start(), "RECITALS", match.group(0).upper(), 1))

    # Sort by position and drop duplicates/overlaps at the same start.
    boundaries.sort(key=lambda b: b[0])
    deduped: list[tuple[int, str, str, int]] = []
    last_start = -1
    for b in boundaries:
        if b[0] == last_start:
            continue
        deduped.append(b)
        last_start = b[0]

    sections: list[Section] = []
    if not deduped:
        body = text.strip()
        if body:
            sections.append(Section("", "(whole document)", 0, 0, len(text), body))
        return sections

    for idx, (start, number, heading, level) in enumerate(deduped):
        end = deduped[idx + 1][0] if idx + 1 < len(deduped) else len(text)
        sections.append(
            Section(number, heading, level, start, end, text[start:end].strip())
        )
    return sections


def _find_parties(text: str) -> list[dict]:
    head = text[:4000]
    parties: list[dict] = []
    intro = _PARTY_INTRO.search(head)
    scope = intro.group("body") if intro else head
    for match in _ENTITY_SUFFIX.finditer(scope):
        name = re.sub(r"\s+", " ", match.group(1)).strip(" ,.")
        if len(name) < 4:
            continue
        parties.append({"name": name, "role": "party", "source": "intro" if intro else "header"})
    # Deduplicate by name.
    seen: set[str] = set()
    out: list[dict] = []
    for p in parties:
        key = p["name"].lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out[:20]


def _find_dates(text: str) -> list[dict]:
    dates: list[dict] = []
    dated = _DATED_AS_OF.search(text)
    if dated:
        dates.append({"value": dated.group("date").strip(), "role": "dated_as_of"})
    raw: list[str] = []
    for pattern in _DATE_PATTERNS:
        raw.extend(m.group(1) for m in pattern.finditer(text))
    for value in _dedupe(raw)[:40]:
        dates.append({"value": value, "role": "mentioned"})
    return dates


def _find_defined_terms(text: str) -> list[dict]:
    terms: list[dict] = []
    for match in _DEFINED_TERM.finditer(text):
        terms.append({
            "term": match.group("term").strip(),
            "definition": re.sub(r"\s+", " ", match.group("def")).strip(" .:-"),
            "char_start": match.start(),
        })
    for match in _PARENTHETICAL_TERM.finditer(text):
        terms.append({
            "term": match.group("term").strip(),
            "definition": "",
            "char_start": match.start(),
        })
    # Deduplicate by term, preferring an entry that has a definition.
    best: dict[str, dict] = {}
    for t in terms:
        key = t["term"].lower()
        if key not in best or (not best[key]["definition"] and t["definition"]):
            best[key] = t
    return sorted(best.values(), key=lambda t: t["char_start"])[:200]


def _find_obligations(text: str, sections: list[Section]) -> list[dict]:
    def section_for(pos: int) -> str:
        for sec in sections:
            if sec.char_start <= pos < sec.char_end:
                return sec.number or sec.heading
        return ""

    obligations: list[dict] = []
    for match in _OBLIGATION.finditer(text):
        subject = re.sub(r"\s+", " ", match.group("subject")).strip(" ,.")
        # Reject subjects that are just sentence fragments / lowercase noise.
        if len(subject) < 3 or subject[0].islower():
            continue
        obligations.append({
            "party": subject,
            "modality": match.group("modal").lower().strip(),
            "text": re.sub(r"\s+", " ", match.group("body")).strip(),
            "section": section_for(match.start()),
            "char_start": match.start(),
        })
    return obligations[:400]


def _classify_fact_kind(context: str) -> str:
    lowered = context.lower()
    for keyword, kind in _FACT_KIND_RULES:
        if keyword in lowered:
            return kind
    return "amount"


def _find_financial_facts(text: str) -> list[dict]:
    facts: list[dict] = []
    for match in _MONEY.finditer(text):
        sym = match.group("sym")
        mag = (match.group("mag") or "").lower()
        code = (match.group("code") or "").upper().replace("US$", "USD")
        num_raw = match.group("num")
        # Require a currency signal OR a magnitude word to avoid matching noise.
        if not sym and not code and not mag:
            continue
        try:
            value = float(num_raw.replace(",", ""))
        except ValueError:
            continue
        unit = ""
        if mag:
            value *= _MAGNITUDE.get(mag, 1)
            unit = mag
        currency = ""
        if sym:
            currency = _CURRENCY_SYMBOL.get(sym, "")
        if not currency and code:
            if code.startswith("DOLLAR"):
                currency = "USD"
            elif code.startswith("POUND"):
                currency = "GBP"
            elif code.startswith("EURO"):
                currency = "EUR"
            else:
                currency = code
        window = text[max(0, match.start() - 60):match.end() + 20]
        facts.append({
            "raw": match.group(0).strip(),
            "amount": value,
            "currency": currency,
            "unit": unit,
            "kind": _classify_fact_kind(window),
            "context": re.sub(r"\s+", " ", window).strip(),
            "char_start": match.start(),
        })
    return facts[:400]


def _find_tables(text: str) -> list[dict]:
    lines = text.split("\n")
    tables: list[dict] = []
    run: list[str] = []
    run_start_line = 0
    offset = 0
    line_offsets: list[int] = []
    for line in lines:
        line_offsets.append(offset)
        offset += len(line) + 1

    def flush(start_line: int, rows: list[str]) -> None:
        if len(rows) >= 2:
            start = line_offsets[start_line]
            block = "\n".join(rows)
            tables.append({
                "char_start": start,
                "char_end": start + len(block),
                "row_count": len(rows),
                "text": block,
            })

    for i, line in enumerate(lines):
        is_row = bool(_TABLE_ROW.match(line)) and len(_NUMERIC_TOKEN.findall(line)) >= 2
        if is_row:
            if not run:
                run_start_line = i
            run.append(line)
        else:
            flush(run_start_line, run)
            run = []
    flush(run_start_line, run)
    return tables[:50]


def parse_document(text: str) -> ParsedDocument:
    """Parse cleaned document text into structured elements."""
    if not text or not text.strip():
        return ParsedDocument()
    sections = _find_sections(text)
    status, evidence = _detect_status(text)
    return ParsedDocument(
        parties=_find_parties(text),
        dates=_find_dates(text),
        defined_terms=_find_defined_terms(text),
        sections=sections,
        obligations=_find_obligations(text, sections),
        financial_facts=_find_financial_facts(text),
        tables=_find_tables(text),
        document_status=status,
        status_evidence=evidence,
    )
