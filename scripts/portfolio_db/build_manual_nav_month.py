r"""Create or refresh a manual, NAV-only month in the portfolio DB.

Used when there is no monthly Portfolio Summary tracker workbook yet (e.g. an
interim month-end). It carries a base month's positions forward into a target
month, records the provenance of every carried value in `nav_observations`, and
optionally applies cited NAV overrides on top (for listed holdings priced at
month-end).

Nothing is invented: carried values are labelled `carried_forward`; only rows
present in an overrides file are changed, and each override must carry its own
source reference. Idempotent: re-running replaces the target month in place, so
it is safe and reversible (delete the target month to roll back).

Run from repo root, e.g.:
    .\.venv\Scripts\python.exe -m scripts.portfolio_db.build_manual_nav_month \
        --base 2026-07 --target 2026-08 --as-of 2026-08-31 --label "Aug'26"
    # optional NAV overrides (listed holdings):
    #   --overrides data/source_of_truth/nav_overrides_2026-08.csv
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "data" / "portfolio" / "portfolio.sqlite"

_POSITION_COLS = [
    "tab", "section", "deal_name", "status", "investing_entity", "vintage",
    "instrument", "geography", "sector", "deal_type", "committed", "invested",
    "remaining_commitment", "distributions", "carrying_value", "gain", "tvpi", "notes",
]

# Columns an overrides CSV may carry. Only `carrying_value` is required to change
# a value; the rest are provenance and are stored verbatim in nav_observations.
_OVERRIDE_COLS = [
    "deal_name", "carrying_value", "method", "source_ref", "valuation_date", "note",
]


def _ensure_nav_observations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS nav_observations (
            month_id TEXT,
            deal_name TEXT,
            carrying_value REAL,
            method TEXT,              -- carried_forward | observed | computed | override
            source_ref TEXT,          -- workbook cell, URL+date, statement, etc.
            valuation_date TEXT,      -- as-of date of the value's evidence
            base_month TEXT,          -- for carried_forward: where it came from
            entered_by TEXT,
            entered_at TEXT,
            note TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_navobs_month ON nav_observations(month_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_navobs_deal ON nav_observations(deal_name)")


def _load_base_positions(conn: sqlite3.Connection, base_month: str) -> pd.DataFrame:
    cols = ", ".join(_POSITION_COLS)
    df = pd.read_sql_query(
        f"SELECT {cols} FROM monthly_positions WHERE month_id = ?",
        conn, params=(base_month,))
    if df.empty:
        raise SystemExit(f"No positions found for base month {base_month}.")
    return df


def _load_overrides(path: Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame(columns=_OVERRIDE_COLS)
    if not path.exists():
        raise SystemExit(f"Overrides file not found: {path}")
    ov = pd.read_csv(path).fillna("")
    missing = {"deal_name", "carrying_value"} - set(ov.columns)
    if missing:
        raise SystemExit(f"Overrides file missing required columns: {sorted(missing)}")
    for col in _OVERRIDE_COLS:
        if col not in ov.columns:
            ov[col] = ""
    return ov


def _num(v) -> float | None:
    n = pd.to_numeric(v, errors="coerce")
    return None if pd.isna(n) else float(n)


def build_month(db: Path, base_month: str, target_month: str, as_of: str,
                label: str, overrides_path: Path | None) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = sqlite3.connect(str(db))
    try:
        _ensure_nav_observations(conn)
        base = _load_base_positions(conn, base_month)
        overrides = _load_overrides(overrides_path)
        override_by_name = {str(r["deal_name"]).strip(): r for _, r in overrides.iterrows()}

        # Fresh target month (idempotent / reversible).
        conn.execute("DELETE FROM monthly_positions WHERE month_id = ?", (target_month,))
        conn.execute("DELETE FROM tracker_months  WHERE month_id = ?", (target_month,))
        conn.execute("DELETE FROM nav_observations WHERE month_id = ?", (target_month,))

        applied, carried = 0, 0
        for _, row in base.iterrows():
            deal = str(row["deal_name"]).strip()
            carry = _num(row["carrying_value"])
            method, source_ref, val_date, note = (
                "carried_forward",
                f"DB {base_month} monthly_positions",
                "",
                "No Aug update; carried forward pending NAV.",
            )
            ov = override_by_name.get(deal)
            if ov is not None:
                new_val = _num(ov["carrying_value"])
                if new_val is not None:
                    carry = new_val
                    method = str(ov.get("method") or "observed")
                    source_ref = str(ov.get("source_ref") or "")
                    val_date = str(ov.get("valuation_date") or "")
                    note = str(ov.get("note") or "")
                    applied += 1
            else:
                carried += 1

            values = [row[c] for c in _POSITION_COLS]
            values[_POSITION_COLS.index("carrying_value")] = carry
            placeholders = ", ".join(["?"] * (len(_POSITION_COLS) + 2))
            conn.execute(
                f"INSERT INTO monthly_positions (month_id, as_of_date, {', '.join(_POSITION_COLS)}) "
                f"VALUES ({placeholders})",
                (target_month, as_of, *values),
            )
            conn.execute(
                "INSERT INTO nav_observations (month_id, deal_name, carrying_value, method, "
                "source_ref, valuation_date, base_month, entered_by, entered_at, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (target_month, deal, carry, method, source_ref, val_date,
                 base_month, "im_platform:build_manual_nav_month", now, note),
            )

        live = base[base["tab"] == "Live"]
        exited = base[base["tab"] == "Exited"]
        # Recompute live carrying from the (possibly overridden) target rows.
        tgt = pd.read_sql_query(
            "SELECT tab, invested, carrying_value, gain FROM monthly_positions WHERE month_id = ?",
            conn, params=(target_month,))
        tgt_live = tgt[tgt["tab"] == "Live"]
        conn.execute(
            "INSERT INTO tracker_months (month_id, year, month, as_of_date, label, "
            "source_folder, source_file, source_version, parsed_ok, deal_count, live_count, "
            "exited_count, live_invested, live_carrying, live_gain, parse_error, ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (target_month, int(target_month[:4]), int(target_month[5:7]), as_of, label,
             "(manual)", f"MANUAL carry-forward from {base_month} (NAV-only month)",
             "manual-cf-v1", 1, int(len(base)), int(len(live)), int(len(exited)),
             float(pd.to_numeric(tgt_live["invested"], errors="coerce").sum()),
             float(pd.to_numeric(tgt_live["carrying_value"], errors="coerce").sum()),
             float(pd.to_numeric(tgt_live["gain"], errors="coerce").sum()),
             None, now),
        )
        conn.commit()
        return {
            "target": target_month,
            "rows": int(len(base)),
            "carried": carried,
            "overrides_applied": applied,
            "live_carrying": float(pd.to_numeric(tgt_live["carrying_value"], errors="coerce").sum()),
        }
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--base", required=True, help="Base month_id to carry forward, e.g. 2026-07")
    ap.add_argument("--target", required=True, help="Target month_id to create, e.g. 2026-08")
    ap.add_argument("--as-of", required=True, help="As-of date for the target month, e.g. 2026-08-31")
    ap.add_argument("--label", required=True, help="Display label, e.g. Aug'26")
    ap.add_argument("--overrides", type=Path, default=None, help="Optional cited NAV overrides CSV")
    args = ap.parse_args()

    result = build_month(args.db, args.base, args.target, args.as_of, args.label, args.overrides)
    print(
        f"Built {result['target']}: {result['rows']} rows "
        f"({result['carried']} carried, {result['overrides_applied']} overridden). "
        f"Live carrying = {result['live_carrying']:.1f}m."
    )


if __name__ == "__main__":
    main()
