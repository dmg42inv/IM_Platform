"""Additional tracker-derived views for the dashboard beyond Live/Exited:
- Historical NAV series (scans prior monthly tracker snapshots)
- Ownership % + domiciliation ("%" tab)
- Monthly change log ("Log" tab)
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .live_exited_sections import extract_live_exited_sections


def discover_monthly_tracker_files(monthly_root: Path) -> dict[str, Path]:
    """Finds the latest-version 'Portfolio Summary' workbook in each dated
    monthly folder (e.g. '2.1 31 Jan 26') under the monthly report root."""
    files: dict[str, Path] = {}
    for folder in sorted(monthly_root.iterdir()):
        if not folder.is_dir():
            continue
        m = re.match(r"2\.\d+ \d+ (\w+) (\d+)", folder.name)
        if not m:
            continue
        label = f"{m.group(1)}'{m.group(2)}"
        candidates = [p for p in folder.glob("1. Portfolio Summary *.xlsx") if "~$" not in p.name]
        if not candidates:
            continue

        def version_key(p: Path) -> tuple[int, int]:
            vm = re.search(r"v(\d+)\.(\d+)", p.name)
            return (int(vm.group(1)), int(vm.group(2))) if vm else (0, 0)

        candidates.sort(key=version_key)
        files[label] = candidates[-1]
    return files


def build_historical_nav_series(monthly_files: dict[str, Path]) -> pd.DataFrame:
    """Live-investment invested/carrying-value totals per month, using the
    same Live/Exited tab parser as the main dashboard (so this ties out to
    the same 'Grand Total' the tracker itself shows each month)."""
    rows = []
    for label, path in monthly_files.items():
        try:
            deals = extract_live_exited_sections(path)
            live = deals[deals["tab"] == "Live"]
            rows.append(
                {
                    "month": label,
                    "invested": live["invested"].sum(),
                    "carrying_value": live["carrying_value"].sum(),
                    "gain": live["gain"].sum(),
                    "source_file": path.name,
                }
            )
        except Exception as e:  # noqa: BLE001 - keep going, flag which month failed
            rows.append({"month": label, "invested": None, "carrying_value": None, "gain": None, "source_file": f"PARSE ERROR: {e}"})
    return pd.DataFrame(rows)


def build_per_company_nav_history(monthly_files: dict[str, Path]) -> pd.DataFrame:
    """Per-company carrying-value / invested history across the prepared
    monthly tracker workbooks - one row per deal per month, using the same
    Live/Exited parser as the main dashboard. This is the source for each
    company's NAV-history sparkline (the full historical series, not the
    recent two-month snapshot file). Month order is preserved via month_index
    (monthly_files is already chronological)."""
    rows = []
    for index, (label, path) in enumerate(monthly_files.items()):
        try:
            deals = extract_live_exited_sections(path)
        except Exception:  # noqa: BLE001 - skip a month that won't parse
            continue
        for _, d in deals.iterrows():
            rows.append(
                {
                    "month": label,
                    "month_index": index,
                    "deal_name": str(d.get("deal_name", "")).strip(),
                    "tab": d.get("tab", ""),
                    "carrying_value": d.get("carrying_value"),
                    "invested": d.get("invested"),
                }
            )
    return pd.DataFrame(rows)


def _norm(v: object) -> str:
    return str(v).strip() if pd.notna(v) else ""


def extract_ownership_domicile(path: Path) -> pd.DataFrame:
    """Parses the '%' tab: per-deal fully-diluted ownership %, source for
    the % holding, incorporation/jurisdiction, and country."""
    raw = pd.read_excel(path, sheet_name="%", header=None)
    header_row = None
    for idx in range(len(raw)):
        cells = [_norm(v).lower() for v in raw.iloc[idx].tolist()]
        if "deals" in cells and "shares / units" in cells:
            header_row = idx
            break
    if header_row is None:
        raise ValueError("Could not find header row in '%' tab")

    col_map = {_norm(v).lower(): idx for idx, v in raw.iloc[header_row].items() if pd.notna(v)}
    c_deals = col_map.get("deals")
    c_shares = col_map.get("shares / units")
    c_total = col_map.get("total")
    c_pct = col_map.get("%")
    c_source = col_map.get("source for % holding")
    c_jurisdiction = col_map.get("incorporation/jurisdiction")
    c_country = col_map.get("country")

    rows = []
    section = "Direct Investments"
    for idx in range(header_row + 1, len(raw)):
        row = raw.iloc[idx]
        deal_name = _norm(row[c_deals]) if c_deals is not None else ""
        if not deal_name:
            continue
        if deal_name.lower() in ("direct investments", "funds investments"):
            section = deal_name
            continue
        rows.append(
            {
                "section": section,
                "deal_name": deal_name,
                "status_flag": _norm(row[1]) if pd.notna(row[1]) else "",
                "shares_units": pd.to_numeric(row[c_shares], errors="coerce") if c_shares is not None else None,
                "fully_diluted_total": pd.to_numeric(row[c_total], errors="coerce") if c_total is not None else None,
                "ownership_pct": pd.to_numeric(row[c_pct], errors="coerce") if c_pct is not None else None,
                "source_for_pct": _norm(row[c_source]) if c_source is not None else "",
                "jurisdiction": _norm(row[c_jurisdiction]) if c_jurisdiction is not None else "",
                "country": _norm(row[c_country]) if c_country is not None else "",
            }
        )
    return pd.DataFrame(rows)


def extract_change_log(path: Path) -> pd.DataFrame:
    """Parses the 'Log' tab into (month, company, update) rows, forward-
    filling the month label down from its header row."""
    raw = pd.read_excel(path, sheet_name="Log", header=None)
    rows = []
    current_month = ""
    for idx in range(len(raw)):
        row = raw.iloc[idx]
        month_cell = _norm(row[1]) if len(row) > 1 else ""
        company_cell = _norm(row[2]) if len(row) > 2 else ""
        update_cell = _norm(row[3]) if len(row) > 3 else ""

        if month_cell and month_cell.lower() != "date log":
            current_month = month_cell
        if company_cell and update_cell:
            rows.append({"month": current_month, "company": company_cell, "update": update_cell})
    return pd.DataFrame(rows)


# The tracker's own "NAV" sheet is laid out as: a "NAV Date" cell near the
# top, a header row ("Investments"/"Investing Entity"/"Instrument"/
# "Carrying Value"/.../"Comment"), then deals grouped under plain-text
# section rows ("Direct Investments", "Debt Investments", "Funds
# Investments") - the MGX rows continue directly after "Funds Investments"
# with no section label of their own, still Funds. A trailing "Note:" row
# (and any further bullet notes under it) ends the data.
_NAV_SHEET_SECTION_LABELS = {"direct investments", "debt investments", "funds investments"}


def extract_nav_sheet(path: Path) -> tuple[pd.DataFrame, str]:
    """Parses the tracker's own 'NAV' sheet for the two fields not otherwise
    captured anywhere else in the pipeline: an asset Type (Listed/Fund/PE,
    derived from the section + the tracker's own Comment text) and a
    Comment (source/last-revised note per deal). Returns (nav_df, nav_date)
    - nav_df has columns deal_name/investment_type/comment. Deliberately
    does NOT return the tracker's own Carrying Value figures - those are
    joined onto the platform's own already FX-corrected `carrying_value`
    by deal name instead, so this sheet is only a source for Type/Comment,
    not for the NAV number itself."""
    raw = pd.read_excel(path, sheet_name="NAV", header=None)

    nav_date = ""
    for idx in range(len(raw)):
        row = raw.iloc[idx]
        if _norm(row[1]).lower() == "nav date" and len(row) > 2 and pd.notna(row[2]):
            nav_date = pd.Timestamp(row[2]).strftime("%d %b %Y")
            break

    rows = []
    current_section = ""
    for idx in range(len(raw)):
        row = raw.iloc[idx]
        deal_name = _norm(row[1]) if len(row) > 1 else ""
        if not deal_name:
            continue
        if deal_name.lower() == "note:":
            break
        if deal_name.lower() in _NAV_SHEET_SECTION_LABELS:
            current_section = deal_name.lower()
            continue
        comment = _norm(row[7]) if len(row) > 7 else ""
        if current_section == "funds investments":
            investment_type = "Fund"
        elif "listed" in comment.lower():
            investment_type = "Listed"
        else:
            investment_type = "PE"
        rows.append({"deal_name": deal_name, "investment_type": investment_type, "comment": comment})
    return pd.DataFrame(rows), nav_date

