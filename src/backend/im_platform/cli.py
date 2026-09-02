from __future__ import annotations

import argparse
import calendar
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
from .adapters.entity_glossary import build_glossary_table
from .adapters.register_citations import build_entity_citation_lookup
from .adapters.live_exited_sections import (
    build_deal_entity_map,
    build_quarterly_cashflows,
    compute_section_irr,
    compute_vintage_irr,
    enrich_with_irr,
    extract_live_exited_sections,
    recompute_deal_financials,
)
from .adapters.monthly_snapshot import build_monthly_snapshot, write_snapshot_outputs
from .adapters.tracker_style_dashboard import build_tracker_style_dashboard_html
from .adapters.tracker_supplementary_tabs import (
    build_historical_nav_series,
    build_per_company_nav_history,
    discover_monthly_tracker_files,
    extract_change_log,
    extract_nav_sheet,
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
    output_path = args.output_file or Path("data/source_of_truth/Investment_Register_Intake.xlsx")
    result = build_intake_workbook(args.investments_root, output_path)
    print(f"Intake workbook written to: {result}")


def _reconcile_entities_command(args: argparse.Namespace) -> None:
    output_path = args.output_file or Path("data/source_of_truth/Entity_Reconciliation.xlsx")
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
    intake_path = args.intake_file or Path("data/source_of_truth/Investment_Register_Intake.xlsx")
    append_draft_rows(intake_path, new_rows)

    print(f"Seeded {len(new_rows)} tracker-only draft rows: {', '.join(names)}")
    print(f"Updated: {intake_path}")


def _list_source_gaps_command(args: argparse.Namespace) -> None:
    intake_path = args.intake_file or Path("data/source_of_truth/Investment_Register_Intake.xlsx")
    refresh_needs_source_documents(intake_path)
    gaps = pd.read_excel(intake_path, sheet_name="Needs_Source_Documents")
    print(f"{len(gaps)} rows still need an original source document. See 'Needs_Source_Documents' tab in {intake_path}")


def _load_real_pipeline_inputs(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list]:
    """Shared load/reconcile/rollup logic for both `build-real-output` and
    `generate-output-pack`: register view + cashflow/valuation joined onto it,
    with fund sub-vehicle remapping applied, plus the resulting data-quality
    issues list."""
    intake_path = args.intake_file or Path("data/source_of_truth/Investment_Register_Intake.xlsx")
    tracker_path = args.tracker_extract_file or Path("data/outputs/Tracker_Extract_Reconciled.xlsx")
    reconciliation_path = args.reconciliation_file or Path("data/source_of_truth/Entity_Reconciliation.xlsx")

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


def _build_financials_triangulation_notes(deals: pd.DataFrame, tolerance_pct: float = 0.02) -> list[str]:
    """Flags deals where the recomputed (cashflow/NAV-sourced) financials
    differ materially from the tracker's own Live/Exited figures - a real
    discrepancy worth investigating, not necessarily a bug in either side."""
    notes: list[str] = []
    for _, d in deals.iterrows():
        for label, computed_col, tracker_col in [
            ("Invested", "invested", "tracker_invested"),
            ("Distributions", "distributions", "tracker_distributions"),
            ("Carrying Value", "carrying_value", "tracker_carrying_value"),
        ]:
            computed = d[computed_col] or 0.0
            tracker_val = d[tracker_col] or 0.0
            if tracker_val and abs(computed - tracker_val) / abs(tracker_val) > tolerance_pct:
                notes.append(
                    f"'{d['deal_name']}' {label}: computed from cash flows/NAV = {computed:,.2f}, "
                    f"tracker's own Live/Exited figure = {tracker_val:,.2f} - differs by more than "
                    f"{tolerance_pct:.0%}, worth investigating."
                )
    return notes


def _prepare_tracker_deals(tracker_file: Path, reconciliation_path: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    deals = extract_live_exited_sections(tracker_file)
    deal_entity_map = build_deal_entity_map(reconciliation_path)

    # MGX I Denali Holding LP has no line item in the tracker's own "1. Live"/
    # "2. Exited" report tabs at all (unlike MGX I LP / Strategic Co-Invest /
    # Group Holding 1 GP) - it only exists in our register + manual valuation
    # override. Inject a synthetic deal row so it isn't silently missing from
    # the dashboard's main Live Investments table; its own committed/invested/
    # carrying value are still recomputed from cashflow/valuation below, not
    # hardcoded here.
    if "MGX I Denali Holding LP" not in deals["deal_name"].values:
        deal_entity_map["MGX I Denali Holding LP"] = "MGX I Denali Holding LP"
        denali_row = pd.DataFrame([{
            "tab": "Live",
            "section": "GX Investments Ltd : MGX and Related Investments",
            "deal_name": "MGX I Denali Holding LP",
            "status": "Unrealized",
            "investing_entity": "G42 Holding",
            "investing_entity_raw": "G42 Holding",
            "vintage": "2024",
            "instrument": "LP",
            "committed": None, "invested": None, "remaining_commitment": None,
            "distributions": None, "carrying_value": None, "gain": None, "tvpi": None,
            "notes": "Not in the tracker's own Live/Exited tabs - added from register + manual NAV override.",
        }])
        deals = pd.concat([deals, denali_row], ignore_index=True)

    # User-specified display order within the MGX section (2026-08-18):
    # LP, Denali, Strategic Co-Invest, Group Holding GP - overriding whatever
    # order the tracker/injection happened to produce.
    _mgx_order = {
        "MGX I LP": 0,
        "MGX I Denali Holding LP": 1,
        "MGX 1 Strategic Co-invest": 2,
        "MGX Group Holding 1 Ltd (GP)": 3,
    }
    mgx_section = "GX Investments Ltd : MGX and Related Investments"
    deals = deals.reset_index(drop=True)
    deals["_pos"] = deals.index.astype(float)
    mask = deals["section"] == mgx_section
    if mask.any():
        anchor = deals.loc[mask, "_pos"].min()
        deals.loc[mask, "_pos"] = deals.loc[mask, "deal_name"].map(_mgx_order).fillna(99) + anchor - 0.5
    deals = deals.sort_values("_pos", kind="stable").drop(columns="_pos").reset_index(drop=True)
    return deals, deal_entity_map


def _load_reconciled_tracker_extract(tracker_file: Path, reconciliation_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    mapping = load_confirmed_mapping(reconciliation_path)
    cashflow = apply_confirmed_mapping(load_tracker_cashflows(tracker_file), mapping)
    valuation = apply_confirmed_mapping(load_tracker_valuations(tracker_file), mapping)
    return cashflow, valuation


def _filter_resolved_extract(cashflow: pd.DataFrame, valuation: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cashflow = cashflow[cashflow["entity_resolved"] == True].copy()  # noqa: E712
    valuation = valuation[valuation["entity_resolved"] == True].copy()  # noqa: E712
    return cashflow, valuation


def _correct_deals_for_snapshot(
    deals: pd.DataFrame,
    cashflow: pd.DataFrame,
    valuation: pd.DataFrame,
    deal_entity_map: dict[str, str],
    intake_path: Path,
) -> tuple[pd.DataFrame, dict[str, dict]]:
    draft = pd.read_excel(intake_path, sheet_name="Investment_Register_Draft").fillna("")
    citation_lookup = build_entity_citation_lookup(draft)

    deals = enrich_with_irr(deals, cashflow, valuation, deal_entity_map)
    deals = recompute_deal_financials(deals, cashflow, valuation, deal_entity_map, citation_lookup)
    return deals, citation_lookup


def _apply_db_positions(deals: pd.DataFrame, month_id: str, db_path: Path) -> pd.DataFrame:
    """Replace deal figures with the reconciled positions held in the database.

    The tracker workbook and the reconciled extract are separate inputs that drift apart: the
    extract's valuations stopped at 31 July, so a dashboard built from the August tracker still
    carried July prices for the listed names and reconciled to neither source. Taking the figures
    from monthly_positions makes this view agree with every other view by construction, because
    they read the same table.
    """
    import sqlite3

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "select deal_name, tab, committed, invested, remaining_commitment, distributions,"
            " carrying_value, gain, tvpi from monthly_positions where month_id=?",
            (month_id,)).fetchall()
    finally:
        con.close()
    if not rows:
        raise SystemExit(f"no positions in the database for {month_id}")

    by_deal = {r["deal_name"].strip(): dict(r) for r in rows}
    # The tracker reports MGX I LP and Denali on one line; the register keeps Denali separate, so
    # the combined row takes MGX I LP and Denali stands on its own row alongside it.
    aliases = {"MGX I LP + Denali": "MGX I LP"}
    numeric = ["committed", "invested", "remaining_commitment", "distributions",
               "carrying_value", "gain", "tvpi"]
    updated = deals.copy()
    matched, unmatched = 0, []
    for index, row in updated.iterrows():
        name = str(row["deal_name"]).strip()
        record = by_deal.get(aliases.get(name, name))
        if record is None:
            unmatched.append(name)
            continue
        for column in numeric:
            updated.at[index, column] = record[column]
        if name in aliases:
            updated.at[index, "deal_name"] = aliases[name]
        matched += 1

    missing_from_dashboard = sorted(set(by_deal) - {str(d).strip() for d in updated["deal_name"]})
    print(f"Positions from database {month_id}: {matched} deals updated.")
    if unmatched:
        # A deal the database does not hold for this month is not a position in this month.
        # Keeping the extract's figures would silently add value the register never had.
        print(f"  dropped, not held in {month_id}: {', '.join(unmatched)}")
        updated = updated[~updated["deal_name"].astype(str).str.strip().isin(unmatched)].reset_index(drop=True)
    if missing_from_dashboard:
        print(f"  in the database but not on the dashboard: {', '.join(missing_from_dashboard)}")
    return updated


def _generate_tracker_dashboard_command(args: argparse.Namespace) -> None:
    output_path = args.output_file or Path("data/outputs/Tracker_Style_Dashboard.html")
    intake_path = args.intake_file or Path("data/source_of_truth/Investment_Register_Intake.xlsx")
    tracker_extract_path = args.tracker_extract_file or Path("data/outputs/Tracker_Extract_Reconciled.xlsx")
    reconciliation_path = args.reconciliation_file or Path("data/source_of_truth/Entity_Reconciliation.xlsx")
    scan_report_path = Path("data/outputs/Update_Scan_Report.json")
    snapshot_history_path = Path("data/source_of_truth/Portfolio_Snapshot_History.xlsx")
    monthly_diff_path = Path("data/outputs/Portfolio_Monthly_Diff.xlsx")

    deals, deal_entity_map = _prepare_tracker_deals(args.tracker_file, reconciliation_path)

    glossary = build_glossary_table()

    cashflow = pd.read_excel(tracker_extract_path, sheet_name="Cashflow_Extract").fillna("")
    valuation = pd.read_excel(tracker_extract_path, sheet_name="Valuation_Extract").fillna("")
    cashflow, valuation = _filter_resolved_extract(cashflow, valuation)

    deals, citation_lookup = _correct_deals_for_snapshot(deals, cashflow, valuation, deal_entity_map, intake_path)
    if getattr(args, "deals_from_db", None):
        deals = _apply_db_positions(deals, args.deals_from_db,
                                    args.portfolio_db or Path("data/portfolio/portfolio.sqlite"))
    section_irr = compute_section_irr(deals, cashflow, valuation, deal_entity_map)
    vintage_irr = compute_vintage_irr(deals, cashflow, valuation, deal_entity_map)
    quarterly = build_quarterly_cashflows(cashflow)
    triangulation_notes = _build_triangulation_notes(deals, deal_entity_map, intake_path)
    triangulation_notes += _build_financials_triangulation_notes(deals)

    monthly_root = args.tracker_file.parent.parent
    monthly_files = discover_monthly_tracker_files(monthly_root)
    historical_nav = build_historical_nav_series(monthly_files)
    per_company_nav = build_per_company_nav_history(monthly_files)

    ownership = extract_ownership_domicile(args.tracker_file)
    change_log = extract_change_log(args.tracker_file)
    nav_sheet_df, nav_date = extract_nav_sheet(args.tracker_file)
    nav_info = nav_sheet_df.set_index("deal_name")[["investment_type", "comment"]].to_dict(orient="index")

    scan_report = None
    if scan_report_path.exists():
        scan_report = json.loads(scan_report_path.read_text(encoding="utf-8"))

    as_of_date = valuation["valuation_date"].max() if len(valuation) else None
    if getattr(args, "deals_from_db", None):
        # The label must name the month the figures are actually on.
        _y, _m = int(args.deals_from_db[:4]), int(args.deals_from_db[5:7])
        as_of_date = pd.Timestamp(_y, _m, calendar.monthrange(_y, _m)[1])
    snapshot = build_monthly_snapshot(deals, str(as_of_date) if as_of_date is not None else "")
    if getattr(args, "skip_snapshot", False):
        # Rendering a month must not mutate the history; only a deliberate run should append.
        snapshot_history, monthly_diff = pd.DataFrame(), pd.DataFrame()
    else:
        snapshot_history, monthly_diff = write_snapshot_outputs(snapshot, snapshot_history_path, monthly_diff_path)

    html = build_tracker_style_dashboard_html(
        deals, section_irr, vintage_irr, quarterly, historical_nav, cashflow, ownership, change_log,
        pd.DataFrame(), triangulation_notes, deal_entity_map, citation_lookup, glossary,
        nav_info=nav_info, nav_date=nav_date,
        scan_report=scan_report, as_of_date=as_of_date, monthly_diff=monthly_diff,
        snapshot_history=snapshot_history,
        per_company_nav=per_company_nav,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    print(f"Live deals: {len(deals[deals['tab'] == 'Live'])}. Exited deals: {len(deals[deals['tab'] == 'Exited'])}.")
    print(f"Triangulation notes: {len(triangulation_notes)}.")
    print(f"Historical NAV months: {len(historical_nav)}. Ownership rows: {len(ownership)}. Log rows: {len(change_log)}.")
    print(f"Snapshot history rows: {len(snapshot_history)}. Monthly diff rows: {len(monthly_diff)}.")
    print(f"Snapshot history written to: {snapshot_history_path}")
    print(f"Monthly diff written to: {monthly_diff_path}")
    print(f"Dashboard written to: {output_path}")


def _backfill_monthly_snapshot_command(args: argparse.Namespace) -> None:
    intake_path = args.intake_file or Path("data/source_of_truth/Investment_Register_Intake.xlsx")
    reconciliation_path = args.reconciliation_file or Path("data/source_of_truth/Entity_Reconciliation.xlsx")
    snapshot_history_path = args.snapshot_history_file or Path("data/source_of_truth/Portfolio_Snapshot_History.xlsx")
    monthly_diff_path = args.monthly_diff_file or Path("data/outputs/Portfolio_Monthly_Diff.xlsx")

    snapshot_history = pd.DataFrame()
    monthly_diff = pd.DataFrame()
    for tracker_file in args.tracker_file:
        deals, deal_entity_map = _prepare_tracker_deals(tracker_file, reconciliation_path)
        cashflow, valuation = _load_reconciled_tracker_extract(tracker_file, reconciliation_path)
        total_cf = len(cashflow)
        total_val = len(valuation)
        resolved_cf = int(cashflow["entity_resolved"].sum())
        resolved_val = int(valuation["entity_resolved"].sum())
        cashflow, valuation = _filter_resolved_extract(cashflow, valuation)

        deals, _citation_lookup = _correct_deals_for_snapshot(deals, cashflow, valuation, deal_entity_map, intake_path)
        as_of_date = valuation["valuation_date"].max() if len(valuation) else None
        snapshot = build_monthly_snapshot(deals, str(as_of_date) if as_of_date is not None else "")
        snapshot_history, monthly_diff = write_snapshot_outputs(snapshot, snapshot_history_path, monthly_diff_path)

        month = snapshot["snapshot_month"].iloc[0] if len(snapshot) else "unknown"
        print(
            f"Backfilled {month} from {tracker_file.name}: "
            f"{len(snapshot)} deals, cashflow {resolved_cf}/{total_cf} resolved, "
            f"valuation {resolved_val}/{total_val} resolved."
        )

    print(f"Snapshot history rows: {len(snapshot_history)}. Monthly diff rows: {len(monthly_diff)}.")
    print(f"Snapshot history written to: {snapshot_history_path}")
    print(f"Monthly diff written to: {monthly_diff_path}")


def _scan_for_updates_command(args: argparse.Namespace) -> None:
    intake_path = args.intake_file or Path("data/source_of_truth/Investment_Register_Intake.xlsx")
    output_path = args.output_file or Path("data/outputs/Update_Scan_Report.json")
    manifest_path = Path("data/source_of_truth/Document_Manifest.json")

    result = scan_for_new_investments(args.investments_root, intake_path, manifest_path=manifest_path)
    write_scan_report(result, output_path)

    print(f"New company folders: {result['new_company_folders'] or 'none'}")
    print(f"New fund folders: {result['new_fund_folders'] or 'none'}")
    print(f"Recently modified folders (last 30 days): {len(result['recently_modified_folders'])}")
    print(f"New files since last scan: {len(result['added_files'])}")
    print(f"Modified files since last scan: {len(result['modified_files'])}")
    print(f"Deleted files since last scan: {len(result['deleted_files'])}")
    print(f"Renamed/moved files since last scan: {len(result['renamed_files'])}")
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
    tracker_dashboard_parser.add_argument("--deals-from-db", type=str, default=None, help="Month id, e.g. 2026-08. Take deal figures from the reconciled positions in the database instead of the tracker extract")
    tracker_dashboard_parser.add_argument("--portfolio-db", type=Path, default=None, help="Portfolio database path")
    tracker_dashboard_parser.add_argument("--skip-snapshot", action="store_true", help="Do not append to the snapshot history; use when rendering a month for display")
    tracker_dashboard_parser.set_defaults(func=_generate_tracker_dashboard_command)

    snapshot_backfill_parser = subparsers.add_parser(
        "backfill-monthly-snapshot",
        help="Append or replace historical portfolio snapshots from one or more monthly tracker workbooks.",
    )
    snapshot_backfill_parser.add_argument(
        "--tracker-file",
        type=Path,
        action="append",
        required=True,
        help="Path to a monthly Portfolio Summary tracker workbook. Repeat for multiple months.",
    )
    snapshot_backfill_parser.add_argument("--intake-file", type=Path, default=None, help="Path to the Investment_Register_Intake workbook")
    snapshot_backfill_parser.add_argument("--reconciliation-file", type=Path, default=None, help="Path to the Entity_Reconciliation workbook")
    snapshot_backfill_parser.add_argument("--snapshot-history-file", type=Path, default=None, help="Where to write/read the cumulative snapshot history workbook")
    snapshot_backfill_parser.add_argument("--monthly-diff-file", type=Path, default=None, help="Where to write the latest monthly diff workbook")
    snapshot_backfill_parser.set_defaults(func=_backfill_monthly_snapshot_command)

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
