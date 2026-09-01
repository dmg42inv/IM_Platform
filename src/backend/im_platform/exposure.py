"""Fund look-through: what we are really exposed to, asset by asset.

A fund position on the register is one line. Underneath it sits a portfolio of companies, and our
economic exposure to each of those companies is what actually matters for concentration. This
module attributes each underlying holding back to us.

ATTRIBUTION BASIS
    The obvious factor - our NAV / fund NAV - is wrong. Instrument fair values in the quarterly
    reports are gross, while the fund's ending NAV is net of incentive allocation, management fees
    and expenses. Using it overstates: for MGX Fund I LP it gives 3.98%, attributing 1,145.6m to us
    against an actual carrying value of 948.5m - a 21% overstatement.

    We use instead:

        factor = our carrying value / sum of the fund's instrument fair values

    which makes the attributed holdings sum to our own carrying value exactly. Every underlying
    figure is then a decomposition of a number we have already tied to a capital account statement,
    rather than an independent estimate.

The same underlying company can be held through more than one vehicle - OpenAI sits in both
MGX Fund I LP and the Strategic Co-Invest - so exposures are aggregated by company as well as
reported by vehicle.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Fund name in fund_holdings -> the position it rolls up to in monthly_positions.
FUND_TO_POSITION = {
    "MGX Fund I LP": "MGX I LP",
    "MGX I Strategic Co-invest LP": "MGX 1 Strategic Co-invest",
    "NewSpace Capital Fund SCS": "New Space Capital Fund I",
}

# Underlying names that are the same company recorded differently across vehicles.
NAME_ALIASES = {
    "openai global, llc": "OpenAI",
    "openai global llc": "OpenAI",
    "x.ai corp.": "xAI",
    "x.ai corp": "xAI",
    "safe superintelligence inc.": "Safe Superintelligence",
    "databricks, inc.": "Databricks",
    "the binance vertical holdcos": "Binance",
    "iceye oy": "ICEYE",
    "cesiumastro inc.": "CesiumAstro",
    "fibrecoat inc.": "FibreCoat",
    "cailabs sas": "Cailabs",
    "simera sense holdings nv": "Simera Sense",
    "k2 space corporation": "K2 Space",
    "slp vii gryphon aggregator, l.p.": "SLP VII Gryphon Aggregator",
    "khazna data center holdings limited": "Khazna Data Centers",
    "tik tok": "TikTok",
    "campus ai": "Campus AI",
    "isomorphic": "Isomorphic Labs",
}


def canonical_name(raw: str) -> str:
    return NAME_ALIASES.get(str(raw or "").strip().lower(), str(raw or "").strip())


@dataclass
class Exposure:
    company: str
    fund: str
    position: str
    fund_fair_value: float
    our_fair_value: float
    currency: str
    as_of_date: str
    attribution_factor: float
    source_doc: str


def _latest_holdings_date(con: sqlite3.Connection, fund: str) -> str | None:
    row = con.execute(
        "select max(as_of_date) from fund_holdings where fund=? and level='instrument'", (fund,)
    ).fetchone()
    return row[0] if row and row[0] else None


def build_exposures(db_path: str | Path, month_id: str) -> tuple[list[Exposure], list[str]]:
    """Return per-underlying exposures for the given reporting month, plus any warnings.

    Warnings are surfaced to the user rather than swallowed: a fund we hold but cannot look
    through is a gap in the analysis and must be visible.
    """
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    exposures: list[Exposure] = []
    warnings: list[str] = []

    positions = {
        r["deal_name"]: float(r["carrying_value"] or 0.0)
        for r in con.execute(
            "select deal_name, carrying_value from monthly_positions"
            " where month_id=? and tab='Live'", (month_id,))
    }

    for fund, position in FUND_TO_POSITION.items():
        if position not in positions:
            warnings.append(f"{fund}: no matching live position '{position}' in {month_id}.")
            continue
        our_value = positions[position]
        as_of = _latest_holdings_date(con, fund)
        if not as_of:
            warnings.append(f"{fund}: no instrument-level holdings on file, so it cannot be looked through.")
            continue

        rows = con.execute(
            "select investment_name, reporting_currency, fair_value, doc_id from fund_holdings"
            " where fund=? and as_of_date=? and level='instrument' and fair_value is not null",
            (fund, as_of)).fetchall()
        gross = sum(float(r["fair_value"] or 0.0) for r in rows)
        if not rows or gross <= 0:
            warnings.append(f"{fund}: instrument holdings carry no fair value at {as_of}.")
            continue

        factor = our_value / gross
        doc = con.execute(
            "select file_name from fund_documents where doc_id=?", (rows[0]["doc_id"],)
        ).fetchone()
        source_doc = doc["file_name"] if doc else "fund quarterly report"

        for r in rows:
            fv = float(r["fair_value"] or 0.0)
            exposures.append(Exposure(
                company=canonical_name(r["investment_name"]),
                fund=fund,
                position=position,
                fund_fair_value=fv,
                our_fair_value=fv * factor,
                currency=r["reporting_currency"] or "",
                as_of_date=as_of,
                attribution_factor=factor,
                source_doc=source_doc,
            ))

    # Funds we hold that have no look-through at all.
    for name, value in positions.items():
        if name in FUND_TO_POSITION.values():
            continue
        if any(k in name for k in ("Capital Fund", "Investments Fund", "Com SCSp", "Group Holding")):
            warnings.append(f"{name} ({value:,.1f}m) has no underlying holdings on file yet.")

    return exposures, warnings


def by_company(exposures: list[Exposure]) -> list[dict]:
    """Aggregate the same underlying company across vehicles - the number that matters."""
    grouped: dict[str, dict] = {}
    for e in exposures:
        g = grouped.setdefault(e.company, {
            "company": e.company, "our_fair_value": 0.0, "vehicles": [], "as_of": e.as_of_date})
        g["our_fair_value"] += e.our_fair_value
        g["vehicles"].append(e.position)
    for g in grouped.values():
        g["vehicle_count"] = len(set(g["vehicles"]))
        g["via"] = ", ".join(sorted(set(g["vehicles"])))
    return sorted(grouped.values(), key=lambda g: -g["our_fair_value"])
