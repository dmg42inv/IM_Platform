"""Portfolio metric definitions - the single source of truth.

Every displayed metric is computed here and nowhere else. Before this module existed the same
concept was calculated three different ways across the app: the Overview showed a gross multiple
of (distributions + fair value) / invested while Analytics and the MGX card showed
fair value / invested, so the same portfolio reported two different multiples on two tabs.

Definitions follow the tracker's own basis of preparation:

    Capital deployed   cumulative Invested
    Fair value         Carrying Value
    Distributions      cash returned to us, excluding recallable capital (which is netted
                       against invested instead, so it is never counted twice)
    Value created      Fair value + Distributions - Capital deployed
    Gross multiple     (Distributions + Fair value) / Capital deployed        [TVPI]
    DPI                Distributions / Capital deployed
    RVPI               Fair value / Capital deployed

`BASIS_OF_PREPARATION` is rendered directly in the app, so the wording shown to a reader and the
arithmetic behind it cannot drift apart.
"""
from __future__ import annotations

import pandas as pd

# Column names as held in monthly_positions.
INVESTED = "invested"
FAIR_VALUE = "carrying_value"
DISTRIBUTIONS = "distributions"
GAIN = "gain"


def _total(frame: pd.DataFrame, column: str) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0.0).sum())


def capital_deployed(frame: pd.DataFrame) -> float:
    return _total(frame, INVESTED)


def fair_value(frame: pd.DataFrame) -> float:
    return _total(frame, FAIR_VALUE)


def distributions(frame: pd.DataFrame) -> float:
    return _total(frame, DISTRIBUTIONS)


def value_created(frame: pd.DataFrame) -> float:
    """Read from the stored `gain` column, which the ingest validates against the identity
    fair value + distributions - invested (see scripts/portfolio_db/validate_month.py)."""
    return _total(frame, GAIN)


def value_created_recomputed(frame: pd.DataFrame) -> float:
    """The identity itself, for reconciliation against the stored column."""
    return fair_value(frame) + distributions(frame) - capital_deployed(frame)


def gross_multiple(frame: pd.DataFrame) -> float | None:
    """TVPI. Returns None rather than 0.0 when there is no capital deployed, so callers
    can show 'n/a' instead of a misleading zero."""
    deployed = capital_deployed(frame)
    if not deployed:
        return None
    return (distributions(frame) + fair_value(frame)) / deployed


def dpi(frame: pd.DataFrame) -> float | None:
    deployed = capital_deployed(frame)
    if not deployed:
        return None
    return distributions(frame) / deployed


def rvpi(frame: pd.DataFrame) -> float | None:
    deployed = capital_deployed(frame)
    if not deployed:
        return None
    return fair_value(frame) / deployed


def headline(frame: pd.DataFrame) -> dict[str, float | None]:
    """Every headline figure for a set of positions, computed once."""
    return {
        "capital_deployed": capital_deployed(frame),
        "fair_value": fair_value(frame),
        "distributions": distributions(frame),
        "value_created": value_created(frame),
        "gross_multiple": gross_multiple(frame),
        "dpi": dpi(frame),
        "rvpi": rvpi(frame),
    }


def format_multiple(value: float | None) -> str:
    return f"{value:.2f}x" if value is not None else "n/a"


BASIS_OF_PREPARATION = [
    "**Capital deployed** = cumulative invested.",
    "**Fair value** = carrying value.",
    "**Distributions** = cash returned to us. Recallable capital is netted against invested "
    "rather than shown as a distribution, so it is never counted twice.",
    "**Value created** = fair value + distributions \u2212 capital deployed.",
    "**Gross multiple (TVPI)** = (distributions + fair value) / capital deployed.",
    "**DPI** = distributions / capital deployed. **RVPI** = fair value / capital deployed.",
]
