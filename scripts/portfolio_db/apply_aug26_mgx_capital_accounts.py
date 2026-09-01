"""Apply the Q2 2026 MGX capital account statements to the Aug'26 month.

Until now Aug'26 carried the Jul'26 MGX figures, which were themselves derived from the Q4'25 /
May'26 estimates. The Q2 2026 capital account statements were extracted into
`fund_capital_accounts` by the fund look-through work but never flowed into `monthly_positions`.

Every figure written here comes from `fund_capital_accounts` (extracted from the GP-issued PDFs)
except the recallable distributions, which that table does not carry. Those are stated below with
the statement line they come from, and are independently corroborated by the Aug'26 accounts
tracker MGX tab.

MGX I Denali Holding LP is written as its own position rather than folded into MGX I LP: it is a
separate legal entity with its own capital account statement, so it can be verified on its own.
This takes the live count from 26 to 27.

Run with --apply to write. Without it, the script only reports what it would change.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "portfolio" / "portfolio.sqlite"
MONTH = "2026-08"
AS_OF = "2026-08-31"
STATEMENT_DATE = "2026-06-30"

# Recallable distributions are not held in fund_capital_accounts. Taken from the same statements,
# page 1 "Distributions - Cash & Non-Cash" / page 2 "Plus Recallable Distributions" (since inception).
RECALLABLE_DISTRIBUTIONS = {
    "MGX Fund I LP": 14_688_852.0,
    "MGX I Denali Holding LP": 0.0,
    "MGX I Strategic Co-Invest LP": 234_999_999.0,
}

# Recallable capital is a return of capital, not a profit distribution, so it is netted against
# invested and reported as nil distributions. This is the only basis on which both identities hold:
#   gain     = carrying value - invested
#   unfunded = commitment - invested        (agrees with the statement's own ending unfunded to the cent)
# Carrying invested gross and the recallable amount as a distribution breaks the unfunded check by
# 14.7m on MGX I LP and 235.0m on the Co-Invest. The cash receipts themselves remain visible in the
# `cashflows` table with their source cells; only the classification differs.
CASH_DISTRIBUTIONS = {
    "MGX Fund I LP": 0.0,
    "MGX I Denali Holding LP": 0.0,
    "MGX I Strategic Co-Invest LP": 0.0,
}

# fund_capital_accounts.fund -> the monthly_positions row it maps to.
FUND_TO_POSITION = {
    "MGX Fund I LP": "MGX I LP",
    "MGX I Denali Holding LP": "MGX I Denali Holding LP",
    "MGX I Strategic Co-Invest LP": "MGX 1 Strategic Co-invest",
}

# Template for the Denali position, which does not exist in monthly_positions yet.
DENALI_TEMPLATE = {
    "tab": "Live",
    "section": "GX Investments Ltd : MGX and Related Investments",
    "status": "Unrealized",
    "investing_entity": "G42 Holding",
    "vintage": "2024",
    "instrument": "LP",
    "geography": "UAE",
    "sector": "Fund",
    "deal_type": "MGX LP",
}

M = 1_000_000.0


def main() -> int:
    apply = "--apply" in sys.argv
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    lines: list[str] = []

    accounts = con.execute(
        "select fund, our_ending_nav, our_contributions_itd, our_total_commitment,"
        " our_ending_unfunded, file_name, source_page"
        " from fund_capital_accounts where as_of_date=?", (STATEMENT_DATE,)
    ).fetchall()

    for acct in accounts:
        fund = acct["fund"]
        deal = FUND_TO_POSITION.get(fund)
        if deal is None:
            continue

        recallable = RECALLABLE_DISTRIBUTIONS[fund]
        committed = float(acct["our_total_commitment"]) / M
        # Invested is contributions net of recallable distributions: the basis the tracker uses,
        # and the basis on which the statement's own unfunded commitment is struck.
        invested = (float(acct["our_contributions_itd"]) - recallable) / M
        carrying = float(acct["our_ending_nav"]) / M
        distributions = CASH_DISTRIBUTIONS[fund] / M
        unfunded = float(acct["our_ending_unfunded"] or 0.0) / M
        gain = carrying - invested
        tvpi = (carrying + distributions) / invested if invested else 0.0

        existing = con.execute(
            "select committed, invested, distributions, carrying_value, gain"
            " from monthly_positions where month_id=? and deal_name=?", (MONTH, deal)
        ).fetchone()

        if existing is None:
            lines.append(
                f"  NEW  {deal:<30} cmt {committed:>9,.3f}  inv {invested:>9,.3f}  "
                f"cv {carrying:>10,.3f}  gain {gain:>10,.3f}"
            )
            if apply:
                con.execute(
                    "insert into monthly_positions (month_id, as_of_date, tab, section, deal_name,"
                    " status, investing_entity, vintage, instrument, committed, invested,"
                    " remaining_commitment, distributions, carrying_value, gain, tvpi, notes,"
                    " geography, sector, deal_type)"
                    " values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (MONTH, AS_OF, DENALI_TEMPLATE["tab"], DENALI_TEMPLATE["section"], deal,
                     DENALI_TEMPLATE["status"], DENALI_TEMPLATE["investing_entity"],
                     DENALI_TEMPLATE["vintage"], DENALI_TEMPLATE["instrument"],
                     committed, invested, unfunded, distributions, carrying, gain, tvpi,
                     f"Q2 2026 capital account statement ({acct['file_name']})",
                     DENALI_TEMPLATE["geography"], DENALI_TEMPLATE["sector"],
                     DENALI_TEMPLATE["deal_type"]),
                )
        else:
            lines.append(f"  {deal}")
            for label, old, new in (
                ("committed", existing["committed"], committed),
                ("invested", existing["invested"], invested),
                ("distributions", existing["distributions"], distributions),
                ("carrying value", existing["carrying_value"], carrying),
                ("gain", existing["gain"], gain),
            ):
                if abs(float(old or 0) - new) > 0.0005:
                    lines.append(f"      {label:<16} {float(old or 0):>12,.3f} -> {new:>12,.3f}")
            if apply:
                con.execute(
                    "update monthly_positions set committed=?, invested=?, remaining_commitment=?,"
                    " distributions=?, carrying_value=?, gain=?, tvpi=?, notes=?"
                    " where month_id=? and deal_name=?",
                    (committed, invested, unfunded, distributions, carrying, gain, tvpi,
                     f"Q2 2026 capital account statement ({acct['file_name']})", MONTH, deal),
                )

        if apply:
            source_ref = (
                f"{acct['file_name']} p.{acct['source_page']} - Ending NAV net of incentive "
                f"allocation {float(acct['our_ending_nav']):,.0f} USD at {STATEMENT_DATE}; "
                f"invested is contributions {float(acct['our_contributions_itd']):,.0f} less "
                f"recallable distributions {recallable:,.0f}"
            )
            con.execute("delete from nav_observations where month_id=? and deal_name=?", (MONTH, deal))
            con.execute(
                "insert into nav_observations (month_id, deal_name, carrying_value, method,"
                " source_ref, valuation_date, base_month, entered_by, entered_at)"
                " values (?,?,?,?,?,?,?,?, datetime('now'))",
                (MONTH, deal, carrying, "Capital account statement", source_ref,
                 STATEMENT_DATE, MONTH, "apply_aug26_mgx_capital_accounts"),
            )

    if apply:
        totals = con.execute(
            "select count(*), sum(invested), sum(carrying_value), sum(gain)"
            " from monthly_positions where month_id=? and tab='Live'", (MONTH,)
        ).fetchone()
        con.execute(
            "update tracker_months set live_count=?, live_invested=?, live_carrying=?, live_gain=?"
            " where month_id=?",
            (totals[0], totals[1], totals[2], totals[3], MONTH),
        )
        con.commit()

    print(f"MGX Aug'26 capital accounts - {'APPLIED' if apply else 'DRY RUN (pass --apply to write)'}\n")
    print("\n".join(lines) or "  nothing to change")
    mgx = con.execute(
        "select round(sum(carrying_value),4), count(*) from monthly_positions"
        " where month_id=? and tab='Live' and deal_name like 'MGX%'", (MONTH,)
    ).fetchone()
    print(f"\n  MGX carrying value now {mgx[0]:,.3f} USDm across {mgx[1]} positions")
    if not apply:
        print("  no changes written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
