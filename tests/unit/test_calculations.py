from __future__ import annotations

import pandas as pd
import pytest

from im_platform.calculations import build_portfolio_snapshot, build_returns_summary


def test_returns_summary_and_snapshot_usd_conversion() -> None:
    investments = pd.DataFrame(
        [
            {
                "investment_id": "INV-1",
                "entity_id": "Company A",
                "fund_vehicle_id": "Fund I",
                "instrument_type": "Equity",
                "initial_commitment_amount": 1000000,
                "investment_currency": "EUR",
                "close_date": "2025-01-10",
                "lifecycle_state": "Live",
                "lifecycle_state_date": "2025-01-10",
            }
        ]
    )

    cashflow = pd.DataFrame(
        [
            {
                "cashflow_id": "CF-1",
                "investment_id": "INV-1",
                "flow_date": "2025-01-10",
                "flow_type": "Deployment",
                "amount": -1000000,
                "currency": "EUR",
                "fx_to_usd": 1.1,
                "fx_rate_date": "2025-01-10",
                "fx_rate_source": "ECB",
                "approval_status": "Approved",
            },
            {
                "cashflow_id": "CF-2",
                "investment_id": "INV-1",
                "flow_date": "2026-01-10",
                "flow_type": "Distribution",
                "amount": 200000,
                "currency": "USD",
                "fx_to_usd": None,
                "fx_rate_date": None,
                "fx_rate_source": None,
                "approval_status": "Approved",
            },
        ]
    )

    valuations = pd.DataFrame(
        [
            {
                "valuation_id": "V-1",
                "investment_id": "INV-1",
                "valuation_date": "2026-06-30",
                "fair_value_local": 900000,
                "valuation_currency": "EUR",
                "fx_to_usd": 1.15,
                "fx_rate_date": "2026-06-30",
                "fx_rate_source": "ECB",
                "valuation_status": "Approved",
            }
        ]
    )

    monitoring = pd.DataFrame(
        [
            {
                "monitoring_id": "M-1",
                "investment_id": "INV-1",
                "as_of_date": "2026-06-30",
                "watchlist_flag": "No",
                "covenant_status": "Green",
                "milestone_status": "OnTrack",
            }
        ]
    )

    snapshot = build_portfolio_snapshot(investments, valuations, monitoring, cashflow)
    returns = build_returns_summary(cashflow, valuations)

    assert len(snapshot) == 1
    assert snapshot.iloc[0]["invested_cost_base"] == pytest.approx(1100000.0)
    assert snapshot.iloc[0]["latest_fair_value_base"] == pytest.approx(1035000.0)

    assert len(returns) == 1
    assert returns.iloc[0]["PaidIn"] == pytest.approx(1100000.0)
    assert returns.iloc[0]["Distributed"] == pytest.approx(200000.0)
    assert returns.iloc[0]["ResidualValue"] == pytest.approx(1035000.0)
