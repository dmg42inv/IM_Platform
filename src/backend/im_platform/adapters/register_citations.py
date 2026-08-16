"""Builds a lookup from the cashflow join key (confirmed_entity_id, as used
throughout the pipeline - equal to entity_id for most equities, but a more
granular fund sub-vehicle name for some funds) back to the specific
register row(s) that document it, so the dashboard can show the SPA/CAS-
confirmed investing entity and commitment amount as a hover citation
instead of blindly trusting the tracker's own simplified grouping.
"""

from __future__ import annotations

import re

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

# Ordered so the most specific/authoritative document type wins when several
# are mentioned in one citation (e.g. an IAF referencing a signed SPA should
# report "signed SPA", not the IAF).
_DOCUMENT_TYPE_PHRASES = [
    ("Capital Account Statement", "signed Capital Account Statement"),
    ("Capital Call Notice", "signed Capital Call Notice"),
    ("Drawdown", "signed Drawdown Notice"),
    ("Issuance Letter", "signed Issuance Letter"),
    ("Limited Partnership Agreement", "signed LPA"),
    ("LPA", "signed LPA"),
    ("Subscription Agreement", "signed Subscription Agreement"),
    ("Purchase Agreement", "signed SPA"),
    ("SAFE", "signed SAFE"),
    ("Convertible Note", "signed Convertible Note"),
    ("Side Letter", "signed Side Letter"),
    ("Debenture", "signed Debenture Agreement"),
    ("Warrant", "signed Warrant"),
    ("Restructuring Agreement", "signed Restructuring Agreement"),
]


def short_citation(confirmed_texts: list[str]) -> str:
    """Reduces a (often long) confirmed_by citation down to a simple, clean
    phrase like 'Confirmed from signed SPA'. Only claims a document is
    'signed'/executed when the citation itself was tagged as genuinely
    verified (CONFIRMED/FULLY CONFIRMED/UPDATED, or explicitly says
    signed/executed) - a shallow 'AI-extracted' pass (e.g. just an internal
    Investment Summary referencing a document type) is NOT enough to claim
    that, and is labelled as still needing verification instead."""
    combined = " ".join(confirmed_texts)
    if not combined:
        return "Not yet confirmed against a primary document"

    verified = (
        "CONFIRMED" in combined or "FULLY CONFIRMED" in combined
        or "signed" in combined.lower() or "executed" in combined.lower()
    )
    if "term sheet" in combined.lower() and "signed" not in combined.lower():
        return "Non-binding term sheet only - signed agreement not yet located"

    for needle, phrase in _DOCUMENT_TYPE_PHRASES:
        if needle.lower() in combined.lower():
            return f"Confirmed from {phrase}" if verified else f"Referenced in an internal summary citing a {phrase.replace('signed ', '')} - not yet independently verified as executed"
    if combined.startswith("AI-extracted"):
        return "Sourced from an internal Investment Summary - not yet cross-checked against the signed transaction document"
    return "Confirmed from primary transaction document" if verified else "Not yet independently verified as a primary/executed document"


# Ordered so a specific series/round designation is preferred over a generic
# instrument-type word (e.g. "Series C Preferred Stock" over just "Preferred").
_INSTRUMENT_PATTERNS = [
    re.compile(r"Series\s+[A-Z][0-9]?(?:-[0-9])?\s*(?:Preferred\s+(?:Stock|Units|Shares)|Prefs)", re.IGNORECASE),
    re.compile(r"Series\s+[A-Z][0-9]?(?:-[0-9])?", re.IGNORECASE),
    re.compile(r"[A-Z][0-9]?(?:-[0-9](?:,[0-9])?)?\s*Prefs", re.IGNORECASE),
    re.compile(r"Convertible\s+(?:Promissory\s+)?Note", re.IGNORECASE),
    re.compile(r"Convertible\s+Debenture", re.IGNORECASE),
    re.compile(r"\bSAFE\b"),
    re.compile(r"Stock\s+Appreciation\s+Rights?|\bSARs?\b"),
    re.compile(r"Ordinary\s+Shares"),
    re.compile(r"Warrant"),
    re.compile(r"Registered\s+Capital"),
    re.compile(r"\bLP\b|Limited\s+Partnership\s+Interest"),
]


def extract_instrument(confirmed_texts: list[str]) -> str | None:
    """Pulls the specific instrument/series designation (e.g. 'Series C
    Preferred Stock') out of the confirmed_by citation text, if mentioned."""
    combined = " ".join(confirmed_texts)
    for pattern in _INSTRUMENT_PATTERNS:
        m = pattern.search(combined)
        if m:
            return m.group(0).strip()
    return None


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
        commitment_amounts_usd = []
        for _, r in rows.iterrows():
            if r["initial_commitment_amount"]:
                commitments.append(f"{r['investment_currency']} {float(r['initial_commitment_amount']):,.2f} ({r['investment_id']})")
                if str(r["investment_currency"]).upper() == "USD":
                    commitment_amounts_usd.append(float(r["initial_commitment_amount"]))
        confirmed_texts = [r["confirmed_by"] for _, r in rows.iterrows() if r["confirmed_by"]]
        close_dates = sorted({str(r["close_date"]) for _, r in rows.iterrows() if r["close_date"]})
        lookup[key] = {
            "investing_entities": investing_entities,
            "commitments": commitments,
            "commitment_amounts_usd": commitment_amounts_usd,
            "confirmed_by": confirmed_texts,
            # A confirmed investing entity IS the primary-source signal - if we
            # don't know which vehicle invested, nothing else here can be trusted.
            "has_primary_source": bool(investing_entities),
            "short_citation": short_citation(confirmed_texts),
            "instrument": extract_instrument(confirmed_texts),
            "close_dates": close_dates,
        }

    for entity_id, rows in draft.groupby("entity_id"):
        _add(entity_id, rows)

    for subvehicle_key, investment_id in _SUBVEHICLE_TO_INVESTMENT_ID.items():
        rows = draft[draft["investment_id"] == investment_id]
        _add(subvehicle_key, rows)

    return lookup
