"""Extract fund look-through holdings from MGX quarterly report PDFs.

The MGX 'SCHEDULE OF INVESTMENTS' page reports two levels: the fund's own
sub-vehicles (MGX AI Tech I LP, MGX Semis I LP, ...) and, below them, the
instrument level - the actual portfolio companies (OpenAI, SpaceX, Anthropic,
...). The instrument level is what gives us look-through exposure.

Parsing note: the PDF splits numbers into adjacent fragments with no gap
between them ('8' immediately followed by '07,308,075'). Words are therefore
merged by horizontal adjacency before being read as numbers, rather than split
on whitespace, which would corrupt every figure.

Nothing is inferred: each stored row keeps its source document, page and the
raw text line it came from, and the parsed rows are checked against the
document's own 'Total:' line before anything is written.

    .\\.venv\\Scripts\\python.exe -m scripts.fund_lookthrough.extract_mgx --list
    .\\.venv\\Scripts\\python.exe -m scripts.fund_lookthrough.extract_mgx --apply
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "data" / "portfolio" / "portfolio.sqlite"

MGX_ROOT = Path(
    r"C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.1 SPPM ###"
    r"\1. I N V E S T M E N T S  -  Global (Ex China)\1. F U N D - I N V E S T M E N T\4. MGX"
)

# Column order of the schedule, after the investment name and reporting currency.
NUMERIC_COLUMNS = [
    "invested_capital", "cost", "realized_cost", "realized_gain_loss",
    "proceeds_repayments", "unrealised_gain_loss", "fair_value", "total_return",
    "multiple",
]

# `irr` is appended for the vehicle block only, which reports one extra column.
STORED_COLUMNS = NUMERIC_COLUMNS

_NIL = {"-", "\u2013", "\u2014", "\u00fb", "", "n/a", "na"}
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}


@dataclass
class Holding:
    level: str
    investment_name: str
    reporting_currency: str
    values: dict[str, float | None]
    source_page: int
    source_line: str


@dataclass
class Schedule:
    as_of_date: str
    page: int
    vehicles: list[Holding] = field(default_factory=list)
    instruments: list[Holding] = field(default_factory=list)
    totals: dict[str, dict[str, float | None]] = field(default_factory=dict)
    unmapped: list[str] = field(default_factory=list)


def parse_number(token: str) -> float | None:
    """Read one cell. Returns None when the cell is a nil dash, 0.0 stays 0.0."""
    t = token.strip()
    if t.lower() in _NIL:
        return None
    negative = "(" in t
    t = t.replace("(", "").replace(")", "").replace(",", "").replace(" ", "")
    t = t.rstrip("x%").replace("\u00fb", "")
    if t in ("", "-"):
        return None
    try:
        value = float(t)
    except ValueError:
        return None
    return -value if negative else value


def merge_row_words(words: list[dict], max_gap: float = 1.2) -> list[tuple[str, float, float]]:
    """Join words that are horizontally adjacent; the PDF fragments numbers."""
    out: list[tuple[str, float, float]] = []
    for w in sorted(words, key=lambda w: w["x0"]):
        if out and (w["x0"] - out[-1][2]) <= max_gap:
            text, x0, _ = out[-1]
            out[-1] = (text + w["text"], x0, w["x1"])
        else:
            out.append((w["text"], w["x0"], w["x1"]))
    return out


def page_rows(page) -> list[tuple[float, list[tuple[str, float, float]]]]:
    """Group words into visual lines. Baselines wobble by a point or two, so an
    exact `top` match splits single rows and silently loses figures."""
    words = sorted(page.extract_words(x_tolerance=1.0, y_tolerance=2.0),
                   key=lambda w: (w["top"], w["x0"]))
    rows: list[tuple[float, list[tuple[str, float, float]]]] = []
    bucket: list[dict] = []
    top = None
    for w in words:
        if top is not None and abs(w["top"] - top) > 3.0:
            rows.append((top, merge_row_words(bucket)))
            bucket = []
            top = None
        bucket.append(w)
        top = w["top"] if top is None else top
    if bucket:
        rows.append((top or 0.0, merge_row_words(bucket)))
    return rows


def long_path(path: Path) -> str:
    """Some report paths exceed 260 chars; Windows needs the extended-length form."""
    p = str(path)
    if len(p) > 250 and not p.startswith("\\\\?\\"):
        p = "\\\\?\\" + p
    return p


def open_pdf(path: Path):
    return pdfplumber.open(long_path(path))


def anchors_from_total(total_numeric: list[tuple[str, float, float]]) -> list[float]:
    """Right-edge x of each column, taken from the schedule's own Total line.

    The Total line occupies every column, so it is a reliable template; data
    rows leave cells blank and cannot be mapped by token order alone.

    Nil cells ('-') must be kept. Dropping them shortens the template and
    silently shifts every column to their right by one, which reads the fair
    value column as unrealised gain and so on - a corruption that reconciling
    rows against the same mis-mapped Total line cannot detect.
    """
    return [x1 for _text, _x0, x1 in total_numeric]


def map_to_columns(numeric: list[tuple[str, float, float]], anchors: list[float],
                   columns: list[str]) -> dict[str, float | None]:
    """Assign cells to columns by right edge, splitting at the midpoint between
    anchors. A fixed tolerance cannot be used: numbers are right-aligned but a
    nil dash sits mid-cell, so its anchor is well left of the column's edge.
    """
    values: dict[str, float | None] = {c: None for c in columns}
    if not anchors:
        return values
    usable = min(len(anchors), len(columns))
    bounds = [(anchors[i] + anchors[i + 1]) / 2.0 for i in range(len(anchors) - 1)]
    for text, _x0, x1 in numeric:
        value = parse_number(text)
        if value is None:
            continue
        if x1 < anchors[0] - 30.0 or x1 > anchors[-1] + 30.0:
            continue
        idx = bisect.bisect_left(bounds, x1)
        if idx < usable:
            values[columns[idx]] = value
    return values


def parse_as_of(text: str) -> str:
    m = re.search(r"As at\s+([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", text)
    if m and m.group(1).lower() in _MONTHS:
        return f"{m.group(3)}-{_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if m and m.group(2).lower() in _MONTHS:
        return f"{m.group(3)}-{_MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return ""


def parse_schedule(page, page_no: int) -> Schedule | None:
    text = page.extract_text() or ""
    if "SCHEDULE OF INVESTMENTS" not in text.upper():
        return None
    sched = Schedule(as_of_date=parse_as_of(text), page=page_no)

    # First pass: classify each line and hold its tokens; columns are resolved after,
    # once the whole section is known.
    staged: dict[str, list[tuple[str, str, list, str, bool]]] = {"vehicle": [], "instrument": []}
    level = "vehicle"
    for _top, tokens in page_rows(page):
        if not tokens:
            continue
        line = " ".join(t[0] for t in tokens)
        if re.match(r"^\s*Instrument\s*Level", line, re.I):
            level = "instrument"
            continue
        if "Page" in line and "Confidential" in line:
            continue
        if "EXPRESSED IN" in line.upper() or "SCHEDULE OF INVESTMENTS" in line.upper():
            continue

        currency_idx = next((i for i, t in enumerate(tokens)
                             if t[0].strip().upper() in ("USD", "EUR", "GBP", "AED")), None)
        is_total = tokens[0][0].strip().rstrip(":").lower() == "total"
        if currency_idx is None and not is_total:
            continue

        if is_total:
            name, currency, numeric = "Total", "", tokens[1:]
        else:
            name = " ".join(t[0] for t in tokens[:currency_idx]).strip()
            currency = tokens[currency_idx][0].strip().upper()
            numeric = tokens[currency_idx + 1:]
        if not is_total and not name:
            continue
        staged[level].append((name, currency, numeric, line, is_total))

    for lvl, entries in staged.items():
        if not entries:
            continue
        # The vehicle block carries an extra IRR column; the instrument block does not.
        columns = NUMERIC_COLUMNS + (["irr"] if lvl == "vehicle" else [])
        total_entry = next((e for e in entries if e[4]), None)
        if total_entry is None:
            sched.unmapped.append(f"{lvl}: no Total row to anchor columns on")
            continue
        anchors = anchors_from_total(total_entry[2])
        if len(anchors) < 3:
            sched.unmapped.append(f"{lvl}: Total row gave only {len(anchors)} columns")
            continue
        for name, currency, numeric, line, is_total in entries:
            values = map_to_columns(numeric, anchors, columns)
            if is_total:
                sched.totals[lvl] = values
                continue
            holding = Holding(lvl, name, currency, values, page_no, line)
            (sched.vehicles if lvl == "vehicle" else sched.instruments).append(holding)
    return sched


def check_identities(level: str, rows: list[Holding]) -> list[str]:
    """Cross-column arithmetic the schedule must satisfy row by row.

    Summing rows against the printed Total proves nothing about column mapping,
    because both sides are mapped the same way. These identities span columns,
    so a one-place shift breaks them.
    """
    problems: list[str] = []
    for r in rows:
        cost = r.values.get("cost")
        fair_value = r.values.get("fair_value")
        if cost is not None and fair_value is not None:
            expected = cost + (r.values.get("unrealised_gain_loss") or 0.0)
            if abs(expected - fair_value) > max(2.0, abs(fair_value) * 1e-9):
                problems.append(
                    f"{level}.{r.investment_name}: cost + unrealised = {expected:,.0f} "
                    f"but fair value column reads {fair_value:,.0f}")
        invested = r.values.get("invested_capital")
        multiple = r.values.get("multiple")
        if invested and multiple is not None:
            expected_m = (invested + (r.values.get("total_return") or 0.0)) / invested
            if abs(expected_m - multiple) > 0.02:
                problems.append(
                    f"{level}.{r.investment_name}: (invested + total return) / invested = "
                    f"{expected_m:.2f}x but printed multiple is {multiple:.2f}x")
    return problems


def validate(sched: Schedule) -> list[str]:
    """Reconcile parsed rows to the schedule's own printed Total line."""
    problems = list(sched.unmapped)
    for level, rows in (("vehicle", sched.vehicles), ("instrument", sched.instruments)):
        if not rows:
            continue
        problems.extend(check_identities(level, rows))
        total = sched.totals.get(level)
        if not total:
            problems.append(f"{level}: {len(rows)} rows but no Total row to check against")
            continue
        checked = 0
        for col in ("invested_capital", "cost", "fair_value"):
            got = sum(r.values.get(col) or 0.0 for r in rows)
            want = total.get(col)
            if want is None:
                continue
            checked += 1
            if abs(got - want) > max(1.0, abs(want) * 1e-9):
                problems.append(
                    f"{level}.{col}: rows sum {got:,.2f} != printed total {want:,.2f} "
                    f"(diff {got - want:,.2f})")
        if checked == 0:
            problems.append(f"{level}: Total row had no comparable figures")
    return problems


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS fund_documents (
            doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
            fund TEXT, doc_type TEXT, as_of_date TEXT,
            file_name TEXT, file_path TEXT, sha256 TEXT UNIQUE,
            pages INTEGER, ingested_at TEXT
        );
        CREATE TABLE IF NOT EXISTS fund_holdings (
            doc_id INTEGER, fund TEXT, as_of_date TEXT, level TEXT,
            investment_name TEXT, reporting_currency TEXT,
            invested_capital REAL, cost REAL, realized_cost REAL,
            realized_gain_loss REAL, proceeds_repayments REAL,
            unrealised_gain_loss REAL, fair_value REAL, total_return REAL,
            multiple REAL, source_page INTEGER, source_line TEXT, extracted_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_fh_doc ON fund_holdings(doc_id);
        CREATE INDEX IF NOT EXISTS ix_fh_name ON fund_holdings(investment_name);
        """
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(long_path(path), "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_reports(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.pdf")
                  if "quarterly report" in p.name.lower() and not p.name.startswith("~"))


def fund_from_name(name: str) -> str:
    m = re.match(r"(MGX[^_]*?)(?:\s*[-_]\s*Quarterly|_Quarterly)", name, re.I)
    return (m.group(1) if m else name).strip(" -_")


def process(path: Path, conn: sqlite3.Connection | None, apply: bool) -> dict:
    fund = fund_from_name(path.name)
    result = {"file": path.name, "fund": fund, "schedules": 0,
              "vehicles": 0, "instruments": 0, "problems": []}
    with open_pdf(path) as pdf:
        pages = len(pdf.pages)
        scheds = [s for s in (parse_schedule(pg, i)
                              for i, pg in enumerate(pdf.pages, start=1)) if s]
    result["schedules"] = len(scheds)
    if not scheds:
        result["problems"].append("no SCHEDULE OF INVESTMENTS page")
        return result

    for sched in scheds:
        result["vehicles"] += len(sched.vehicles)
        result["instruments"] += len(sched.instruments)
        result["problems"].extend(f"p{sched.page}: {p}" for p in validate(sched))
        result["as_of"] = sched.as_of_date

    if not apply or conn is None or result["problems"]:
        return result

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    digest = sha256(path)
    # Reports are filed in more than one folder, so replace on fund and reporting
    # date rather than file hash, otherwise holdings are counted twice.
    conn.execute("DELETE FROM fund_holdings WHERE doc_id IN "
                 "(SELECT doc_id FROM fund_documents WHERE fund = ? AND as_of_date = ?)",
                 (fund, scheds[0].as_of_date))
    conn.execute("DELETE FROM fund_documents WHERE fund = ? AND as_of_date = ?",
                 (fund, scheds[0].as_of_date))
    cur = conn.execute(
        "INSERT INTO fund_documents (fund, doc_type, as_of_date, file_name, file_path, "
        "sha256, pages, ingested_at) VALUES (?,?,?,?,?,?,?,?)",
        (fund, "Quarterly Report", scheds[0].as_of_date, path.name, str(path),
         digest, pages, now))
    doc_id = cur.lastrowid
    for sched in scheds:
        for h in sched.vehicles + sched.instruments:
            conn.execute(
                "INSERT INTO fund_holdings (doc_id, fund, as_of_date, level, investment_name, "
                "reporting_currency, invested_capital, cost, realized_cost, realized_gain_loss, "
                "proceeds_repayments, unrealised_gain_loss, fair_value, total_return, multiple, "
                "source_page, source_line, extracted_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (doc_id, fund, sched.as_of_date, h.level, h.investment_name, h.reporting_currency,
                 *[h.values.get(c) for c in NUMERIC_COLUMNS],
                 h.source_page, h.source_line, now))
    conn.commit()
    result["doc_id"] = doc_id
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--root", type=Path, default=MGX_ROOT)
    ap.add_argument("--file", type=Path, default=None, help="Process a single PDF")
    ap.add_argument("--list", action="store_true", help="List candidate reports and exit")
    ap.add_argument("--apply", action="store_true", help="Write results to the database")
    args = ap.parse_args()

    reports = [args.file] if args.file else find_reports(args.root)
    if args.list:
        for r in reports:
            print(f"  {r.relative_to(args.root) if not args.file else r.name}")
        print(f"\n{len(reports)} quarterly report(s).")
        return

    conn = None
    if args.apply:
        conn = sqlite3.connect(str(args.db))
        ensure_tables(conn)
    try:
        ok = bad = 0
        for r in reports:
            res = process(r, conn, args.apply)
            status = "OK  " if not res["problems"] else "FAIL"
            print(f"[{status}] {res['fund']:<28} as_of={res.get('as_of', '?'):<10} "
                  f"vehicles={res['vehicles']:<3} instruments={res['instruments']:<3} "
                  f"{res['file'][:52]}")
            for p in res["problems"][:4]:
                print(f"         ! {p}")
            ok, bad = (ok + 1, bad) if not res["problems"] else (ok, bad + 1)
        print(f"\n{ok} clean, {bad} with problems."
              f"{'' if args.apply else '  (dry run - use --apply to write)'}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
