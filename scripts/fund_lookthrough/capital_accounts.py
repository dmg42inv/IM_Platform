r"""Extract our capital account position in each fund, and attribute look-through exposure.

A quarterly report tells us what the *fund* owns; it does not tell us what *we*
own. The capital account statement does: it reports our allocation of the fund
side by side with the total partnership. Our economic share of the fund is

    our ending NAV / total partnership ending NAV

and our exposure to any underlying company is that share of the company's fair
value as reported in the fund's schedule of investments.

Both the extraction and the attribution are checked before anything is written:
the six reported columns must parse, and the share must be a sensible fraction.

    .\\.venv\\Scripts\\python.exe -m scripts.fund_lookthrough.capital_accounts
    .\\.venv\\Scripts\\python.exe -m scripts.fund_lookthrough.capital_accounts --apply
    .\\.venv\\Scripts\\python.exe -m scripts.fund_lookthrough.capital_accounts --exposure
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .extract_mgx import (DEFAULT_DB, MGX_ROOT, merge_row_words, open_pdf,
                          page_rows, parse_number, sha256)

# Balance-sheet lines we need. Ending NAV anchors the columns because it is the
# only line guaranteed to populate all six.
LINES = {
    "ending_nav": re.compile(r"^Ending NAV", re.I),
    "beginning_nav": re.compile(r"^Beginning NAV", re.I),
    "contributions": re.compile(r"^Contributions\s*-\s*Cash", re.I),
    "distributions": re.compile(r"^Distributions\s*-\s*Cash", re.I),
    "total_commitment": re.compile(r"^Total Commitment", re.I),
    "ending_unfunded": re.compile(r"^Ending Unfunded Commitment", re.I),
}

# Six reported columns: our QTD/YTD/ITD, then the partnership's QTD/YTD/ITD.
OUR_ITD, FUND_ITD = 2, 5

_MONTHS = {m[:3].lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS fund_capital_accounts (
            fund TEXT, partner TEXT, as_of_date TEXT,
            our_ending_nav REAL, fund_ending_nav REAL, our_share REAL,
            our_contributions_itd REAL, fund_contributions_itd REAL,
            our_total_commitment REAL, fund_total_commitment REAL,
            our_ending_unfunded REAL,
            file_name TEXT, file_path TEXT, sha256 TEXT, source_page INTEGER,
            source_line TEXT, extracted_at TEXT,
            PRIMARY KEY (fund, partner, as_of_date)
        );
        """
    )


def parse_period_end(text: str) -> str:
    """Statements are headed e.g. '(Apr-26 - Jun-26)'; take the closing month."""
    matches = re.findall(r"([A-Za-z]{3})-(\d{2})\)", text)
    if not matches:
        return ""
    mon, yy = matches[0]
    m = _MONTHS.get(mon.lower())
    if not m:
        return ""
    year = 2000 + int(yy)
    last = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
            7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}[m]
    if m == 2 and year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
        last = 29
    return f"{year}-{m:02d}-{last:02d}"


def parse_statement(path: Path) -> dict:
    fund = partner = ""
    period_end = ""
    anchors: list[float] = []
    values: dict[str, list[float | None]] = {}
    source_lines: dict[str, tuple[int, str]] = {}

    with open_pdf(path) as pdf:
        pages = [(i, pg) for i, pg in enumerate(pdf.pages, start=1)]
        for pno, page in pages:
            text = page.extract_text() or ""
            if not period_end:
                period_end = parse_period_end(text)
            if not partner:
                m = re.search(r"Capital Account Statement for\s+(.+)", text)
                if m:
                    partner = m.group(1).strip().splitlines()[0].strip()
            if not fund:
                first = next((ln.strip() for ln in text.splitlines()
                              if ln.strip() and not ln.strip().startswith("QTD")), "")
                fund = re.sub(r"\(.*", "", first).strip()

            for _top, tokens in page_rows(page):
                label = " ".join(t[0] for t in tokens)
                numeric = [t for t in tokens if parse_number(t[0]) is not None]
                for key, pattern in LINES.items():
                    if not pattern.match(label.strip()):
                        continue
                    if key == "ending_nav" and len(numeric) >= 6:
                        anchors = [t[2] for t in numeric][:6]
                    if key in values:
                        continue
                    values[key] = numeric  # resolved to columns after anchors known
                    source_lines[key] = (pno, label.strip())

    if not anchors:
        return {"error": "could not locate a fully populated 'Ending NAV' line to set columns",
                "file": path.name}

    def column(key: str, idx: int) -> float | None:
        tokens = values.get(key)
        if not tokens:
            return None
        for text, _x0, x1 in tokens:
            if abs(anchors[idx] - x1) <= 10.0:
                return parse_number(text)
        return None

    our_nav = column("ending_nav", OUR_ITD)
    fund_nav = column("ending_nav", FUND_ITD)
    if not our_nav or not fund_nav:
        return {"error": "ending NAV missing for our column or the partnership column",
                "file": path.name}

    share = our_nav / fund_nav
    if not 0 < share <= 1.0000001:
        return {"error": f"implausible share {share:.6f} (our {our_nav:,.0f} / fund {fund_nav:,.0f})",
                "file": path.name}

    page_no, line = source_lines.get("ending_nav", (0, ""))
    return {
        "fund": fund, "partner": partner, "as_of_date": period_end,
        "our_ending_nav": our_nav, "fund_ending_nav": fund_nav, "our_share": share,
        "our_contributions_itd": column("contributions", OUR_ITD),
        "fund_contributions_itd": column("contributions", FUND_ITD),
        "our_total_commitment": column("total_commitment", OUR_ITD),
        "fund_total_commitment": column("total_commitment", FUND_ITD),
        "our_ending_unfunded": column("ending_unfunded", OUR_ITD),
        "file_name": path.name, "file_path": str(path), "sha256": sha256(path),
        "source_page": page_no, "source_line": line,
    }


def find_statements(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.pdf")
                  if "capital account" in p.name.lower() and not p.name.startswith("~"))


def show_exposure(conn: sqlite3.Connection, as_of: str) -> None:
    rows = conn.execute(
        """
        SELECT h.investment_name, h.fund, h.fair_value, c.our_share,
               h.fair_value * c.our_share AS our_exposure
        FROM fund_holdings h
        JOIN fund_capital_accounts c
          ON c.fund = h.fund COLLATE NOCASE AND c.as_of_date = h.as_of_date
        WHERE h.level = 'instrument' AND h.as_of_date = ? AND h.fair_value IS NOT NULL
        ORDER BY our_exposure DESC
        """, (as_of,)).fetchall()
    if not rows:
        print(f"No attributable look-through rows at {as_of}.")
        return
    print(f"\nLook-through exposure at {as_of} (our share of each fund's holdings)")
    print(f"{'Investment':<38} {'Fund':<30} {'Fund FV $m':>11} {'Share':>8} {'Ours $m':>10}")
    print("-" * 101)
    for name, fund, fv, share, ours in rows:
        print(f"{name[:38]:<38} {fund[:30]:<30} {fv/1e6:>11,.1f} {share:>7.2%} {ours/1e6:>10,.1f}")
    print("-" * 101)
    print(f"{'TOTAL (gross of incentive allocation)':<38} {'':<30} {'':>11} {'':>8} "
          f"{sum(r[4] for r in rows)/1e6:>10,.1f}")

    print("\nWhy this differs from our capital account NAV, per fund:")
    for fund, nav, share in conn.execute(
            "SELECT fund, our_ending_nav, our_share FROM fund_capital_accounts "
            "WHERE as_of_date = ? ORDER BY fund", (as_of,)):
        ours = sum(r[4] for r in rows if r[1].lower() == fund.lower())
        if ours == 0:
            print(f"  {fund:<32} no holdings extracted yet (our NAV {nav/1e6:,.1f}m, share {share:.2%})")
            continue
        gross = ours / share if share else 0.0
        print(f"  {fund:<32} our holdings {ours/1e6:>9,.1f}m vs our NAV {nav/1e6:>9,.1f}m "
              f"({(ours - nav)/1e6:>+8,.1f}m)")
        print(f"  {'':<32} fund investments {gross/1e6:>12,.1f}m vs fund NAV "
              f"{(nav/share)/1e6 if share else 0:>12,.1f}m")
    print("\n  Bases differ, so a gap is expected in either direction: the schedule of")
    print("  investments is gross, while NAV is net of incentive allocation, management")
    print("  fees and expenses; a fund may also hold undeployed cash. Any holding whose")
    print("  fair value is blank in the source is excluded, which understates that fund.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--root", type=Path, default=MGX_ROOT)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--exposure", action="store_true", help="Show attributed look-through")
    ap.add_argument("--as-of", default="2026-06-30")
    args = ap.parse_args()

    conn = sqlite3.connect(str(args.db))
    ensure_tables(conn)
    try:
        if args.exposure:
            show_exposure(conn, args.as_of)
            return

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        ok = bad = 0
        for path in find_statements(args.root):
            res = parse_statement(path)
            if "error" in res:
                bad += 1
                print(f"[FAIL] {res['file'][:66]}\n         ! {res['error']}")
                continue
            ok += 1
            print(f"[OK  ] {res['fund'][:30]:<30} {res['as_of_date']}  "
                  f"ours {res['our_ending_nav']/1e6:>9,.1f}m / fund "
                  f"{res['fund_ending_nav']/1e6:>10,.1f}m = {res['our_share']:>7.3%}")
            if args.apply:
                conn.execute(
                    "INSERT OR REPLACE INTO fund_capital_accounts VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (res["fund"], res["partner"], res["as_of_date"], res["our_ending_nav"],
                     res["fund_ending_nav"], res["our_share"], res["our_contributions_itd"],
                     res["fund_contributions_itd"], res["our_total_commitment"],
                     res["fund_total_commitment"], res["our_ending_unfunded"],
                     res["file_name"], res["file_path"], res["sha256"], res["source_page"],
                     res["source_line"], now))
        if args.apply:
            conn.commit()
        print(f"\n{ok} parsed, {bad} failed."
              f"{'' if args.apply else '  (dry run - use --apply to write)'}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
