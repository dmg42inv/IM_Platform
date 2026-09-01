"""Set the Aug'26 ONT FX to the month-end close, and derive the New Space GP position.

ONT
    The database carried GBPUSD 1.3545 (xe.com mid-market, intraday) and the tracker 1.348
    (xe.com at 23:45 on 31 Aug). Investing.com daily history gives a 31 Aug close of 1.3548.
    All three are within 0.5% of each other, inside the 2% tolerance agreed for FX, so the
    tracker rate is adopted so both systems report the same number.

New Space Capital GP Com SCSp
    No Q2 2026 GP capital account statement exists; only Q3 2025. The position is therefore
    derived on the tracker's basis, pro-rating the fund NAV on the commitment ratio and adding a
    constant of 0.871 translated at EURUSD. That constant has no recorded source. The derivation
    is reproduced here so the figure is at least transparent, and it is flagged in the note as
    derived rather than evidenced.

Run with --apply to write.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "portfolio" / "portfolio.sqlite"
MONTH = "2026-08"

ONT_FX = 1.348
ONT_FX_DATE = "2026-08-31"
ONT_FX_SOURCE = (
    "XE.com GBP/USD 1.348 at 2026-08-31 23:45, as used in the Aug'26 accounts tracker "
    "('NAV'!M22). Cross-checked against Investing.com daily history, which shows a 31 Aug close "
    "of 1.3548 on a range of 1.3524-1.3567; the two are 0.50% apart, inside the 2% tolerance "
    "agreed for FX, so the tracker rate is adopted for consistency across both systems."
)

GP_CONSTANT = 0.871
EURUSD = 1.16169
GP_NOTE = (
    "DERIVED, not evidenced: no Q2 2026 GP capital account statement exists (latest on file is "
    "Q3 2025). Computed as GP commitment / fund commitment x fund NAV, plus a constant of 0.871 "
    "translated at EURUSD 1.16169. The constant has no recorded source and should be replaced "
    "when a GP statement is obtained."
)


def main() -> int:
    apply = "--apply" in sys.argv
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    out: list[str] = []

    ont = con.execute(
        "select shares, price, price_divisor, fx_rate, carrying_value_usd_m from valuation_inputs"
        " where month_id=? and ticker='ONT'", (MONTH,)
    ).fetchone()
    shares = float(ont["shares"])
    gbp = shares * float(ont["price"]) / float(ont["price_divisor"] or 100)
    new_cv = gbp * ONT_FX / 1_000_000
    out.append(
        f"  ONT plc   FX {ont['fx_rate']} -> {ONT_FX}   "
        f"carrying {float(ont['carrying_value_usd_m']):.6f} -> {new_cv:.6f} USDm"
    )

    gp = con.execute(
        "select committed, invested, distributions from monthly_positions"
        " where month_id=? and deal_name='New Space Capital GP Com SCSp'", (MONTH,)
    ).fetchone()
    fund = con.execute(
        "select committed, carrying_value from monthly_positions"
        " where month_id=? and deal_name='New Space Capital Fund I'", (MONTH,)
    ).fetchone()
    gp_cv = (float(gp["committed"]) / float(fund["committed"])) * float(fund["carrying_value"]) \
        + GP_CONSTANT * EURUSD
    gp_old = float(con.execute(
        "select carrying_value from monthly_positions where month_id=? and deal_name=?",
        (MONTH, "New Space Capital GP Com SCSp")).fetchone()[0] or 0)
    out.append(f"  New Space GP   carrying {gp_old:.6f} -> {gp_cv:.6f} USDm  (derived, not evidenced)")

    if apply:
        con.execute(
            "update valuation_inputs set fx_rate=?, fx_date=?, fx_source=?, carrying_value_usd_m=?,"
            " formula=? where month_id=? and ticker='ONT'",
            (ONT_FX, ONT_FX_DATE, ONT_FX_SOURCE, new_cv,
             f"{shares:,.0f} shares x ({ont['price']} GBX / 100) x {ONT_FX} GBPUSD", MONTH),
        )
        for deal, cv, note, method, ref in (
            ("ONT plc", new_cv, "Listed month-end close", "Listed price", ONT_FX_SOURCE),
            ("New Space Capital GP Com SCSp", gp_cv, GP_NOTE, "Derived from fund NAV", GP_NOTE),
        ):
            row = con.execute(
                "select invested, distributions from monthly_positions where month_id=? and deal_name=?",
                (MONTH, deal)).fetchone()
            invested = float(row["invested"] or 0)
            dist = float(row["distributions"] or 0)
            con.execute(
                "update monthly_positions set carrying_value=?, gain=?, tvpi=?, notes=?"
                " where month_id=? and deal_name=?",
                (cv, cv + dist - invested, ((cv + dist) / invested) if invested else 0.0,
                 note, MONTH, deal),
            )
            con.execute("delete from nav_observations where month_id=? and deal_name=?", (MONTH, deal))
            con.execute(
                "insert into nav_observations (month_id, deal_name, carrying_value, method,"
                " source_ref, valuation_date, base_month, entered_by, entered_at)"
                " values (?,?,?,?,?,?,?,?, datetime('now'))",
                (MONTH, deal, cv, method, ref, ONT_FX_DATE, MONTH, "apply_aug26_ont_fx_and_gp"),
            )
        totals = con.execute(
            "select count(*), sum(invested), sum(carrying_value), sum(gain)"
            " from monthly_positions where month_id=? and tab='Live'", (MONTH,)
        ).fetchone()
        con.execute(
            "update tracker_months set live_count=?, live_invested=?, live_carrying=?, live_gain=?"
            " where month_id=?", (totals[0], totals[1], totals[2], totals[3], MONTH))
        con.commit()

    print(f"ONT FX and New Space GP - {'APPLIED' if apply else 'DRY RUN (pass --apply to write)'}\n")
    print("\n".join(out))
    if not apply:
        print("\n  no changes written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
