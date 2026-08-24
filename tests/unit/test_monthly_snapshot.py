from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from im_platform.adapters.monthly_snapshot import (
    build_monthly_diff,
    build_monthly_snapshot,
    upsert_snapshot_history,
    write_snapshot_outputs,
)


def _deals(carrying_value: float, tab: str = "Live") -> pd.DataFrame:
    return pd.DataFrame([
        {
            "tab": tab,
            "section": "Section A",
            "deal_name": "Company A",
            "status": "Unrealized" if tab == "Live" else "Realized",
            "investing_entity": "G42 Holding",
            "vintage": "2025",
            "instrument": "Equity",
            "committed": 10.0,
            "invested": 8.0,
            "remaining_commitment": 2.0 if tab == "Live" else 0.0,
            "distributions": 1.0,
            "carrying_value": carrying_value,
            "gain": carrying_value + 1.0 - 8.0,
            "tvpi": (carrying_value + 1.0) / 8.0,
            "irr": 0.12,
            "valuation_date": "2026-07-31",
            "assumption_note": "Latest approved NAV.",
        }
    ])


def test_snapshot_history_replaces_same_month_and_diff_detects_change() -> None:
    july = build_monthly_snapshot(_deals(12.0), "2026-07-31")
    july_rerun = build_monthly_snapshot(_deals(13.0), "2026-07-31")
    august = build_monthly_snapshot(_deals(14.5), "2026-08-31")

    history = upsert_snapshot_history(pd.DataFrame(), july)
    history = upsert_snapshot_history(history, july_rerun)
    history = upsert_snapshot_history(history, august)
    diff = build_monthly_diff(history)

    assert len(history[history["snapshot_month"] == "2026-07"]) == 1
    assert history.loc[history["snapshot_month"] == "2026-07", "carrying_value"].iloc[0] == pytest.approx(13.0)
    assert len(diff) == 1
    assert diff.iloc[0]["change_type"] == "Changed"
    assert "carrying_value" in diff.iloc[0]["changed_metrics"]
    assert diff.iloc[0]["delta_carrying_value"] == pytest.approx(1.5)


def test_write_snapshot_outputs_creates_history_and_diff_workbooks(tmp_path: Path) -> None:
    history_path = tmp_path / "Portfolio_Snapshot_History.xlsx"
    diff_path = tmp_path / "Portfolio_Monthly_Diff.xlsx"

    write_snapshot_outputs(build_monthly_snapshot(_deals(12.0), "2026-07-31"), history_path, diff_path)
    history, diff = write_snapshot_outputs(build_monthly_snapshot(_deals(14.0, tab="Exited"), "2026-08-31"), history_path, diff_path)

    assert history_path.exists()
    assert diff_path.exists()
    assert len(history) == 2
    assert len(diff) == 1
    assert diff.iloc[0]["change_type"] == "Exited"