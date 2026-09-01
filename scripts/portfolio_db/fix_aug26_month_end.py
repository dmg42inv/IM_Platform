"""Correct the Aug'26 month: month-end listed prices, and recompute derived figures.

Two defects, both found by scripts/portfolio_db/validate_month.py:

1. Cerebras and vTv were marked at the 28 Aug close. Month end (31 Aug 2026) was the UK Summer
   Bank Holiday, which closes the LSE but not NASDAQ, so the holiday rule was applied to US
   listings that were in fact trading. ONT keeps its 28 Aug price: for the LSE that reasoning
   is correct.
2. `gain` and `tvpi` were carried forward from Jul'26 and never recomputed after the listed
   marks moved, leaving the Aug'26 gain overstated by 59.1m.

Run with --apply to write. Without it, the script only reports what it would change.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "portfolio" / "portfolio.sqlite"
MONTH = "2026-08"
PRICE_DATE = "2026-08-31"

_HOLIDAY_NOTE = (
    "NASDAQ traded normally on 31 Aug 2026; the UK Summer Bank Holiday closes the LSE only."
)

# ticker -> (month-end close, provenance). Only US listings are corrected; ONT is correctly
# held at its 28 Aug LSE close.
CORRECTIONS: dict[str, tuple[float, str]] = {
    "CBRS": (
        184.24,
        "MarketWatch marketwatch.com/investing/stock/cbrs and Yahoo Finance CBRS historical data - "
        f"close 184.24 USD on 2026-08-31, read 2026-09-01. {_HOLIDAY_NOTE} "
        "Agrees with the Aug'26 accounts tracker NAV tab (G21/G22).",
    ),
    "VTVT": (
        32.00,
        "Yahoo Finance VTVT historical data - close 32.00 USD on 2026-08-31, read 2026-09-01 "
        f"(28 Aug close was 32.36). {_HOLIDAY_NOTE} "
        "Agrees with the Aug'26 accounts tracker NAV tab (G19/M19).",
    ),
}


def main() -> int:
    apply = "--apply" in sys.argv
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    changes: list[str] = []

    repriced = 0
    for ticker, (price, source) in CORRECTIONS.items():
        rows = con.execute(
            "select deal_name, shares, price, carrying_value_usd_m from valuation_inputs"
            " where month_id=? and ticker=? order by deal_name", (MONTH, ticker)
        ).fetchall()
        for row in rows:
            shares = float(row["shares"])
            new_cv = shares * price / 1_000_000
            if abs(float(row["price"] or 0) - price) < 1e-9:
                continue
            repriced += 1
            changes.append(
                f"  {row['deal_name']:<28} price {row['price']} -> {price}   "
                f"carrying {row['carrying_value_usd_m']:.4f} -> {new_cv:.4f} USDm"
            )
            if apply:
                con.execute(
                    "update valuation_inputs set price=?, price_date=?, price_source=?,"
                    " carrying_value_usd_m=?, formula=? where month_id=? and deal_name=?",
                    (price, PRICE_DATE, source, new_cv,
                     f"{shares:,.0f} shares x {price} USD", MONTH, row["deal_name"]),
                )
                con.execute(
                    "update monthly_positions set carrying_value=? where month_id=? and deal_name=?",
                    (new_cv, MONTH, row["deal_name"]),
                )
                con.execute(
                    "update nav_observations set carrying_value=?, source_ref=?, valuation_date=?"
                    " where month_id=? and deal_name=?",
                    (new_cv, source, PRICE_DATE, MONTH, row["deal_name"]),
                )

    # Recompute the derived columns for every live line, so nothing is left carried forward.
    positions = con.execute(
        "select deal_name, invested, distributions, carrying_value, gain, tvpi"
        " from monthly_positions where month_id=? and tab='Live'", (MONTH,)
    ).fetchall()
    regain = 0
    for row in positions:
        invested = float(row["invested"] or 0)
        dist = float(row["distributions"] or 0)
        # Re-read carrying value: it may have just been updated above.
        carry = float(con.execute(
            "select carrying_value from monthly_positions where month_id=? and deal_name=?",
            (MONTH, row["deal_name"])).fetchone()[0] or 0)
        gain = carry + dist - invested
        tvpi = (carry + dist) / invested if invested else 0.0
        if abs(gain - float(row["gain"] or 0)) > 0.0005:
            regain += 1
            changes.append(
                f"  {row['deal_name']:<28} gain {float(row['gain'] or 0):>10.4f} -> {gain:>10.4f} USDm"
            )
        if apply:
            keep_tvpi = float(row["tvpi"] or 0) == 0.0 and carry > 0 and invested > 0
            if keep_tvpi:
                con.execute("update monthly_positions set gain=? where month_id=? and deal_name=?",
                            (gain, MONTH, row["deal_name"]))
            else:
                con.execute("update monthly_positions set gain=?, tvpi=? where month_id=? and deal_name=?",
                            (gain, tvpi, MONTH, row["deal_name"]))

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

    print(f"Aug'26 correction - {'APPLIED' if apply else 'DRY RUN (pass --apply to write)'}\n")
    print("\n".join(changes) or "  nothing to change")
    print(f"\n  {repriced} listed marks repriced, {regain} gain values recomputed")
    if not apply:
        print("\n  no changes written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
