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

    def npv(rate: float) -> float:
        t0 = cashflows[0][0]
        return sum(v / ((1 + rate) ** ((d - t0).days / 365.0)) for d, v in cashflows)

    rate = 0.1
    for _ in range(80):
        t0 = cashflows[0][0]
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
        if abs(new_rate - rate) < 1e-8:
            return new_rate
        rate = new_rate

    return None


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
            "watchlist_flag",
        ]
    ].rename(columns={"entity_id": "company_name", "fund_vehicle_id": "fund_vehicle"})

    return out


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
