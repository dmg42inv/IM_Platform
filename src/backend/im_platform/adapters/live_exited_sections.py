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
        entity_cf = cf[cf["resolved_entity_id"] == entity]
        invested_usd = -entity_cf.loc[entity_cf["amount"] < 0, "amount"].sum() / 1_000_000
        distributed_usd = entity_cf.loc[entity_cf["amount"] > 0, "amount"].sum() / 1_000_000

        entity_val = val[val["resolved_entity_id"] == entity].sort_values("valuation_date")
        carrying_usd = float(entity_val.iloc[-1]["fair_value_local"]) / 1_000_000 if len(entity_val) else 0.0

        citation = citation_lookup.get(entity, {})
        commitment_amounts = citation.get("commitment_amounts_usd", [])
        committed_usd = sum(commitment_amounts) / 1_000_000 if commitment_amounts else d["committed"]

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
    both 'Cerebras Systems Inc (1)' and '(2)' map to 'Cerebras', so IRR for
    that pair is necessarily blended across both tracker lines."""
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

        entity_cf = cf[cf["resolved_entity_id"] == entity]
        points = [
            (d.to_pydatetime(), float(a))
            for d, a in zip(entity_cf["flow_date"], entity_cf["amount"])
            if pd.notna(d)
        ]
        entity_val = val[val["resolved_entity_id"] == entity].sort_values("valuation_date")
        if len(entity_val):
            last = entity_val.iloc[-1]
            if pd.notna(last["valuation_date"]) and last["fair_value_local"]:
                points.append((last["valuation_date"].to_pydatetime(), float(last["fair_value_local"])))

        irr_values.append(_xirr(sorted(points, key=lambda x: x[0])))
        note = f"Blended across {int(entity_counts.get(entity, 1))} tracker line(s)" if entity_counts.get(entity, 1) > 1 else ""
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
    """One row per (tab, section): pools all underlying cash flows (and
    latest fair values as terminal cashflows) across every deal mapped to
    that section, for a genuine blended section-level IRR."""
    cf = cashflow.copy()
    cf["flow_date"] = pd.to_datetime(cf["flow_date"], errors="coerce")
    val = valuation.copy()
    val["valuation_date"] = pd.to_datetime(val["valuation_date"], errors="coerce")

    rows = []
    for (tab, section), group in deals.groupby(["tab", "section"]):
        entities = {deal_entity_map[d] for d in group["deal_name"] if d in deal_entity_map}
        section_cf = cf[cf["resolved_entity_id"].isin(entities)]
        points = [
            (d.to_pydatetime(), float(a))
            for d, a in zip(section_cf["flow_date"], section_cf["amount"])
            if pd.notna(d)
        ]
        section_val = val[val["resolved_entity_id"].isin(entities)].sort_values("valuation_date")
        latest_per_entity = section_val.groupby("resolved_entity_id", as_index=False).tail(1)
        as_of = latest_per_entity["valuation_date"].max() if len(latest_per_entity) else None
        for _, v in latest_per_entity.iterrows():
            if pd.notna(v["valuation_date"]) and v["fair_value_local"]:
                points.append((v["valuation_date"].to_pydatetime(), float(v["fair_value_local"])))

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
