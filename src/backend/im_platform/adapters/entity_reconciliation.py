"""Reconciliation helper linking free-text investment names from the monthly
tracker (CF/NAV tabs) to the structural register's company folders.

This does NOT auto-merge records. It only proposes a best-guess match (via
plain string similarity) for a human to confirm or override -- entity
identity is exactly the kind of fact that must not be silently assumed.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

import pandas as pd

from .document_intake import (
    discover_company_folders,
    discover_fund_folders,
    discover_fund_subvehicles,
)
from .tracker_adapter import load_tracker_cashflows, load_tracker_valuations

# Trailing administrative tags (not part of the legal entity's identity) that
# can suppress an otherwise-correct string match, e.g. "Cerebras Systems Inc
# (2)" vs "Cerebras", or "Esyasoft Holding (Debt)" vs "Esyasoft Holding".
_TRAILING_TAG_RE = re.compile(r"\s*\((?:\d+|debt|aiv|gp)\)\s*$", re.IGNORECASE)


def _strip_trailing_tag(name: str) -> str:
    return _TRAILING_TAG_RE.sub("", name).strip()


def _best_match(name: str, candidates: list[str]) -> tuple[str, float]:
    matches = difflib.get_close_matches(name, candidates, n=1, cutoff=0.0)
    if not matches:
        return "", 0.0
    best = matches[0]
    score = difflib.SequenceMatcher(None, name.lower(), best.lower()).ratio()
    return best, round(score, 3)


def _best_match_with_tag_normalization(name: str, candidates: list[str]) -> tuple[str, float]:
    best, score = _best_match(name, candidates)
    stripped = _strip_trailing_tag(name)
    if stripped != name:
        stripped_best, stripped_score = _best_match(stripped, candidates)
        if stripped_score > score:
            return stripped_best, stripped_score
    return best, score


def _load_prior_confirmations(output_path: Path) -> dict[str, dict[str, str]]:
    """Preserve human confirmations/notes across re-runs of the adapter."""
    if not output_path.exists():
        return {}
    try:
        prior = pd.read_excel(output_path, sheet_name="Entity_Reconciliation")
    except (FileNotFoundError, ValueError):
        return {}
    prior = prior.fillna("")
    return {
        str(row["tracker_investment_id"]): {
            "confirmed_entity_id": str(row.get("confirmed_entity_id", "")),
            "notes": str(row.get("notes", "")),
        }
        for _, row in prior.iterrows()
    }


def build_reconciliation_worksheet(
    tracker_file: Path, investments_root: Path, output_path: Path
) -> Path:
    cashflow = load_tracker_cashflows(tracker_file)
    valuation = load_tracker_valuations(tracker_file)

    prior_confirmations = _load_prior_confirmations(output_path)

    company_names = [p.name for p in discover_company_folders(investments_root)]
    fund_folders = discover_fund_folders(investments_root)

    candidate_rows = [(name, "entity", "") for name in company_names]
    for fund_folder in fund_folders:
        candidate_rows.append((fund_folder.name, "fund_vehicle", ""))
        for subvehicle_name in discover_fund_subvehicles(fund_folder):
            candidate_rows.append((subvehicle_name, "fund_subvehicle", fund_folder.name))

    candidate_names = [name for name, _, _ in candidate_rows]
    candidate_info_by_name = {name: (kind, parent) for name, kind, parent in candidate_rows}

    cf_counts = cashflow.groupby("investment_id").size().rename("cashflow_rows")
    val_counts = valuation.groupby("investment_id").size().rename("valuation_rows")
    tracker_names = sorted(set(cf_counts.index) | set(val_counts.index))

    rows = []
    for name in tracker_names:
        suggested, score = _best_match_with_tag_normalization(name, candidate_names)
        match_type, parent_fund = candidate_info_by_name.get(suggested, ("", ""))
        prior = prior_confirmations.get(name, {})
        default_notes = "" if score >= 0.6 else "LOW CONFIDENCE - verify manually"
        rows.append(
            {
                "tracker_investment_id": name,
                # this is the answer that matters - everything after it is just
                # supporting evidence for why the algorithm suggested what it did
                "confirmed_entity_id": prior.get("confirmed_entity_id", ""),
                "notes": prior.get("notes") or default_notes,
                "cashflow_rows": int(cf_counts.get(name, 0)),
                "valuation_rows": int(val_counts.get(name, 0)),
                "suggested_match (algorithm guess - may be wrong)": suggested,
                "suggested_match_type": match_type,
                "parent_fund_folder": parent_fund,
                "match_confidence": score,
            }
        )

    reconciliation_df = pd.DataFrame(rows).sort_values("match_confidence").reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        reconciliation_df.to_excel(writer, index=False, sheet_name="Entity_Reconciliation")

    return output_path


def load_confirmed_mapping(reconciliation_file: Path) -> dict[str, str]:
    """Load tracker_investment_id -> confirmed_entity_id, human-confirmed rows only."""
    df = pd.read_excel(reconciliation_file, sheet_name="Entity_Reconciliation").fillna("")
    return {
        str(row["tracker_investment_id"]): str(row["confirmed_entity_id"])
        for _, row in df.iterrows()
        if str(row["confirmed_entity_id"]).strip()
    }


def apply_confirmed_mapping(
    df: pd.DataFrame, mapping: dict[str, str], id_col: str = "investment_id"
) -> pd.DataFrame:
    """Add a resolved_entity_id column using confirmed reconciliation mappings.

    The original id_col is left untouched (raw tracker name, for traceability).
    Rows with no confirmed mapping get an empty resolved_entity_id and are
    flagged via entity_resolved=False rather than silently dropped or guessed.
    """
    out = df.copy()
    out["resolved_entity_id"] = out[id_col].map(mapping).fillna("")
    out["entity_resolved"] = out["resolved_entity_id"] != ""
    return out


# Marker written into Entity_Reconciliation notes when a name has no document
# folder but should still get a minimal register row from tracker data alone
# (e.g. fully exited investments with no supporting documents on file).
TRACKER_ONLY_MARKER = "TRACK IT"


def find_tracker_only_names(reconciliation_file: Path) -> list[str]:
    df = pd.read_excel(reconciliation_file, sheet_name="Entity_Reconciliation").fillna("")
    return [
        str(row["tracker_investment_id"])
        for _, row in df.iterrows()
        if not str(row["confirmed_entity_id"]).strip() and TRACKER_ONLY_MARKER in str(row["notes"])
    ]


def build_tracker_only_register_rows(tracker_file: Path, names: list[str]) -> pd.DataFrame:
    """Build minimal draft register rows purely from tracker cashflow/NAV data,
    for investments with no document folder on file. Every derived field is
    clearly sourced so a human can spot-check rather than trust it blindly."""
    from .document_intake import REGISTER_DRAFT_COLUMNS

    cashflow = load_tracker_cashflows(tracker_file)
    valuation = load_tracker_valuations(tracker_file)

    rows = []
    for name in names:
        cf = cashflow[cashflow["investment_id"] == name].copy()
        val = valuation[valuation["investment_id"] == name].copy()

        cf["flow_date"] = pd.to_datetime(cf["flow_date"], errors="coerce")
        invested = -cf.loc[cf["amount"] < 0, "amount"].sum()
        close_date = cf["flow_date"].min() if not cf.empty else pd.NaT
        lifecycle_date = cf["flow_date"].max() if not cf.empty else pd.NaT
        currency = cf["currency"].mode().iat[0] if not cf.empty else "USD"
        is_fund_sheet = cf["cashflow_id"].astype(str).str.startswith("TRK-CF-FD").any()

        row = {col: "" for col in REGISTER_DRAFT_COLUMNS}
        row.update(
            {
                "entity_id": name,
                "instrument_type": "FundInterest" if is_fund_sheet else "Equity",
                "initial_commitment_amount": round(float(invested), 2),
                "investment_currency": currency,
                "close_date": close_date.strftime("%Y-%m-%d") if pd.notna(close_date) else "",
                "lifecycle_state": "Exited",
                "lifecycle_state_date": lifecycle_date.strftime("%Y-%m-%d") if pd.notna(lifecycle_date) else "",
                "source_document": (
                    "TRACKER ONLY - no source document on file; figures derived from monthly "
                    f"tracker cashflow/NAV data ({len(cf)} cashflow rows, {len(val)} valuation rows)"
                ),
            }
        )
        rows.append(row)

    return pd.DataFrame(rows, columns=REGISTER_DRAFT_COLUMNS)
