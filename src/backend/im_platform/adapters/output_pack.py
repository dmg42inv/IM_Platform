"""Assembles the full V1 Output Pack (docs/implementation/V1_Output_Pack_Spec.md):
the portfolio workbook's extra tabs beyond Portfolio_Snapshot/Returns_Summary,
and the accompanying Markdown summary note.

Monitoring_Summary and Governance_and_Control are written as placeholder tabs:
no monthly monitoring (KPI/covenant/milestone) or IC decision adapter has been
built yet, so there is no source data to populate them from. They are still
emitted (per spec, so the workbook shape is stable) with an explicit
'not available' note per metric rather than being silently omitted.
"""

from __future__ import annotations

from datetime import date

import pandas as pd


def build_monitoring_summary_placeholder() -> pd.DataFrame:
    reason = "Not available - no monthly monitoring (KPI/covenant/milestone) input dataset has been built yet"
    metrics = [
        "as_of_date",
        "kpi_trend_flags",
        "covenant_status_distribution",
        "milestone_status_distribution",
        "watchlist_movement_mom",
        "top_exceptions_with_owner",
    ]
    return pd.DataFrame({"metric": metrics, "value": [reason] * len(metrics)})


def build_governance_and_control_placeholder() -> pd.DataFrame:
    reason = "Not available - no IC/governance decisions input dataset has been built yet"
    metrics = [
        "ic_decisions_by_outcome",
        "open_conditions_aging",
        "compliance_risk_exception_counts",
        "approval_sla_breaches",
        "audit_trail_completeness_pct",
    ]
    return pd.DataFrame({"metric": metrics, "value": [reason] * len(metrics)})


def build_summary_note(
    snapshot: pd.DataFrame,
    returns: pd.DataFrame,
    issues: pd.DataFrame,
    as_of_date: str | None = None,
) -> str:
    """Render the Markdown summary note per V1 Output Pack Spec section 3."""
    as_of_date = as_of_date or date.today().isoformat()

    total_invested = snapshot["invested_cost_base"].sum() if len(snapshot) else 0.0
    total_fv = snapshot["latest_fair_value_base"].sum() if len(snapshot) else 0.0
    total_unrealized = snapshot["unrealized_gain_loss_base"].sum() if len(snapshot) else 0.0
    live_count = int((snapshot["lifecycle_state"] == "Live").sum()) if len(snapshot) else 0

    movers = pd.DataFrame()
    if len(returns):
        movers = returns.dropna(subset=["TVPI"]).copy()
        movers = movers.sort_values("TVPI", ascending=False)

    lines: list[str] = []
    lines.append("# V1 Portfolio Summary Note")
    lines.append("")
    lines.append(f"## 1. As-of Date and Data Cut Timestamp")
    lines.append(f"- As-of date: {as_of_date}")
    lines.append(f"- Generated: {date.today().isoformat()}")
    lines.append("")
    lines.append("## 2. Portfolio Headline Numbers")
    lines.append(f"- Total invested cost (USD): {total_invested:,.0f}")
    lines.append(f"- Total latest fair value (USD): {total_fv:,.0f}")
    lines.append(f"- Total unrealized gain/(loss) (USD): {total_unrealized:,.0f}")
    lines.append(f"- Live positions: {live_count} of {len(snapshot)} total register rows in this view")
    lines.append("")
    lines.append("## 3. Returns Highlights and Notable Movers")
    if len(movers):
        top = movers.head(5)
        bottom = movers.tail(5)
        lines.append("Top 5 by TVPI:")
        for _, row in top.iterrows():
            lines.append(f"- {row['investment_id']}: TVPI {row['TVPI']:.2f}x, DPI {row['DPI']:.2f}x, PaidIn ${row['PaidIn']:,.0f}")
        lines.append("")
        lines.append("Bottom 5 by TVPI:")
        for _, row in bottom.iterrows():
            lines.append(f"- {row['investment_id']}: TVPI {row['TVPI']:.2f}x, DPI {row['DPI']:.2f}x, PaidIn ${row['PaidIn']:,.0f}")
    else:
        lines.append("No positions with a computable TVPI in this view.")
    lines.append("")
    lines.append("## 4. Risk and Monitoring Exceptions")
    lines.append("Not available - no monthly monitoring input dataset has been built yet (see Monitoring_Summary tab).")
    lines.append("")
    lines.append("## 5. Governance/Control Exceptions")
    lines.append("Not available - no IC/governance decisions input dataset has been built yet (see Governance_and_Control tab).")
    lines.append("")
    lines.append("## 6. Data Quality Caveats")
    if len(issues):
        lines.append(f"{len(issues)} data quality exception(s) - see Data_Quality_Exceptions tab for detail.")
        for _, row in issues.head(10).iterrows():
            lines.append(f"- [{row.get('severity', '')}] {row.get('dataset_name', '')} / {row.get('record_key', '')}: {row.get('issue_description', '')}")
    else:
        lines.append("No data quality exceptions raised by validation checks in this run.")
    lines.append("")
    lines.append("## 7. Recommended Actions Before Next Cycle")
    lines.append("- Resolve any remaining rows in Needs_Source_Documents (Investment_Register_Intake.xlsx).")
    lines.append("- Build a monthly monitoring (KPI/covenant/milestone) input adapter to populate Monitoring_Summary.")
    lines.append("- Build an IC/governance decisions input adapter to populate Governance_and_Control.")
    lines.append("")

    return "\n".join(lines)
