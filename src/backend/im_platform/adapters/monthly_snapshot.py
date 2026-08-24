from __future__ import annotations

from pathlib import Path

import pandas as pd


SNAPSHOT_SHEET = "Portfolio_Snapshot_History"
LATEST_SNAPSHOT_SHEET = "Latest_Snapshot"
LATEST_DIFF_SHEET = "Latest_Diff"
CURRENT_SNAPSHOT_SHEET = "Current_Snapshot"
PREVIOUS_SNAPSHOT_SHEET = "Previous_Snapshot"

SNAPSHOT_COLUMNS = [
    "snapshot_month",
    "as_of_date",
    "tab",
    "section",
    "deal_name",
    "status",
    "investing_entity",
    "vintage",
    "instrument",
    "committed",
    "invested",
    "remaining_commitment",
    "distributions",
    "carrying_value",
    "gain",
    "tvpi",
    "irr",
    "valuation_date",
    "assumption_note",
]

METRIC_COLUMNS = [
    "committed",
    "invested",
    "remaining_commitment",
    "distributions",
    "carrying_value",
    "gain",
    "tvpi",
    "irr",
]


def build_monthly_snapshot(deals: pd.DataFrame, as_of_date: str) -> pd.DataFrame:
    snapshot = deals.copy()
    as_of = pd.to_datetime(as_of_date, errors="coerce")
    if pd.isna(as_of):
        as_of = pd.Timestamp.today().normalize()

    snapshot["snapshot_month"] = as_of.strftime("%Y-%m")
    snapshot["as_of_date"] = as_of.strftime("%Y-%m-%d")

    for col in SNAPSHOT_COLUMNS:
        if col not in snapshot.columns:
            snapshot[col] = None

    return snapshot[SNAPSHOT_COLUMNS].copy()


def upsert_snapshot_history(existing: pd.DataFrame, snapshot: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        history = snapshot.copy()
    else:
        existing = existing.copy()
        for col in SNAPSHOT_COLUMNS:
            if col not in existing.columns:
                existing[col] = None

        keys = set(zip(snapshot["snapshot_month"], snapshot["deal_name"]))
        keep = ~existing.apply(lambda row: (row["snapshot_month"], row["deal_name"]) in keys, axis=1)
        history = pd.concat([existing.loc[keep, SNAPSHOT_COLUMNS], snapshot], ignore_index=True)

    return history.sort_values(["snapshot_month", "tab", "section", "deal_name"], kind="stable").reset_index(drop=True)


def build_monthly_diff(history: pd.DataFrame, tolerance: float = 0.05) -> pd.DataFrame:
    if history.empty or "snapshot_month" not in history.columns:
        return _empty_diff()

    months = sorted(str(m) for m in history["snapshot_month"].dropna().unique())
    if len(months) < 2:
        return _empty_diff()

    previous_month, current_month = months[-2], months[-1]
    previous = history[history["snapshot_month"].astype(str) == previous_month].set_index("deal_name", drop=False)
    current = history[history["snapshot_month"].astype(str) == current_month].set_index("deal_name", drop=False)

    rows = []
    for deal_name in sorted(set(previous.index).union(current.index)):
        previous_row = previous.loc[deal_name] if deal_name in previous.index else None
        current_row = current.loc[deal_name] if deal_name in current.index else None

        if current_row is None:
            rows.append(_removed_row(deal_name, previous_month, current_month, previous_row))
            continue
        if previous_row is None:
            rows.append(_new_row(deal_name, previous_month, current_month, current_row))
            continue

        metric_changes = _metric_changes(previous_row, current_row, tolerance)
        status_changed = str(previous_row.get("tab", "")) != str(current_row.get("tab", ""))
        if not metric_changes and not status_changed:
            continue

        change_type = "Exited" if str(previous_row.get("tab", "")) != "Exited" and str(current_row.get("tab", "")) == "Exited" else "Changed"
        rows.append(_changed_row(deal_name, previous_month, current_month, previous_row, current_row, change_type, metric_changes))

    if not rows:
        return _empty_diff()
    return pd.DataFrame(rows)


def write_snapshot_outputs(
    snapshot: pd.DataFrame,
    history_path: Path,
    diff_output_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    existing = _read_history(history_path)
    history = upsert_snapshot_history(existing, snapshot)
    diff = build_monthly_diff(history)

    history_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(history_path, engine="openpyxl") as writer:
        history.to_excel(writer, index=False, sheet_name=SNAPSHOT_SHEET)
        snapshot.to_excel(writer, index=False, sheet_name=LATEST_SNAPSHOT_SHEET)
        diff.to_excel(writer, index=False, sheet_name=LATEST_DIFF_SHEET)

    diff_output_path.parent.mkdir(parents=True, exist_ok=True)
    current, previous = _latest_pair(history)
    with pd.ExcelWriter(diff_output_path, engine="openpyxl") as writer:
        diff.to_excel(writer, index=False, sheet_name=LATEST_DIFF_SHEET)
        current.to_excel(writer, index=False, sheet_name=CURRENT_SNAPSHOT_SHEET)
        previous.to_excel(writer, index=False, sheet_name=PREVIOUS_SNAPSHOT_SHEET)

    return history, diff


def _read_history(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    try:
        return pd.read_excel(path, sheet_name=SNAPSHOT_SHEET).fillna("")
    except ValueError:
        return pd.DataFrame(columns=SNAPSHOT_COLUMNS)


def _latest_pair(history: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if history.empty:
        return history.copy(), history.copy()
    months = sorted(str(m) for m in history["snapshot_month"].dropna().unique())
    current = history[history["snapshot_month"].astype(str) == months[-1]].copy()
    previous = history[history["snapshot_month"].astype(str) == months[-2]].copy() if len(months) > 1 else pd.DataFrame(columns=history.columns)
    return current, previous


def _empty_diff() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "previous_month",
        "current_month",
        "change_type",
        "deal_name",
        "previous_tab",
        "current_tab",
        "previous_status",
        "current_status",
        "previous_section",
        "current_section",
        "changed_metrics",
        *[f"previous_{col}" for col in METRIC_COLUMNS],
        *[f"current_{col}" for col in METRIC_COLUMNS],
        *[f"delta_{col}" for col in METRIC_COLUMNS],
    ])


def _metric_changes(previous_row: pd.Series, current_row: pd.Series, tolerance: float) -> list[str]:
    changes = []
    for col in METRIC_COLUMNS:
        previous_val = pd.to_numeric(previous_row.get(col), errors="coerce")
        current_val = pd.to_numeric(current_row.get(col), errors="coerce")
        if pd.isna(previous_val) and pd.isna(current_val):
            continue
        previous_num = 0.0 if pd.isna(previous_val) else float(previous_val)
        current_num = 0.0 if pd.isna(current_val) else float(current_val)
        if abs(current_num - previous_num) > tolerance:
            changes.append(col)
    return changes


def _base_row(deal_name: str, previous_month: str, current_month: str, previous_row, current_row) -> dict:
    row = {
        "previous_month": previous_month,
        "current_month": current_month,
        "deal_name": deal_name,
        "previous_tab": _get(previous_row, "tab"),
        "current_tab": _get(current_row, "tab"),
        "previous_status": _get(previous_row, "status"),
        "current_status": _get(current_row, "status"),
        "previous_section": _get(previous_row, "section"),
        "current_section": _get(current_row, "section"),
    }
    for col in METRIC_COLUMNS:
        previous_val = _numeric(_get(previous_row, col))
        current_val = _numeric(_get(current_row, col))
        row[f"previous_{col}"] = previous_val
        row[f"current_{col}"] = current_val
        row[f"delta_{col}"] = None if previous_val is None or current_val is None else current_val - previous_val
    return row


def _changed_row(deal_name: str, previous_month: str, current_month: str, previous_row, current_row, change_type: str, metric_changes: list[str]) -> dict:
    row = _base_row(deal_name, previous_month, current_month, previous_row, current_row)
    row["change_type"] = change_type
    row["changed_metrics"] = ", ".join(metric_changes)
    return row


def _new_row(deal_name: str, previous_month: str, current_month: str, current_row) -> dict:
    row = _base_row(deal_name, previous_month, current_month, None, current_row)
    row["change_type"] = "New"
    row["changed_metrics"] = "new deal"
    return row


def _removed_row(deal_name: str, previous_month: str, current_month: str, previous_row) -> dict:
    row = _base_row(deal_name, previous_month, current_month, previous_row, None)
    row["change_type"] = "Removed"
    row["changed_metrics"] = "not present in current snapshot"
    return row


def _get(row, col: str):
    if row is None:
        return None
    return row.get(col)


def _numeric(value):
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return float(parsed)