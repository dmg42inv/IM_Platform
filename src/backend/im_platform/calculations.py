from __future__ import annotations

from datetime import datetime

import pandas as pd


def _xirr(cashflows: list[tuple[datetime, float]]) -> float | None:
    if len(cashflows) < 2:
        return None

    has_pos = any(v > 0 for _, v in cashflows)
    has_neg = any(v < 0 for _, v in cashflows)
    if not (has_pos and has_neg):
        return None

    t0 = cashflows[0][0]

    def npv(rate: float) -> float:
        return sum(v / ((1 + rate) ** ((d - t0).days / 365.0)) for d, v in cashflows)

    # Newton-Raphson first (fast, exact when it converges).
    rate = 0.1
    for _ in range(80):
        f = 0.0
        df = 0.0
        for d, v in cashflows:
            y = (d - t0).days / 365.0
            denom = (1 + rate) ** y
            f += v / denom
            if rate > -0.999999:
                df -= (y * v) / ((1 + rate) ** (y + 1))
        if abs(df) < 1e-12:
            break
        new_rate = rate - f / df
        if new_rate <= -0.999999:
            break  # would go out of domain - fall through to bisection below
        if abs(new_rate - rate) < 1e-8:
            return new_rate
        rate = new_rate

    # Bisection fallback: Newton-Raphson can fail to converge (and silently
    # return None) for extreme cases - e.g. a large realized/unrealized loss
    # where the true IRR is a large negative number close to -100%. Bisection
    # is slower but far more robust as long as npv() changes sign somewhere
    # in a wide bracket, which it always does for a genuine loss or gain.
    lo, hi = -0.999999, 100.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if (f_lo > 0) == (f_hi > 0):
        return None  # no sign change in the bracket - genuinely unsolvable
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if f_mid == 0 or (hi - lo) < 1e-10:
            return mid
        if (f_lo > 0) == (f_mid > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


def _to_usd_amount(df: pd.DataFrame, amount_col: str, currency_col: str, fx_col: str) -> pd.Series:
    currency = df[currency_col].astype(str).str.upper()
    usd = df[amount_col].astype(float)
    fx = pd.to_numeric(df[fx_col], errors="coerce")
    converted = usd.where(currency == "USD", usd * fx)
    return converted.fillna(0.0)


def build_portfolio_snapshot(
    investments: pd.DataFrame,
    valuations: pd.DataFrame,
    monitoring: pd.DataFrame,
    cashflow: pd.DataFrame,
) -> pd.DataFrame:
    valuations = valuations.copy()
    valuations["fair_value_usd"] = _to_usd_amount(
        valuations, "fair_value_local", "valuation_currency", "fx_to_usd"
    )
    latest_val = valuations.sort_values("valuation_date").groupby("investment_id", as_index=False).tail(1)

    latest_mon = (
        monitoring.sort_values("as_of_date").groupby("investment_id", as_index=False).tail(1)
    )

    snapshot = investments.merge(
        latest_val[["investment_id", "fair_value_local", "valuation_currency", "fair_value_usd"]],
        on="investment_id",
        how="left",
    ).merge(
        latest_mon[["investment_id", "watchlist_flag"]],
        on="investment_id",
        how="left",
    )

    snapshot["invested_cost_local"] = pd.to_numeric(snapshot["initial_commitment_amount"], errors="coerce").fillna(0.0)
    snapshot["invested_cost_currency"] = snapshot["investment_currency"]

    cf = cashflow.copy()
    cf["amount_usd"] = _to_usd_amount(cf, "amount", "currency", "fx_to_usd")
    invested_by_cf = (
        cf[cf["amount_usd"] < 0]
        .groupby("investment_id", as_index=False)["amount_usd"]
        .sum()
        .rename(columns={"amount_usd": "invested_cost_base"})
    )
    invested_by_cf["invested_cost_base"] = -invested_by_cf["invested_cost_base"]
    snapshot = snapshot.merge(invested_by_cf, on="investment_id", how="left")
    snapshot["invested_cost_base"] = snapshot["invested_cost_base"].fillna(0.0)
    snapshot["latest_fair_value_local"] = snapshot["fair_value_local"].fillna(0.0)
    snapshot["latest_fair_value_currency"] = snapshot["valuation_currency"].fillna(snapshot["investment_currency"])
    snapshot["latest_fair_value_base"] = snapshot["fair_value_usd"].fillna(0.0)
    snapshot["unrealized_gain_loss_base"] = (
        snapshot["latest_fair_value_base"] - snapshot["invested_cost_base"]
    )

    for col in ["entity_id", "fund_vehicle_id", "instrument_type", "lifecycle_state", "close_date", "watchlist_flag"]:
        if col not in snapshot:
            snapshot[col] = ""

    if "ownership_pct_fully_diluted" not in snapshot:
        snapshot["ownership_pct_fully_diluted"] = pd.NA

    out = snapshot[
        [
            "investment_id",
            "entity_id",
            "fund_vehicle_id",
            "instrument_type",
            "lifecycle_state",
            "close_date",
            "invested_cost_local",
            "invested_cost_currency",
            "invested_cost_base",
            "latest_fair_value_local",
            "latest_fair_value_currency",
            "latest_fair_value_base",
            "unrealized_gain_loss_base",
            "ownership_pct_fully_diluted",
            "watchlist_flag",
        ]
    ].rename(
        columns={
            "entity_id": "company_name",
            "fund_vehicle_id": "fund_vehicle",
            "ownership_pct_fully_diluted": "ownership_pct_fully_diluted_latest",
        }
    )

    return out


def build_pipeline_and_lifecycle(investments: pd.DataFrame) -> pd.DataFrame:
    """One-row summary of the register's lifecycle_state distribution, per
    V1 Output Pack Spec section 2.3. Stage conversion rates use Sourced as
    the funnel denominator when present; otherwise the metric is left null
    since sourced/dropped counts require pipeline-stage data not yet tracked."""
    counts = investments["lifecycle_state"].value_counts() if len(investments) else pd.Series(dtype=int)

    def _count(state: str) -> int:
        return int(counts.get(state, 0))

    sourced = _count("Sourced")
    approved = _count("Approved")
    live = _count("Live")
    dropped = _count("Dropped")
    partially_exited = _count("PartiallyExited")
    exited = _count("Exited")

    approval_rate = (approved / sourced) if sourced else None
    live_conversion_rate = (live / sourced) if sourced else None

    return pd.DataFrame(
        [
            {
                "sourced_count": sourced,
                "dropped_count": dropped,
                "approved_count": approved,
                "live_count": live,
                "partially_exited_count": partially_exited,
                "exited_count": exited,
                "stage_conversion_rate_approved": round(approval_rate, 4) if approval_rate is not None else None,
                "stage_conversion_rate_live": round(live_conversion_rate, 4) if live_conversion_rate is not None else None,
                "median_time_to_decision_days": None,
            }
        ]
    )


def build_returns_summary(cashflow: pd.DataFrame, valuations: pd.DataFrame) -> pd.DataFrame:
    cf = cashflow.copy()
    cf["amount_usd"] = _to_usd_amount(cf, "amount", "currency", "fx_to_usd")
    cf["flow_date"] = pd.to_datetime(cf["flow_date"], errors="coerce")

    latest_val = valuations.copy()
    latest_val["fair_value_usd"] = _to_usd_amount(
        latest_val, "fair_value_local", "valuation_currency", "fx_to_usd"
    )
    latest_val["valuation_date"] = pd.to_datetime(latest_val["valuation_date"], errors="coerce")
    latest_val = latest_val.sort_values("valuation_date").groupby("investment_id", as_index=False).tail(1)

    rows = []
    for inv_id, group in cf.groupby("investment_id"):
        paid_in = -group.loc[group["amount_usd"] < 0, "amount_usd"].sum()
        distributed = group.loc[group["amount_usd"] > 0, "amount_usd"].sum()

        val_row = latest_val[latest_val["investment_id"] == inv_id]
        residual = float(val_row["fair_value_usd"].iloc[0]) if not val_row.empty else 0.0
        terminal_date = (
            pd.Timestamp(val_row["valuation_date"].iloc[0])
            if not val_row.empty
            else group["flow_date"].max()
        )

        tvpi = (distributed + residual) / paid_in if paid_in else None
        dpi = distributed / paid_in if paid_in else None
        moic = (distributed + residual) / paid_in if paid_in else None

        cf_points = [(d.to_pydatetime(), float(a)) for d, a in zip(group["flow_date"], group["amount_usd"]) if pd.notna(d)]
        if terminal_date is not pd.NaT and residual:
            cf_points.append((pd.Timestamp(terminal_date).to_pydatetime(), residual))
        cf_points = sorted(cf_points, key=lambda x: x[0])

        irr = _xirr(cf_points)

        rows.append(
            {
                "investment_id": inv_id,
                "PaidIn": round(paid_in, 2),
                "Distributed": round(distributed, 2),
                "ResidualValue": round(residual, 2),
                "TVPI": round(tvpi, 4) if tvpi is not None else None,
                "DPI": round(dpi, 4) if dpi is not None else None,
                "MOIC": round(moic, 4) if moic is not None else None,
                "IRR": round(irr, 6) if irr is not None else None,
            }
        )

    return pd.DataFrame(rows)
