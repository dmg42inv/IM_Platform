"""Generates a single self-contained HTML dashboard structured the same way
as the monthly tracker's own "1. Live" / "2. Exited" report tabs: deals
grouped into sections (Mozn / G42 Investments / G42 Capital / Core42 /
GX Investments-MGX) with subtotal rows, plus IRR (deal-level and section-
level, computed from dated cash flows - not in the tracker's own view),
a full cash flow transaction list, ownership/domiciliation, the tracker's
own change log, a portfolio growth view (historical NAV + quarterly cash
flow bar charts), and an update-scan panel. Every data cell carries a
hover tooltip citing its source; each table has a CSV download button.
Charts use Chart.js from a CDN; everything else is vanilla HTML/CSS/JS.
"""

from __future__ import annotations

import html as _html
import json
from datetime import date

import pandas as pd

from .entity_glossary import display_name, investing_entity_full_name
from .formatting import fmt_multiple, fmt_num
from .live_exited_sections import _COMMITTED_EQUALS_INVESTED_DEALS, _FUND_CAS_CASHFLOW_OVERRIDES

# Deal names where the Invested/cash-flow figure has been specifically
# cross-checked against a primary source document (not just "sourced from
# Treasury" - actually verified to match). Extend this whenever a deal's
# cash flow amount is confirmed against a signed document/CAS - see repo
# memory for the verification trail behind each entry.
_CASHFLOW_VALIDATED_DEALS: dict[str, str] = {
    "Esyasoft Holding": "matches the executed Note Purchase Agreement/Debenture exactly.",
    "Esyasoft Holding (Debt)": "matches the executed Loan Agreement exactly.",
    "Mena Mobile Inc": "matches the executed Series B Purchase Agreement exactly.",
    "Mena Mobile Inc (Debt)": "matches the executed Loan Agreement exactly.",
    "vTv Therapeutics Inc.": "matches the audited public 10-K disclosure exactly.",
}


def _fnum(v, digits: int = 1) -> str:
    return fmt_num(v, default_digits=digits)


def _fx(v) -> str:
    return fmt_multiple(v)


def _fpct(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return f"{v * 100:.1f}%"


def _esc(v) -> str:
    return _html.escape(str(v)) if v is not None else ""


def _td(content: str, tooltip: str = "", cls: str = "") -> str:
    classes = cls
    if tooltip:
        classes = (classes + " tt").strip()
        return f'<td class="{classes}" data-tt="{_esc(tooltip)}">{content}</td>'
    return f'<td class="{classes}">{content}</td>' if classes else f"<td>{content}</td>"


def _section_subtotal(group: pd.DataFrame) -> dict:
    committed = group["committed"].sum()
    invested = group["invested"].sum()
    remaining = group["remaining_commitment"].sum()
    distributions = group["distributions"].sum()
    carrying = group["carrying_value"].sum()
    gain = group["gain"].sum()
    tvpi = (distributions + carrying) / invested if invested else None
    return {
        "committed": committed, "invested": invested, "remaining_commitment": remaining,
        "distributions": distributions, "carrying_value": carrying, "gain": gain, "tvpi": tvpi,
    }


def _render_deal_table(
    deals: pd.DataFrame,
    section_irr: pd.DataFrame,
    tab_label: str,
    as_of_date: str,
    deal_entity_map: dict[str, str],
    citation_lookup: dict[str, dict],
) -> str:
    rows_html = []
    section_irr_map = {row["section"]: row["irr"] for _, row in section_irr[section_irr["tab"] == tab_label].iterrows()}
    tracker_src = f"tracker's own '{'1. Live' if tab_label == 'Live' else '2. Exited'}' report tab, as of {as_of_date}"

    for section, group in deals[deals["tab"] == tab_label].groupby("section", sort=False):
        rows_html.append(f'<tr class="section-header"><td colspan="13">{_esc(section)}</td></tr>')
        for _, d in group.iterrows():
            irr_tt = (
                f"Computed via XIRR from dated cash flows + latest NAV fair value (see All Cashflows tab). {d['irr_note']}"
                if d["irr_note"] else "Computed via XIRR from dated cash flows + latest NAV fair value (see All Cashflows tab)."
            )
            citation = citation_lookup.get(deal_entity_map.get(d["deal_name"], ""), {})
            # Committed uses the deal-specific citation first (see
            # _DEAL_NAME_TO_INVESTMENT_IDS) so it isn't pooled across every
            # deal row sharing one entity - investing entity/vintage/
            # instrument stay entity-level, since those are genuinely facts
            # about the whole company, not split per tranche/deal row.
            committed_citation = citation_lookup.get(d["deal_name"]) or citation
            full_code_name = investing_entity_full_name(d["investing_entity"])
            investing_entity_tt = f"{citation.get('short_citation', 'Not yet confirmed against a primary document')}: {full_code_name}."
            if committed_citation.get("commitments"):
                committed_tt = f"{committed_citation.get('short_citation', '')}: {'; '.join(committed_citation['commitments'])}."
            elif "commitment_amounts_usd" in committed_citation:
                committed_tt = committed_citation.get("short_citation", "")
            else:
                committed_tt = f"No confirmed primary-source commitment amount in the register yet - showing {tracker_src}."
            if d["deal_name"] in _COMMITTED_EQUALS_INVESTED_DEALS:
                committed_tt = _COMMITTED_EQUALS_INVESTED_DEALS[d["deal_name"]]
            elif committed_citation.get("excluded_non_usd_commitments"):
                committed_tt += (
                    " WARNING: Committed is UNDERSTATED - excludes a non-USD commitment not converted here: "
                    + "; ".join(committed_citation["excluded_non_usd_commitments"]) + "."
                )
            invested_tt = "Sourced from cash flows provided by Treasury (see All Cashflows tab)."
            distributions_tt = "Sourced from cash flows provided by Treasury (see All Cashflows tab)."
            if d["deal_name"] in _CASHFLOW_VALIDATED_DEALS:
                note = _CASHFLOW_VALIDATED_DEALS[d["deal_name"]]
                invested_tt += f" Validated - {note}"
                distributions_tt += f" Validated - {note}"
            if d["deal_name"] in _FUND_CAS_CASHFLOW_OVERRIDES:
                cas_note = _FUND_CAS_CASHFLOW_OVERRIDES[d["deal_name"]]["note"]
                invested_tt = f"Sourced from the fund's own Capital Account Statement, not the tracker's cash flow rows. {cas_note}"
                distributions_tt = invested_tt
            carrying_tt = "Latest carrying value from the tracker's own NAV tab (not the Live/Exited tab)."
            remaining_tt = "Formula: Committed - Invested."
            gain_tt = "Formula: Carrying Value + Distributions - Invested."
            tvpi_tt = "Formula: (Distributions + Carrying Value) / Invested."
            if citation.get("close_dates"):
                vintage_tt = f"{citation.get('short_citation', '')}: close date {', '.join(citation['close_dates'])}."
            else:
                vintage_tt = f"No confirmed primary-source close date in the register yet - showing {tracker_src}."
            if citation.get("instrument"):
                instrument_tt = f"{citation.get('short_citation', '')}: '{citation['instrument']}' as stated in the citation."
            else:
                instrument_tt = f"Not yet cross-checked against a primary document - showing {tracker_src}."
            rows_html.append(
                "<tr>"
                + _td(_esc(d["deal_name"]), cls="left")
                + _td(_esc(d["status"]))
                + _td(_esc(d["investing_entity"]), investing_entity_tt)
                + _td(_esc(d["vintage"]), vintage_tt)
                + _td(_esc(d["instrument"]), instrument_tt)
                + _td(_fnum(d["committed"]), committed_tt)
                + _td(_fnum(d["invested"]), invested_tt)
                + _td(_fnum(d["remaining_commitment"]), remaining_tt)
                + _td(_fnum(d["distributions"]), distributions_tt)
                + _td(_fnum(d["carrying_value"]), carrying_tt)
                + _td(_fnum(d["gain"]), gain_tt)
                + _td(_fx(d["tvpi"]), tvpi_tt)
                + _td(_fpct(d["irr"]), irr_tt)
                + "</tr>"
            )
        sub = _section_subtotal(group)
        irr_val = section_irr_map.get(section)
        section_irr_tt = "Blended IRR: pools every deal's cash flows + latest fair value in this section, then runs XIRR once."
        rows_html.append(
            '<tr class="subtotal">'
            + _td("Subtotal", cls="left") + "<td></td><td></td><td></td><td></td>"
            + _td(_fnum(sub["committed"]))
            + _td(_fnum(sub["invested"]))
            + _td(_fnum(sub["remaining_commitment"]))
            + _td(_fnum(sub["distributions"]))
            + _td(_fnum(sub["carrying_value"]))
            + _td(_fnum(sub["gain"]))
            + _td(_fx(sub["tvpi"]))
            + _td(_fpct(irr_val), section_irr_tt)
            + "</tr>"
        )

    grand = _section_subtotal(deals[deals["tab"] == tab_label])
    rows_html.append(
        '<tr class="grand-total">'
        + _td("Grand Total", cls="left") + "<td></td><td></td><td></td><td></td>"
        + _td(_fnum(grand["committed"]))
        + _td(_fnum(grand["invested"]))
        + _td(_fnum(grand["remaining_commitment"]))
        + _td(_fnum(grand["distributions"]))
        + _td(_fnum(grand["carrying_value"]))
        + _td(_fnum(grand["gain"]))
        + _td(_fx(grand["tvpi"]))
        + "<td></td>"
        + "</tr>"
    )

    header = (
        "<thead><tr>"
        "<th class='left'>Deal</th><th>Status</th><th>Investing Entity</th><th>Vintage</th><th>Instrument</th>"
        "<th>Committed ($m)</th><th>Invested ($m)</th><th>Remaining ($m)</th><th>Distributions ($m)</th>"
        "<th>Carrying Value ($m)</th><th>Gain ($m)</th><th>TVPI</th><th>IRR</th>"
        "</tr></thead>"
    )
    # Fixed column widths (via colgroup + table-layout: fixed on .deal-table)
    # so columns line up and stay a consistent width - both between the Live
    # and Exited tables, and across dashboard regenerations - instead of each
    # table auto-sizing its own columns from whatever content happens to be
    # in it that run.
    colgroup = (
        "<colgroup>"
        "<col style='width:16%'><col style='width:6%'><col style='width:8%'><col style='width:5%'>"
        "<col style='width:9%'><col style='width:7%'><col style='width:7%'><col style='width:7%'>"
        "<col style='width:8%'><col style='width:8%'><col style='width:7%'><col style='width:6%'><col style='width:6%'>"
        "</colgroup>"
    )
    table_id = f"table-{tab_label.lower()}"
    return f"<div class='table-scroll'><table id='{table_id}' class='deal-table'>{colgroup}{header}<tbody>{''.join(rows_html)}</tbody></table></div>"


def _render_cashflow_table(cashflow: pd.DataFrame) -> str:
    cf = cashflow.copy()
    cf["flow_date"] = pd.to_datetime(cf["flow_date"], errors="coerce")
    cf = cf.sort_values("flow_date", ascending=False)
    rows_html = []
    for _, r in cf.iterrows():
        amt = r["amount"]
        cls = "pos" if amt >= 0 else "neg"
        tt = f"Source: {r.get('source_reference', '')} (tracker cashflow_id {r.get('cashflow_id', '')})"
        name_tt = f"Register entity_id: {r['resolved_entity_id']}" if display_name(r["resolved_entity_id"]) != r["resolved_entity_id"] else ""
        rows_html.append(
            "<tr>"
            + _td(r["flow_date"].strftime("%Y-%m-%d") if pd.notna(r["flow_date"]) else "", cls="left")
            + _td(_esc(display_name(r["resolved_entity_id"])), name_tt, cls="left")
            + _td(_esc(r["flow_type"]))
            + _td(f"{amt:,.0f}", tt, cls=cls)
            + _td(_esc(r["currency"]))
            + _td(_esc(r.get("consideration_type", "")), cls="left")
            + "</tr>"
        )
    header = (
        "<thead><tr><th class='left'>Date</th><th class='left'>Investment</th><th>Flow Type</th>"
        "<th>Amount (USD)</th><th>Currency</th><th class='left'>Consideration Type</th></tr></thead>"
    )
    return f"<div class='table-scroll'><table id='table-cashflows'>{header}<tbody>{''.join(rows_html)}</tbody></table></div>"


def _render_glossary_table(glossary: pd.DataFrame) -> str:
    rows_html = []
    for _, r in glossary.iterrows():
        rows_html.append(
            "<tr>"
            + _td(_esc(r["display_name"]), cls="left")
            + _td(_esc(r["full_legal_name"]), cls="left")
            + _td(_esc(r["entity_id"]), cls="left")
            + _td(_esc(r["note"]), cls="left wrap")
            + "</tr>"
        )
    header = (
        "<thead><tr><th class='left'>Display Name</th><th class='left'>Full Legal Name</th>"
        "<th class='left'>Internal Register ID</th><th class='left'>Note</th></tr></thead>"
    )
    return f"<div class='table-scroll'><table id='table-glossary'>{header}<tbody>{''.join(rows_html)}</tbody></table></div>"


def _render_ownership_table(ownership: pd.DataFrame) -> str:
    rows_html = []
    for section, group in ownership.groupby("section", sort=False):
        rows_html.append(f'<tr class="section-header"><td colspan="7">{_esc(section)}</td></tr>')
        for _, r in group.iterrows():
            tt = f"Source for % holding: {r['source_for_pct'] or 'not specified in tracker'}"
            rows_html.append(
                "<tr>"
                + _td(_esc(r["deal_name"]), cls="left")
                + _td(_esc(r["status_flag"]))
                + _td(_fnum(r["shares_units"], 0))
                + _td(_fnum(r["fully_diluted_total"], 0))
                + _td(_fpct(r["ownership_pct"]), tt)
                + _td(_esc(r["jurisdiction"]), cls="left")
                + _td(_esc(r["country"]), cls="left")
                + "</tr>"
            )
    header = (
        "<thead><tr><th class='left'>Deal</th><th>Status</th><th>Shares/Units</th><th>Fully Diluted Total</th>"
        "<th>Ownership %</th><th class='left'>Jurisdiction</th><th class='left'>Country</th></tr></thead>"
    )
    return f"<div class='table-scroll'><table id='table-ownership'>{header}<tbody>{''.join(rows_html)}</tbody></table></div>"


def _render_log_table(change_log: pd.DataFrame) -> str:
    rows_html = []
    for _, r in change_log.iterrows():
        rows_html.append(
            "<tr>"
            + _td(_esc(r["month"]), cls="left")
            + _td(_esc(r["company"]), cls="left")
            + _td(_esc(r["update"]), cls="left wrap")
            + "</tr>"
        )
    header = "<thead><tr><th class='left'>Month</th><th class='left'>Company</th><th class='left'>Update</th></tr></thead>"
    return f"<div class='table-scroll'><table id='table-log'>{header}<tbody>{''.join(rows_html)}</tbody></table></div>"


def _render_issues_table(issues: pd.DataFrame) -> str:
    if len(issues) == 0:
        return "<p class='muted'>No data quality exceptions in this run.</p>"
    rows_html = []
    for _, r in issues.iterrows():
        rows_html.append(
            "<tr>"
            + _td(_esc(r.get("dataset_name", "")), cls="left")
            + _td(_esc(r.get("record_key", "")), cls="left")
            + _td(_esc(r.get("issue_type", "")), cls="left")
            + _td(_esc(r.get("issue_description", "")), cls="left wrap")
            + _td(_esc(r.get("severity", "")))
            + "</tr>"
        )
    header = "<thead><tr><th class='left'>Dataset</th><th class='left'>Record</th><th class='left'>Issue Type</th><th class='left'>Description</th><th>Severity</th></tr></thead>"
    return f"<div class='table-scroll'><table id='table-issues'>{header}<tbody>{''.join(rows_html)}</tbody></table></div>"


def _render_notes_list(notes: list[str]) -> str:
    if not notes:
        return "<p class='muted'>No triangulation issues flagged.</p>"
    return "<ul>" + "".join(f"<li>{_esc(n)}</li>" for n in notes) + "</ul>"


# Curated, hand-written explanations for specific data points on the Live/
# Exited tables that aren't otherwise self-explanatory from a hover tooltip -
# e.g. why one company appears as two deal rows, or context behind a figure
# that might otherwise look surprising. Written for a senior leadership /
# board audience: state the facts plainly to illuminate the position, without
# framing anything as a correction or error. Add to this list whenever a
# reviewer would reasonably ask "why does this number/row look like that?"
# Kept separate from the auto-generated triangulation notes (register vs.
# tracker mismatches), which are data-quality flags rather than context.
_DEAL_NOTES: list[str] = [
    "Tools for Humanity Corporation (Live) and WLD Tokens (Exited) reflect the same underlying "
    "relationship (TFH - Worldcoin) shown as two separate lines: the Series C equity position "
    "remains Live, while the WLD token holding's $100M exchange into Inveniam's SAR is reported "
    "as a fully realized, Exited outcome - each carries its own Invested/Distributions figures.",
    "Cerebras Systems Inc appears as two lines by instrument: the original Series F Preferred "
    "position ($40M, 2021) and two subsequent Warrant exercises (~$0.035M combined, 2026) - each "
    "shown with its own Committed/Invested rather than a single combined figure.",
    "HeyGears' vintage year is 2020: while the Equity Subscription Agreement is dated 30 Sep "
    "2019, the transaction's Closing Date is 9 Jan 2020 per the closing binder, and the $60M "
    "funding was wired on 1 Dec 2020.",
    "Beyond Limits' Committed figure is shown equal to Invested ($90M), with no Remaining "
    "Commitment: the Note Purchase and Investment Agreement scheduled a final ~$10M Series C "
    "tranche, which has been cancelled - no further capital is intended for this position.",
    "Flyr's vintage year is 2019: a $5M convertible note was funded in April 2019, ahead of the "
    "Series B round it converted into in 2020 - the two closings together total the full $10M "
    "position.",
    "ONT plc's Committed figure is shown equal to Invested ($141.5M), with no Remaining "
    "Commitment: the co-investment JV structure originally contemplated alongside this position "
    "did not proceed, and the full committed capital has been deployed. One tranche (a "
    "GBP 61,632,106 Pre-Emptive Rights purchase) is carried in GBP and not separately converted "
    "to USD in this total.",
    "Liquid AI's Committed figure ($60.8M) is net of a $5.78M credit due back from Core42 (a G42 "
    "affiliate) under the compute Service Order tied to this transaction - the gross round size "
    "before that credit is $66.6M.",
    "School Hack's Committed figure ($2.75M) includes a $250,000 cloud-compute services credit "
    "the company is entitled to under the Subscription Agreement, in addition to the $2.5M cash "
    "equity subscription.",
]


def _render_deal_notes() -> str:
    return "<ul>" + "".join(f"<li>{_esc(n)}</li>" for n in _DEAL_NOTES) + "</ul>"


def _render_scan_report(scan_report: dict | None) -> str:
    if not scan_report:
        return (
            "<p class='muted'>No scan has been run yet. Run "
            "<code>python -m im_platform.cli scan-for-updates --investments-root &lt;path&gt;</code> "
            "from a terminal, then regenerate this dashboard to see results here. "
            "A static HTML file cannot execute a local Python process on its own - "
            "there is no server behind this page.</p>"
        )
    parts = [f"<p class='muted'>Last scanned: {_esc(scan_report['scan_date'])} "
             f"({scan_report['total_company_folders_scanned']} company folders, "
             f"{scan_report['total_fund_folders_scanned']} fund folders checked)</p>"]
    if scan_report["new_company_folders"] or scan_report["new_fund_folders"]:
        parts.append("<h3>New folders not yet in the register</h3><ul>")
        for f in scan_report["new_company_folders"]:
            parts.append(f"<li>{_esc(f)} (equity)</li>")
        for f in scan_report["new_fund_folders"]:
            parts.append(f"<li>{_esc(f)} (fund)</li>")
        parts.append("</ul>")
    else:
        parts.append("<p class='muted'>No new company/fund folders found since the register was last built.</p>")
    if scan_report["recently_modified_folders"]:
        parts.append("<h3>Folders with files modified in the last 30 days</h3><ul>")
        for r in scan_report["recently_modified_folders"]:
            parts.append(f"<li>{_esc(r['folder'])} - {_esc(r['last_modified'])}</li>")
        parts.append("</ul>")
    if scan_report.get("added_files"):
        parts.append("<h3>New files since last scan (may need capturing in the register)</h3><ul>")
        for f in scan_report["added_files"]:
            parts.append(f"<li>{_esc(f['file'])} - <i>{_esc(f['impact'])}</i></li>")
        parts.append("</ul>")
    if scan_report.get("modified_files"):
        parts.append("<h3>Modified files since last scan (may need re-review)</h3><ul>")
        for f in scan_report["modified_files"]:
            parts.append(f"<li>{_esc(f['file'])} - <i>{_esc(f['impact'])}</i></li>")
        parts.append("</ul>")
    if scan_report.get("renamed_files"):
        parts.append(
            "<h3>Likely renamed/moved files since last scan (same size, different path/name - "
            "heuristic, confirm before relying on it)</h3><ul>"
        )
        for f in scan_report["renamed_files"]:
            parts.append(
                f"<li>{_esc(f['old_file'])} &rarr; {_esc(f['new_file'])} - <i>{_esc(f['impact'])}</i></li>"
            )
        parts.append("</ul>")
    if scan_report.get("deleted_files"):
        parts.append("<h3>Files no longer found since last scan (removed, moved out, or renamed)</h3><ul>")
        for f in scan_report["deleted_files"]:
            parts.append(f"<li>{_esc(f['file'])} - <i>{_esc(f['impact'])}</i></li>")
        parts.append("</ul>")
    return "".join(parts)


def build_tracker_style_dashboard_html(
    deals: pd.DataFrame,
    section_irr: pd.DataFrame,
    quarterly: pd.DataFrame,
    historical_nav: pd.DataFrame,
    cashflow: pd.DataFrame,
    ownership: pd.DataFrame,
    change_log: pd.DataFrame,
    issues: pd.DataFrame,
    triangulation_notes: list[str],
    deal_entity_map: dict[str, str],
    citation_lookup: dict[str, dict],
    glossary: pd.DataFrame,
    scan_report: dict | None = None,
    as_of_date: str | None = None,
) -> str:
    as_of_date = as_of_date or date.today().isoformat()

    live_grand = _section_subtotal(deals[deals["tab"] == "Live"])
    exited_grand = _section_subtotal(deals[deals["tab"] == "Exited"])

    live_table = _render_deal_table(deals, section_irr, "Live", as_of_date, deal_entity_map, citation_lookup)
    exited_table = _render_deal_table(deals, section_irr, "Exited", as_of_date, deal_entity_map, citation_lookup)
    cashflow_table = _render_cashflow_table(cashflow)
    ownership_table = _render_ownership_table(ownership)
    log_table = _render_log_table(change_log)
    issues_table = _render_issues_table(issues)
    glossary_table = _render_glossary_table(glossary)
    notes_html = _render_notes_list(triangulation_notes)
    deal_notes_html = _render_deal_notes()
    scan_html = _render_scan_report(scan_report)

    nav_chart_data = {
        "labels": historical_nav["month"].tolist(),
        "carrying": [None if pd.isna(v) else round(v, 1) for v in historical_nav["carrying_value"]],
        "invested": [None if pd.isna(v) else round(v, 1) for v in historical_nav["invested"]],
    }
    quarterly_chart_data = {
        "labels": quarterly["quarter"].tolist(),
        "inflow": [round(v / 1_000_000, 2) for v in quarterly["inflow"]],
        "outflow": [round(v / 1_000_000, 2) for v in quarterly["outflow"]],
    }

    return _HTML_TEMPLATE.format(
        as_of_date=as_of_date,
        generated=date.today().isoformat(),
        live_committed=_fnum(live_grand["committed"]),
        live_invested=_fnum(live_grand["invested"]),
        live_carrying=_fnum(live_grand["carrying_value"]),
        live_gain=_fnum(live_grand["gain"]),
        live_tvpi=_fx(live_grand["tvpi"]),
        exited_invested=_fnum(exited_grand["invested"]),
        exited_distributions=_fnum(exited_grand["distributions"]),
        exited_gain=_fnum(exited_grand["gain"]),
        exited_tvpi=_fx(exited_grand["tvpi"]),
        live_table=live_table,
        exited_table=exited_table,
        cashflow_table=cashflow_table,
        ownership_table=ownership_table,
        log_table=log_table,
        issues_table=issues_table,
        glossary_table=glossary_table,
        notes_html=notes_html,
        deal_notes_html=deal_notes_html,
        scan_html=scan_html,
        nav_chart_json=json.dumps(nav_chart_data),
        quarterly_chart_json=json.dumps(quarterly_chart_data),
    )


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>IM Platform - Portfolio Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  :root {{
    --bg: #0f172a; --panel: #1e293b; --text: #e2e8f0; --muted: #94a3b8;
    --accent: #38bdf8; --green: #4ade80; --red: #f87171; --border: #334155; --sub-bg: #253449;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; background: var(--bg); color: var(--text); }}
  header {{ padding: 18px 28px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }}
  header h1 {{ font-size: 18px; margin: 0; font-weight: 600; }}
  header .meta {{ color: var(--muted); font-size: 12px; }}
  nav {{ display: flex; gap: 4px; padding: 0 28px; border-bottom: 1px solid var(--border); overflow-x: auto; }}
  nav button {{ background: none; border: none; color: var(--muted); padding: 12px 16px; cursor: pointer; font-size: 13px; border-bottom: 2px solid transparent; white-space: nowrap; }}
  nav button.active {{ color: var(--accent); border-bottom-color: var(--accent); }}
  main {{ padding: 22px 28px; }}
  .tab {{ display: none; }}
  .tab.active {{ display: block; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 22px; }}
  .kpi-card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }}
  .kpi-card .label {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.03em; }}
  .kpi-card .value {{ font-size: 20px; font-weight: 600; margin-top: 6px; }}
  .panel {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 18px; }}
  .table-scroll {{ overflow-x: auto; }}
  .panel-head {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
  .panel h2 {{ font-size: 13px; margin: 0; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; }}
  .dl-btn {{ background: var(--sub-bg); border: 1px solid var(--border); color: var(--accent); border-radius: 6px; padding: 5px 12px; font-size: 11px; cursor: pointer; }}
  .dl-btn:hover {{ background: var(--border); }}
  table {{ width: 100%; min-width: 1100px; border-collapse: collapse; font-size: 12.5px; }}
  table.deal-table {{ table-layout: fixed; }}
  th, td {{ padding: 6px 9px; text-align: right; vertical-align: middle; border-bottom: 1px solid var(--border); white-space: nowrap; }}
  table.deal-table th, table.deal-table td {{ overflow: hidden; text-overflow: ellipsis; }}
  th.left, td.left {{ text-align: left; white-space: nowrap; min-width: 220px; }}
  td.wrap {{ white-space: normal; max-width: 420px; min-width: 260px; vertical-align: middle; }}
  th {{ color: var(--muted); font-weight: 500; vertical-align: middle; }}
  tr.section-header td {{ background: var(--sub-bg); font-weight: 600; color: var(--accent); vertical-align: middle; text-align: left; }}
  tr.subtotal td {{ background: #182234; font-weight: 600; border-top: 1px solid var(--border); vertical-align: middle; }}
  tr.grand-total td {{ background: #0b1220; font-weight: 700; border-top: 2px solid var(--accent); vertical-align: middle; }}
  .pos {{ color: var(--green); }} .neg {{ color: var(--red); }}
  .muted {{ color: var(--muted); font-size: 13px; }}
  ul {{ margin: 0; padding-left: 20px; color: var(--text); font-size: 13px; line-height: 1.6; }}
  code {{ background: var(--sub-bg); padding: 1px 6px; border-radius: 4px; font-size: 12px; }}
  .chart-box {{ position: relative; height: 340px; }}
  .top-actions {{ display: flex; gap: 8px; align-items: center; }}
  .top-actions button {{ background: var(--panel); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 8px 14px; font-size: 12px; cursor: pointer; }}
  .top-actions button:hover {{ border-color: var(--accent); color: var(--accent); }}

  /* Hover tooltip - "soft popup" citing the source of a data point.
     Rendered via JS into a single body-level fixed-position element (see
     the script block below) rather than CSS ::after, so it can never be
     clipped by any ancestor's overflow/scroll box - a real, hard-to-debug
     bug hit with the pure-CSS version. */
  .tt {{ cursor: help; border-bottom: 1px dotted var(--muted); }}
  #jsTooltip {{
    display: none; position: fixed; background: #0b1220; color: var(--text);
    border: 1px solid var(--accent); padding: 8px 10px; border-radius: 6px;
    font-size: 11.5px; white-space: normal; max-width: 320px; text-align: left;
    line-height: 1.4; z-index: 1000; box-shadow: 0 4px 14px rgba(0,0,0,0.4);
    pointer-events: none;
  }}

  #updateModal {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.55); z-index: 100; align-items: center; justify-content: center; }}
  #updateModal .box {{ background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 24px; max-width: 520px; }}
  #updateModal .box h3 {{ margin-top: 0; }}
  #updateModal button.close {{ margin-top: 14px; background: var(--accent); border: none; color: #0b1220; font-weight: 600; padding: 8px 16px; border-radius: 6px; cursor: pointer; }}
</style>
</head>
<body>

<header>
  <h1>IM Platform &mdash; Portfolio Report</h1>
  <div class="top-actions">
    <span class="meta">As-of {as_of_date} &middot; Generated {generated}</span>
    <button id="btnUpdate">Update</button>
  </div>
</header>

<nav>
  <button class="tab-btn active" data-tab="live">Live Investments</button>
  <button class="tab-btn" data-tab="exited">Exited Investments</button>
  <button class="tab-btn" data-tab="cashflows">All Cashflows</button>
  <button class="tab-btn" data-tab="ownership">Ownership &amp; Domiciliation</button>
  <button class="tab-btn" data-tab="log">Log</button>
  <button class="tab-btn" data-tab="growth">Portfolio Growth</button>
  <button class="tab-btn" data-tab="quality">Data Quality &amp; Triangulation</button>
  <button class="tab-btn" data-tab="glossary">Glossary</button>
</nav>

<main>

  <section id="live" class="tab active">
    <div class="kpi-grid">
      <div class="kpi-card"><div class="label">Committed ($m)</div><div class="value">{live_committed}</div></div>
      <div class="kpi-card"><div class="label">Invested ($m)</div><div class="value">{live_invested}</div></div>
      <div class="kpi-card"><div class="label">Carrying Value ($m)</div><div class="value">{live_carrying}</div></div>
      <div class="kpi-card"><div class="label">Gain ($m)</div><div class="value">{live_gain}</div></div>
      <div class="kpi-card"><div class="label">TVPI</div><div class="value">{live_tvpi}</div></div>
    </div>
    <div class="panel">
      <div class="panel-head"><h2>Live Investments, by Investing Entity</h2><button class="dl-btn" onclick="downloadCSV('table-live','live_investments.csv')">Download CSV</button></div>
      {live_table}
    </div>
    <div class="panel">
      <h2>Notes</h2>
      {deal_notes_html}
    </div>
  </section>

  <section id="exited" class="tab">
    <div class="kpi-grid">
      <div class="kpi-card"><div class="label">Invested ($m)</div><div class="value">{exited_invested}</div></div>
      <div class="kpi-card"><div class="label">Distributions ($m)</div><div class="value">{exited_distributions}</div></div>
      <div class="kpi-card"><div class="label">Gain ($m)</div><div class="value">{exited_gain}</div></div>
      <div class="kpi-card"><div class="label">TVPI</div><div class="value">{exited_tvpi}</div></div>
    </div>
    <div class="panel">
      <div class="panel-head"><h2>Exited Investments, by Investing Entity</h2><button class="dl-btn" onclick="downloadCSV('table-exited','exited_investments.csv')">Download CSV</button></div>
      {exited_table}
    </div>
  </section>

  <section id="cashflows" class="tab">
    <div class="panel">
      <div class="panel-head"><h2>All Cash Flow Transactions</h2><button class="dl-btn" onclick="downloadCSV('table-cashflows','all_cashflows.csv')">Download CSV</button></div>
      {cashflow_table}
    </div>
  </section>

  <section id="ownership" class="tab">
    <div class="panel">
      <div class="panel-head"><h2>Ownership % and Domiciliation</h2><button class="dl-btn" onclick="downloadCSV('table-ownership','ownership.csv')">Download CSV</button></div>
      {ownership_table}
    </div>
  </section>

  <section id="log" class="tab">
    <div class="panel">
      <div class="panel-head"><h2>Monthly Change Log (from tracker)</h2><button class="dl-btn" onclick="downloadCSV('table-log','change_log.csv')">Download CSV</button></div>
      {log_table}
    </div>
  </section>

  <section id="growth" class="tab">
    <div class="panel">
      <h2>Historical Portfolio NAV (Live Carrying Value, by month)</h2>
      <div class="chart-box"><canvas id="chartNav"></canvas></div>
    </div>
    <div class="panel">
      <h2>Quarterly Gross Inflows / Outflows, All Deals ($m)</h2>
      <div class="chart-box"><canvas id="chartQuarterly"></canvas></div>
    </div>
  </section>

  <section id="quality" class="tab">
    <div class="panel">
      <h2>Methodology</h2>
      <ul>
        <li><b>Committed</b>: primary-source commitment amount from the register (signed SPA/Subscription Agreement/Capital Account Statement etc.), NOT the tracker's Live/Exited tab - falls back to the tracker's own figure only when no primary-source amount has been confirmed yet.</li>
        <li><b>Invested</b>: sum of cash deployments from dated cash flows (CF (Equity, Debt) / CF (Funds) tabs), not the tracker's Live/Exited tab.</li>
        <li><b>Distributions</b>: sum of cash distributions from dated cash flows. Shows 0 where there are no distribution records.</li>
        <li><b>Carrying Value</b>: latest mark from the tracker's own NAV tab, not the Live/Exited tab.</li>
        <li><b>Remaining</b> = Committed - Invested.</li>
        <li><b>Gain</b> = Carrying Value + Distributions - Invested.</li>
        <li><b>TVPI</b> = (Distributions + Carrying Value) / Invested.</li>
        <li><b>IRR</b> (deal and section level): XIRR over the same dated cash flows, with the latest NAV mark as a terminal cash flow.</li>
      </ul>
      <p class="muted">These match how the tracker's own underlying formulas work (verified directly against its 'A. All deals (a)' tab) - the difference is we compute them from primary sources (register + cash flows + NAV) rather than reading the tracker's own derived output.</p>
    </div>
    <div class="panel"><h2>Triangulation Notes (register vs. tracker's own Live/Exited report)</h2>{notes_html}</div>
    <div class="panel"><h2>Data Quality Exceptions</h2>{issues_table}</div>
    <div class="panel"><h2>Update Scan (new/changed document folders)</h2>{scan_html}</div>
  </section>

  <section id="glossary" class="tab">
    <div class="panel">
      <div class="panel-head"><h2>Entity Name Glossary</h2><button class="dl-btn" onclick="downloadCSV('table-glossary','glossary.csv')">Download CSV</button></div>
      <p class="muted">Display names shown across this dashboard vs. the full legal name and internal register identifier (often derived from document folder names) - use this if a name looks unfamiliar or abbreviated.</p>
      {glossary_table}
    </div>
  </section>

</main>

<div id="jsTooltip"></div>

<div id="updateModal">
  <div class="box">
    <h3>Update Portfolio Data</h3>
    <p>A static HTML file can't run a local Python process by itself - there's no server behind this page.</p>
    <p>To check for new investments or changed documents, run this from a terminal in the project folder, then regenerate this dashboard:</p>
    <p><code>python -m im_platform.cli scan-for-updates --investments-root &lt;path&gt;</code></p>
    <p>Results appear in the "Data Quality &amp; Triangulation" tab after the next regeneration.</p>
    <button class="close" onclick="document.getElementById('updateModal').style.display='none'">Close</button>
  </div>
</div>

<script>
// JS-driven tooltip (see #jsTooltip CSS comment for why this replaced a
// pure-CSS ::after popup): position:fixed on a body-level element can't be
// clipped by any ancestor's overflow, unlike position:absolute inside a
// scrollable table/panel.
(function () {{
  const tip = document.getElementById("jsTooltip");
  function place(evt) {{
    const margin = 14;
    let x = evt.clientX + margin;
    let y = evt.clientY + margin;
    const maxX = window.innerWidth - tip.offsetWidth - margin;
    const maxY = window.innerHeight - tip.offsetHeight - margin;
    if (x > maxX) x = evt.clientX - tip.offsetWidth - margin;
    if (y > maxY) y = evt.clientY - tip.offsetHeight - margin;
    tip.style.left = Math.max(margin, x) + "px";
    tip.style.top = Math.max(margin, y) + "px";
  }}
  document.body.addEventListener("mouseover", (evt) => {{
    const el = evt.target.closest(".tt");
    if (!el || !el.dataset.tt) return;
    tip.textContent = el.dataset.tt;
    tip.style.display = "block";
    place(evt);
  }});
  document.body.addEventListener("mousemove", (evt) => {{
    if (tip.style.display === "block") place(evt);
  }});
  document.body.addEventListener("mouseout", (evt) => {{
    const el = evt.target.closest(".tt");
    if (!el) return;
    if (evt.relatedTarget && el.contains(evt.relatedTarget)) return;
    tip.style.display = "none";
  }});
}})();

document.querySelectorAll(".tab-btn").forEach(btn => {{
  btn.addEventListener("click", () => {{
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
  }});
}});

document.getElementById("btnUpdate").addEventListener("click", () => {{
  document.getElementById("updateModal").style.display = "flex";
}});

function downloadCSV(tableId, filename) {{
  const table = document.getElementById(tableId);
  if (!table) return;
  const rows = [];
  table.querySelectorAll("tr").forEach(tr => {{
    const cells = [...tr.children].map(td => {{
      const text = td.innerText.replace(/"/g, '""');
      return `"${{text}}"`;
    }});
    if (cells.length) rows.push(cells.join(","));
  }});
  const blob = new Blob([rows.join("\n")], {{ type: "text/csv;charset=utf-8;" }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}}

const NAV_DATA = {nav_chart_json};
new Chart(document.getElementById("chartNav"), {{
  type: "bar",
  data: {{
    labels: NAV_DATA.labels,
    datasets: [
      {{ label: "Carrying Value ($m)", data: NAV_DATA.carrying, backgroundColor: "#38bdf8" }},
      {{ label: "Invested ($m)", data: NAV_DATA.invested, backgroundColor: "#64748b" }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ labels: {{ color: "#e2e8f0" }} }} }},
    scales: {{ x: {{ ticks: {{ color: "#94a3b8" }} }}, y: {{ ticks: {{ color: "#94a3b8" }} }} }}
  }}
}});

const Q_DATA = {quarterly_chart_json};
new Chart(document.getElementById("chartQuarterly"), {{
  type: "bar",
  data: {{
    labels: Q_DATA.labels,
    datasets: [
      {{ label: "Inflow ($m)", data: Q_DATA.inflow, backgroundColor: "#4ade80" }},
      {{ label: "Outflow ($m)", data: Q_DATA.outflow, backgroundColor: "#f87171" }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ labels: {{ color: "#e2e8f0" }} }} }},
    scales: {{ x: {{ ticks: {{ color: "#94a3b8" }} }}, y: {{ ticks: {{ color: "#94a3b8" }} }} }}
  }}
}});
</script>

</body>
</html>
"""
