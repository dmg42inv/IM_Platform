"""Parses the monthly tracker's "1. Live" and "2. Exited" report tabs into a
clean deal-level table with section (Investing Entity holding company) and
subtotals - this is the tracker's OWN authoritative Live/Exited classification
and Investing Entity grouping (Mozn / G42 Investments / G42 Capital / Core42 /
GX Investments-MGX), used as-is rather than re-derived, per the agreed
source-of-truth split (tracker owns cash flow/valuation reporting views).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..calculations import _xirr

_FOOTER_MARKERS = ("for notes", "position exited", "checks:")


def _norm(v: object) -> str:
    return str(v).strip() if pd.notna(v) else ""


def _strip_footnote_marker(investing_entity: str) -> str:
    """The tracker sometimes appends a trailing digit as a footnote reference
    (e.g. 'Mozn 4', 'G42 3') pointing to a note in its '9. All deals (a)' tab -
    it is NOT a different investing entity. Strip it for display consistency."""
    import re
    return re.sub(r"\s+\d+$", "", investing_entity).strip()


# Deal names where Committed is deliberately pinned to Invested (Remaining =
# 0), overriding the register's own commitment-amount sum - used when a
# register tranche never materialized (e.g. a JV/co-investment that was
# discussed but never closed) and there is no genuine further commitment
# outstanding. User-confirmed case-by-case; do not add to this without an
# explicit confirmation, since it deliberately overrides the primary-source
# commitment figure.
_COMMITTED_EQUALS_INVESTED_DEALS: dict[str, str] = {
    "ONT plc": (
        "User-confirmed (2026-08-16): the JVCo co-investment tranche referenced in the register "
        "never materialized (talks fell through) and all committed capital has been deployed - "
        "Remaining Commitment cannot be negative, so Committed is pinned to Invested here rather "
        "than the register's raw commitment-amount sum (which understates Committed further by "
        "excluding a GBP-denominated tranche not converted to USD - see the Committed tooltip)."
    ),
    "Beyond Limits": (
        "User-confirmed (2026-08-16): the undrawn ~$10M final Series C tranche (of the 4 "
        "scheduled in the executed Note Purchase and Investment Agreement) has been cancelled - "
        "substantial time has passed and there is no intention to invest further, so Committed "
        "is pinned to Invested here (no separate cancellation document on file yet; user is "
        "trying to obtain one)."
    ),
    "vTv Therapeutics Inc.": (
        "User-confirmed (2026-08-18): the $25.0M agreed purchase price was reduced by a "
        "document-verified 3.75% early-payment discount (~$468,750) on the deferred $12.5M "
        "promissory note - G42 paid what was agreed, in full, with the discount reflecting the "
        "deal's own terms, not an unfunded/outstanding balance. Committed is pinned to Invested "
        "($24.53M) here rather than the register's raw $25.0M commitment-amount figure, since "
        "there is no outstanding commitment remaining."
    ),
    "Life Biosciences LLC": (
        "User-confirmed (2026-08-18): actual cash invested was $40.0M on a dollar basis (a "
        "$20.0M initial convertible note, plus a further ~$20.0M on conversion). The register's "
        "$40,947,395.44 figure includes ~$0.95M of accrued PIK interest on that convertible note, "
        "paid in additional converted shares rather than cash - not an unfunded/outstanding "
        "balance. Committed is pinned to Invested ($40.0M) here rather than the register's raw "
        "figure, since there is no outstanding commitment remaining."
    ),
    "Inveniam Ltd": (
        "User-confirmed (2026-08-18): the register's $100,032,722.58 figure is an exact "
        "instrument-level calculation (13,481,499 SARs x $7.42/SAR) - the $7.42 strike price "
        "itself is a rounded display of the actual per-unit price, so the product doesn't land "
        "cleanly on the deal's real $100.0M size even though that IS the intended commitment. "
        "There is no outstanding/remaining commitment - Committed is pinned to Invested ($100.0M) "
        "here rather than the register's raw SAR-math figure."
    ),
    "North Summit Capital Fund": (
        "Document-confirmed (2026-08-18) from the executed Side Letter dated December 2023 "
        "(effective 1 January 2023) between Galbot Holding RSC Ltd (Investor) and North Summit "
        "Capital Fund GP Limited: 'the General Partner hereby fully irrevocably and "
        "unconditionally waives the Investor's obligation to make Capital Contributions...the "
        "outstanding amount of US$217,693,608 which constitutes the Investor's outstanding "
        "Capital Contribution...is hereby waived.' The register's $300,000,000 commitment figure "
        "is the ORIGINAL 2019 subscription amount (still correctly the primary-source structural "
        "fact for that date), but the entire remaining/uncalled balance was irrevocably released "
        "in this side letter - no further capital will ever be called. Committed is pinned to "
        "Invested here to reflect that there is no outstanding commitment remaining, not the "
        "original $300M subscription size."
    ),
}

# POLICY (user-confirmed 2026-08-18): for FUND vehicles, the Capital Account
# Statement (or Limited Partner Statement) is the primary source of truth for
# cumulative Invested/Distributions, not the sum of the tracker's own dated
# "CF (Funds)" cash flow rows - proven necessary after finding the tracker's
# own fund-cashflow tagging can have mixed sign conventions (e.g. a capital-
# call reduction/equalization wrongly recorded as a gross distribution) or
# gaps (an interim capital call not yet entered into the monthly tracker at
# all). This does NOT apply to direct equity/debt deals, where the tracker's
# dated cash flow + signed transaction documents remain primary (see
# _CASHFLOW_VALIDATED_DEALS in tracker_style_dashboard.py for that side).
# Always keep the underlying dated tracker rows too (never delete them) so
# the All Cashflows drill-down and IRR still have something to compute from -
# just know they may not individually foot to the CAS-sourced summary above
# them until/unless the specific mis-tagged entries are separately corrected.
_FUND_CAS_CASHFLOW_OVERRIDES: dict[str, dict] = {
    "North Summit Capital Fund": {
        "invested": 83.361611,
        "distributions": 7.875571,
        "note": (
            "Sourced from the Q1 2026 Capital Account Statement (Galbot Holding RSC Ltd's 99.5% "
            "allocation), 'since inception' cumulative figures - not summed from the tracker's own "
            "dated cash flow rows. The tracker-derived NET position (Invested - Distributions) "
            "matches this CAS exactly to the dollar ($75,486,040 both ways), confirming the "
            "underlying transaction data is complete and correct in total - but the GROSS Invested/"
            "Distributions were mis-bucketed by $16,647,690 (some capital-call reductions/"
            "equalizations appear to have been wrongly recorded as distributions in the tracker). "
            "The All Cashflows tab still shows the tracker's own dated entries, which will not "
            "individually foot to this total until the specific mis-tagged rows are identified "
            "(needs the underlying capital call/distribution notices, not yet located)."
        ),
    },
    "New Space Capital Fund I": {
        "invested": 17.80166535,
        "distributions": 6.50828684,
        "note": (
            "Invested is 'Total contributions' EUR 15,479,709 (since inception) from the latest "
            "(Q2 2026, 30 June 2026) Limited Partner Statement for NewSpace Capital Fund S.C.S. - "
            "already NET of every equalisation capital-return event (confirmed against the "
            "Remaining Commitment rollforward in each Drawdown/Equalisation notice). Distributions "
            "is NOT the Statement's own 'Total distributions' line (EUR 2,402,466), because that "
            "line is explicitly labelled 'Non-recallable' and by design excludes equalisation-"
            "driven cash payments to G42 (confirmed user-explained 2026-08-18: as new investors "
            "join, the Fund returns capital AND pays actualisation interest to existing investors "
            "for having funded earlier) - those are real cash but are recallable/capital-return in "
            "nature, not permanent profit distributions. Distributions here = EUR 2,402,466 (non-"
            "recallable) + EUR 3,256,913.86 (the actualisation INTEREST component only, traced "
            "through every Drawdown/Equalisation/Distribution notice 2023-2025 and confirmed as "
            "actually paid out in cash, not merely netted against a still-positive capital call: "
            "EUR2,067,567.04 in Distribution 1/27-Jan-2023, EUR62,495.83 in Distribution 2/DD14, "
            "EUR345,590.90 in Distribution 4/DD17, EUR781,260.09 in DD20 - DD16's EUR56,063.44 "
            "interest is excluded because it only reduced a still-net-positive capital call, never "
            "paid out as cash) = EUR 5,659,379.86, converted to USD at the fixed 1.15 EUR/USD "
            "hedging rate used by Treasury for this fund (same rate applied to Committed - see "
            "NewSpace-FundSCS-2020 in register_citations.py). Not summed from the tracker's own "
            "dated cash flow rows, which totalled a much larger USD36.1M invested - overstated by "
            "the same class of sign/bucketing bug found at North Summit (e.g. the Aug-2025 "
            "Drawdown 20 notice's 3 components were tracker-tagged 'Distribution'/'Fee'/"
            "'CapitalCall' with signs that invert their true economic direction)."
        ),
    },
}


def _deal_cashflow(deal_name: str, entity: str, cf: pd.DataFrame) -> pd.DataFrame:
    """Cash flow rows for one tracker deal row. Some entities have more than
    one tracker deal line mapped to the same confirmed_entity_id (e.g. 'Tools
    for Humanity Corporation' and 'WLD Tokens' both resolve to 'TFH -
    Worldcoin'; 'Cerebras Systems Inc (1)'/'(2)' both resolve to 'Cerebras') -
    if the tracker's own cashflow rows are tagged with that exact deal name in
    their (pre-reconciliation) investment_id, use only that subset so each
    deal shows its own Invested/Distributions rather than the whole pooled
    entity's total on every one of its deal rows. Falls back to pooling all
    cash flow for the entity when the deal name isn't separately tagged."""
    exact = cf[cf["investment_id"] == deal_name]
    if len(exact):
        return exact
    return cf[cf["resolved_entity_id"] == entity]


def _deal_valuation(deal_name: str, entity: str, val: pd.DataFrame) -> pd.DataFrame:
    """Same granularity rule as _deal_cashflow, for the NAV/valuation extract."""
    exact = val[val["investment_id"] == deal_name]
    if len(exact):
        return exact
    return val[val["resolved_entity_id"] == entity]


def _parse_tab(raw: pd.DataFrame, tab_label: str) -> list[dict]:
    header_row = None
    for idx in range(len(raw)):
        cells = [_norm(v).lower() for v in raw.iloc[idx].tolist()]
        if "deals" in cells and "investing entity" in cells:
            header_row = idx
            break
    if header_row is None:
        raise ValueError(f"Could not find header row in {tab_label}")

    col_map = {_norm(v).lower(): idx for idx, v in raw.iloc[header_row].items() if pd.notna(v)}

    def col(label: str) -> int | None:
        return col_map.get(label)

    c_deals = col("deals")
    c_status = col("status")
    c_investing_entity = col("investing entity")
    c_vintage = next((v for k, v in col_map.items() if k.startswith("vintage")), None)
    c_instrument = col("instrument")
    c_committed = col("committed")
    c_invested = col("invested")
    c_remaining = col("remaining commitment")
    c_distributions = col("distributions")
    c_carrying = col("carrying value")
    c_gain = col("gain")
    c_tvpi = col("tvpi")
    c_notes = next((v for k, v in col_map.items() if "upside" in k or "downside" in k), None)

    rows: list[dict] = []
    current_section = None
    for idx in range(header_row + 1, len(raw)):
        row = raw.iloc[idx]
        deal_name = _norm(row[c_deals]) if c_deals is not None else ""
        investing_entity = _norm(row[c_investing_entity]) if c_investing_entity is not None else ""

        if not deal_name:
            continue
        if any(marker in deal_name.lower() for marker in _FOOTER_MARKERS):
            continue

        if not investing_entity:
            # Section header row (deal name present, Investing Entity blank).
            current_section = deal_name
            continue

        rows.append(
            {
                "tab": tab_label,
                "section": current_section,
                "deal_name": deal_name,
                "status": _norm(row[c_status]) if c_status is not None else "",
                "investing_entity": _strip_footnote_marker(investing_entity),
                "investing_entity_raw": investing_entity,
                "vintage": _norm(row[c_vintage]) if c_vintage is not None else "",
                "instrument": _norm(row[c_instrument]) if c_instrument is not None else "",
                "committed": pd.to_numeric(row[c_committed], errors="coerce") if c_committed is not None else None,
                "invested": pd.to_numeric(row[c_invested], errors="coerce") if c_invested is not None else None,
                "remaining_commitment": pd.to_numeric(row[c_remaining], errors="coerce") if c_remaining is not None else None,
                "distributions": pd.to_numeric(row[c_distributions], errors="coerce") if c_distributions is not None else None,
                "carrying_value": pd.to_numeric(row[c_carrying], errors="coerce") if c_carrying is not None else None,
                "gain": pd.to_numeric(row[c_gain], errors="coerce") if c_gain is not None else None,
                "tvpi": pd.to_numeric(row[c_tvpi], errors="coerce") if c_tvpi is not None else None,
                "notes": _norm(row[c_notes]) if c_notes is not None else "",
            }
        )

    return rows


def extract_live_exited_sections(path: Path) -> pd.DataFrame:
    """Returns one row per deal, in USD millions (as shown in the tracker),
    with 'tab' ('Live'/'Exited'), 'section' (Investing Entity holding co.),
    and 'investing_entity' (short code: Mozn/G42 Investments/G42 Capital/
    Core42/G42 Holding)."""
    xl = pd.ExcelFile(path)
    all_rows: list[dict] = []
    all_rows.extend(_parse_tab(xl.parse("1. Live", header=None), "Live"))
    all_rows.extend(_parse_tab(xl.parse("2. Exited", header=None), "Exited"))
    return pd.DataFrame(all_rows)


def recompute_deal_financials(
    deals: pd.DataFrame,
    cashflow: pd.DataFrame,
    valuation: pd.DataFrame,
    deal_entity_map: dict[str, str],
    citation_lookup: dict[str, dict],
) -> pd.DataFrame:
    """Replaces the tracker's own Committed/Invested/Remaining/Distributions/
    Carrying Value/Gain/TVPI with values computed the same way the tracker's
    OWN underlying formulas do (verified directly against its 'A. All deals
    (a)' tab): Invested = -SUMIF(cashflow, deal, contributions), Distributions
    = SUMIF(cashflow, deal, distributions), Carrying Value = latest NAV mark,
    Remaining = Committed - Invested, Gain = Carrying + Distributions -
    Invested, TVPI = (Distributions + Carrying) / Invested. Committed comes
    from the register's primary-source commitment where confirmed, falling
    back to the tracker's own Committed figure only when the register has
    none yet (flagged separately via citation_lookup). The tracker's original
    values are preserved as tracker_* columns for a triangulation check.
    """
    deals = deals.copy()
    cf = cashflow.copy()
    cf["flow_date"] = pd.to_datetime(cf["flow_date"], errors="coerce")
    val = valuation.copy()
    val["valuation_date"] = pd.to_datetime(val["valuation_date"], errors="coerce")

    for col in ["committed", "invested", "remaining_commitment", "distributions", "carrying_value", "gain", "tvpi"]:
        deals[f"tracker_{col}"] = deals[col]

    new_committed, new_invested, new_remaining = [], [], []
    new_distributions, new_carrying, new_gain, new_tvpi = [], [], [], []

    for _, d in deals.iterrows():
        entity = deal_entity_map.get(d["deal_name"], "")
        entity_cf = _deal_cashflow(d["deal_name"], entity, cf)
        cas_override = _FUND_CAS_CASHFLOW_OVERRIDES.get(d["deal_name"])
        if cas_override:
            invested_usd = cas_override["invested"]
            distributed_usd = cas_override["distributions"]
        else:
            invested_usd = -entity_cf.loc[entity_cf["amount"] < 0, "amount"].sum() / 1_000_000
            distributed_usd = entity_cf.loc[entity_cf["amount"] > 0, "amount"].sum() / 1_000_000

        entity_val = _deal_valuation(d["deal_name"], entity, val).sort_values("valuation_date")
        if len(entity_val):
            latest_val = entity_val.iloc[-1]
            fx_to_usd = float(latest_val["fx_to_usd"]) if pd.notna(latest_val.get("fx_to_usd")) else 1.0
            carrying_usd = float(latest_val["fair_value_local"]) * fx_to_usd / 1_000_000
        else:
            carrying_usd = 0.0

        # Deal-name-specific citation first (see _DEAL_NAME_TO_INVESTMENT_IDS
        # in register_citations.py) so Committed isn't pooled across every
        # deal row sharing one entity; falls back to the entity-level one.
        citation = citation_lookup.get(d["deal_name"]) or citation_lookup.get(entity, {})
        commitment_amounts = citation.get("commitment_amounts_usd", [])
        committed_usd = sum(commitment_amounts) / 1_000_000 if commitment_amounts else d["committed"]
        # A fully exited position has no outstanding commitment left by
        # definition, regardless of what the original commitment document
        # said - structural rule (user-confirmed 2026-08-19), applies to
        # every deal in the Exited tab, not a case-by-case list.
        if d["tab"] == "Exited" or d["deal_name"] in _COMMITTED_EQUALS_INVESTED_DEALS:
            committed_usd = invested_usd

        remaining_usd = committed_usd - invested_usd if committed_usd is not None else None
        gain_usd = carrying_usd + distributed_usd - invested_usd
        tvpi_val = (distributed_usd + carrying_usd) / invested_usd if invested_usd else None

        new_committed.append(committed_usd)
        new_invested.append(invested_usd)
        new_remaining.append(remaining_usd)
        new_distributions.append(distributed_usd)
        new_carrying.append(carrying_usd)
        new_gain.append(gain_usd)
        new_tvpi.append(tvpi_val)

    deals["committed"] = new_committed
    deals["invested"] = new_invested
    deals["remaining_commitment"] = new_remaining
    deals["distributions"] = new_distributions
    deals["carrying_value"] = new_carrying
    deals["gain"] = new_gain
    deals["tvpi"] = new_tvpi
    return deals


def build_deal_entity_map(reconciliation_path: Path) -> dict[str, str]:
    """Tracker deal name -> confirmed_entity_id (cashflow join key), taken
    directly from Entity_Reconciliation.xlsx. This is a many-to-one map: e.g.
    both 'Cerebras Systems Inc (1)' and '(2)' map to 'Cerebras', and 'Tools
    for Humanity Corporation'/'WLD Tokens' both map to 'TFH - Worldcoin'.
    When the tracker's own cash flow/valuation rows separately tag each deal
    name (see _deal_cashflow/_deal_valuation), each deal still gets its own
    figures; IRR is only truly blended across tracker lines when the
    underlying cash flow for that specific deal name isn't separately
    tagged and both lines have to share the whole entity's pooled cash
    flow."""
    rec = pd.read_excel(reconciliation_path, sheet_name="Entity_Reconciliation").fillna("")
    return {
        row["tracker_investment_id"]: row["confirmed_entity_id"]
        for _, row in rec.iterrows()
        if row["confirmed_entity_id"]
    }


def enrich_with_irr(
    deals: pd.DataFrame,
    cashflow: pd.DataFrame,
    valuation: pd.DataFrame,
    deal_entity_map: dict[str, str],
) -> pd.DataFrame:
    """Adds an 'irr' column (deal-level) computed from the underlying dated
    cash flows (not the tracker's own summary figures), plus an 'irr_note'
    flagging when a deal's IRR is necessarily blended with another tracker
    line (because both map to the same underlying cashflow entity)."""
    deals = deals.copy()
    entity_counts = pd.Series(list(deal_entity_map.values())).value_counts()

    cf = cashflow.copy()
    cf["flow_date"] = pd.to_datetime(cf["flow_date"], errors="coerce")
    val = valuation.copy()
    val["valuation_date"] = pd.to_datetime(val["valuation_date"], errors="coerce")

    irr_values = []
    irr_notes = []
    for _, row in deals.iterrows():
        entity = deal_entity_map.get(row["deal_name"])
        if not entity:
            irr_values.append(None)
            irr_notes.append("No cashflow mapping found")
            continue

        entity_cf = _deal_cashflow(row["deal_name"], entity, cf)
        tagged_separately = len(cf[cf["investment_id"] == row["deal_name"]]) > 0
        points = [
            (d.to_pydatetime(), float(a))
            for d, a in zip(entity_cf["flow_date"], entity_cf["amount"])
            if pd.notna(d)
        ]
        entity_val = _deal_valuation(row["deal_name"], entity, val).sort_values("valuation_date")
        if len(entity_val):
            last = entity_val.iloc[-1]
            if pd.notna(last["valuation_date"]) and last["fair_value_local"]:
                points.append((last["valuation_date"].to_pydatetime(), float(last["fair_value_local"])))

        irr_values.append(_xirr(sorted(points, key=lambda x: x[0])))
        # Only genuinely "blended" when this deal's cash flow ISN'T separately
        # tagged in the tracker and had to fall back to the whole entity's pool.
        blended = (not tagged_separately) and entity_counts.get(entity, 1) > 1
        note = f"Blended across {int(entity_counts.get(entity, 1))} tracker line(s)" if blended else ""
        irr_notes.append(note)

    deals["irr"] = irr_values
    deals["irr_note"] = irr_notes
    return deals


def compute_section_irr(
    deals: pd.DataFrame,
    cashflow: pd.DataFrame,
    valuation: pd.DataFrame,
    deal_entity_map: dict[str, str],
) -> pd.DataFrame:
    """One row per (tab, section): pools each deal's own cash flows (and
    latest fair value as a terminal cash flow) across every deal in that
    section, for a genuine blended section-level IRR. Each deal's cash flow
    is taken at the same granularity as recompute_deal_financials (exact
    tracker deal-name tag when the tracker's own cashflow separately tags it,
    else pooled by entity) - otherwise a section with more than one deal row
    mapped to the same entity (e.g. a Live equity deal and a separately
    exited token/warrant leg for the same company) would double-count that
    entity's cash flow once per deal row."""
    cf = cashflow.copy()
    cf["flow_date"] = pd.to_datetime(cf["flow_date"], errors="coerce")
    val = valuation.copy()
    val["valuation_date"] = pd.to_datetime(val["valuation_date"], errors="coerce")

    rows = []
    for (tab, section), group in deals.groupby(["tab", "section"]):
        points = []
        valuation_dates = []
        for _, d in group.iterrows():
            entity = deal_entity_map.get(d["deal_name"], "")
            deal_cf = _deal_cashflow(d["deal_name"], entity, cf)
            points.extend(
                (dt.to_pydatetime(), float(a))
                for dt, a in zip(deal_cf["flow_date"], deal_cf["amount"])
                if pd.notna(dt)
            )
            deal_val = _deal_valuation(d["deal_name"], entity, val).sort_values("valuation_date")
            if len(deal_val):
                last = deal_val.iloc[-1]
                if pd.notna(last["valuation_date"]) and last["fair_value_local"]:
                    points.append((last["valuation_date"].to_pydatetime(), float(last["fair_value_local"])))
                    valuation_dates.append(last["valuation_date"])

        as_of = max(valuation_dates) if valuation_dates else None
        rows.append(
            {
                "tab": tab,
                "section": section,
                "irr": _xirr(sorted(points, key=lambda x: x[0])),
                "as_of_date": as_of.strftime("%Y-%m-%d") if as_of is not None and pd.notna(as_of) else "",
            }
        )
    return pd.DataFrame(rows)


def build_quarterly_cashflows(cashflow: pd.DataFrame, num_quarters: int = 30) -> pd.DataFrame:
    """Quarterly inflow (distributions)/outflow (deployments) totals across
    ALL resolved cashflow (equity/debt + funds combined), most recent
    `num_quarters` quarters with any activity."""
    cf = cashflow.copy()
    cf["flow_date"] = pd.to_datetime(cf["flow_date"], errors="coerce")
    cf = cf[cf["flow_date"].notna()]
    cf["quarter"] = cf["flow_date"].dt.to_period("Q").astype(str)

    grouped = cf.groupby("quarter")["amount"].agg(
        inflow=lambda s: s[s > 0].sum(),
        outflow=lambda s: s[s < 0].sum(),
        net=lambda s: s.sum(),
    ).reset_index()
    grouped = grouped.sort_values("quarter")
    return grouped.tail(num_quarters).reset_index(drop=True)
