"""Reporting views over the structural Investment Register.

The register itself stays fully granular (one row per instrument/vehicle -
e.g. Cerebras has separate rows for the Mozn-vehicle equity round and the
Core42/EPTH-vehicle warrants). This module builds rolled-up VIEWS on top of
that detail for reporting, without ever discarding the underlying detail.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_subvehicle_parent_map(reconciliation_path: Path) -> dict[str, str]:
    """Map a fund sub-vehicle's resolved name (e.g. 'MGX I LP') to its parent
    fund folder (e.g. '4. MGX'), so cashflow/valuation rows tracked at
    sub-vehicle granularity can be rolled up consistently with a register
    view built at a coarser grouping (entity_id, fund_vehicle_id, etc.)."""
    rec = pd.read_excel(reconciliation_path, sheet_name="Entity_Reconciliation").fillna("")
    mapping: dict[str, str] = {}
    for _, row in rec.iterrows():
        if row["suggested_match_type"] == "fund_subvehicle" and row["parent_fund_folder"] and row["confirmed_entity_id"]:
            mapping[row["confirmed_entity_id"]] = row["parent_fund_folder"]
    return mapping


def build_rollup_view(draft: pd.DataFrame, group_by: str = "entity_id") -> pd.DataFrame:
    """Roll up the granular register to the given grouping level.

    group_by="entity_id" (default): one row per portfolio company, blending
        across instruments/vehicles - good for a simple portfolio overview.
    group_by="fund_vehicle_id": one row per investing vehicle - useful for
        answering "how much has each G42/Mozn/Expansion Project entity
        deployed", cutting across portfolio companies.
    """
    draft = draft[draft["investment_id"] != ""].copy()
    draft["initial_commitment_amount"] = pd.to_numeric(
        draft["initial_commitment_amount"], errors="coerce"
    ).fillna(0.0)
    draft["close_date_parsed"] = pd.to_datetime(draft["close_date"], errors="coerce")

    rows = []
    for key, group in draft.groupby(group_by):
        entity_ids = group["entity_id"].dropna().unique().tolist()
        fund_vehicles = group["fund_vehicle_id"].dropna().unique().tolist()
        instrument_types = group["instrument_type"].dropna().unique().tolist()
        rows.append(
            {
                "investment_id": key,
                "entity_id": entity_ids[0] if len(entity_ids) == 1 else key,
                "fund_vehicle_id": fund_vehicles[0] if len(fund_vehicles) == 1 else "Mixed",
                "instrument_type": instrument_types[0] if len(instrument_types) == 1 else "Mixed",
                "initial_commitment_amount": group["initial_commitment_amount"].sum(),
                "investment_currency": (
                    group["investment_currency"].mode().iat[0]
                    if not group["investment_currency"].mode().empty
                    else "USD"
                ),
                "close_date": (
                    group["close_date_parsed"].min().strftime("%Y-%m-%d")
                    if group["close_date_parsed"].notna().any()
                    else ""
                ),
                "lifecycle_state": group["lifecycle_state"].iloc[-1],
                "lifecycle_state_date": (
                    group["lifecycle_state_date"].replace("", pd.NA).dropna().max()
                    if group["lifecycle_state_date"].replace("", pd.NA).notna().any()
                    else ""
                ),
                "component_count": len(group),
                "component_investment_ids": ", ".join(group["investment_id"].tolist()),
            }
        )
    return pd.DataFrame(rows)
