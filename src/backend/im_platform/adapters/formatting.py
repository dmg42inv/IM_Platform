"""Shared display-formatting helpers for dollar figures and multiples shown
across the dashboard and in citation/tooltip text, so a formatting rule only
has to be fixed in one place, not wherever a number happens to get rendered.
"""

from __future__ import annotations

import pandas as pd


def fmt_num(v, default_digits: int = 1) -> str:
    """Formats a number (already in the desired unit, e.g. millions) at 1
    decimal place by default - except when that would round a genuinely
    non-zero value down to "0.0" (or "-0.0"), in which case 2 decimals are
    used instead so small-but-real values stay visible."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    v = float(v)
    rounded = round(v, default_digits)
    if rounded == 0 and v != 0:
        v = 0.0 if round(v, 2) == 0 else v
        return f"{v:,.2f}"
    return f"{v:,.{default_digits}f}"


def fmt_multiple(v, cap: float = 100.0) -> str:
    """Formats a TVPI/multiple at 1 decimal place, capped at e.g. '>100.0x'
    for absurd values (a warrant/tiny-basis position marked up thousands of
    times over does not need a literal number to be meaningful - it needs to
    be shown as capped so it doesn't dominate/mislead at a glance)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    v = float(v)
    if v > cap:
        return f">{cap:,.0f}x"
    return f"{v:,.1f}x"


def fmt_money_millions(amount: float, currency: str = "USD") -> str:
    """Formats a raw dollar/currency amount (e.g. 6000000.0) as a citation-
    friendly millions string (e.g. 'USD 6.0M') instead of the full unrounded
    figure (e.g. 'USD 6,000,000.00') - large exact figures in hover-text are
    hard to read at a glance and aren't the point of a citation."""
    millions = amount / 1_000_000.0
    return f"{currency} {fmt_num(millions)}M"
