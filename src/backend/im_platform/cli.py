from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .adapters.document_intake import build_intake_workbook
from .adapters.entity_reconciliation import build_reconciliation_worksheet
from .adapters.tracker_adapter import load_tracker_cashflows, load_tracker_valuations
from .pipeline import run_pipeline
from .validation import (
    issues_to_dataframe,
    validate_non_usd_fx_fields,
    validate_primary_key,
    validate_required_columns,
)


def _run_pipeline_command(args: argparse.Namespace) -> None:
    output_file = run_pipeline(input_root=args.input_root, output_root=args.output_root)
    print(f"Pipeline completed. Output: {output_file}")


def _extract_tracker_command(args: argparse.Namespace) -> None:
    cashflow = load_tracker_cashflows(args.tracker_file)
    valuation = load_tracker_valuations(args.tracker_file)

    issues = []
    issues.extend(validate_required_columns("cashflow", cashflow))
    issues.extend(validate_primary_key("cashflow", cashflow))
    issues.extend(validate_non_usd_fx_fields("cashflow", cashflow, "currency"))
    issues.extend(validate_required_columns("valuation", valuation))
    issues.extend(validate_primary_key("valuation", valuation))
    issues.extend(validate_non_usd_fx_fields("valuation", valuation, "valuation_currency"))

    output_path = args.output_file or Path("data/outputs/Tracker_Extract_Preview.xlsx")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        cashflow.to_excel(writer, index=False, sheet_name="Cashflow_Extract")
        valuation.to_excel(writer, index=False, sheet_name="Valuation_Extract")
        issues_to_dataframe(issues).to_excel(writer, index=False, sheet_name="Data_Quality_Exceptions")

    print(f"Extracted {len(cashflow)} cashflow rows, {len(valuation)} valuation rows, {len(issues)} data quality issues.")
    print(f"Preview written to: {output_path}")


def _build_intake_command(args: argparse.Namespace) -> None:
    output_path = args.output_file or Path("data/outputs/Investment_Register_Intake.xlsx")
    result = build_intake_workbook(args.investments_root, output_path)
    print(f"Intake workbook written to: {result}")


def _reconcile_entities_command(args: argparse.Namespace) -> None:
    output_path = args.output_file or Path("data/outputs/Entity_Reconciliation.xlsx")
    result = build_reconciliation_worksheet(args.tracker_file, args.investments_root, output_path)
    print(f"Reconciliation worksheet written to: {result}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run IM Platform v1 ingestion/report pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the pipeline against clean canonical input files.")
    run_parser.add_argument("--input-root", type=Path, default=None, help="Root folder containing input files")
    run_parser.add_argument("--output-root", type=Path, default=None, help="Output folder for generated workbook")
    run_parser.set_defaults(func=_run_pipeline_command)

    extract_parser = subparsers.add_parser(
        "extract-tracker",
        help="Extract cashflow/valuation records from the monthly tracker workbook (CF + NAV tabs only).",
    )
    extract_parser.add_argument("--tracker-file", type=Path, required=True, help="Path to the monthly Portfolio Summary workbook")
    extract_parser.add_argument("--output-file", type=Path, default=None, help="Where to write the extract preview workbook")
    extract_parser.set_defaults(func=_extract_tracker_command)

    intake_parser = subparsers.add_parser(
        "build-intake",
        help="Scan investment document folders and build a draft structural register + raw text extract for human review.",
    )
    intake_parser.add_argument("--investments-root", type=Path, required=True, help="Root folder containing per-company investment document folders")
    intake_parser.add_argument("--output-file", type=Path, default=None, help="Where to write the intake workbook")
    intake_parser.set_defaults(func=_build_intake_command)

    reconcile_parser = subparsers.add_parser(
        "reconcile-entities",
        help="Suggest matches between tracker investment names and structural register company folders (human confirms).",
    )
    reconcile_parser.add_argument("--tracker-file", type=Path, required=True, help="Path to the monthly Portfolio Summary workbook")
    reconcile_parser.add_argument("--investments-root", type=Path, required=True, help="Root folder containing per-company investment document folders")
    reconcile_parser.add_argument("--output-file", type=Path, default=None, help="Where to write the reconciliation workbook")
    reconcile_parser.set_defaults(func=_reconcile_entities_command)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
