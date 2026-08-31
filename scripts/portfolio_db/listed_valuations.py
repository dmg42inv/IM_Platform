r"""Compute listed-holding NAVs from their valuation inputs, and persist those inputs.

Carrying value for a listed holding is not a stored opinion, it is a computation:

    carrying_value_usd = shares x (price / price_divisor) x fx_rate

where GBX (pence) prices carry a divisor of 100 and USD prices a divisor of 1.
The inputs below are transcribed from cited sources (the monthly tracker's NAV
tab for share counts, and dated market closes for prices/FX), and are stored in
a `valuation_inputs` table so any figure can be re-derived and traced later.

The July inputs are included deliberately: the script recomputes July from them
and asserts the result matches the carrying value already in the database. That
proves the formula before it is applied to a month we have not seen verified.

Run from repo root:
    .\.venv\Scripts\python.exe -m scripts.portfolio_db.listed_valuations --month 2026-08
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "data" / "portfolio" / "portfolio.sqlite"
OVERRIDES_DIR = REPO_ROOT / "data" / "source_of_truth"

_TRACKER_NAV_REF = (
    "Jul'26 tracker NAV tab (data/portfolio/_tracker_cache/2026-07.xlsx, sheet 'NAV', "
    "NAV Date 2026-07-31)")

# Share counts are carried from the tracker's NAV tab and are unchanged month to
# month unless a cash movement occurs; August had no investment cashflows.
_SHARES = {
    "ONT plc": 44_328_120,
    "vTv Therapeutics Inc.": 259_657,
    "Cerebras Systems Inc (1)": 1_441_711,
    "Cerebras Systems Inc (2)": 3_513_491,
}

LISTED_INPUTS: dict[str, list[dict]] = {
    # Baseline month, used to prove the formula against known-good figures.
    "2026-07": [
        {
            "deal_name": "ONT plc", "ticker": "ONT", "exchange": "LSE",
            "price": "113", "price_currency": "GBX", "price_divisor": 100,
            "price_date": "2026-07-31",
            "price_source": f"{_TRACKER_NAV_REF} market block row 18, 'source' column",
            "fx_pair": "GBPUSD", "fx_rate": "1.348", "fx_date": "2026-07-31",
            "fx_source": f"{_TRACKER_NAV_REF} market block row 22",
        },
        {
            "deal_name": "vTv Therapeutics Inc.", "ticker": "VTVT", "exchange": "NASDAQ",
            "price": "32.35", "price_currency": "USD", "price_divisor": 1,
            "price_date": "2026-07-31",
            "price_source": f"{_TRACKER_NAV_REF} market block row 19",
            "fx_pair": "", "fx_rate": "1", "fx_date": "", "fx_source": "",
        },
        {
            "deal_name": "Cerebras Systems Inc (1)", "ticker": "CBRS", "exchange": "NASDAQ",
            "price": "198.71", "price_currency": "USD", "price_divisor": 1,
            "price_date": "2026-07-31",
            "price_source": f"{_TRACKER_NAV_REF} market block row 20",
            "fx_pair": "", "fx_rate": "1", "fx_date": "", "fx_source": "",
        },
        {
            "deal_name": "Cerebras Systems Inc (2)", "ticker": "CBRS", "exchange": "NASDAQ",
            "price": "198.71", "price_currency": "USD", "price_divisor": 1,
            "price_date": "2026-07-31",
            "price_source": f"{_TRACKER_NAV_REF} market block row 20",
            "fx_pair": "", "fx_rate": "1", "fx_date": "", "fx_source": "",
        },
    ],
    "2026-08": [
        {
            "deal_name": "ONT plc", "ticker": "ONT", "exchange": "LSE",
            "price": "176.10", "price_currency": "GBX", "price_divisor": 100,
            "price_date": "2026-08-28",
            "price_source": ("stockanalysis.com/quote/lon/ONT close 176.10 GBX on 2026-08-28; "
                             "LSE closed 2026-08-31 (UK Summer Bank Holiday) so last trading day used"),
            "fx_pair": "GBPUSD", "fx_rate": "1.3545", "fx_date": "2026-08-31",
            "fx_source": "xe.com GBP/USD mid-market 1.3545 at 2026-08-31 10:09 UTC",
        },
        {
            "deal_name": "vTv Therapeutics Inc.", "ticker": "VTVT", "exchange": "NASDAQ",
            "price": "32.36", "price_currency": "USD", "price_divisor": 1,
            "price_date": "2026-08-28",
            "price_source": "stockanalysis.com/stocks/VTVT close 32.36 USD on 2026-08-28",
            "fx_pair": "", "fx_rate": "1", "fx_date": "", "fx_source": "",
        },
        {
            "deal_name": "Cerebras Systems Inc (1)", "ticker": "CBRS", "exchange": "NASDAQ",
            "price": "179.08", "price_currency": "USD", "price_divisor": 1,
            "price_date": "2026-08-28",
            "price_source": "stockanalysis.com/stocks/CBRS close 179.08 USD on 2026-08-28",
            "fx_pair": "", "fx_rate": "1", "fx_date": "", "fx_source": "",
        },
        {
            "deal_name": "Cerebras Systems Inc (2)", "ticker": "CBRS", "exchange": "NASDAQ",
            "price": "179.08", "price_currency": "USD", "price_divisor": 1,
            "price_date": "2026-08-28",
            "price_source": "stockanalysis.com/stocks/CBRS close 179.08 USD on 2026-08-28",
            "fx_pair": "", "fx_rate": "1", "fx_date": "", "fx_source": "",
        },
    ],
}

_INSTRUMENT = {
    "ONT plc": "Ordinary Shares",
    "vTv Therapeutics Inc.": "Ordinary Shares",
    "Cerebras Systems Inc (1)": "F Prefs",
    "Cerebras Systems Inc (2)": "Preferred Shares",
}


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS valuation_inputs (
            month_id TEXT,
            deal_name TEXT,
            ticker TEXT,
            exchange TEXT,
            instrument TEXT,
            shares REAL,
            shares_source TEXT,
            price REAL,
            price_currency TEXT,
            price_divisor REAL,
            price_date TEXT,
            price_source TEXT,
            fx_pair TEXT,
            fx_rate REAL,
            fx_date TEXT,
            fx_source TEXT,
            carrying_value_usd_m REAL,
            formula TEXT,
            entered_at TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_valinp_month ON valuation_inputs(month_id)")


def compute(row: dict) -> tuple[Decimal, str]:
    shares = Decimal(_SHARES[row["deal_name"]])
    price = Decimal(row["price"])
    divisor = Decimal(row["price_divisor"])
    fx = Decimal(row["fx_rate"] or "1")
    value_usd_m = (shares * (price / divisor) * fx) / Decimal(1_000_000)
    if divisor == 1 and fx == 1:
        formula = f"{shares:,} shares x {price} {row['price_currency']}"
    else:
        formula = (f"{shares:,} shares x ({price} {row['price_currency']} / {divisor}) "
                   f"x {fx} {row['fx_pair']}")
    return value_usd_m, formula


def db_carrying(conn: sqlite3.Connection, month_id: str, deal_name: str) -> Decimal | None:
    cur = conn.execute(
        "SELECT carrying_value FROM monthly_positions WHERE month_id = ? AND deal_name = ?",
        (month_id, deal_name))
    hit = cur.fetchone()
    return None if hit is None or hit[0] is None else Decimal(str(hit[0]))


def validate_baseline(conn: sqlite3.Connection, baseline_month: str) -> list[str]:
    """Recompute the baseline month from its inputs and compare to the stored
    figures. Any mismatch means the formula or an input is wrong, so we stop."""
    failures = []
    print(f"Validating formula against {baseline_month} (must reproduce stored values exactly):")
    for row in LISTED_INPUTS[baseline_month]:
        computed, formula = compute(row)
        stored = db_carrying(conn, baseline_month, row["deal_name"])
        if stored is None:
            failures.append(f"{row['deal_name']}: no stored value in {baseline_month}")
            continue
        diff = abs(computed - stored)
        ok = diff < Decimal("0.0000001")
        print(f"  [{'PASS' if ok else 'FAIL'}] {row['deal_name']:<28} "
              f"computed {computed:.10f} vs stored {stored:.10f}  (diff {diff:.12f})")
        if not ok:
            failures.append(f"{row['deal_name']}: computed {computed} != stored {stored}")
    return failures


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--month", required=True, help="Target month_id, e.g. 2026-08")
    ap.add_argument("--baseline", default="2026-07", help="Month used to prove the formula")
    ap.add_argument("--out", type=Path, default=None, help="Where to write the overrides CSV")
    args = ap.parse_args()

    if args.month not in LISTED_INPUTS:
        raise SystemExit(f"No listed valuation inputs defined for {args.month}.")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = sqlite3.connect(str(args.db))
    try:
        _ensure_table(conn)

        failures = validate_baseline(conn, args.baseline)
        if failures:
            raise SystemExit("Baseline validation failed; refusing to write:\n  " +
                             "\n  ".join(failures))
        print("Baseline validation passed - formula proven.\n")

        out_rows = []
        for month_id in (args.baseline, args.month):
            conn.execute("DELETE FROM valuation_inputs WHERE month_id = ?", (month_id,))
            for row in LISTED_INPUTS[month_id]:
                value, formula = compute(row)
                conn.execute(
                    "INSERT INTO valuation_inputs (month_id, deal_name, ticker, exchange, "
                    "instrument, shares, shares_source, price, price_currency, price_divisor, "
                    "price_date, price_source, fx_pair, fx_rate, fx_date, fx_source, "
                    "carrying_value_usd_m, formula, entered_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (month_id, row["deal_name"], row["ticker"], row["exchange"],
                     _INSTRUMENT[row["deal_name"]], float(_SHARES[row["deal_name"]]),
                     _TRACKER_NAV_REF, float(row["price"]), row["price_currency"],
                     float(row["price_divisor"]), row["price_date"], row["price_source"],
                     row["fx_pair"], float(row["fx_rate"] or 1), row["fx_date"],
                     row["fx_source"], float(value), formula, now),
                )
                if month_id != args.month:
                    continue
                prior = db_carrying(conn, args.baseline, row["deal_name"])
                source_ref = row["price_source"]
                if row["fx_source"]:
                    source_ref += f"; FX: {row['fx_source']}"
                source_ref += f"; shares {_SHARES[row['deal_name']]:,} per {_TRACKER_NAV_REF}"
                out_rows.append({
                    "deal_name": row["deal_name"],
                    "carrying_value": f"{value:f}",
                    "method": "observed",
                    "source_ref": source_ref,
                    "valuation_date": row["price_date"],
                    "note": (f"Marked to market. {formula}. "
                             f"Prior {args.baseline}: {prior:.6f}m." if prior is not None
                             else f"Marked to market. {formula}."),
                })
        conn.commit()

        out_path = args.out or (OVERRIDES_DIR / f"nav_overrides_{args.month}.csv")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=[
                "deal_name", "carrying_value", "method", "source_ref", "valuation_date", "note"])
            writer.writeheader()
            writer.writerows(out_rows)

        print(f"Computed {args.month} listed NAVs:")
        for r in out_rows:
            print(f"  {r['deal_name']:<28} {float(r['carrying_value']):>14,.6f} m")
        print(f"\nValuation inputs persisted for {args.baseline} and {args.month}.")
        print(f"Overrides written to: {out_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
