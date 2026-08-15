from __future__ import annotations

from pathlib import Path

import pandas as pd

from .calculations import build_portfolio_snapshot, build_returns_summary
from .config import DEFAULT_INPUT_ROOT, DEFAULT_OUTPUT_ROOT, OUTPUT_FILE_NAME
from .io import load_datasets
from .validation import (
    issues_to_dataframe,
    validate_non_usd_fx_fields,
    validate_primary_key,
    validate_required_columns,
)


def run_pipeline(input_root: Path | None = None, output_root: Path | None = None) -> Path:
    input_root = input_root or DEFAULT_INPUT_ROOT
    output_root = output_root or DEFAULT_OUTPUT_ROOT

    datasets = load_datasets(input_root)

    issues = []
    for name, df in datasets.items():
        issues.extend(validate_required_columns(name, df))
        issues.extend(validate_primary_key(name, df))

    issues.extend(validate_non_usd_fx_fields("cashflow", datasets["cashflow"], "currency"))
    issues.extend(
        validate_non_usd_fx_fields("valuation", datasets["valuation"], "valuation_currency")
    )

    portfolio_snapshot = build_portfolio_snapshot(
        datasets["investment_register"],
        datasets["valuation"],
        datasets["monitoring"],
        datasets["cashflow"],
    )
    returns_summary = build_returns_summary(datasets["cashflow"], datasets["valuation"])

    output_root.mkdir(parents=True, exist_ok=True)
    output_file = output_root / OUTPUT_FILE_NAME

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        portfolio_snapshot.to_excel(writer, index=False, sheet_name="Portfolio_Snapshot")
        returns_summary.to_excel(writer, index=False, sheet_name="Returns_Summary")

        dq_df = issues_to_dataframe(issues)
        dq_df.to_excel(writer, index=False, sheet_name="Data_Quality_Exceptions")

    return output_file
