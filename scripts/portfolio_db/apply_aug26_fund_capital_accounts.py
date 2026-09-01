"""Apply the Q2 2026 capital account statements for the non-MGX funds to the Aug'26 month.

North Summit, Acies and New Space were still carrying their Jul'26 values. Each figure below is
taken from the GP-issued statement named against it; those statements were read directly and every
figure was independently agreed to the Aug'26 accounts tracker.

New Space is reported in Euro, so the statement NAV is rolled forward for the post-statement
drawdown and then translated:
    EUR 47,540,482 (Q2 2026 partner statement, NAV after carried interest)
  + EUR  1,660,407.40 (Drawdown 23, called 17 Jul 2026 for value 22 Jul, CesiumAstro follow-on)
  = EUR 49,200,889.40  x  1.16169 GBP.. EURUSD  =  USD 57,156,181.21

New Space Capital GP Com SCSp is deliberately NOT updated here. The tracker derives it by
pro-rating the fund NAV on the commitment ratio and adding a hard-coded constant of 0.871 for which
no source is recorded, and the only GP capital account statement on file is Q3 2025. It stays at
its Jul'26 value and is reported as an open item rather than given a number we cannot evidence.

Run with --apply to write.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "portfolio" / "portfolio.sqlite"
MONTH = "2026-08"
STATEMENT_DATE = "2026-06-30"

# deal_name -> (committed, invested, distributions, carrying_value, remaining, source)
# All amounts in USD millions.
UPDATES: dict[str, tuple[float | None, float, float, float, float | None, str]] = {
    "North Summit Capital Fund": (
        None, 83.361611, 7.875571, 72.566225, None,
        "Investor's Capital Account Statement as of 6.30.26_Gailbot Holding RSC Ltd.pdf p.1 - "
        "Galbot Holding RSC Ltd (99.5000%): contributions 83,361,611, distributions (7,875,571), "
        "capital account at fair value carried forward 72,566,225, inception to 30 June 2026",
    ),
    "Acies Investments Fund I, L.P.": (
        17.112500, 15.726388, 0.0, 14.034903, 1.386113,
        "2026 Q2-CapitalAccountStatement.pdf p.1 - commitment $17,112,500, paid in capital "
        "$15,726,388, remaining $1,386,113, partner's capital ending $14,034,903 (inception to date). "
        "Statement rounds to whole dollars.",
    ),
    "New Space Capital Fund I": (
        None, None, None, 57.156181207085986, None,
        "NSC Fund SCS - Partner Statement - Q2 2026 p.1 partner's NAV after carried interest "
        "EUR 47,540,482, plus 2026.07.17 NSC Fund Drawdown 23 p.2 total capital call EUR 1,660,407.40 "
        "(CesiumAstro follow-on, carried at cost), = EUR 49,200,889.40 translated at EURUSD 1.16169",
    ),
}


def main() -> int:
    apply = "--apply" in sys.argv
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    lines: list[str] = []

    for deal, (committed, invested, distributions, carrying, remaining, source) in UPDATES.items():
        row = con.execute(
            "select committed, invested, distributions, carrying_value, remaining_commitment"
            " from monthly_positions where month_id=? and deal_name=?", (MONTH, deal)
        ).fetchone()
        if row is None:
            lines.append(f"  {deal}: NOT FOUND in {MONTH}")
            continue

        new = {
            "committed": committed if committed is not None else float(row["committed"] or 0),
            "invested": invested if invested is not None else float(row["invested"] or 0),
            "distributions": distributions if distributions is not None else float(row["distributions"] or 0),
            "carrying_value": carrying,
            "remaining_commitment": remaining if remaining is not None else float(row["remaining_commitment"] or 0),
        }
        new["gain"] = new["carrying_value"] + new["distributions"] - new["invested"]
        new["tvpi"] = ((new["carrying_value"] + new["distributions"]) / new["invested"]) if new["invested"] else 0.0

        lines.append(f"  {deal}")
        for field in ("committed", "invested", "distributions", "carrying_value", "remaining_commitment"):
            old = float(row[field] or 0)
            if abs(old - new[field]) > 0.0005:
                lines.append(f"      {field:<22} {old:>12,.6f} -> {new[field]:>12,.6f}")

        if apply:
            con.execute(
                "update monthly_positions set committed=?, invested=?, distributions=?,"
                " carrying_value=?, remaining_commitment=?, gain=?, tvpi=?, notes=?"
                " where month_id=? and deal_name=?",
                (new["committed"], new["invested"], new["distributions"], new["carrying_value"],
                 new["remaining_commitment"], new["gain"], new["tvpi"],
                 f"Q2 2026 capital account statement", MONTH, deal),
            )
            con.execute("delete from nav_observations where month_id=? and deal_name=?", (MONTH, deal))
            con.execute(
                "insert into nav_observations (month_id, deal_name, carrying_value, method,"
                " source_ref, valuation_date, base_month, entered_by, entered_at)"
                " values (?,?,?,?,?,?,?,?, datetime('now'))",
                (MONTH, deal, new["carrying_value"], "Capital account statement", source,
                 STATEMENT_DATE, MONTH, "apply_aug26_fund_capital_accounts"),
            )

    if apply:
        totals = con.execute(
            "select count(*), sum(invested), sum(carrying_value), sum(gain)"
            " from monthly_positions where month_id=? and tab='Live'", (MONTH,)
        ).fetchone()
        con.execute(
            "update tracker_months set live_count=?, live_invested=?, live_carrying=?, live_gain=?"
            " where month_id=?", (totals[0], totals[1], totals[2], totals[3], MONTH),
        )
        con.commit()

    print(f"Aug'26 fund capital accounts - {'APPLIED' if apply else 'DRY RUN (pass --apply to write)'}\n")
    print("\n".join(lines))
    print("\n  New Space Capital GP Com SCSp left unchanged: derived figure with an undocumented "
          "0.871 constant and no Q2 2026 GP statement on file. Reported as an open item.")
    if not apply:
        print("\n  no changes written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
