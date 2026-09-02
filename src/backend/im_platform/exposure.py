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

import calendar
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
    fund_fair_value: float   # USD millions, to match monthly_positions
    our_fair_value: float    # USD millions
    currency: str
    as_of_date: str
    attribution_factor: float  # true fraction of the fund we are attributed
    source_doc: str
    capital_account_share: float | None = None  # our NAV / partnership NAV, per the statement


def _month_end(month_id: str) -> str:
    year, month = int(month_id[:4]), int(month_id[5:7])
    return f"{month_id}-{calendar.monthrange(year, month)[1]:02d}"


def _latest_holdings_date(con: sqlite3.Connection, fund: str, month_id: str) -> str | None:
    """Most recent holdings reported on or before the month end.

    Attributing a month using a schedule published after it would import hindsight the portfolio
    did not have, which is how a historical view quietly becomes a forecast.
    """
    row = con.execute(
        "select max(as_of_date) from fund_holdings"
        " where fund=? and level='instrument' and as_of_date<=?",
        (fund, _month_end(month_id))).fetchone()
    return row[0] if row and row[0] else None


def _capital_account_share(con: sqlite3.Connection, fund: str, as_of: str) -> float | None:
    """Ownership per the capital account statement. Names differ in case between tables."""
    row = con.execute(
        "select our_share from fund_capital_accounts"
        " where fund=? collate nocase and as_of_date=? and our_share is not null",
        (fund, as_of)).fetchone()
    return float(row[0]) if row and row[0] is not None else None


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
        as_of = _latest_holdings_date(con, fund, month_id)
        if not as_of:
            newest = con.execute(
                "select max(as_of_date) from fund_holdings where fund=? and level='instrument'",
                (fund,)).fetchone()
            if newest and newest[0]:
                warnings.append(
                    f"{fund}: the earliest holdings on file are dated {newest[0]}, after "
                    f"{month_id} ended, so this month cannot be looked through without using "
                    f"information the portfolio did not have at the time.")
            else:
                warnings.append(
                    f"{fund}: no instrument-level holdings on file, so it cannot be looked through.")
            continue

        rows = con.execute(
            "select investment_name, reporting_currency, fair_value, doc_id from fund_holdings"
            " where fund=? and as_of_date=? and level='instrument' and fair_value is not null",
            (fund, as_of)).fetchall()
        # A holding with no fair value drops out of both the numerator and the attribution
        # factor, so it disappears from the analysis without a trace. Say so instead.
        missing = [
            r["investment_name"] for r in con.execute(
                "select investment_name from fund_holdings where fund=? and as_of_date=?"
                " and level='instrument' and fair_value is null", (fund, as_of))
        ]
        if missing:
            warnings.append(
                f"{fund}: no fair value on file for {', '.join(missing)}, "
                f"so {'they are' if len(missing) > 1 else 'it is'} excluded from the look-through.")
        # fund_holdings stores whole units; monthly_positions stores USD millions. Normalise here
        # so the attribution factor is a genuine fraction rather than a mixed-unit ratio.
        gross = sum(float(r["fair_value"] or 0.0) for r in rows) / 1_000_000.0
        if not rows or gross <= 0:
            warnings.append(f"{fund}: instrument holdings carry no fair value at {as_of}.")
            continue

        factor = our_value / gross
        # The statement's own ownership percentage is an independent check on the factor. The two
        # only agree where the fund carries no material accrued carry or fund-level liability.
        cap_share = _capital_account_share(con, fund, as_of)
        if cap_share is not None and abs(cap_share - factor) > 0.005:
            warnings.append(
                f"{fund}: capital account puts our ownership at {cap_share * 100:.2f}%, but the "
                f"look-through uses {factor * 100:.2f}%. The partnership's NAV is net of incentive "
                f"allocation and fund-level items that cannot be attributed to any one holding, "
                f"so the NAV share would overstate exposure to each company.")
        doc = con.execute(
            "select file_name from fund_documents where doc_id=?", (rows[0]["doc_id"],)
        ).fetchone()
        source_doc = doc["file_name"] if doc else "fund quarterly report"

        for r in rows:
            fv = float(r["fair_value"] or 0.0) / 1_000_000.0
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
                capital_account_share=cap_share,
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
