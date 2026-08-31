r"""Extract NewSpace Capital portfolio companies from the quarterly board report.

MGX publishes a schedule of investments; NewSpace instead devotes a page to each
portfolio company ("PortCo Updates - <company>"), which carries the holding's
economics together with its sector and headquarters. Those pages are the source
for both the look-through position and the classification of the entity, so the
sector and geography we report are the manager's own words rather than a guess.

Figures are reported in euro. They are stored as reported, with the currency
recorded, and converted only where an FX rate with a date and source is supplied.

    .\\.venv\\Scripts\\python.exe -m scripts.fund_lookthrough.extract_newspace
    .\\.venv\\Scripts\\python.exe -m scripts.fund_lookthrough.extract_newspace --apply
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .extract_mgx import DEFAULT_DB, ensure_tables, open_pdf, parse_number, sha256

NSC_ROOT = Path(
    r"C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.1 SPPM ###"
    r"\1. I N V E S T M E N T S  -  Global (Ex China)\1. F U N D - I N V E S T M E N T"
    r"\1. New Space Capital Fund"
)
FUND_NAME = "NewSpace Capital Fund SCS"

_MONEY = r"[\u20ac\u00a3$]?\s*([\d.,]+)\s*([MBK]?)"

# Each PortCo page is two columns, so a label's value runs until the next
# column's label rather than to the end of the line.
_STOP = (r"(?=\s+(?:Management|Fund|Investor|Equity|Investment|Board|Staff|Main|Debt|"
         r"Realised|Reported|Gross|Initial|Sector|Headquarter|Invested)\b|$)")

TEXT_FIELDS = {
    "sector": re.compile(r"\bSector\s+(.+?)" + _STOP, re.M),
    "headquarter": re.compile(r"\bHeadquarter\s+(.+?)" + _STOP, re.M),
    "investment_round": re.compile(r"\bInvestment Round\s+(.+?)" + _STOP, re.M),
}

PCT_FIELDS = {
    "fund_ownership_pct": re.compile(r"Fund Ownership %\s+([\d.]+)\s*%"),
    "investor_group_ownership_pct": re.compile(r"Investor Group Ownership %\s+([\d.]+)\s*%"),
    "investment_multiple": re.compile(r"Investment Multiple\s+([\d.]+)\s*x"),
    "gross_irr": re.compile(r"Gross IRR\s+([\d.]+)\s*%"),
}

# Money labels are not line-initial; a holding may also report an equity and a
# debt tranche on the same line, which together make up the position.
MONEY_LABELS = {
    "invested_capital": "Invested Capital",
    "investment_commitment": "Investment Commitment",
    "realised_proceeds": "Realised Proceeds",
    "reported_value": "Reported Value",
}

_SCALE = {"B": 1_000_000_000, "M": 1_000_000, "K": 1_000, "": 1.0}


def money(match: tuple[str, str] | None) -> float | None:
    if not match:
        return None
    raw, suffix = match
    value = parse_number(raw)
    return None if value is None else value * _SCALE.get(suffix.upper(), 1.0)


def money_after_label(text: str, label: str) -> tuple[float | None, str]:
    """Total the amounts following a label on its line, and return that line.

    Equity and debt tranches are reported side by side; the position is both.
    """
    for line in text.splitlines():
        idx = line.find(label)
        if idx < 0:
            continue
        tail = line[idx + len(label):]
        amounts = [money(m) for m in re.findall(_MONEY, tail)]
        amounts = [a for a in amounts if a is not None]
        if amounts:
            return sum(amounts), line.strip()
    return None, ""


def parse_portco_page(text: str) -> dict | None:
    title = re.search(r"PortCo Updates\s*[\u2013\u2014-]\s*(.+)", text)
    if not title:
        return None
    row: dict = {"investment_name": title.group(1).strip()}
    for key, pattern in TEXT_FIELDS.items():
        m = pattern.search(text)
        row[key] = m.group(1).strip() if m else None
    for key, pattern in PCT_FIELDS.items():
        m = pattern.search(text)
        row[key] = parse_number(m.group(1)) if m else None
    for key, label in MONEY_LABELS.items():
        row[key], row[f"{key}_line"] = money_after_label(text, label)
    return row


def parse_fund_summary(text: str) -> dict:
    out: dict = {}
    for key, label in {
        "total_commitment": "Total Commitment",
        "total_drawdowns": "Total Drawdowns since inception",
        "remaining_commitments": "Remaining Commitments",
        "nav": "Net Asset Value as at",
        "distributions": "Total Distributions",
    }.items():
        out[key], _ = money_after_label(text, label)
    m = re.search(r"Net TVPI[^\n]*?([\d.]+)\s*x", text)
    out["net_tvpi"] = parse_number(m.group(1)) if m else None
    return out


def ensure_classification_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS entity_classification (
            entity_name TEXT, sector TEXT, sub_sector TEXT, geography TEXT,
            classification_source TEXT, source_file TEXT, source_page INTEGER,
            as_of_date TEXT, method TEXT, recorded_at TEXT,
            PRIMARY KEY (entity_name, as_of_date)
        );
        """
    )


def process(path: Path, conn: sqlite3.Connection | None, apply: bool) -> dict:
    portcos: list[dict] = []
    summary: dict = {}
    as_of = ""
    with open_pdf(path) as pdf:
        pages = len(pdf.pages)
        for pno, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not as_of:
                m = re.search(r"Net Asset Value as at\s+(\d{1,2})\s*([A-Za-z]{3})[^\d]*(\d{4})", text)
                if m:
                    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                              "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
                    as_of = (f"{m.group(3)}-{months[m.group(2)[:3].lower()]:02d}-"
                             f"{int(m.group(1)):02d}")
            if "Fund Executive Summary" in text:
                summary = parse_fund_summary(text)
            row = parse_portco_page(text)
            if row:
                row["source_page"] = pno
                portcos.append(row)

    result = {"file": path.name, "as_of": as_of, "portcos": len(portcos),
              "summary": summary, "rows": portcos, "problems": [], "skipped": False}
    if not portcos:
        # Older reports predate the per-company format; nothing to extract.
        result["skipped"] = True
        return result
    missing = [r["investment_name"] for r in portcos if r.get("reported_value") is None]
    if missing:
        result["problems"].append(f"reported value missing for: {', '.join(missing)}")
    if not as_of:
        result["problems"].append("could not determine reporting date")

    if not apply or conn is None or result["problems"]:
        return result

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    digest = sha256(path)
    # The same report is filed in more than one folder, so replace on fund and
    # reporting date rather than file hash, otherwise holdings are counted twice.
    conn.execute("DELETE FROM fund_holdings WHERE doc_id IN "
                 "(SELECT doc_id FROM fund_documents WHERE fund = ? AND as_of_date = ?)",
                 (FUND_NAME, as_of))
    conn.execute("DELETE FROM fund_documents WHERE fund = ? AND as_of_date = ?",
                 (FUND_NAME, as_of))
    cur = conn.execute(
        "INSERT INTO fund_documents (fund, doc_type, as_of_date, file_name, file_path, "
        "sha256, pages, ingested_at) VALUES (?,?,?,?,?,?,?,?)",
        (FUND_NAME, "Board Report", as_of, path.name, str(path), digest, pages, now))
    doc_id = cur.lastrowid
    for r in portcos:
        conn.execute(
            "INSERT INTO fund_holdings (doc_id, fund, as_of_date, level, investment_name, "
            "reporting_currency, invested_capital, cost, realized_cost, realized_gain_loss, "
            "proceeds_repayments, unrealised_gain_loss, fair_value, total_return, multiple, "
            "source_page, source_line, extracted_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (doc_id, FUND_NAME, as_of, "instrument", r["investment_name"], "EUR",
             r.get("invested_capital"), r.get("invested_capital"), None, None,
             r.get("realised_proceeds"), None, r.get("reported_value"), None,
             r.get("investment_multiple"), r["source_page"],
             f"PortCo page: sector={r.get('sector')}, HQ={r.get('headquarter')}, "
             f"fund ownership={r.get('fund_ownership_pct')}%", now))
        conn.execute(
            "INSERT OR REPLACE INTO entity_classification VALUES (?,?,?,?,?,?,?,?,?,?)",
            (r["investment_name"], r.get("sector") or "Unclassified", None,
             r.get("headquarter") or "Unclassified",
             "NewSpace Capital quarterly board report, PortCo update page",
             path.name, r["source_page"], as_of, "reported_by_manager", now))
    conn.commit()
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--root", type=Path, default=NSC_ROOT)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    reports = sorted(p for p in args.root.rglob("*.pdf")
                     if "board report" in p.name.lower() and not p.name.startswith("~"))
    conn = None
    if args.apply:
        conn = sqlite3.connect(str(args.db))
        ensure_tables(conn)
        ensure_classification_table(conn)
    try:
        for path in reports:
            res = process(path, conn, args.apply)
            if res["skipped"]:
                continue
            flag = "OK  " if not res["problems"] else "FAIL"
            s = res["summary"]
            nav = s.get("nav")
            print(f"[{flag}] {res['as_of'] or '?':<10} portcos={res['portcos']:<3} "
                  f"NAV={'?' if nav is None else format(nav/1e6, ',.1f') + 'm EUR':<14} "
                  f"{res['file'][:46]}")
            for p in res["problems"][:3]:
                print(f"         ! {p}")
            for r in res["rows"]:
                rv = r.get("reported_value")
                print(f"           {r['investment_name'][:26]:<26} "
                      f"{str(r.get('sector'))[:18]:<18} {str(r.get('headquarter'))[:22]:<22} "
                      f"own={str(r.get('fund_ownership_pct')):>6}%  "
                      f"value={'?' if rv is None else format(rv/1e6, ',.1f')}m")
            holdings = sum(r.get("reported_value") or 0.0 for r in res["rows"])
            if nav:
                print(f"           {'-> portfolio vs NAV':<26} "
                      f"holdings {holdings/1e6:,.1f}m vs NAV {nav/1e6:,.1f}m "
                      f"({(holdings - nav)/1e6:+,.1f}m, i.e. fund cash and expenses)")
        if not args.apply:
            print("\n(dry run - use --apply to write)")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
