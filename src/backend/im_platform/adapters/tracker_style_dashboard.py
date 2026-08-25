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
import re
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
            elif tab_label == "Exited":
                committed_tt = (
                    "Position fully exited - Committed is pinned to Invested here (no outstanding "
                    "commitment remains for an exited position, regardless of the original commitment "
                    "document's figure)."
                )
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


def _render_vintage_table(
    deals: pd.DataFrame,
    vintage_irr: pd.DataFrame,
    as_of_date: str,
    deal_entity_map: dict[str, str],
    citation_lookup: dict[str, dict],
    table_id: str = "table-vintage",
) -> str:
    """Same deal-level table as _render_deal_table, but grouped by vintage
    year (across BOTH Live and Exited) instead of by investing entity - shows
    how much was deployed and how each vintage has performed, cutting across
    current Live/Exited status rather than being split by it."""
    rows_html = []
    vintage_irr_map = {row["vintage"]: row["irr"] for _, row in vintage_irr.iterrows()}
    tracker_src = f"tracker's own report tabs, as of {as_of_date}"

    def _vintage_sort_key(v: str):
        return (1, "") if not v else (0, v)

    vintages = sorted(deals["vintage"].unique(), key=_vintage_sort_key)
    for vintage in vintages:
        group = deals[deals["vintage"] == vintage]
        label = vintage if vintage else "Unknown vintage"
        rows_html.append(f'<tr class="section-header"><td colspan="13">{_esc(label)}</td></tr>')
        for _, d in group.iterrows():
            irr_tt = (
                f"Computed via XIRR from dated cash flows + latest NAV fair value (see All Cashflows tab). {d['irr_note']}"
                if d["irr_note"] else "Computed via XIRR from dated cash flows + latest NAV fair value (see All Cashflows tab)."
            )
            citation = citation_lookup.get(deal_entity_map.get(d["deal_name"], ""), {})
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
            elif d["tab"] == "Exited":
                committed_tt = (
                    "Position fully exited - Committed is pinned to Invested here (no outstanding "
                    "commitment remains for an exited position, regardless of the original commitment "
                    "document's figure)."
                )
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
            if citation.get("instrument"):
                instrument_tt = f"{citation.get('short_citation', '')}: '{citation['instrument']}' as stated in the citation."
            else:
                instrument_tt = f"Not yet cross-checked against a primary document - showing {tracker_src}."
            rows_html.append(
                "<tr>"
                + _td(_esc(d["deal_name"]), cls="left")
                + _td(_esc(d["status"]))
                + _td(_esc(d["tab"]))
                + _td(_esc(d["investing_entity"]), investing_entity_tt)
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
        irr_val = vintage_irr_map.get(vintage)
        vintage_irr_tt = "Blended IRR: pools every deal's cash flows + latest fair value for this vintage year, then runs XIRR once."
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
            + _td(_fpct(irr_val), vintage_irr_tt)
            + "</tr>"
        )

    grand = _section_subtotal(deals)
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
        "<th class='left'>Deal</th><th>Status</th><th>Tab</th><th>Investing Entity</th><th>Instrument</th>"
        "<th>Committed ($m)</th><th>Invested ($m)</th><th>Remaining ($m)</th><th>Distributions ($m)</th>"
        "<th>Carrying Value ($m)</th><th>Gain ($m)</th><th>TVPI</th><th>IRR</th>"
        "</tr></thead>"
    )
    colgroup = (
        "<colgroup>"
        "<col style='width:16%'><col style='width:6%'><col style='width:6%'><col style='width:9%'>"
        "<col style='width:9%'><col style='width:7%'><col style='width:7%'><col style='width:7%'>"
        "<col style='width:8%'><col style='width:8%'><col style='width:7%'><col style='width:5%'><col style='width:5%'>"
        "</colgroup>"
    )
    return f"<div class='table-scroll'><table id='{table_id}' class='deal-table'>{colgroup}{header}<tbody>{''.join(rows_html)}</tbody></table></div>"


def _render_nav_table(deals: pd.DataFrame, nav_info: dict[str, dict], nav_date: str) -> str:
    """NAV-focused view: Live deals grouped by asset Type (Listed/Fund/PE),
    with Exited deals kept in their own separate trailing section (mostly
    zero NAV, not worth sub-grouping by Type) - with a subtotal per group
    and a grand total. Carrying Value is always the platform's OWN already
    FX-corrected figure, never the tracker's raw NAV sheet number. Type
    comes from the tracker's own 'NAV' sheet (not captured anywhere else in
    the pipeline). Comment is the platform's OWN `assumption_note` for the
    exact valuation row used for Carrying Value (paired with its date) -
    deliberately NOT the tracker's own NAV-sheet Comment text, which can go
    stale relative to the platform's own NAV roll-forwards (e.g. showing
    last quarter's CAS after this session already rolled the figure
    forward to the latest one)."""
    rows_html = []

    def _comment_for(d: pd.Series) -> str:
        note = d.get("assumption_note", "") or ""
        vdate = d.get("valuation_date", "") or ""
        if note and vdate:
            return f"{note} (as of {vdate})"
        return note

    def _render_group(group: pd.DataFrame, type_label: str) -> None:
        for _, d in group.iterrows():
            comment = _comment_for(d)
            comment_tt = "Platform's own valuation source note for this Carrying Value - see the Live/Exited tabs for full sourcing."
            carrying_tt = "Latest carrying value, FX-corrected - same figure shown in the Live/Exited tabs."
            rows_html.append(
                "<tr>"
                + _td(_esc(d["deal_name"]), cls="left")
                + _td(_esc(d["status"]))
                + _td(_esc(d["investing_entity"]))
                + _td(_esc(d["instrument"]))
                + _td(_esc(type_label))
                + _td(_fnum(d["carrying_value"]), carrying_tt)
                + _td(_esc(comment), comment_tt, cls="left wrap")
                + "</tr>"
            )
        subtotal = group["carrying_value"].sum()
        rows_html.append(
            '<tr class="subtotal">'
            + _td("Subtotal", cls="left") + "<td></td><td></td><td></td><td></td>"
            + _td(_fnum(subtotal))
            + "<td></td>"
            + "</tr>"
        )

    live_deals = deals[deals["tab"] == "Live"]
    exited_deals = deals[deals["tab"] == "Exited"]

    type_order = ["Listed", "Fund", "PE", "Not classified"]
    live_with_type = live_deals.assign(
        _nav_type=live_deals["deal_name"].map(lambda d: nav_info.get(d, {}).get("investment_type", "Not classified"))
    )
    for inv_type in type_order:
        group = live_with_type[live_with_type["_nav_type"] == inv_type]
        if len(group) == 0:
            continue
        rows_html.append(f'<tr class="section-header"><td colspan="7">{_esc(inv_type)}</td></tr>')
        _render_group(group, inv_type)

    if len(exited_deals):
        rows_html.append('<tr class="section-header"><td colspan="7">Exited</td></tr>')
        _render_group(exited_deals, "Exited")

    grand_total = deals["carrying_value"].sum()
    rows_html.append(
        '<tr class="grand-total">'
        + _td("Grand Total", cls="left") + "<td></td><td></td><td></td><td></td>"
        + _td(_fnum(grand_total))
        + "<td></td>"
        + "</tr>"
    )

    header = (
        "<thead><tr>"
        "<th class='left'>Deal</th><th>Status</th><th>Investing Entity</th><th>Instrument</th><th>Type</th>"
        "<th>Carrying Value ($m)</th><th class='left'>Comment</th>"
        "</tr></thead>"
    )
    colgroup = (
        "<colgroup>"
        "<col style='width:18%'><col style='width:8%'><col style='width:10%'><col style='width:10%'>"
        "<col style='width:7%'><col style='width:10%'><col style='width:37%'>"
        "</colgroup>"
    )
    return f"<div class='table-scroll'><table id='table-nav' class='deal-table'>{colgroup}{header}<tbody>{''.join(rows_html)}</tbody></table></div>"


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
            + "</tr>"
        )
    header = (
        "<thead><tr><th class='left'>Display Name</th><th class='left'>Full Legal Name</th></tr></thead>"
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


def _render_monthly_diff_table(monthly_diff: pd.DataFrame | None) -> str:
    if monthly_diff is None or len(monthly_diff) == 0:
        return "<p class='muted'>No month-over-month changes detected yet. This tab populates once at least two snapshot months exist and a deal's corrected figures or Live/Exited status changes.</p>"

    rows_html = []
    for _, r in monthly_diff.iterrows():
        rows_html.append(
            "<tr>"
            + _td(_esc(r.get("change_type", "")), cls="left")
            + _td(_esc(r.get("deal_name", "")), cls="left")
            + _td(_esc(r.get("previous_month", "")))
            + _td(_esc(r.get("current_month", "")))
            + _td(_esc(r.get("previous_tab", "")))
            + _td(_esc(r.get("current_tab", "")))
            + _td(_esc(r.get("changed_metrics", "")), cls="left wrap")
            + _td(_fnum(r.get("delta_committed")))
            + _td(_fnum(r.get("delta_invested")))
            + _td(_fnum(r.get("delta_distributions")))
            + _td(_fnum(r.get("delta_carrying_value")))
            + _td(_fnum(r.get("delta_gain")))
            + _td(_fpct(r.get("delta_irr")))
            + "</tr>"
        )
    header = (
        "<thead><tr>"
        "<th class='left'>Change</th><th class='left'>Deal</th><th>Previous</th><th>Current</th>"
        "<th>Prev Tab</th><th>Current Tab</th><th class='left'>Changed Metrics</th>"
        "<th>Committed Delta ($m)</th><th>Invested Delta ($m)</th><th>Distributions Delta ($m)</th>"
        "<th>Carrying Delta ($m)</th><th>Gain Delta ($m)</th><th>IRR Delta</th>"
        "</tr></thead>"
    )
    return f"<div class='table-scroll'><table id='table-monthly-diff'>{header}<tbody>{''.join(rows_html)}</tbody></table></div>"


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
    "vTv Therapeutics Inc.'s Committed figure is shown equal to Invested (~$24.5M): against an "
    "original commitment of approximately $25M, the subscription was ultimately taken up at a "
    "discount, so somewhat less capital was deployed - the tracker records the discounted amount "
    "as both Committed and Invested.",
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


def _sparkline(values: list[float], width: int = 160, height: int = 34) -> str:
    """Compact inline-SVG line of a numeric series (NAV history)."""
    clean = [v for v in values if v is not None and not pd.isna(v)]
    if len(clean) < 2:
        return "<span class='muted'>n/a</span>"
    lo, hi = min(clean), max(clean)
    span = (hi - lo) or 1.0
    n = len(clean)
    pts = []
    for i, v in enumerate(clean):
        x = round(i / (n - 1) * (width - 4) + 2, 1)
        y = round(height - 2 - (v - lo) / span * (height - 4), 1)
        pts.append(f"{x},{y}")
    last_up = clean[-1] >= clean[0]
    stroke = "#4ade80" if last_up else "#f87171"
    return (
        f"<svg class='spark' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
        f"<polyline fill='none' stroke='{stroke}' stroke-width='1.5' points='{' '.join(pts)}'/></svg>"
    )


def _monogram(name: str) -> str:
    letters = "".join(w[0] for w in re.split(r"\s+", name.strip()) if w)[:2].upper()
    return letters or "?"


def _profile_field(label: str, value: str, pending: bool = False) -> str:
    cls = "pf-val pending" if pending else "pf-val"
    shown = value if value else "&mdash;"
    return f"<div class='pf'><div class='pf-lbl'>{_esc(label)}</div><div class='{cls}'>{shown}</div></div>"


_COMPANY_QUALIFIER = re.compile(r"\s*\((?:\d+|debt|equity|debt\s*&\s*equity)\)\s*$", re.IGNORECASE)


def _company_key(name: str) -> str:
    """Collapse deal-name qualifiers so multiple instruments in one company
    (e.g. 'Cerebras Systems Inc (2)', 'Esyasoft Holding (Debt)') consolidate.
    Preserves meaningful parentheticals (e.g. 'School Hack (AIREV Holding ...)').
    """
    s = str(name).strip()
    prev = None
    while s != prev:
        prev = s
        s = _COMPANY_QUALIFIER.sub("", s).strip()
    return s or str(name).strip()


def _load_company_facts() -> dict:
    """Analyst/grounded descriptive facts (website, description, sector, HQ,
    key people) keyed by company name, each carrying its own `source`. Missing
    file -> empty, so fields simply show as pending."""
    try:
        with open("data/source_of_truth/company_descriptive_facts.json", encoding="utf-8") as handle:
            data = json.load(handle)
        return {str(k).strip().lower(): v for k, v in data.items() if not str(k).startswith("_")}
    except Exception:  # noqa: BLE001 - optional file
        return {}


def _load_domicile_legal() -> dict:
    """Grounded domicile candidates sourced from the legal knowledge base
    (see scripts/legal_kb/export_domicile.py), keyed by company name. Each
    carries `domicile`, `domicile_source` (citation) and status='candidate'."""
    try:
        with open("data/source_of_truth/company_domicile_legal.json", encoding="utf-8") as handle:
            data = json.load(handle)
        return {str(k).strip().lower(): v for k, v in data.items() if not str(k).startswith("_")}
    except Exception:  # noqa: BLE001 - optional file
        return {}


_MGX_RE = re.compile(r"^\s*MGX\b", re.IGNORECASE)
_FUND_RE = re.compile(r"\bFund\b|\bL\.?\s*P\.?\b|\bSCSp\b|\bGP\s+Com\b", re.IGNORECASE)


def _segment_of(name: str) -> tuple[str, str]:
    """Classify a company into (segment, subgroup) for the left-rail grouping:
    ('Equity',''), ('Funds','') or ('Funds','MGX'). MGX vehicles are grouped
    under their own sub-category within Funds."""
    n = str(name or "").strip()
    if _MGX_RE.match(n):
        return ("Funds", "MGX")
    if _FUND_RE.search(n):
        return ("Funds", "")
    return ("Equity", "")


def _consolidate_companies(deals: pd.DataFrame) -> pd.DataFrame:
    """One row per company: sums economics across all our instruments in it
    (equity + debt + follow-ons) and records the member deal names."""
    def num(v) -> float:
        n = pd.to_numeric(v, errors="coerce")
        return 0.0 if pd.isna(n) else float(n)

    groups: dict[str, list] = {}
    seen: list[str] = []
    for _, d in deals.iterrows():
        key = _company_key(d.get("deal_name", ""))
        if key not in groups:
            groups[key] = []
            seen.append(key)
        groups[key].append(d)

    def joined(members: list, field: str) -> str:
        vals: list[str] = []
        for m in members:
            v = str(m.get(field, "") or "").strip()
            if v and v not in vals:
                vals.append(v)
        return " + ".join(vals)

    rows = []
    for key in seen:
        members = groups[key]
        tabs = [str(m.get("tab", "")) for m in members]
        tab = "Live" if "Live" in tabs else ("Exited" if "Exited" in tabs else (tabs[0] if tabs else ""))
        invested = sum(num(m.get("invested")) for m in members)
        distributions = sum(num(m.get("distributions")) for m in members)
        carrying = sum(num(m.get("carrying_value")) for m in members)
        vintages = [str(m.get("vintage", "")).strip() for m in members if str(m.get("vintage", "")).strip()]
        rows.append({
            "deal_name": key,
            "tab": tab,
            "section": str(members[0].get("section", "")),
            "investing_entity": joined(members, "investing_entity"),
            "instrument": joined(members, "instrument"),
            "geography": joined(members, "geography"),
            "sector": joined(members, "sector"),
            "vintage": min(vintages) if vintages else "",
            "committed": sum(num(m.get("committed")) for m in members),
            "invested": invested,
            "distributions": distributions,
            "carrying_value": carrying,
            "gain": sum(num(m.get("gain")) for m in members),
            "tvpi": ((distributions + carrying) / invested) if invested else None,
            "irr": members[0].get("irr") if len(members) == 1 else None,
            "_members": [str(m.get("deal_name", "")) for m in members],
            "_multi": len(members) > 1,
        })
    return pd.DataFrame(rows)


def _cashflow_cum_chart(rows: list[dict], width: int = 360, height: int = 100) -> str:
    """Cumulative net cashflow ($m) over time, baselined at $0 a week before
    the first flow so the investment date reads clearly. Light-theme colours."""
    dated = []
    for r in rows:
        d = pd.to_datetime(r.get("date"), errors="coerce")
        a = pd.to_numeric(r.get("amt"), errors="coerce")
        if pd.notna(d) and pd.notna(a):
            dated.append((d, float(a)))
    if not dated:
        return "<span class='muted' style='font-size:12px'>No dated cashflows.</span>"
    dated.sort(key=lambda x: x[0])
    series = [(dated[0][0] - pd.Timedelta(days=7), 0.0)]
    cum = 0.0
    for d, a in dated:
        cum += a / 1_000_000
        series.append((d, cum))

    xs = [d.toordinal() for d, _ in series]
    ys = [v for _, v in series]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys + [0.0]), max(ys + [0.0])
    xr = (x1 - x0) or 1
    yr = (y1 - y0) or 1

    def X(x): return round((x - x0) / xr * (width - 44) + 38, 1)

    def Y(y): return round(height - 20 - (y - y0) / yr * (height - 30), 1)

    poly = " ".join(f"{X(x)},{Y(y)}" for x, y in zip(xs, ys))
    zero_y = Y(0.0)
    dots = "".join(
        f"<circle cx='{X(d.toordinal())}' cy='{Y(v)}' r='2.4' "
        f"fill='{'#dc2626' if v < series[i - 1][1] else '#16a34a'}'/>"
        for i, (d, v) in enumerate(series) if i > 0)
    first_lbl = series[1][0].strftime("%d %b %y")
    last_lbl = series[-1][0].strftime("%d %b %y")
    return (
        f"<svg class='cfchart' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
        f"<line x1='38' y1='{zero_y}' x2='{width - 6}' y2='{zero_y}' stroke='#cbd5e1' stroke-dasharray='3 3'/>"
        f"<text x='4' y='{zero_y + 3}' font-size='9' fill='#94a3b8'>$0</text>"
        f"<polyline fill='none' stroke='#2563eb' stroke-width='1.6' points='{poly}'/>"
        f"{dots}"
        f"<text x='38' y='{height - 4}' font-size='9' fill='#94a3b8'>{first_lbl}</text>"
        f"<text x='{width - 6}' y='{height - 4}' font-size='9' fill='#94a3b8' text-anchor='end'>{last_lbl}</text>"
        f"</svg>")


def _bar_chart(pairs: list[tuple], width: int = 300, height: int = 110,
               pos: str = "#6366f1", neg: str = "#dc2626", unit: str = "$m") -> str:
    """Small zero-based inline-SVG bar chart. Bars rise/fall from a $0 baseline,
    so NAV (all positive) and signed cashflows read on the same convention."""
    vals = [(l, float(v)) for l, v in pairs if v is not None and not pd.isna(v)]
    if not vals:
        return "<span class='muted' style='font-size:12px'>n/a</span>"
    values = [v for _, v in vals]
    ymax = max(values + [0.0])
    ymin = min(values + [0.0])
    yr = (ymax - ymin) or 1.0
    pad_t, pad_b, pad_l, pad_r = 8, 18, 8, 8
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(vals)
    slot = plot_w / n
    bar_w = min(slot * 0.62, 30)

    def Y(v: float) -> float:
        return pad_t + (ymax - v) / yr * plot_h

    zero_y = Y(0.0)

    def _lab(v: float) -> str:
        av = abs(v)
        if av >= 10:
            return f"{v:.0f}"
        if av >= 1:
            return f"{v:.1f}"
        return f"{v:.2f}"

    bars = []
    for i, (lbl, v) in enumerate(vals):
        cx = pad_l + slot * (i + 0.5)
        top = min(Y(v), zero_y)
        h = max(1.2, abs(Y(v) - zero_y))
        color = pos if v >= 0 else neg
        lbl_y = (top - 2.5) if v >= 0 else (Y(v) + 8)
        bars.append(
            f"<rect x='{cx - bar_w / 2:.1f}' y='{top:.1f}' width='{bar_w:.1f}' height='{h:.1f}' "
            f"rx='1.5' fill='{color}'><title>{_esc(str(lbl))}: {v:.2f} {unit}</title></rect>"
            f"<text x='{cx:.1f}' y='{lbl_y:.1f}' font-size='7.5' fill='#64748b' text-anchor='middle'>{_lab(v)}</text>")
    first_lbl = _esc(str(vals[0][0]))
    last_lbl = _esc(str(vals[-1][0]))
    return (
        f"<svg class='barchart' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
        f"<line x1='{pad_l}' y1='{zero_y:.1f}' x2='{width - pad_r}' y2='{zero_y:.1f}' stroke='#cbd5e1'/>"
        f"<text x='{pad_l + 2}' y='{zero_y - 2:.1f}' font-size='8' fill='#94a3b8'>$0</text>"
        f"{''.join(bars)}"
        f"<text x='{pad_l}' y='{height - 5}' font-size='9' fill='#94a3b8'>{first_lbl}</text>"
        f"<text x='{width - pad_r}' y='{height - 5}' font-size='9' fill='#94a3b8' text-anchor='end'>{last_lbl}</text>"
        f"</svg>")


def _cashflow_bar_chart(rows: list[dict], width: int = 300, height: int = 110) -> str:
    """Per-event cashflow bars ($m) from a $0 baseline - deployments below,
    distributions above - so the investment timing reads at a glance."""
    pairs = []
    for r in rows:
        d = pd.to_datetime(r.get("date"), errors="coerce")
        a = pd.to_numeric(r.get("amt"), errors="coerce")
        if pd.notna(d) and pd.notna(a):
            pairs.append((d.strftime("%b'%y"), float(a) / 1_000_000))
    return _bar_chart(pairs, width, height, pos="#16a34a", neg="#dc2626", unit="$m")


def _cashflow_direction_chart(rows: list[dict], width: int = 320, height: int = 130) -> str:
    """Per-event cashflow magnitude ($m) drawn upward from a $0 baseline:
    cash OUT (deployments, red) and cash IN (distributions, blue) both rise as
    positive bars, so relative sizes read directly side-by-side."""
    events = []
    for r in rows:
        d = pd.to_datetime(r.get("date"), errors="coerce")
        a = pd.to_numeric(r.get("amt"), errors="coerce")
        if pd.notna(d) and pd.notna(a):
            events.append((d.strftime("%b'%y"), float(a) / 1_000_000))
    if not events:
        return "<span class='muted' style='font-size:12px'>No dated cashflows.</span>"
    ymax = max((abs(v) for _, v in events), default=1.0) or 1.0
    pad_t, pad_b, pad_l, pad_r = 10, 18, 8, 8
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(events)
    slot = plot_w / n
    bar_w = min(slot * 0.62, 30)
    zero_y = pad_t + plot_h

    def _lab(v: float) -> str:
        av = abs(v)
        return f"{av:.0f}" if av >= 10 else (f"{av:.1f}" if av >= 1 else f"{av:.2f}")

    bars = []
    for i, (lbl, v) in enumerate(events):
        cx = pad_l + slot * (i + 0.5)
        h = max(1.2, abs(v) / ymax * plot_h)
        top = zero_y - h
        outflow = v < 0
        color = "#dc2626" if outflow else "#2563eb"
        kind = "Cash out" if outflow else "Cash in"
        bars.append(
            f"<rect x='{cx - bar_w / 2:.1f}' y='{top:.1f}' width='{bar_w:.1f}' height='{h:.1f}' "
            f"rx='1.5' fill='{color}'><title>{_esc(lbl)}: {kind} {abs(v):.2f} $m</title></rect>"
            f"<text x='{cx:.1f}' y='{top - 2.5:.1f}' font-size='7.5' fill='#64748b' "
            f"text-anchor='middle'>{_lab(v)}</text>")
    first_lbl = _esc(events[0][0])
    last_lbl = _esc(events[-1][0])
    return (
        f"<svg class='barchart' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
        f"<line x1='{pad_l}' y1='{zero_y:.1f}' x2='{width - pad_r}' y2='{zero_y:.1f}' stroke='#cbd5e1'/>"
        f"<text x='{pad_l + 2}' y='{zero_y - 2:.1f}' font-size='8' fill='#94a3b8'>$0</text>"
        f"{''.join(bars)}"
        f"<text x='{pad_l}' y='{height - 5}' font-size='9' fill='#94a3b8'>{first_lbl}</text>"
        f"<text x='{width - pad_r}' y='{height - 5}' font-size='9' fill='#94a3b8' text-anchor='end'>{last_lbl}</text>"
        f"</svg>")


def _render_company_profiles(
    deals: pd.DataFrame,
    ownership: pd.DataFrame,
    per_company_nav: pd.DataFrame,
    cashflow: pd.DataFrame,
    as_of_date: str,
) -> str:
    """Master-detail company view: a left rail of investment names (Live then
    Exited); clicking a name opens that company's one-pager card.

    NAV history is read per company from the prepared monthly tracker
    workbooks; cashflows are the historical dated transactions. Domicile,
    website, logo, description, sector, HQ and key people remain source-
    grounded placeholders until populated and analyst-confirmed.
    """
    own_by_deal: dict[str, dict] = {}
    if ownership is not None and len(ownership):
        for _, r in ownership.iterrows():
            own_by_deal[str(r.get("deal_name", "")).strip().lower()] = r.to_dict()

    # Per-company NAV points from the monthly trackers (keyed by deal name,
    # so consolidated companies can sum their instruments' carrying values).
    nav_by_deal: dict[str, list[tuple[int, str, float]]] = {}
    if per_company_nav is not None and len(per_company_nav):
        pcn = per_company_nav.dropna(subset=["deal_name"]).copy()
        for _, r in pcn.iterrows():
            k = str(r.get("deal_name", "")).strip().lower()
            nav_by_deal.setdefault(k, []).append(
                (int(r.get("month_index", 0)), str(r.get("month", "")),
                 pd.to_numeric(r.get("carrying_value"), errors="coerce")))

    def nav_series_for(member_keys: list[str]) -> list[tuple[str, float]]:
        bucket: dict[int, list] = {}
        for mk in member_keys:
            for mi, lbl, cv in nav_by_deal.get(mk, []):
                if pd.notna(cv):
                    if mi not in bucket:
                        bucket[mi] = [lbl, 0.0]
                    bucket[mi][1] += float(cv)
        return [(bucket[mi][0], bucket[mi][1]) for mi in sorted(bucket)]

    # Per-company cashflow history (historical dated transactions).
    amount_col = "amount_usd" if (cashflow is not None and "amount_usd" in cashflow.columns) else "amount"
    cf_by_deal: dict[str, list[dict]] = {}
    if cashflow is not None and len(cashflow) and "investment_id" in cashflow.columns:
        cf = cashflow.copy()
        for inv_id, grp in cf.groupby("investment_id"):
            cf_by_deal[str(inv_id).strip().lower()] = [
                {"date": str(r.get("flow_date", "")), "type": str(r.get("flow_type", "")),
                 "amt": pd.to_numeric(r.get(amount_col), errors="coerce")}
                for _, r in grp.iterrows()
            ]

    def _date_key(r: dict) -> int:
        d = pd.to_datetime(r.get("date"), errors="coerce")
        return d.toordinal() if pd.notna(d) else 0

    def cf_rows_for(member_keys: list[str]) -> list[dict]:
        rows: list[dict] = []
        for mk in member_keys:
            rows.extend(cf_by_deal.get(mk, []))
        rows.sort(key=_date_key)
        return rows

    def cashflow_table(rows: list[dict]) -> str:
        if not rows:
            return "<p class='muted' style='font-size:12px'>No dated cashflows recorded for this company.</p>"
        body = []
        total = 0.0
        for r in rows:
            amt = r["amt"]
            amt_m = (amt / 1_000_000) if pd.notna(amt) else None
            if amt_m is not None:
                total += amt_m
            cls = "cf-out" if (amt_m is not None and amt_m < 0) else "cf-in"
            body.append(
                f"<tr><td>{_esc(r['date'])}</td><td>{_esc(r['type'])}</td>"
                f"<td class='{cls}' style='text-align:right'>{_fnum(amt_m)}</td></tr>")
        return (
            "<table class='cf-table'><thead><tr><th style='text-align:left'>Date</th>"
            "<th style='text-align:left'>Type</th><th style='text-align:right'>USD $m</th></tr></thead>"
            f"<tbody>{''.join(body)}</tbody>"
            f"<tfoot><tr><td colspan='2'>Net</td><td style='text-align:right'>{_fnum(total)}</td></tr></tfoot></table>")

    facts = _load_company_facts()
    domicile_legal = _load_domicile_legal()
    order = _consolidate_companies(deals)
    segs = list(order["deal_name"].map(_segment_of))
    order["_seg"] = [s[0] for s in segs]
    order["_subgroup"] = [s[1] for s in segs]
    order["_seg_order"] = order["_seg"].map({"Equity": 0, "Funds": 1}).fillna(2)
    order["_sub_order"] = order["_subgroup"].map(lambda s: 1 if s == "MGX" else 0)
    order["_tab_order"] = order["tab"].map({"Live": 0, "Exited": 1}).fillna(2)
    order = order.sort_values(
        ["_seg_order", "_sub_order", "_tab_order", "deal_name"], kind="stable").reset_index(drop=True)

    def _desc_field(label: str, fact: dict, fk: str, is_link: bool = False) -> str:
        v = str(fact.get(fk, "") or "").strip() if fact else ""
        if v:
            src = str(fact.get("source", "") or "").strip()
            tag = f" <span class='src'>({_esc(src)})</span>" if src else ""
            shown = f"<a href='{_esc(v)}' target='_blank' rel='noopener'>{_esc(v)}</a>" if is_link else _esc(v)
            return _profile_field(label, shown + tag)
        return _profile_field(label, "pending &mdash; from website/docs", pending=True)

    def _grounded_field(label: str, tracker_val, fact: dict, fk: str) -> str:
        """Prefer the tracker's own grounded value; fall back to the facts file."""
        tv = str(tracker_val or "").strip()
        if tv:
            return _profile_field(label, _esc(tv) + " <span class='src'>(tracker)</span>")
        return _desc_field(label, fact, fk)

    rail: list[str] = []
    cards: list[str] = []
    last_seg = None
    last_sub = None
    for idx, d in order.iterrows():
        name = str(d.get("deal_name", ""))
        key = name.strip().lower()
        member_keys = [str(m).strip().lower() for m in (d.get("_members") or [name])]
        status = str(d.get("tab", ""))
        seg = str(d.get("_seg", ""))
        sub = str(d.get("_subgroup", "") or "")
        if seg != last_seg:
            rail.append(f"<div class='rail-group'>{_esc(seg)}</div>")
            last_seg = seg
            last_sub = None
        if sub and sub != last_sub:
            rail.append(f"<div class='rail-subgroup'>{_esc(sub)}</div>")
            last_sub = sub
        dot = "live" if status == "Live" else "exited"
        active = " active" if idx == 0 else ""
        rail.append(
            f"<button class='rail-item{active}' data-company='{idx}'>"
            f"<span class='rdot {dot}'></span><span class='rname'>{_esc(name)}</span></button>")

        own = own_by_deal.get(key, {})
        if not own:
            for mk in member_keys:
                if mk in own_by_deal:
                    own = own_by_deal[mk]
                    break
        jurisdiction = str(own.get("jurisdiction", "") or "")
        country = str(own.get("country", "") or "")
        own_pct = own.get("ownership_pct")
        status_cls = "live" if status == "Live" else "exited"
        fact = {**facts.get(key, {}), **(domicile_legal.get(key) or {})}

        series = nav_series_for(member_keys)
        nav_chart = _bar_chart([(m, v) for m, v in series], width=320, pos="#2F6B45", unit="$m")
        nav_latest = _fnum(series[-1][1]) if series else _fnum(d.get("carrying_value"))
        nav_range = f"{series[0][0]} &rarr; {series[-1][0]}" if len(series) >= 2 else (as_of_date or "")

        # Domicile: grounded legal-doc value if present, else tracker (flagged).
        dom_fact = str(fact.get("domicile", "") or "").strip() if fact else ""
        if dom_fact:
            dom_src = str(fact.get("domicile_source", "legal doc") or "legal doc")
            domicile_field = _profile_field("Domicile / Jurisdiction", f"{_esc(dom_fact)} <span class='src'>({_esc(dom_src)})</span>")
        elif jurisdiction:
            domicile_field = _profile_field("Domicile / Jurisdiction", _esc(jurisdiction) + " <span class='src'>(tracker &mdash; pending legal-doc validation)</span>")
        else:
            domicile_field = _profile_field("Domicile / Jurisdiction", "pending &mdash; from legal docs", pending=True)

        identity = "".join([
            domicile_field,
            _profile_field("Country", _esc(country)),
            _profile_field("Ownership %", _fpct(own_pct) if own_pct is not None else ""),
            _profile_field("Investing Entity", _esc(str(d.get("investing_entity", "")))),
            _profile_field("Instrument", _esc(str(d.get("instrument", "")))),
            _profile_field("Vintage", _esc(str(d.get("vintage", "")))),
            _desc_field("Website", fact, "website", is_link=True),
            _grounded_field("Sector", d.get("sector"), fact, "sector"),
            _grounded_field("Geography", d.get("geography"), fact, "hq"),
        ])
        econ = "".join([
            _profile_field("Committed ($m)", _fnum(d.get("committed"))),
            _profile_field("Invested ($m)", _fnum(d.get("invested"))),
            _profile_field("Distributions ($m)", _fnum(d.get("distributions"))),
            _profile_field("Carrying Value ($m)", _fnum(d.get("carrying_value"))),
            _profile_field("Gain ($m)", _fnum(d.get("gain"))),
            _profile_field("TVPI", _fx(d.get("tvpi"))),
            _profile_field("IRR", _fpct(d.get("irr")) if d.get("irr") is not None else ""),
        ])

        desc_v = str(fact.get("description", "") or "").strip() if fact else ""
        if desc_v:
            desc_src = str(fact.get("source", "") or "").strip()
            desc_html = f"<div class='pc-desc'>{_esc(desc_v)} <span class='src'>({_esc(desc_src)})</span></div>"
        else:
            desc_html = "<div class='pc-desc pending'>Business description pending &mdash; to be sourced from the company website / legal docs and analyst-confirmed.</div>"

        consol = ""
        if d.get("_multi"):
            consol = f"<div class='consol-note'>Consolidated across {len(member_keys)} instruments: {_esc(' + '.join(d.get('_members', [])))}</div>"

        cf_rows = cf_rows_for(member_keys)
        hidden = "" if idx == 0 else " hidden"
        cards.append(
            f"<div class='profile-card{hidden}' data-card='{idx}'>"
            f"<div class='pc-head'>"
            f"<div class='pc-logo' title='Logo pending (from website)'>{_esc(_monogram(name))}</div>"
            f"<div class='pc-title'><h3>{_esc(name)}</h3>"
            f"<div class='pc-sub'><span class='badge {status_cls}'>{_esc(status)}</span> "
            f"{_esc(str(d.get('instrument','')))} &middot; Vintage {_esc(str(d.get('vintage','')))}</div></div>"
            f"</div>"
            f"{desc_html}{consol}"
            f"<div class='pc-section-label'>Company</div>"
            f"<div class='pf-grid'>{identity}</div>"
            f"<div class='pc-section-label'>Our Investment</div>"
            f"<div class='pf-grid'>{econ}</div>"
            f"<div class='pc-charts-row'>"
            f"<div class='pc-chart-col'>"
            f"<div class='pc-section-label'>NAV / Carrying Value <span class='muted' style='text-transform:none;letter-spacing:0'>(monthly trackers)</span></div>"
            f"<div class='pc-chart'>{nav_chart}</div>"
            f"<div class='pc-nav-meta'>Latest {nav_latest} $m<span class='muted'> &nbsp;({nav_range})</span></div>"
            f"</div>"
            f"<div class='pc-chart-col'>"
            f"<div class='pc-section-label'>Cashflows <span class='muted' style='text-transform:none;letter-spacing:0'>(Treasury)</span></div>"
            f"<div class='pc-chart'>{_cashflow_direction_chart(cf_rows)}</div>"
            f"<div class='cf-legend'>"
            f"<span class='cf-key'><span class='cf-sw out'></span>Cash out (deployed)</span>"
            f"<span class='cf-key'><span class='cf-sw in'></span>Cash in (returned)</span></div>"
            f"</div>"
            f"</div>"
            f"</div>"
        )

    style = (
        "<style>"
        ".profiles-layout{display:grid;grid-template-columns:300px 1fr;gap:18px;align-items:start;}"
        ".profiles-rail{position:sticky;top:8px;max-height:calc(100vh - 170px);overflow:auto;padding-right:6px;}"
        ".rail-group{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:14px 4px 6px;}"
        ".rail-subgroup{font-size:10.5px;text-transform:uppercase;letter-spacing:.03em;color:var(--accent);"
        "margin:8px 4px 4px 12px;padding-left:8px;border-left:2px solid var(--accent);opacity:.85;}"
        ".rail-item{display:flex;align-items:center;gap:8px;width:100%;text-align:left;background:var(--panel);"
        "border:1px solid var(--border);color:var(--text);padding:8px 11px;border-radius:7px;margin:5px 0;"
        "cursor:pointer;font-size:13px;overflow:hidden;}"
        ".rail-item:hover{border-color:var(--accent);}"
        ".rail-item.active{border-color:var(--accent);background:var(--sub-bg);color:var(--accent);}"
        ".rname{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}"
        ".rdot{width:7px;height:7px;border-radius:50%;flex:0 0 auto;}"
        ".rdot.live{background:var(--green);}.rdot.exited{background:var(--red);}"
        ".profiles-detail .profile-card{background:linear-gradient(180deg,#ffffff 0%,#eef2f7 100%);color:#0f172a;"
        "border:1px solid rgba(148,163,184,.35);border-radius:14px;padding:20px 22px;max-width:860px;"
        "box-shadow:0 14px 36px rgba(2,6,23,.55),inset 0 1px 0 rgba(255,255,255,.75);}"
        ".profile-card.hidden{display:none;}"
        ".pc-head{display:flex;gap:12px;align-items:center;}"
        ".profiles-detail .pc-logo{width:48px;height:48px;border-radius:10px;"
        "background:linear-gradient(135deg,#2F6B45,#5a9e78);color:#fff;"
        "display:flex;align-items:center;justify-content:center;font-weight:700;font-size:16px;flex:0 0 auto;"
        "box-shadow:0 4px 12px rgba(79,70,229,.4);}"
        ".profiles-detail .pc-title h3{margin:0;font-size:17px;color:#0f172a;}"
        ".profiles-detail .pc-sub{color:#64748b;font-size:12px;margin-top:2px;}"
        ".badge{padding:1px 8px;border-radius:10px;font-size:11px;}"
        ".badge.live{background:#dcfce7;color:#166534;}.badge.exited{background:#fee2e2;color:#991b1b;}"
        ".profiles-detail .pc-desc{font-size:12.5px;margin:10px 0;color:#334155;}"
        ".profiles-detail .pc-section-label{font-size:11px;text-transform:uppercase;letter-spacing:.04em;"
        "color:#64748b;margin:14px 0 6px;border-top:1px solid #e2e8f0;padding-top:8px;}"
        ".pf-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px 18px;}"
        ".profiles-detail .pf-lbl{color:#64748b;font-size:11px;}"
        ".profiles-detail .pf-val{font-size:13px;color:#0f172a;}"
        ".profiles-detail .pf-val a{color:#2563eb;}"
        ".profiles-detail .pf-val.pending,.profiles-detail .pc-desc.pending{color:#b45309;font-style:italic;}"
        ".profiles-detail .pf-val .src,.profiles-detail .pc-desc .src{color:#94a3b8;font-size:10px;font-style:italic;}"
        ".profiles-detail .muted{color:#94a3b8;}"
        ".consol-note{font-size:11px;color:#64748b;font-style:italic;margin:2px 0 0;}"
        ".pc-nav-meta{font-size:12px;color:#334155;margin-top:2px;}"
        ".pc-chart{margin:2px 0 4px;}"
        ".pc-charts-row{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start;}"
        ".pc-chart-col{min-width:0;}"
        ".cf-legend{display:flex;gap:14px;font-size:10.5px;color:#64748b;margin-top:2px;}"
        ".cf-key{display:flex;align-items:center;gap:5px;}"
        ".cf-sw{width:10px;height:10px;border-radius:2px;display:inline-block;}"
        ".cf-sw.out{background:#dc2626;}.cf-sw.in{background:#2563eb;}"
        ".barchart{background:#f1f5f9;border:1px solid #e2e8f0;border-radius:8px;max-width:100%;}"
        ".cf-table{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px;}"
        ".profiles-detail .cf-table th,.profiles-detail .cf-table td{padding:3px 6px;border-bottom:1px solid #e2e8f0;color:#334155;}"
        ".profiles-detail .cf-table tfoot td{font-weight:600;border-top:1px solid #cbd5e1;color:#0f172a;}"
        ".cf-in{color:#16a34a;}.cf-out{color:#dc2626;}"
        "</style>"
    )
    script = (
        "<script>(function(){"
        "var rail=document.querySelectorAll('#companies .rail-item');"
        "var cards=document.querySelectorAll('#companies .profile-card');"
        "function show(i){rail.forEach(function(b){b.classList.toggle('active',b.dataset.company===i);});"
        "cards.forEach(function(c){c.classList.toggle('hidden',c.dataset.card!==i);});}"
        "rail.forEach(function(b){b.addEventListener('click',function(){show(b.dataset.company);});});"
        "})();</script>"
    )
    if not cards:
        return "<p class='muted'>No company profiles available.</p>"
    return (style
            + "<div class='profiles-layout'>"
            + f"<div class='profiles-rail'>{''.join(rail)}</div>"
            + f"<div class='profiles-detail'>{''.join(cards)}</div>"
            + "</div>" + script)


def build_tracker_style_dashboard_html(
    deals: pd.DataFrame,
    section_irr: pd.DataFrame,
    vintage_irr: pd.DataFrame,
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
    nav_info: dict[str, dict] | None = None,
    nav_date: str = "",
    scan_report: dict | None = None,
    as_of_date: str | None = None,
    monthly_diff: pd.DataFrame | None = None,
    snapshot_history: pd.DataFrame | None = None,
    per_company_nav: pd.DataFrame | None = None,
) -> str:
    as_of_date = as_of_date or date.today().isoformat()

    live_grand = _section_subtotal(deals[deals["tab"] == "Live"])
    exited_grand = _section_subtotal(deals[deals["tab"] == "Exited"])

    live_table = _render_deal_table(deals, section_irr, "Live", as_of_date, deal_entity_map, citation_lookup)
    exited_table = _render_deal_table(deals, section_irr, "Exited", as_of_date, deal_entity_map, citation_lookup)
    vintage_table = _render_vintage_table(deals, vintage_irr, as_of_date, deal_entity_map, citation_lookup)
    nav_table = _render_nav_table(deals, nav_info or {}, nav_date)
    cashflow_table = _render_cashflow_table(cashflow)
    ownership_table = _render_ownership_table(ownership)
    log_table = _render_log_table(change_log)
    issues_table = _render_issues_table(issues)
    monthly_diff_table = _render_monthly_diff_table(monthly_diff)
    glossary_table = _render_glossary_table(glossary)
    company_profiles = _render_company_profiles(
        deals, ownership,
        per_company_nav if per_company_nav is not None else pd.DataFrame(),
        cashflow, as_of_date)
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

    _asd = pd.to_datetime(as_of_date, errors="coerce")
    as_of_short = _asd.strftime("%b'%y") if pd.notna(_asd) else str(as_of_date)
    gen_short = date.today().strftime("%d%b%y")
    return _HTML_TEMPLATE.format(
        as_of_date=as_of_date,
        generated=date.today().isoformat(),
        as_of_short=as_of_short,
        gen_short=gen_short,
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
        vintage_table=vintage_table,
        nav_table=nav_table,
        nav_date=nav_date or as_of_date,
        cashflow_table=cashflow_table,
        ownership_table=ownership_table,
        log_table=log_table,
        issues_table=issues_table,
        monthly_diff_table=monthly_diff_table,
        glossary_table=glossary_table,
        company_profiles=company_profiles,
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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  :root {{
    --bg: #F4F1E7; --panel: #FFFFFF; --text: #22302A; --muted: #6b746a;
    --accent: #2F6B45; --green: #2F6B45; --red: #b3253a; --border: #E4E0D0; --sub-bg: #EFEBDF;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: "EB Garamond", Garamond, Georgia, "Times New Roman", serif; background: var(--bg); color: var(--text); }}
  header {{ padding: 14px 18px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }}
  header .report-asof {{ font-size: 15px; color: var(--text); }}
  header .report-asof .gen {{ color: var(--muted); font-size: 12px; font-weight: 400; font-style: italic; }}
  nav {{ display: flex; gap: 6px; padding: 10px 18px; border-bottom: 1px solid var(--border); overflow-x: auto; }}
  nav button {{ background: rgba(47,107,69,0.06); border: 1px solid var(--border); color: var(--muted); padding: 8px 14px; cursor: pointer; font-size: 13px; border-radius: 8px; white-space: nowrap; }}
  nav button.active {{ background: var(--accent); color: #ffffff; border-color: var(--accent); }}
  main {{ padding: 18px 14px; }}
  .tab {{ display: none; }}
  .tab.active {{ display: block; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 22px; }}
  .kpi-card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }}
  .kpi-card .label {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.03em; }}
  .kpi-card .value {{ font-size: 20px; font-weight: 600; margin-top: 6px; }}
  .panel {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px; margin-bottom: 16px; }}
  .table-scroll {{ overflow-x: auto; }}
  .panel-head {{ display: flex; justify-content: space-between; align-items: center; gap: 14px; margin-bottom: 12px; }}
  .panel h2 {{ font-size: 13px; margin: 0; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; }}
    .table-filter-bar {{ display: flex; justify-content: flex-end; align-items: center; gap: 10px; margin: 0 0 10px; }}
    .table-filter-bar .row-count {{ color: var(--muted); font-size: 12px; }}
    th .th-label {{ display: block; margin-bottom: 5px; }}
    th .column-filter {{ width: 100%; min-width: 72px; background: #FFFFFF; border: 1px solid var(--border); color: var(--text); border-radius: 5px; padding: 4px 6px; font-size: 11px; }}
    th .column-filter:focus {{ outline: none; border-color: var(--accent); }}
  .dl-btn {{ background: var(--sub-bg); border: 1px solid var(--border); color: var(--accent); border-radius: 6px; padding: 5px 12px; font-size: 11px; cursor: pointer; }}
  .dl-btn:hover {{ background: var(--border); }}
  table {{ width: 100%; min-width: 1100px; border-collapse: collapse; font-size: 12.5px; }}
  table.deal-table {{ table-layout: fixed; }}
  th, td {{ padding: 6px 9px; text-align: right; vertical-align: middle; border-bottom: 1px solid var(--border); white-space: nowrap; }}
  table.deal-table tbody tr:not(.section-header):not(.subtotal):not(.grand-total) td {{ background: #FBFAF4; }}
  table.deal-table tbody tr:not(.section-header):not(.subtotal):not(.grand-total):nth-child(even) td {{ background: #ECE7D8; }}
  table.deal-table th, table.deal-table td {{ overflow: hidden; text-overflow: ellipsis; }}
  th.left, td.left {{ text-align: left; white-space: nowrap; min-width: 220px; }}
  td.wrap {{ white-space: normal; max-width: 420px; min-width: 260px; vertical-align: middle; }}
  th {{ color: var(--muted); font-weight: 500; vertical-align: middle; }}
  tr.section-header td {{ background: #E7EFE8; font-weight: 600; color: var(--accent); vertical-align: middle; text-align: left; border-top: 14px solid var(--bg); }}
  tr.subtotal td {{ background: #E1D8C0; font-weight: 600; border-top: 1px solid var(--border); vertical-align: middle; }}
  tr.grand-total td {{ background: #DCE7DE; font-weight: 700; border-top: 2px solid var(--accent); vertical-align: middle; }}
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
  td.tt {{ border-bottom: 1px solid var(--border); }}
  #jsTooltip {{
    display: none; position: fixed; background: #FFFFFF; color: var(--text);
    border: 1px solid var(--accent); padding: 8px 10px; border-radius: 6px;
    font-size: 11.5px; white-space: normal; max-width: 320px; text-align: left;
    line-height: 1.4; z-index: 1000; box-shadow: 0 4px 14px rgba(34,48,42,0.18);
    pointer-events: none;
  }}

  #updateModal {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.55); z-index: 100; align-items: center; justify-content: center; }}
  #updateModal .box {{ background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 24px; max-width: 520px; }}
  #updateModal .box h3 {{ margin-top: 0; }}
  #updateModal button.close {{ margin-top: 14px; background: var(--accent); border: none; color: #ffffff; font-weight: 600; padding: 8px 16px; border-radius: 6px; cursor: pointer; }}
</style>
</head>
<body>

<nav>
  <button class="tab-btn active" data-tab="live">Live Investments</button>
  <button class="tab-btn" data-tab="exited">Exited Investments</button>
  <button class="tab-btn" data-tab="vintage">Vintage</button>
  <button class="tab-btn" data-tab="nav">NAV</button>
  <button class="tab-btn" data-tab="cashflows">Cashflows</button>
  <button class="tab-btn" data-tab="ownership">Ownership &amp; Domiciliation</button>
  <button class="tab-btn" data-tab="log">Log</button>
  <button class="tab-btn" data-tab="glossary">Glossary</button>
</nav>

<header>
  <div class="report-asof"><strong>As of {as_of_short}</strong><span class="gen"> &middot; generated {gen_short}</span></div>
  <div class="top-actions">
    <button id="btnUpdate">Update</button>
  </div>
</header>

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
      <div class="panel-head"><button class="dl-btn" onclick="downloadCSV('table-live','live_investments.csv')">Download CSV</button></div>
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

  <section id="companies" class="tab">
    <div class="panel">
      <div class="panel-head"><h2>Company Profiles &mdash; PitchBook-style one-pagers</h2></div>
      <p class="muted">One card per investment. Financials, sector, geography, domicile, ownership and NAV/carrying-value history are the platform's own grounded figures. Website, logo, description and key people are marked <i>pending</i> until sourced (from the company website / grounded document extraction) and analyst-confirmed.</p>
      {company_profiles}
    </div>
  </section>

  <section id="vintage" class="tab">
    <div class="panel">
      <div class="panel-head"><h2>All Investments, by Vintage Year</h2><button class="dl-btn" onclick="downloadCSV('table-vintage','vintage.csv')">Download CSV</button></div>
      {vintage_table}
    </div>
  </section>

  <section id="nav" class="tab">
    <div class="panel">
      <div class="panel-head"><h2>NAV as of {nav_date}, by Type</h2><button class="dl-btn" onclick="downloadCSV('table-nav','nav.csv')">Download CSV</button></div>
      <p class="muted">Type (Listed/Fund/PE) is sourced from the tracker's own "NAV" sheet. Carrying Value and Comment (source/last-revised note) are the platform's OWN figures - Carrying Value is the same FX-corrected number shown in the Live/Exited tabs, and Comment is that same valuation row's own source note (not the tracker's NAV-sheet Comment text, which can go stale after this platform rolls a NAV forward). Live positions are grouped by Type; Exited positions are kept in their own separate section below.</p>
      {nav_table}
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

    <section id="monthly-diff" class="tab">
        <div class="panel">
            <div class="panel-head"><h2>Latest Month-over-Month Changes</h2><button class="dl-btn" onclick="downloadCSV('table-monthly-diff','monthly_diff.csv')">Download CSV</button></div>
            <p class="muted">This compares the platform's final corrected per-deal snapshot for the latest month against the previous snapshot month. It uses the post-recomputed figures shown in this dashboard, not the tracker's raw report-tab outputs.</p>
            {monthly_diff_table}
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

function setupTableFilters() {{
    document.querySelectorAll(".panel table").forEach(table => {{
        const headerCells = [...table.querySelectorAll("thead th")];
        const headers = headerCells.map(th => th.innerText.trim()).filter(Boolean);
        const tableWrap = table.closest(".table-scroll");
        if (!headers.length || !tableWrap || table.dataset.filterReady === "true") return;

        table.dataset.filterReady = "true";
        const rows = [...table.querySelectorAll("tbody tr")];
        const dataRows = rows.filter(row => !row.classList.contains("section-header") && !row.classList.contains("subtotal") && !row.classList.contains("grand-total"));
        const filterBar = document.createElement("div");
        filterBar.className = "table-filter-bar";

        const clearButton = document.createElement("button");
        clearButton.type = "button";
        clearButton.className = "dl-btn";
        clearButton.textContent = "Clear filters";

        const rowCount = document.createElement("span");
        rowCount.className = "row-count";

        const panelHead = tableWrap.closest(".panel") ? tableWrap.closest(".panel").querySelector(".panel-head") : null;
        const dlBtn = panelHead ? panelHead.querySelector(".dl-btn") : null;
        if (panelHead) {{
            rowCount.style.marginLeft = "auto";
            panelHead.insertBefore(rowCount, dlBtn);
            panelHead.insertBefore(clearButton, dlBtn);
        }} else {{
            filterBar.append(clearButton, rowCount);
            tableWrap.parentNode.insertBefore(filterBar, tableWrap);
        }}

        const filterSelects = headerCells.map((th, index) => {{
            const label = th.innerText.trim();
            const values = [...new Set(dataRows.map(row => row.children[index]?.innerText.trim() || "").filter(Boolean))].sort((a, b) => a.localeCompare(b, undefined, {{ numeric: true, sensitivity: "base" }}));
            if (!label || !values.length) return null;

            th.innerHTML = `<span class="th-label">${{label}}</span>`;
            const select = document.createElement("select");
            select.className = "column-filter";
            select.setAttribute("aria-label", `Filter ${{label}}`);
            select.innerHTML = `<option value="">All</option>${{values.map(value => `<option value="${{value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")}}">${{value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}}</option>`).join("")}}`;
            th.appendChild(select);
            return select;
        }}).filter(Boolean);

        function applyFilter() {{
            let visibleDataRows = 0;

            dataRows.forEach(row => {{
                const show = filterSelects.every(select => {{
                    if (!select.value) return true;
                    const columnIndex = [...headerCells].indexOf(select.closest("th"));
                    return (row.children[columnIndex]?.innerText.trim() || "") === select.value;
                }});
                row.hidden = !show;
                if (show) visibleDataRows += 1;
            }});

            rows.forEach((row, index) => {{
                if (!row.classList.contains("section-header")) return;
                let hasVisibleDetail = false;
                for (let next = index + 1; next < rows.length; next += 1) {{
                    const nextRow = rows[next];
                    if (nextRow.classList.contains("section-header") || nextRow.classList.contains("grand-total")) break;
                    if (!nextRow.classList.contains("subtotal") && !nextRow.hidden) hasVisibleDetail = true;
                }}
                row.hidden = !hasVisibleDetail;
            }});

            rows.forEach((row, index) => {{
                if (!row.classList.contains("subtotal")) return;
                let hasVisibleDetail = false;
                for (let prev = index - 1; prev >= 0; prev -= 1) {{
                    const prevRow = rows[prev];
                    if (prevRow.classList.contains("section-header") || prevRow.classList.contains("grand-total")) break;
                    if (!prevRow.classList.contains("subtotal") && !prevRow.hidden) hasVisibleDetail = true;
                }}
                row.hidden = !hasVisibleDetail;
            }});

            rows.forEach(row => {{
                if (row.classList.contains("grand-total")) row.hidden = visibleDataRows === 0;
            }});
            const activeFilters = filterSelects.filter(select => select.value).length;
            rowCount.textContent = activeFilters ? `${{visibleDataRows}} of ${{dataRows.length}} rows` : `${{dataRows.length}} rows`;
        }}

        filterSelects.forEach(select => select.addEventListener("change", applyFilter));
        clearButton.addEventListener("click", () => {{
            filterSelects.forEach(select => {{ select.value = ""; }});
            applyFilter();
        }});
        applyFilter();
    }});
}}

setupTableFilters();

function downloadCSV(tableId, filename) {{
  const table = document.getElementById(tableId);
  if (!table) return;
  const rows = [];
  table.querySelectorAll("tr").forEach(tr => {{
        if (tr.hidden) return;
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
Chart.defaults.font.family = "'EB Garamond', Garamond, Georgia, serif";
new Chart(document.getElementById("chartNav"), {{
  type: "bar",
  data: {{
    labels: NAV_DATA.labels,
    datasets: [
      {{ label: "Carrying Value ($m)", data: NAV_DATA.carrying, backgroundColor: "#2F6B45" }},
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
