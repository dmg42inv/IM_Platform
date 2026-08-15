"""Adapter for extracting canonical cashflow/valuation records from the monthly
Portfolio Summary tracker workbook.

Scope (per agreed source-of-truth split):
- Only the "CF (Equity, Debt)" and "CF (Funds)" tabs are treated as authoritative
  cash flow sources (owned/updated monthly by Treasury).
- Only the "NAV" tab is treated as the authoritative valuation source (owned/
  updated monthly by the Valuation team).
- All other tabs (Live, Exited, %, E. Board, etc.) are downstream reports and
  must NOT be used as input here.

`investment_id` in the output is the raw investment/company name as it appears
in the tracker. It is a provisional natural key until the structural
Investment Register (built ab initio from deal documents) assigns canonical
investment_id values and a name-to-id mapping is applied.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _norm(value: object) -> str:
    return str(value).strip().lower() if pd.notna(value) else ""


def _find_header_row(raw: pd.DataFrame, anchor_labels: list[str]) -> int:
    """Find the row index whose cells contain every anchor label (case-insensitive)."""
    anchors = {a.lower() for a in anchor_labels}
    for idx in range(len(raw)):
        cells = {_norm(v) for v in raw.iloc[idx].tolist()}
        if anchors.issubset(cells):
            return idx
    raise ValueError(f"Could not find a header row containing all of: {anchor_labels}")


def _col_map(raw: pd.DataFrame, header_row: int) -> dict[str, int]:
    return {_norm(v): idx for idx, v in raw.iloc[header_row].items() if pd.notna(v)}


def _require_col(col_map: dict[str, int], label: str) -> int:
    key = label.lower()
    if key not in col_map:
        raise KeyError(f"Expected column '{label}' not found in tracker sheet header")
    return col_map[key]


def _finalize_usd_amount(df: pd.DataFrame, currency_col: str) -> pd.DataFrame:
    # Treasury does not retain the local amount/FX rate used for non-USD deals,
    # only the resulting USD figure. We keep the original currency for
    # traceability but treat the amount itself as canonical USD (fx_to_usd=1.0)
    # rather than raising a MissingFX exception we can never resolve.
    df["source_currency"] = df[currency_col]
    df[currency_col] = "USD"
    df["fx_to_usd"] = 1.0
    return df


def extract_equity_debt_cashflows(path: Path, sheet_name: str = "CF (Equity, Debt)") -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    header_row = _find_header_row(raw, ["investment", "payment date", "currency"])
    cols = _col_map(raw, header_row)

    c_entity = _require_col(cols, "Accounting entity")
    c_investment = _require_col(cols, "Investment")
    c_date = _require_col(cols, "Payment date")
    c_contrib = _require_col(cols, "Contributions (in USD, Mn)")
    c_distrib = _require_col(cols, "Distributions (in USD, Mn)")
    c_currency = _require_col(cols, "Currency")

    data = raw.iloc[header_row + 1 :].copy()
    data["flow_date"] = pd.to_datetime(data[c_date], errors="coerce")
    data = data[data["flow_date"].notna()].reset_index(drop=True)

    contrib = pd.to_numeric(data[c_contrib], errors="coerce").fillna(0.0)
    distrib = pd.to_numeric(data[c_distrib], errors="coerce").fillna(0.0)
    signed_amount_mn = contrib + distrib

    out = pd.DataFrame(
        {
            "cashflow_id": [f"TRK-CF-EQ-{i + 1:04d}" for i in range(len(data))],
            "investment_id": data[c_investment].astype(str).str.strip(),
            "flow_date": data["flow_date"].dt.strftime("%Y-%m-%d"),
            "flow_type": ["Deployment" if v < 0 else "Distribution" for v in signed_amount_mn],
            "amount": signed_amount_mn * 1_000_000,
            "currency": data[c_currency].astype(str).str.strip().str.upper(),
            "fx_rate_date": data["flow_date"].dt.strftime("%Y-%m-%d"),
            "fx_rate_source": "Monthly Tracker (Treasury), pre-converted to USD; local rate not retained",
            "source_reference": data[c_entity].astype(str).str.strip() + " | " + sheet_name,
            "approval_status": "Approved",
        }
    )
    return _finalize_usd_amount(out, "currency")


def extract_fund_cashflows(path: Path, sheet_name: str = "CF (Funds)") -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    header_row = _find_header_row(raw, ["investment", "payment date", "cashflows"])
    cols = _col_map(raw, header_row)

    c_entity = _require_col(cols, "Entity")
    c_investment = _require_col(cols, "Investment")
    c_date = _require_col(cols, "Payment date")
    c_cashflows = _require_col(cols, "Cashflows")
    c_currency = _require_col(cols, "Currency")
    c_description = _require_col(cols, "Description")

    data = raw.iloc[header_row + 1 :].copy()
    data["flow_date"] = pd.to_datetime(data[c_date], errors="coerce")
    data = data[data["flow_date"].notna()].reset_index(drop=True)

    amount_mn = pd.to_numeric(data[c_cashflows], errors="coerce").fillna(0.0)
    description = data[c_description].astype(str).str.strip().str.lower()

    def _flow_type(desc: str, amt: float) -> str:
        if "capital call" in desc:
            return "CapitalCall"
        if "return" in desc or "distribution" in desc:
            return "Distribution"
        if "interest" in desc:
            return "Fee"
        return "Deployment" if amt < 0 else "Distribution"

    out = pd.DataFrame(
        {
            "cashflow_id": [f"TRK-CF-FD-{i + 1:04d}" for i in range(len(data))],
            "investment_id": data[c_investment].astype(str).str.strip(),
            "flow_date": data["flow_date"].dt.strftime("%Y-%m-%d"),
            "flow_type": [_flow_type(d, a) for d, a in zip(description, amount_mn)],
            "amount": amount_mn * 1_000_000,
            "currency": data[c_currency].astype(str).str.strip().str.upper(),
            "fx_rate_date": data["flow_date"].dt.strftime("%Y-%m-%d"),
            "fx_rate_source": "Monthly Tracker (Treasury), pre-converted to USD; local rate not retained",
            "source_reference": data[c_entity].astype(str).str.strip() + " | " + sheet_name,
            "approval_status": "Approved",
        }
    )
    return _finalize_usd_amount(out, "currency")


def _extract_nav_as_of_date(raw: pd.DataFrame) -> pd.Timestamp:
    for idx in range(min(10, len(raw))):
        row = raw.iloc[idx].tolist()
        for pos, val in enumerate(row):
            if _norm(val) == "nav date":
                for next_val in row[pos + 1 :]:
                    if pd.notna(next_val):
                        return pd.to_datetime(next_val)
    raise ValueError("Could not locate 'NAV Date' cell in NAV sheet")


def extract_nav_valuations(path: Path, sheet_name: str = "NAV") -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    as_of_date = _extract_nav_as_of_date(raw)

    header_row = _find_header_row(raw, ["investments", "carrying value"])
    cols = _col_map(raw, header_row)

    c_investment = _require_col(cols, "Investments")
    c_carrying = _require_col(cols, "Carrying Value")
    c_comment = _require_col(cols, "Comment")

    data = raw.iloc[header_row + 1 :].copy()
    carrying = pd.to_numeric(data[c_carrying], errors="coerce")
    keep = data[c_investment].notna() & carrying.notna()
    data = data[keep].reset_index(drop=True)
    carrying = carrying[keep.values].reset_index(drop=True)
    as_of_str = as_of_date.strftime("%Y-%m-%d")

    return pd.DataFrame(
        {
            "valuation_id": [f"TRK-VAL-{i + 1:04d}" for i in range(len(data))],
            "investment_id": data[c_investment].astype(str).str.strip(),
            "valuation_date": as_of_str,
            "fair_value_local": carrying * 1_000_000,
            "valuation_currency": "USD",
            "fx_to_usd": 1.0,
            "fx_rate_date": as_of_str,
            "fx_rate_source": "Monthly Tracker (Valuation team)",
            "valuation_method": "NAVLookThrough",
            "assumption_note": data[c_comment].where(data[c_comment].notna(), "").astype(str),
            "reviewer": "Unknown",
            "approver": "Unknown",
            "valuation_status": "Approved",
        }
    )


def load_tracker_cashflows(path: Path) -> pd.DataFrame:
    equity_debt = extract_equity_debt_cashflows(path)
    funds = extract_fund_cashflows(path)
    return pd.concat([equity_debt, funds], ignore_index=True)


def load_tracker_valuations(path: Path) -> pd.DataFrame:
    return extract_nav_valuations(path)
