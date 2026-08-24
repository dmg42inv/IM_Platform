"""Ingest every monthly Portfolio Summary tracker into a SQLite time-series DB.

Discovers the dated monthly folders across all FY archive folders (their names
vary - "1. 31 Jan 24", "1.4  31 Jan 25", "2.1 31 Jan 26", ...), picks the
highest-version "Portfolio Summary" workbook in each, parses it with the same
Live/Exited parser the dashboard uses, and upserts one row per deal per month
into `data/portfolio/portfolio.sqlite`. Idempotent: re-running refreshes each
month in place and records per-month parse status so coverage is auditable.

Run from the repo root:
    python -m scripts.portfolio_db.ingest_trackers
    python -m scripts.portfolio_db.ingest_trackers --main-root "<path>" --db "<path>"
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

# Make the editable package importable even if it isn't installed on this env.
_SRC = Path(__file__).resolve().parents[2] / "src" / "backend"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from im_platform.adapters.live_exited_sections import extract_positions  # noqa: E402

from scripts.portfolio_db.source_registry import (  # noqa: E402
    ensure_sources_table, register_reference_sources, register_source)

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_MAIN_ROOT = Path(
    r"C:\Users\divyesh.mahajan\OneDrive - G42\Desktop"
    r"\0.2 Portfolio Management - Monthly\1. Main (monthly report)"
)
DEFAULT_DB = Path("data/portfolio/portfolio.sqlite")
# Local copies of each source workbook. Copying forces OneDrive to hydrate a
# cloud-only placeholder, and lets later runs work even if OneDrive is offline.
CACHE_DIR = Path("data/portfolio/_tracker_cache")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
# A day-month-year date inside a folder name, e.g. "31 Jan 24", "30 Sep 22".
_DATE_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+'?(\d{2})\b")
_VERSION_RE = re.compile(r"v(\d+)\.(\d+)", re.IGNORECASE)

_POSITION_COLS = [
    "tab", "section", "deal_name", "status", "investing_entity", "vintage",
    "instrument", "geography", "sector", "deal_type", "committed", "invested",
    "remaining_commitment", "distributions", "carrying_value", "gain", "tvpi", "notes",
]


def _version_key(path: Path) -> tuple[int, int]:
    m = _VERSION_RE.search(path.name)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _pick_tracker_file(folder: Path) -> Path | None:
    """Highest-version 'Portfolio Summary' workbook in a month folder."""
    files = [p for p in folder.glob("*Portfolio Summary*.xlsx") if not p.name.startswith("~$")]
    if not files:
        return None
    primary = [p for p in files if p.name.strip().lower().startswith("1. portfolio summary")]
    pool = primary or files
    return max(pool, key=_version_key)


def discover_monthly_trackers(main_root: Path) -> list[dict]:
    """One entry per calendar month (latest version) across all FY folders."""
    found: dict[str, dict] = {}
    for folder in main_root.rglob("*"):
        if not folder.is_dir():
            continue
        m = _DATE_RE.search(folder.name)
        if not m:
            continue
        mon = _MONTHS.get(m.group(2)[:3].lower())
        if not mon:
            continue
        day, year = int(m.group(1)), 2000 + int(m.group(3))
        try:
            as_of = date(year, mon, day)
        except ValueError:
            as_of = date(year, mon, 1)
        tracker = _pick_tracker_file(folder)
        if tracker is None:
            continue
        month_id = f"{year:04d}-{mon:02d}"
        vm = _VERSION_RE.search(tracker.name)
        entry = {
            "month_id": month_id,
            "year": year,
            "month": mon,
            "as_of_date": as_of.isoformat(),
            "label": f"{as_of.strftime('%b')}'{str(year)[2:]}",
            "source_folder": folder.name,
            "source_file": tracker.name,
            "source_version": vm.group(0) if vm else "",
            "path": tracker,
        }
        # If the same month appears twice, keep the higher-version workbook.
        prev = found.get(month_id)
        if prev is None or _version_key(tracker) >= _version_key(prev["path"]):
            found[month_id] = entry
    return [found[k] for k in sorted(found)]


def _ensure_column(conn: sqlite3.Connection, table: str, col: str, decl: str) -> None:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tracker_months (
            month_id TEXT PRIMARY KEY,
            year INTEGER, month INTEGER, as_of_date TEXT, label TEXT,
            source_folder TEXT, source_file TEXT, source_version TEXT,
            parsed_ok INTEGER, deal_count INTEGER, live_count INTEGER,
            exited_count INTEGER, live_invested REAL, live_carrying REAL,
            live_gain REAL, parse_error TEXT, ingested_at TEXT
        );
        CREATE TABLE IF NOT EXISTS monthly_positions (
            month_id TEXT, as_of_date TEXT, tab TEXT, section TEXT,
            deal_name TEXT, status TEXT, investing_entity TEXT, vintage TEXT,
            instrument TEXT, committed REAL, invested REAL,
            remaining_commitment REAL, distributions REAL, carrying_value REAL,
            gain REAL, tvpi REAL, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS cashflows (
            source_id INTEGER, month_id TEXT, sheet TEXT, excel_row INTEGER,
            accounting_entity TEXT, deal_name TEXT, flow_date TEXT,
            contribution REAL, distribution REAL, currency TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_pos_month ON monthly_positions(month_id);
        CREATE INDEX IF NOT EXISTS ix_pos_deal ON monthly_positions(deal_name);
        CREATE INDEX IF NOT EXISTS ix_cf_deal ON cashflows(deal_name);
        """
    )
    ensure_sources_table(conn)
    _ensure_column(conn, "tracker_months", "source_id", "INTEGER")
    _ensure_column(conn, "monthly_positions", "source_id", "INTEGER")
    _ensure_column(conn, "monthly_positions", "geography", "TEXT")
    _ensure_column(conn, "monthly_positions", "sector", "TEXT")
    _ensure_column(conn, "monthly_positions", "deal_type", "TEXT")


_CF_SHEETS = ["CF (Equity, Debt)", "CF (Funds)"]


def _ingest_cashflows(conn: sqlite3.Connection, cache_path: Path,
                      month_id: str, source_id: int) -> int:
    """Load the dated cash movements from a tracker's CF sheets, each row keyed
    to its source file, sheet and Excel row for later verification."""
    conn.execute("DELETE FROM cashflows WHERE month_id = ?", (month_id,))
    xl = pd.ExcelFile(cache_path)
    total = 0
    for sheet in _CF_SHEETS:
        if sheet not in xl.sheet_names:
            continue
        raw = xl.parse(sheet, header=None)
        header = None
        for i in range(min(15, len(raw))):
            vals = [str(v).strip().lower() for v in raw.iloc[i].tolist()]
            if any("payment date" in v for v in vals) and any("contribution" in v for v in vals):
                header = i
                break
        if header is None:
            continue
        hv = [str(v).strip().lower() for v in raw.iloc[header].tolist()]

        def find(key: str) -> int | None:
            return next((j for j, v in enumerate(hv) if key in v), None)

        c_ent, c_deal, c_date = find("accounting"), find("investment"), find("payment date")
        c_con, c_dis, c_cur = find("contribution"), find("distribution"), find("currency")
        if c_deal is None or c_date is None:
            continue
        for i in range(header + 1, len(raw)):
            deal = raw.iat[i, c_deal]
            date = pd.to_datetime(raw.iat[i, c_date], errors="coerce")
            if pd.isna(date) or not str(deal).strip() or str(deal).strip().lower() == "nan":
                continue
            con = pd.to_numeric(raw.iat[i, c_con], errors="coerce") if c_con is not None else None
            dis = pd.to_numeric(raw.iat[i, c_dis], errors="coerce") if c_dis is not None else None
            ent = raw.iat[i, c_ent] if c_ent is not None else None
            cur = raw.iat[i, c_cur] if c_cur is not None else None
            conn.execute(
                "INSERT INTO cashflows (source_id, month_id, sheet, excel_row, "
                "accounting_entity, deal_name, flow_date, contribution, distribution, currency) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (source_id, month_id, sheet, i + 1,
                 (str(ent) if pd.notna(ent) else None), str(deal).strip(),
                 date.date().isoformat(),
                 (None if pd.isna(con) else float(con)),
                 (None if pd.isna(dis) else float(dis)),
                 (str(cur) if pd.notna(cur) else None)),
            )
            total += 1
    return total


def _num(v):
    n = pd.to_numeric(v, errors="coerce")
    return None if pd.isna(n) else float(n)


def _stage_local(src: Path, month_id: str) -> Path:
    """Copy the source workbook into a local cache (forces OneDrive hydration);
    fall back to a previously cached copy if the source can't be reached."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CACHE_DIR / f"{month_id}{src.suffix}"
    try:
        shutil.copy2(src, dest)
    except OSError:
        if dest.exists():
            return dest
        raise
    return dest


def ingest(main_root: Path, db_path: Path) -> dict:
    months = discover_monthly_trackers(main_root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        _init_db(conn)
        ok = failed = 0
        latest_ok = None
        changes = {"new": [], "changed": []}
        for mth in months:
            parse_error = None
            deals = pd.DataFrame()
            source_id = None
            local = None
            try:
                local = _stage_local(mth["path"], mth["month_id"])
                source_id, status = register_source(
                    conn, mth["path"], "tracker_summary", hash_path=local,
                    month_id=mth["month_id"], version=mth["source_version"])
                if status in ("new", "changed"):
                    changes[status].append(f"{mth['label']}: {mth['source_file']}")
                deals = extract_positions(local)
            except Exception as exc:  # noqa: BLE001 - record and continue
                parse_error = f"{type(exc).__name__}: {exc}"

            conn.execute("DELETE FROM monthly_positions WHERE month_id = ?", (mth["month_id"],))
            live = exited = 0
            live_inv = live_carry = live_gain = None
            if parse_error is None and len(deals):
                for _, d in deals.iterrows():
                    conn.execute(
                        f"INSERT INTO monthly_positions (month_id, as_of_date, source_id, {', '.join(_POSITION_COLS)}) "
                        f"VALUES (?, ?, ?, {', '.join(['?'] * len(_POSITION_COLS))})",
                        [mth["month_id"], mth["as_of_date"], source_id]
                        + [
                            (_num(d.get(c)) if c in ("committed", "invested", "remaining_commitment",
                                                      "distributions", "carrying_value", "gain", "tvpi")
                             else (str(d.get(c)) if d.get(c) is not None else None))
                            for c in _POSITION_COLS
                        ],
                    )
                live_df = deals[deals["tab"] == "Live"]
                exited_df = deals[deals["tab"] == "Exited"]
                live, exited = len(live_df), len(exited_df)
                live_inv = _num(live_df["invested"].sum())
                live_carry = _num(live_df["carrying_value"].sum())
                live_gain = _num(live_df["gain"].sum())
                ok += 1
                latest_ok = {"month_id": mth["month_id"], "path": local, "source_id": source_id}
            else:
                failed += 1

            conn.execute(
                """INSERT INTO tracker_months
                   (month_id, year, month, as_of_date, label, source_folder,
                    source_file, source_version, parsed_ok, deal_count,
                    live_count, exited_count, live_invested, live_carrying,
                    live_gain, parse_error, ingested_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(month_id) DO UPDATE SET
                    year=excluded.year, month=excluded.month,
                    as_of_date=excluded.as_of_date, label=excluded.label,
                    source_folder=excluded.source_folder,
                    source_file=excluded.source_file,
                    source_version=excluded.source_version,
                    parsed_ok=excluded.parsed_ok, deal_count=excluded.deal_count,
                    live_count=excluded.live_count, exited_count=excluded.exited_count,
                    live_invested=excluded.live_invested,
                    live_carrying=excluded.live_carrying, live_gain=excluded.live_gain,
                    parse_error=excluded.parse_error, ingested_at=excluded.ingested_at""",
                (
                    mth["month_id"], mth["year"], mth["month"], mth["as_of_date"],
                    mth["label"], mth["source_folder"], mth["source_file"],
                    mth["source_version"], 0 if parse_error else 1,
                    int(len(deals)), live, exited, live_inv, live_carry, live_gain,
                    parse_error, datetime.now().isoformat(timespec="seconds"),
                ),
            )
            if source_id is not None:
                conn.execute("UPDATE tracker_months SET source_id = ? WHERE month_id = ?",
                             (source_id, mth["month_id"]))

        cashflow_rows = 0
        if latest_ok is not None:
            cashflow_rows = _ingest_cashflows(
                conn, latest_ok["path"], latest_ok["month_id"], latest_ok["source_id"])
        ref_sources = register_reference_sources(conn, REPO_ROOT)
        conn.commit()
        source_count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    finally:
        conn.close()
    return {"months": len(months), "ok": ok, "failed": failed, "db": str(db_path),
            "sources": source_count, "cashflows": cashflow_rows, "ref_sources": ref_sources,
            "new_files": changes["new"], "changed_files": changes["changed"]}


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest monthly trackers into the portfolio SQLite DB.")
    ap.add_argument("--main-root", type=Path, default=DEFAULT_MAIN_ROOT)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = ap.parse_args()
    result = ingest(args.main_root, args.db)
    print(f"Discovered {result['months']} monthly trackers; "
          f"parsed OK: {result['ok']}, failed: {result['failed']}.")
    print(f"Sources registered (with SHA-256): {result['sources']} "
          f"(incl. {result['ref_sources']} reference files); "
          f"cashflow rows: {result['cashflows']}.")
    if result["new_files"] or result["changed_files"]:
        print(f"Changes since last run -> new: {len(result['new_files'])}, "
              f"changed: {len(result['changed_files'])}")
        for f in result["changed_files"][:15]:
            print(f"  changed: {f}")
        for f in result["new_files"][:15]:
            print(f"  new:     {f}")
    else:
        print("No source-file changes since last run.")
    print(f"Portfolio DB: {result['db']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
