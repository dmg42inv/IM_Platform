from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass
class ValidationIssue:
    dataset_name: str
    record_key: str
    issue_type: str
    issue_description: str
    severity: str = "High"


REQUIRED_COLUMNS = {
    "investment_register": {
        "investment_id",
        "entity_id",
        "fund_vehicle_id",
        "instrument_type",
        "initial_commitment_amount",
        "investment_currency",
        "close_date",
        "lifecycle_state",
        "lifecycle_state_date",
    },
    "cashflow": {
        "cashflow_id",
        "investment_id",
        "flow_date",
        "flow_type",
        "amount",
        "currency",
        "fx_to_usd",
        "fx_rate_date",
        "fx_rate_source",
        "approval_status",
    },
    "valuation": {
        "valuation_id",
        "investment_id",
        "valuation_date",
        "fair_value_local",
        "valuation_currency",
        "fx_to_usd",
        "fx_rate_date",
        "fx_rate_source",
        "valuation_status",
    },
    "monitoring": {
        "monitoring_id",
        "investment_id",
        "as_of_date",
        "watchlist_flag",
        "covenant_status",
        "milestone_status",
    },
    "decisions": {
        "decision_id",
        "investment_id",
        "decision_date",
        "decision_body",
        "decision_outcome",
        "rationale_summary",
    },
}


PRIMARY_KEYS = {
    "investment_register": "investment_id",
    "cashflow": "cashflow_id",
    "valuation": "valuation_id",
    "monitoring": "monitoring_id",
    "decisions": "decision_id",
}


def validate_required_columns(dataset_name: str, df: pd.DataFrame) -> list[ValidationIssue]:
    required = REQUIRED_COLUMNS.get(dataset_name, set())
    missing = sorted(required - set(df.columns))
    issues: list[ValidationIssue] = []
    for col in missing:
        issues.append(
            ValidationIssue(
                dataset_name=dataset_name,
                record_key="*",
                issue_type="MissingColumn",
                issue_description=f"Required column missing: {col}",
            )
        )
    return issues


def validate_primary_key(dataset_name: str, df: pd.DataFrame) -> list[ValidationIssue]:
    key = PRIMARY_KEYS.get(dataset_name)
    if not key or key not in df.columns:
        return []

    issues: list[ValidationIssue] = []
    if df[key].isna().any():
        issues.append(
            ValidationIssue(
                dataset_name=dataset_name,
                record_key="*",
                issue_type="NullPrimaryKey",
                issue_description=f"Primary key column {key} has null values",
            )
        )

    dupes = df[df[key].duplicated(keep=False)]
    for val in dupes[key].astype(str).unique().tolist()[:200]:
        issues.append(
            ValidationIssue(
                dataset_name=dataset_name,
                record_key=val,
                issue_type="DuplicatePrimaryKey",
                issue_description=f"Duplicate value found in primary key {key}",
            )
        )

    return issues


def validate_non_usd_fx_fields(dataset_name: str, df: pd.DataFrame, currency_col: str) -> list[ValidationIssue]:
    if currency_col not in df.columns:
        return []
    if "fx_to_usd" not in df.columns or "fx_rate_date" not in df.columns:
        return []

    issues: list[ValidationIssue] = []
    non_usd = df[df[currency_col].astype(str).str.upper() != "USD"]
    missing_fx = non_usd[non_usd["fx_to_usd"].isna() | non_usd["fx_rate_date"].isna()]
    key = PRIMARY_KEYS.get(dataset_name)

    for _, row in missing_fx.head(500).iterrows():
        issues.append(
            ValidationIssue(
                dataset_name=dataset_name,
                record_key=str(row.get(key, "*")),
                issue_type="MissingFX",
                issue_description="Non-USD record missing fx_to_usd or fx_rate_date",
            )
        )
    return issues


def issues_to_dataframe(issues: Iterable[ValidationIssue]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "dataset_name": x.dataset_name,
                "record_key": x.record_key,
                "issue_type": x.issue_type,
                "issue_description": x.issue_description,
                "severity": x.severity,
                "owner": "TBD",
                "remediation_due_date": "TBD",
                "status": "Open",
            }
            for x in issues
        ]
    )
