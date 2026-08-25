"""Line-by-line bridge between the two valuation bases for the same book:
- Live-register basis  -> data/portfolio/portfolio.sqlite (Overview / native views)
- NAV-tab + CAS basis  -> parsed from the operational dashboard's Live table

Prints per-holding invested and carrying on both bases with the deltas, so we
can see exactly which holdings drive the gap. Read-only.
"""

from __future__ import annotations

import html as _html
import json
import re
import sqlite3
from pathlib import Path

import pandas as pd

HTML = Path("data/outputs/Tracker_Style_Dashboard.html")
DB = Path("data/portfolio/portfolio.sqlite")

_TAG = re.compile(r"<[^>]+>")


def _cell_text(td: str) -> str:
    return _html.unescape(_TAG.sub("", td)).strip()


def parse_live_table() -> pd.DataFrame:
    text = HTML.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"id='table-live'.*?<tbody>(.*?)</tbody>", text, re.S)
    if not m:
        return pd.DataFrame()
    body = m.group(1)
    rows = re.findall(r"<tr([^>]*)>(.*?)</tr>", body, re.S)
    out = []
    for attrs, r in rows:
        if any(k in attrs for k in ("section-header", "subtotal", "grand-total")):
            continue
        tds = re.findall(r"<td.*?</td>", r, re.S)
        cells = [_cell_text(td) for td in tds]
        if len(cells) < 11:
            continue
        # Deal, Status, Entity, Vintage, Instrument, Committed, Invested,
        # Remaining, Distributions, Carrying, Gain, TVPI, IRR
        name = cells[0]

        def _num(s: str) -> float:
            s = s.replace(",", "").replace("$", "")
            try:
                return float(s)
            except ValueError:
                return float("nan")

        out.append({"name": name, "invested_nav": _num(cells[6]),
                    "carrying_nav": _num(cells[9])})
    return pd.DataFrame(out)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def main() -> None:
    nav = parse_live_table()
    print(f"Parsed {len(nav)} rows from the operational Live table (NAV+CAS basis).")
    c = sqlite3.connect(DB)
    mid = pd.read_sql_query("SELECT MAX(month_id) m FROM monthly_positions", c)["m"].iloc[0]
    live = pd.read_sql_query(
        "SELECT deal_name, invested AS invested_live, carrying_value AS carrying_live "
        f"FROM monthly_positions WHERE month_id='{mid}' AND tab='Live'", c)

    nav["k"] = nav["name"].map(_norm)
    live["k"] = live["deal_name"].map(_norm)
    m = live.merge(nav, on="k", how="outer")
    m["inv_delta"] = m["invested_nav"] - m["invested_live"]
    m["cv_delta"] = m["carrying_nav"] - m["carrying_live"]

    show = m.sort_values("cv_delta", key=lambda s: s.abs(), ascending=False)
    cols = ["deal_name", "name", "invested_live", "invested_nav", "inv_delta",
            "carrying_live", "carrying_nav", "cv_delta"]
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 60)
    print(show[cols].round(1).to_string(index=False))
    print("\nTOTALS:")
    print(f"  Invested  Live={m['invested_live'].sum():9.1f}  NAV+CAS={m['invested_nav'].sum():9.1f}  "
          f"delta={m['inv_delta'].sum():9.1f}")
    print(f"  Carrying  Live={m['carrying_live'].sum():9.1f}  NAV+CAS={m['carrying_nav'].sum():9.1f}  "
          f"delta={m['cv_delta'].sum():9.1f}")

    def _r(v):
        return None if pd.isna(v) else round(float(v), 1)

    drivers = [
        {"holding": (r["deal_name"] if pd.notna(r["deal_name"]) else r["name"]),
         "invested_live": _r(r["invested_live"]), "invested_nav": _r(r["invested_nav"]),
         "inv_delta": _r(r["inv_delta"]), "carrying_live": _r(r["carrying_live"]),
         "carrying_nav": _r(r["carrying_nav"]), "cv_delta": _r(r["cv_delta"])}
        for _, r in show.iterrows()
        if pd.isna(r["cv_delta"]) or abs(r["cv_delta"]) > 0.05
        or pd.isna(r["inv_delta"]) or abs(r["inv_delta"]) > 0.05
    ]
    payload = {
        "drivers": drivers,
        "totals": {
            "invested_live": _r(m["invested_live"].sum()), "invested_nav": _r(m["invested_nav"].sum()),
            "carrying_live": _r(m["carrying_live"].sum()), "carrying_nav": _r(m["carrying_nav"].sum()),
        },
        "n_holdings": int(m["deal_name"].notna().sum()),
        "n_tie": int(((m["cv_delta"].abs() <= 0.05) & m["deal_name"].notna()).sum()),
    }
    Path("data/portfolio/basis_bridge.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")
    print("Wrote data/portfolio/basis_bridge.json")


if __name__ == "__main__":
    main()
