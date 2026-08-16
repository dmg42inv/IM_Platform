from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .adapters.document_intake import (
    append_draft_rows,
    build_intake_workbook,
    refresh_needs_source_documents,
)
from .adapters.entity_reconciliation import (
    apply_confirmed_mapping,
    build_reconciliation_worksheet,
    build_tracker_only_register_rows,
    find_tracker_only_names,
    load_confirmed_mapping,
)
from .adapters.register_views import build_rollup_view, build_subvehicle_parent_map
from .adapters.output_pack import (
    build_governance_and_control_placeholder,
    build_monitoring_summary_placeholder,
    build_summary_note,
)
from .adapters.html_dashboard import build_dashboard_html
from .adapters.live_exited_sections import (
    build_deal_entity_map,
    build_quarterly_cashflows,
    compute_section_irr,
    enrich_with_irr,
    extract_live_exited_sections,
)
from .adapters.tracker_style_dashboard import build_tracker_style_dashboard_html
from .adapters.tracker_supplementary_tabs import (
    build_historical_nav_series,
    discover_monthly_tracker_files,
    extract_change_log,
    extract_ownership_domicile,
)
from .adapters.scan_for_updates import scan_for_new_investments, write_scan_report
from .adapters.tracker_adapter import load_tracker_cashflows, load_tracker_valuations
from .calculations import build_pipeline_and_lifecycle, build_portfolio_snapshot, build_returns_summary
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


def _apply_reconciliation_command(args: argparse.Namespace) -> None:
    mapping = load_confirmed_mapping(args.reconciliation_file)
    cashflow = apply_confirmed_mapping(load_tracker_cashflows(args.tracker_file), mapping)
    valuation = apply_confirmed_mapping(load_tracker_valuations(args.tracker_file), mapping)

    unresolved = []
    for label, df in (("cashflow", cashflow), ("valuation", valuation)):
        unresolved_names = df.loc[~df["entity_resolved"], "investment_id"].unique()
        for name in unresolved_names:
            unresolved.append({"source": label, "tracker_investment_id": name})

    output_path = args.output_file or Path("data/outputs/Tracker_Extract_Reconciled.xlsx")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        cashflow.to_excel(writer, index=False, sheet_name="Cashflow_Extract")
        valuation.to_excel(writer, index=False, sheet_name="Valuation_Extract")
        pd.DataFrame(unresolved).to_excel(writer, index=False, sheet_name="Unresolved_Entities")

    resolved_cf = int(cashflow["entity_resolved"].sum())
    resolved_val = int(valuation["entity_resolved"].sum())
    print(
        f"Cashflow: {resolved_cf}/{len(cashflow)} rows resolved. "
        f"Valuation: {resolved_val}/{len(valuation)} rows resolved. "
        f"{len(unresolved)} distinct unresolved names."
    )
    print(f"Reconciled extract written to: {output_path}")


def _seed_tracker_only_command(args: argparse.Namespace) -> None:
    names = find_tracker_only_names(args.reconciliation_file)
    if not names:
        print("No tracker-only names found (nothing marked 'TRACK IT' with a blank confirmed_entity_id).")
        return

    new_rows = build_tracker_only_register_rows(args.tracker_file, names)
    intake_path = args.intake_file or Path("data/outputs/Investment_Register_Intake.xlsx")
    append_draft_rows(intake_path, new_rows)

    print(f"Seeded {len(new_rows)} tracker-only draft rows: {', '.join(names)}")
    print(f"Updated: {intake_path}")


def _list_source_gaps_command(args: argparse.Namespace) -> None:
    intake_path = args.intake_file or Path("data/outputs/Investment_Register_Intake.xlsx")
    refresh_needs_source_documents(intake_path)
    gaps = pd.read_excel(intake_path, sheet_name="Needs_Source_Documents")
    print(f"{len(gaps)} rows still need an original source document. See 'Needs_Source_Documents' tab in {intake_path}")


def _load_real_pipeline_inputs(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list]:
    """Shared load/reconcile/rollup logic for both `build-real-output` and
    `generate-output-pack`: register view + cashflow/valuation joined onto it,
    with fund sub-vehicle remapping applied, plus the resulting data-quality
    issues list."""
    intake_path = args.intake_file or Path("data/outputs/Investment_Register_Intake.xlsx")
    tracker_path = args.tracker_extract_file or Path("data/outputs/Tracker_Extract_Reconciled.xlsx")
    reconciliation_path = args.reconciliation_file or Path("data/outputs/Entity_Reconciliation.xlsx")

    draft = pd.read_excel(intake_path, sheet_name="Investment_Register_Draft").fillna("")
    investments = build_rollup_view(draft, group_by=args.group_by)

    cashflow = pd.read_excel(tracker_path, sheet_name="Cashflow_Extract").fillna("")
    valuation = pd.read_excel(tracker_path, sheet_name="Valuation_Extract").fillna("")
    cashflow = cashflow[cashflow["entity_resolved"] == True].copy()  # noqa: E712
    valuation = valuation[valuation["entity_resolved"] == True].copy()  # noqa: E712

    # Fund sub-vehicles (e.g. "MGX I LP") are tracked at their own granularity in the
    # tracker, but the register view here is rolled up to entity_id (e.g. "4. MGX") -
    # remap so the join key lines up, instead of silently producing $0 cost basis.
    subvehicle_parent_map = build_subvehicle_parent_map(reconciliation_path)
    cashflow["investment_id"] = cashflow["resolved_entity_id"].map(subvehicle_parent_map).fillna(cashflow["resolved_entity_id"])

    # Valuations are point-in-time NAV/carrying values, not additive cashflows: each
    # sub-vehicle (e.g. "MGX I LP" and "MGX Strategic Co-Invest") carries its own
    # distinct carrying value. Take the latest value per sub-vehicle first, THEN sum
    # across sub-vehicles that roll up to the same parent entity - otherwise a naive
    # remap-then-take-latest would silently discard all but one sub-vehicle's value.
    valuation["investment_id"] = valuation["resolved_entity_id"]
    valuation["valuation_date"] = pd.to_datetime(valuation["valuation_date"], errors="coerce")
    latest_per_subvehicle = (
        valuation.sort_values("valuation_date").groupby("investment_id", as_index=False).tail(1)
    ).copy()
    latest_per_subvehicle["investment_id"] = (
        latest_per_subvehicle["investment_id"].map(subvehicle_parent_map).fillna(latest_per_subvehicle["investment_id"])
    )
    valuation = (
        latest_per_subvehicle.groupby("investment_id", as_index=False)
        .agg(
            fair_value_local=("fair_value_local", "sum"),
            valuation_date=("valuation_date", "max"),
            valuation_currency=("valuation_currency", "first"),
            fx_to_usd=("fx_to_usd", "first"),
            fx_rate_date=("fx_rate_date", "max"),
            fx_rate_source=("fx_rate_source", "first"),
            valuation_status=("valuation_status", "first"),
        )
    )
    valuation["valuation_date"] = valuation["valuation_date"].dt.strftime("%Y-%m-%d")
    valuation["valuation_id"] = "AGG-VAL-" + valuation["investment_id"].astype(str)

    monitoring = pd.DataFrame(columns=["investment_id", "as_of_date", "watchlist_flag"])

    issues = []
    issues.extend(validate_required_columns("investment_register", investments))
    issues.extend(validate_primary_key("investment_register", investments))
    issues.extend(validate_required_columns("cashflow", cashflow))
    issues.extend(validate_non_usd_fx_fields("cashflow", cashflow, "currency"))
    issues.extend(validate_required_columns("valuation", valuation))
    issues.extend(validate_non_usd_fx_fields("valuation", valuation, "valuation_currency"))

    return investments, cashflow, valuation, monitoring, issues


def _build_real_output_command(args: argparse.Namespace) -> None:
    output_path = args.output_file or Path("data/outputs/V1_Portfolio_Output_REAL.xlsx")
    investments, cashflow, valuation, monitoring, issues = _load_real_pipeline_inputs(args)

    snapshot = build_portfolio_snapshot(investments, valuation, monitoring, cashflow)
    returns = build_returns_summary(cashflow, valuation)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        snapshot.to_excel(writer, index=False, sheet_name="Portfolio_Snapshot")
        returns.to_excel(writer, index=False, sheet_name="Returns_Summary")
        issues_to_dataframe(issues).to_excel(writer, index=False, sheet_name="Data_Quality_Exceptions")
        investments.to_excel(writer, index=False, sheet_name="Register_View_Used")

    print(f"View: grouped by '{args.group_by}'. Snapshot rows: {len(snapshot)}. Returns rows: {len(returns)}. Issues: {len(issues)}.")
    print(f"Output written to: {output_path}")


def _generate_output_pack_command(args: argparse.Namespace) -> None:
    output_path = args.output_file or Path("data/outputs/V1_Output_Pack.xlsx")
    note_path = args.summary_note_file or output_path.with_name(output_path.stem + "_Summary_Note.md")

    investments, cashflow, valuation, monitoring, issues = _load_real_pipeline_inputs(args)

    snapshot = build_portfolio_snapshot(investments, valuation, monitoring, cashflow)
    returns = build_returns_summary(cashflow, valuation)
    pipeline_lifecycle = build_pipeline_and_lifecycle(investments)
    monitoring_summary = build_monitoring_summary_placeholder()
    governance = build_governance_and_control_placeholder()
    issues_df = issues_to_dataframe(issues)

    as_of_date = valuation["valuation_date"].max() if len(valuation) else None
    summary_note = build_summary_note(snapshot, returns, issues_df, as_of_date=as_of_date)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        snapshot.to_excel(writer, index=False, sheet_name="Portfolio_Snapshot")
        returns.to_excel(writer, index=False, sheet_name="Returns_Summary")
        pipeline_lifecycle.to_excel(writer, index=False, sheet_name="Pipeline_and_Lifecycle")
        monitoring_summary.to_excel(writer, index=False, sheet_name="Monitoring_Summary")
        governance.to_excel(writer, index=False, sheet_name="Governance_and_Control")
        issues_df.to_excel(writer, index=False, sheet_name="Data_Quality_Exceptions")
        investments.to_excel(writer, index=False, sheet_name="Register_View_Used")

    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(summary_note, encoding="utf-8")

    print(
        f"View: grouped by '{args.group_by}'. Snapshot rows: {len(snapshot)}. Returns rows: {len(returns)}. "
        f"Issues: {len(issues)}."
    )
    print(f"Output pack written to: {output_path}")
    print(f"Summary note written to: {note_path}")


def _generate_html_dashboard_command(args: argparse.Namespace) -> None:
    output_path = args.output_file or Path("data/outputs/Dashboard.html")

    investments, cashflow, valuation, monitoring, issues = _load_real_pipeline_inputs(args)

    snapshot = build_portfolio_snapshot(investments, valuation, monitoring, cashflow)
    returns = build_returns_summary(cashflow, valuation)
    pipeline_lifecycle = build_pipeline_and_lifecycle(investments)
    issues_df = issues_to_dataframe(issues)

    as_of_date = valuation["valuation_date"].max() if len(valuation) else None
    html = build_dashboard_html(snapshot, returns, pipeline_lifecycle, issues_df, as_of_date=as_of_date)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    print(f"View: grouped by '{args.group_by}'. Positions: {len(snapshot)}.")
    print(f"Dashboard written to: {output_path}")


def _build_triangulation_notes(deals: pd.DataFrame, deal_entity_map: dict[str, str], intake_path: Path) -> list[str]:
    """Flags where the register's own lifecycle_state disagrees with the
    tracker's own Live/Exited classification (the tracker wins - it's the
    authoritative, more current source), plus deals whose IRR is
    necessarily blended across more than one tracker line."""
    notes: list[str] = []

    draft = pd.read_excel(intake_path, sheet_name="Investment_Register_Draft").fillna("")
    lifecycle_by_entity = draft.groupby("entity_id")["lifecycle_state"].agg(lambda s: set(s)).to_dict()

    for _, row in deals.iterrows():
        entity = deal_entity_map.get(row["deal_name"])
        if not entity:
            continue
        register_states = lifecycle_by_entity.get(entity, set())
        tab = row["tab"]
        if tab == "Exited" and register_states and "Exited" not in register_states:
            notes.append(
                f"'{row['deal_name']}' is classified Exited/{row['status']} in the tracker's own report, "
                f"but the register's lifecycle_state for '{entity}' is {sorted(register_states)} - register needs updating."
            )
        if tab == "Live" and register_states and register_states == {"Exited"}:
            notes.append(
                f"'{row['deal_name']}' is classified Live in the tracker's own report, "
                f"but the register's lifecycle_state for '{entity}' is Exited - register needs updating."
            )

    blended = sorted({e for e, c in pd.Series(list(deal_entity_map.values())).value_counts().items() if c > 1})
    if blended:
        notes.append(
            "IRR is blended (pooled cash flows) across more than one tracker line for: " + ", ".join(blended) +
            " - the tracker itself splits these by investing-entity/tranche but the underlying cash flow is not separately tagged."
        )

    return notes


def _generate_tracker_dashboard_command(args: argparse.Namespace) -> None:
    output_path = args.output_file or Path("data/outputs/Tracker_Style_Dashboard.html")
    intake_path = args.intake_file or Path("data/outputs/Investment_Register_Intake.xlsx")
    tracker_extract_path = args.tracker_extract_file or Path("data/outputs/Tracker_Extract_Reconciled.xlsx")
    reconciliation_path = args.reconciliation_file or Path("data/outputs/Entity_Reconciliation.xlsx")
    scan_report_path = Path("data/outputs/Update_Scan_Report.json")

    deals = extract_live_exited_sections(args.tracker_file)
    deal_entity_map = build_deal_entity_map(reconciliation_path)

    cashflow = pd.read_excel(tracker_extract_path, sheet_name="Cashflow_Extract").fillna("")
    valuation = pd.read_excel(tracker_extract_path, sheet_name="Valuation_Extract").fillna("")
    cashflow = cashflow[cashflow["entity_resolved"] == True].copy()  # noqa: E712
    valuation = valuation[valuation["entity_resolved"] == True].copy()  # noqa: E712

    deals = enrich_with_irr(deals, cashflow, valuation, deal_entity_map)
    section_irr = compute_section_irr(deals, cashflow, valuation, deal_entity_map)
    quarterly = build_quarterly_cashflows(cashflow)
    triangulation_notes = _build_triangulation_notes(deals, deal_entity_map, intake_path)

    monthly_root = args.tracker_file.parent.parent
    monthly_files = discover_monthly_tracker_files(monthly_root)
    historical_nav = build_historical_nav_series(monthly_files)

    ownership = extract_ownership_domicile(args.tracker_file)
    change_log = extract_change_log(args.tracker_file)

    scan_report = None
    if scan_report_path.exists():
        scan_report = json.loads(scan_report_path.read_text(encoding="utf-8"))

    as_of_date = valuation["valuation_date"].max() if len(valuation) else None
    html = build_tracker_style_dashboard_html(
        deals, section_irr, quarterly, historical_nav, cashflow, ownership, change_log,
        pd.DataFrame(), triangulation_notes, scan_report=scan_report, as_of_date=as_of_date,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    print(f"Live deals: {len(deals[deals['tab'] == 'Live'])}. Exited deals: {len(deals[deals['tab'] == 'Exited'])}.")
    print(f"Triangulation notes: {len(triangulation_notes)}.")
    print(f"Historical NAV months: {len(historical_nav)}. Ownership rows: {len(ownership)}. Log rows: {len(change_log)}.")
    print(f"Dashboard written to: {output_path}")


def _scan_for_updates_command(args: argparse.Namespace) -> None:
    intake_path = args.intake_file or Path("data/outputs/Investment_Register_Intake.xlsx")
    output_path = args.output_file or Path("data/outputs/Update_Scan_Report.json")

    result = scan_for_new_investments(args.investments_root, intake_path)
    write_scan_report(result, output_path)

    print(f"New company folders: {result['new_company_folders'] or 'none'}")
    print(f"New fund folders: {result['new_fund_folders'] or 'none'}")
    print(f"Recently modified folders (last 30 days): {len(result['recently_modified_folders'])}")
    print(f"Scan report written to: {output_path}")


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

    apply_parser = subparsers.add_parser(
        "apply-reconciliation",
        help="Relabel tracker cashflow/valuation rows using confirmed entity reconciliation mappings.",
    )
    apply_parser.add_argument("--tracker-file", type=Path, required=True, help="Path to the monthly Portfolio Summary workbook")
    apply_parser.add_argument("--reconciliation-file", type=Path, required=True, help="Path to the confirmed Entity_Reconciliation workbook")
    apply_parser.add_argument("--output-file", type=Path, default=None, help="Where to write the reconciled extract workbook")
    apply_parser.set_defaults(func=_apply_reconciliation_command)

    seed_parser = subparsers.add_parser(
        "seed-tracker-only",
        help="Append minimal register rows (from tracker data only) for investments with no document folder.",
    )
    seed_parser.add_argument("--tracker-file", type=Path, required=True, help="Path to the monthly Portfolio Summary workbook")
    seed_parser.add_argument("--reconciliation-file", type=Path, required=True, help="Path to the confirmed Entity_Reconciliation workbook")
    seed_parser.add_argument("--intake-file", type=Path, default=None, help="Path to the Investment_Register_Intake workbook to append to")
    seed_parser.set_defaults(func=_seed_tracker_only_command)

    gaps_parser = subparsers.add_parser(
        "list-source-gaps",
        help="Rebuild the Needs_Source_Documents tab from the register's confirmed_by notes.",
    )
    gaps_parser.add_argument("--intake-file", type=Path, default=None, help="Path to the Investment_Register_Intake workbook")
    gaps_parser.set_defaults(func=_list_source_gaps_command)

    real_output_parser = subparsers.add_parser(
        "build-real-output",
        help="Run the calculation engine over the real cleaned register + reconciled tracker data.",
    )
    real_output_parser.add_argument("--intake-file", type=Path, default=None, help="Path to the Investment_Register_Intake workbook")
    real_output_parser.add_argument("--tracker-extract-file", type=Path, default=None, help="Path to the Tracker_Extract_Reconciled workbook")
    real_output_parser.add_argument("--reconciliation-file", type=Path, default=None, help="Path to the Entity_Reconciliation workbook")
    real_output_parser.add_argument("--output-file", type=Path, default=None, help="Where to write the portfolio output workbook")
    real_output_parser.add_argument("--group-by", choices=["entity_id", "fund_vehicle_id"], default="entity_id", help="Rollup level for the register view used in this run")
    real_output_parser.set_defaults(func=_build_real_output_command)

    output_pack_parser = subparsers.add_parser(
        "generate-output-pack",
        help="Generate the full V1 Output Pack (portfolio workbook with all spec tabs + Markdown summary note).",
    )
    output_pack_parser.add_argument("--intake-file", type=Path, default=None, help="Path to the Investment_Register_Intake workbook")
    output_pack_parser.add_argument("--tracker-extract-file", type=Path, default=None, help="Path to the Tracker_Extract_Reconciled workbook")
    output_pack_parser.add_argument("--reconciliation-file", type=Path, default=None, help="Path to the Entity_Reconciliation workbook")
    output_pack_parser.add_argument("--output-file", type=Path, default=None, help="Where to write the output pack workbook")
    output_pack_parser.add_argument("--summary-note-file", type=Path, default=None, help="Where to write the Markdown summary note")
    output_pack_parser.add_argument("--group-by", choices=["entity_id", "fund_vehicle_id"], default="entity_id", help="Rollup level for the register view used in this run")
    output_pack_parser.set_defaults(func=_generate_output_pack_command)

    dashboard_parser = subparsers.add_parser(
        "generate-html-dashboard",
        help="Generate a single self-contained HTML dashboard (charts + sortable tables) from the real pipeline data.",
    )
    dashboard_parser.add_argument("--intake-file", type=Path, default=None, help="Path to the Investment_Register_Intake workbook")
    dashboard_parser.add_argument("--tracker-extract-file", type=Path, default=None, help="Path to the Tracker_Extract_Reconciled workbook")
    dashboard_parser.add_argument("--reconciliation-file", type=Path, default=None, help="Path to the Entity_Reconciliation workbook")
    dashboard_parser.add_argument("--output-file", type=Path, default=None, help="Where to write the HTML dashboard")
    dashboard_parser.add_argument("--group-by", choices=["entity_id", "fund_vehicle_id"], default="entity_id", help="Rollup level for the register view used in this run")
    dashboard_parser.set_defaults(func=_generate_html_dashboard_command)

    tracker_dashboard_parser = subparsers.add_parser(
        "generate-tracker-dashboard",
        help="Generate an HTML dashboard structured like the tracker's own Live/Exited report tabs (sectioned by Investing Entity, with IRR and quarterly cash flows added).",
    )
    tracker_dashboard_parser.add_argument("--tracker-file", type=Path, required=True, help="Path to the monthly Portfolio Summary tracker workbook")
    tracker_dashboard_parser.add_argument("--intake-file", type=Path, default=None, help="Path to the Investment_Register_Intake workbook")
    tracker_dashboard_parser.add_argument("--tracker-extract-file", type=Path, default=None, help="Path to the Tracker_Extract_Reconciled workbook")
    tracker_dashboard_parser.add_argument("--reconciliation-file", type=Path, default=None, help="Path to the Entity_Reconciliation workbook")
    tracker_dashboard_parser.add_argument("--output-file", type=Path, default=None, help="Where to write the HTML dashboard")
    tracker_dashboard_parser.set_defaults(func=_generate_tracker_dashboard_command)

    scan_parser = subparsers.add_parser(
        "scan-for-updates",
        help="Compare the document folders against the register to find new/unrecognized investments and recently-modified folders.",
    )
    scan_parser.add_argument("--investments-root", type=Path, required=True, help="Investment documents root folder")
    scan_parser.add_argument("--intake-file", type=Path, default=None, help="Path to the Investment_Register_Intake workbook")
    scan_parser.add_argument("--output-file", type=Path, default=None, help="Where to write the scan report JSON")
    scan_parser.set_defaults(func=_scan_for_updates_command)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
