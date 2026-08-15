"""Reconciliation helper linking free-text investment names from the monthly
tracker (CF/NAV tabs) to the structural register's company folders.

This does NOT auto-merge records. It only proposes a best-guess match (via
plain string similarity) for a human to confirm or override -- entity
identity is exactly the kind of fact that must not be silently assumed.
"""

from __future__ import annotations

import difflib
from pathlib import Path

import pandas as pd

from .document_intake import discover_company_folders, discover_fund_folders
from .tracker_adapter import load_tracker_cashflows, load_tracker_valuations


def _best_match(name: str, candidates: list[str]) -> tuple[str, float]:
    matches = difflib.get_close_matches(name, candidates, n=1, cutoff=0.0)
    if not matches:
        return "", 0.0
    best = matches[0]
    score = difflib.SequenceMatcher(None, name.lower(), best.lower()).ratio()
    return best, round(score, 3)


def build_reconciliation_worksheet(
    tracker_file: Path, investments_root: Path, output_path: Path
) -> Path:
    cashflow = load_tracker_cashflows(tracker_file)
    valuation = load_tracker_valuations(tracker_file)

    company_names = [p.name for p in discover_company_folders(investments_root)]
    fund_names = [p.name for p in discover_fund_folders(investments_root)]
    candidate_labels = [(name, "entity") for name in company_names] + [
        (name, "fund_vehicle") for name in fund_names
    ]
    candidate_names = [name for name, _ in candidate_labels]
    candidate_type_by_name = dict(candidate_labels)

    cf_counts = cashflow.groupby("investment_id").size().rename("cashflow_rows")
    val_counts = valuation.groupby("investment_id").size().rename("valuation_rows")
    tracker_names = sorted(set(cf_counts.index) | set(val_counts.index))

    rows = []
    for name in tracker_names:
        suggested, score = _best_match(name, candidate_names)
        rows.append(
            {
                "tracker_investment_id": name,
                "cashflow_rows": int(cf_counts.get(name, 0)),
                "valuation_rows": int(val_counts.get(name, 0)),
                "suggested_match": suggested,
                "suggested_match_type": candidate_type_by_name.get(suggested, ""),
                "match_confidence": score,
                "confirmed_entity_id": "",
                "notes": "" if score >= 0.6 else "LOW CONFIDENCE - verify manually",
            }
        )

    reconciliation_df = pd.DataFrame(rows).sort_values("match_confidence").reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        reconciliation_df.to_excel(writer, index=False, sheet_name="Entity_Reconciliation")

    return output_path
