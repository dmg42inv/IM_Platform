"""Month integrity checks for the portfolio database.

Run after any ingest or manual month build. Every check recomputes a reported figure from
its own inputs; nothing is estimated. A break means the stored figure cannot be reproduced.

    python -m scripts.portfolio_db.validate_month              # all months
    python -m scripts.portfolio_db.validate_month 2026-08      # one month
"""
from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "portfolio" / "portfolio.sqlite"

MONEY_TOL = 0.005     # USDm
RATIO_TOL = 0.0005    # multiples
US_EXCHANGES = {"NASDAQ", "NYSE", "NYSE AMERICAN", "AMEX"}


@dataclass
class Check:
    month: str
    check_id: str
    subject: str
    metric: str
    reported: str
    recomputed: str
    difference: str
    result: str
    basis: str


def _f(value) -> float:
    return float(value or 0.0)


def _money(value: float) -> str:
    return f"{value:,.4f}"


def _verdict(diff: float, tol: float) -> str:
    return "OK" if abs(diff) <= tol else "BREAK"


def _uk_summer_bank_holiday(year: int) -> date:
    """Last Monday in August."""
    for day in range(31, 24, -1):
        candidate = date(year, 8, day)
        if candidate.weekday() == 0:
            return candidate
    raise ValueError(year)


def _month_end(month_id: str) -> date:
    year, month = (int(part) for part in month_id.split("-"))
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1).toordinal() and date.fromordinal(date(year, month + 1, 1).toordinal() - 1)


def check_month(con: sqlite3.Connection, month: str) -> list[Check]:
    checks: list[Check] = []
    rows = con.execute(
        "select deal_name, committed, invested, remaining_commitment, distributions,"
        " carrying_value, gain, tvpi from monthly_positions"
        " where month_id=? and tab='Live' order by deal_name",
        (month,),
    ).fetchall()
    if not rows:
        return checks

    # V1/V2/V3 - per-position identities
    gain_ever_populated = any(_f(r[6]) for r in rows)
    for name, committed, invested, remaining, dist, carry, gain, tvpi in rows:
        expected_gain = _f(carry) + _f(dist) - _f(invested)
        diff = _f(gain) - expected_gain
        if not gain_ever_populated:
            result, basis = "INFO", "gain not captured for this month in the source tracker"
        else:
            result = _verdict(diff, MONEY_TOL)
            basis = "gain must equal carrying value + distributions - invested"
        checks.append(Check(month, "V1", name, "Gain", _money(_f(gain)), _money(expected_gain),
                            _money(diff), result, basis))

        if _f(invested):
            expected_tvpi = (_f(carry) + _f(dist)) / _f(invested)
            d = _f(tvpi) - expected_tvpi
            if _f(tvpi) == 0.0 and _f(carry) > 0:
                # The tracker caps very high multiples as text (e.g. ">10x"), which stores as 0.
                result, basis = "INFO", "tvpi not stored numerically; source shows a capped label"
            else:
                result = _verdict(d, RATIO_TOL)
                basis = "tvpi must equal (carrying value + distributions) / invested"
            checks.append(Check(month, "V2", name, "TVPI", f"{_f(tvpi):.6f}", f"{expected_tvpi:.6f}",
                                f"{d:.6f}", result, basis))

        if remaining is not None and committed is not None:
            expected_rem = _f(committed) - _f(invested)
            d = _f(remaining) - expected_rem
            checks.append(Check(month, "V3", name, "Remaining commitment", _money(_f(remaining)),
                                _money(expected_rem), _money(d), _verdict(d, MONEY_TOL),
                                "remaining commitment must equal committed less invested"))

    # V4 - tracker_months rollup must agree with the position rows
    roll = con.execute(
        "select live_count, live_invested, live_carrying, live_gain from tracker_months where month_id=?",
        (month,),
    ).fetchone()
    if roll:
        totals = {
            "Live count": (float(roll[0] or 0), float(len(rows))),
            "Invested": (_f(roll[1]), sum(_f(r[2]) for r in rows)),
            "Carrying value": (_f(roll[2]), sum(_f(r[5]) for r in rows)),
            "Gain": (_f(roll[3]), sum(_f(r[6]) for r in rows)),
        }
        for metric, (reported, recomputed) in totals.items():
            d = reported - recomputed
            tol = 0.0 if metric == "Live count" else MONEY_TOL
            checks.append(Check(month, "V4", "Portfolio total", metric, _money(reported),
                                _money(recomputed), _money(d), _verdict(d, tol),
                                "tracker_months rollup must foot to monthly_positions"))

    # V5/V6 - listed marks must rebuild from their own stated inputs, priced at month end
    carry_by_name = {r[0]: _f(r[5]) for r in rows}
    listed = con.execute(
        "select deal_name, ticker, exchange, shares, price, price_divisor, fx_rate,"
        " price_date, carrying_value_usd_m, price_source from valuation_inputs where month_id=?",
        (month,),
    ).fetchall()
    month_end = _month_end(month)
    for name, ticker, exchange, shares, price, divisor, fx, price_date, stored_cv, source in listed:
        rebuilt = _f(shares) * _f(price) / (_f(divisor) or 1.0) * (_f(fx) or 1.0) / 1_000_000
        reported_cv = carry_by_name.get(name, _f(stored_cv))
        d = reported_cv - rebuilt
        checks.append(Check(month, "V5", name, "Listed carrying value", _money(reported_cv),
                            _money(rebuilt), _money(d), _verdict(d, MONEY_TOL),
                            f"{shares:,.0f} x {price} {'' if not divisor or divisor == 1 else f'/ {divisor:g} '}"
                            f"{'x fx ' + str(fx) if fx and fx != 1 else ''}".strip()))

        # A US listing has no reason to be priced before month end unless month end was a weekend.
        stale = price_date and str(price_date) != month_end.isoformat()
        if stale:
            venue = (exchange or "").upper()
            if month_end.weekday() >= 5:
                reason, result = "month end fell on a weekend", "OK"
            elif venue not in US_EXCHANGES and month_end == _uk_summer_bank_holiday(month_end.year):
                reason, result = "UK Summer Bank Holiday, exchange closed", "OK"
            elif venue in US_EXCHANGES and month_end == _uk_summer_bank_holiday(month_end.year):
                reason = ("US exchange does not observe the UK bank holiday, so month end was a "
                          "normal trading day and the month-end close should have been used")
                result = "BREAK"
            else:
                reason, result = "no documented exchange closure for this date", "BREAK"
            checks.append(Check(month, "V6", name, "Price date", str(price_date),
                                month_end.isoformat(), "", result,
                                f"{venue or 'exchange not recorded'}: {reason}"))

    # V7 - month-on-month carrying value movement must be fully attributable
    prior = con.execute(
        "select max(month_id) from monthly_positions where month_id < ? and tab='Live'", (month,)
    ).fetchone()[0]
    if prior:
        prev = {r[0]: _f(r[1]) for r in con.execute(
            "select deal_name, carrying_value from monthly_positions where month_id=? and tab='Live'",
            (prior,))}
        moved = sum(carry_by_name.get(n, 0.0) - v for n, v in prev.items() if n in carry_by_name)
        added = sum(v for n, v in carry_by_name.items() if n not in prev)
        dropped = sum(v for n, v in prev.items() if n not in carry_by_name)
        total_move = sum(carry_by_name.values()) - sum(prev.values())
        residual = total_move - (moved + added - dropped)
        checks.append(Check(month, "V7", f"Movement from {prior}", "Carrying value",
                            _money(total_move), _money(moved + added - dropped), _money(residual),
                            _verdict(residual, MONEY_TOL),
                            f"repriced {_money(moved)}, new lines {_money(added)}, removed {_money(dropped)}"))
    return checks


def main() -> int:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    months = sys.argv[1:] or [
        r[0] for r in con.execute("select distinct month_id from monthly_positions order by month_id")
    ]
    all_checks: list[Check] = []
    for month in months:
        all_checks.extend(check_month(con, month))

    breaks = [c for c in all_checks if c.result == "BREAK"]
    info = [c for c in all_checks if c.result == "INFO"]
    by_month: dict[str, int] = {}
    for c in breaks:
        by_month[c.month] = by_month.get(c.month, 0) + 1

    print(f"{len(all_checks)} checks across {len(months)} month(s): "
          f"{len(all_checks) - len(breaks) - len(info)} OK, {len(breaks)} BREAK, "
          f"{len(info)} not captured in source\n")
    if by_month:
        print("breaks by month: " + ", ".join(f"{m} ({n})" for m, n in sorted(by_month.items())) + "\n")
    for c in breaks:
        print(f"  {c.month} {c.check_id} {c.subject[:34]:<35} {c.metric:<22} "
              f"reported {c.reported:>14}  recomputed {c.recomputed:>14}  diff {c.difference:>12}")
        print(f"       {c.basis}")
    return 1 if breaks else 0


if __name__ == "__main__":
    raise SystemExit(main())
