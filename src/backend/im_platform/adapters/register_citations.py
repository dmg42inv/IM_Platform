"""Builds a lookup from the cashflow join key (confirmed_entity_id, as used
throughout the pipeline - equal to entity_id for most equities, but a more
granular fund sub-vehicle name for some funds) back to the specific
register row(s) that document it, so the dashboard can show the SPA/CAS-
confirmed investing entity and commitment amount as a hover citation
instead of blindly trusting the tracker's own simplified grouping.
"""

from __future__ import annotations

import pandas as pd

# Fund sub-vehicle cashflow keys whose register investment_id doesn't equal
# entity_id (funds with more than one distinct vehicle under one entity_id).
_SUBVEHICLE_TO_INVESTMENT_ID = {
    "MGX I LP": "MGX-I-LP-2024",
    "MGX I Strategic Co-Invest LP": "MGX-I-StrategicCoInvest-2024",
    "MGX I Strategic Co-invest LP": "MGX-I-StrategicCoInvest-2024",
    "MGX I Denali Holding LP": "MGX-I-DenaliHolding-2024",
    "MGX Group Holding 1 Ltd (GP)": "MGX-GroupHolding1-GP-2024",
    "NewSpace Capital GP Com SCSp": "NewSpace-GPCom-2023",
    "Acies Investments Fund I L.P.": "Acies-LP-2021",
}


def build_entity_citation_lookup(draft: pd.DataFrame) -> dict[str, dict]:
    """confirmed_entity_id -> {investing_entities: [...], commitments: [...],
    confidence: str, has_primary_source: bool}, aggregating all register
    rows for that key (an entity can have several tranches/rows)."""
    lookup: dict[str, dict] = {}

    def _add(key: str, rows: pd.DataFrame) -> None:
        if key in lookup or len(rows) == 0:
            return
        investing_entities = sorted({v for v in rows["fund_vehicle_id"] if v})
        commitments = []
        for _, r in rows.iterrows():
            if r["initial_commitment_amount"]:
                commitments.append(f"{r['investment_currency']} {float(r['initial_commitment_amount']):,.2f} ({r['investment_id']})")
        confirmed_texts = [r["confirmed_by"] for _, r in rows.iterrows() if r["confirmed_by"]]
        has_primary_source = any(
            "AI-extracted" in t or "CONFIRMED" in t or "FULLY CONFIRMED" in t or "UPDATED" in t
            for t in confirmed_texts
        )
        lookup[key] = {
            "investing_entities": investing_entities,
            "commitments": commitments,
            "confirmed_by": confirmed_texts,
            "has_primary_source": has_primary_source and bool(investing_entities),
        }

    for entity_id, rows in draft.groupby("entity_id"):
        _add(entity_id, rows)

    for subvehicle_key, investment_id in _SUBVEHICLE_TO_INVESTMENT_ID.items():
        rows = draft[draft["investment_id"] == investment_id]
        _add(subvehicle_key, rows)

    return lookup
