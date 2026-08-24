"""Extract accounts-team per-holding attributes (IFRS classification, valuation
method, and related descriptive fields) from the Pack HTML, keyed by holding
name, so Tracker 2 can adopt the accountants' classifications while keeping all
economics grounded in our own July data.

Read-only. Writes a mapping JSON we can review before wiring anything in.
"""

from __future__ import annotations

import html as _html
import json
import re
import sqlite3
from pathlib import Path

import pandas as pd

PACK = Path("Accounts Team, G42_Investment_Portfolio_Dashboard_v2.3_21082026.html")
DB = Path("data/portfolio/portfolio.sqlite")

# Attributes we treat as owned by the accounts team (stable classifications), NOT
# their June economics.
WANTED = [
    "IFRS classification", "Investment type", "Valuation method", "Valuation input",
    "Fair value hierarchy", "Valuation basis", "Sub-group", "Holding type",
    "Influence band", "Jurisdiction", "Region", "Sector",
]

_PANEL_RE = re.compile(r'id="p-all-inv-[^"]*">(.*?)(?=<div class="panel" id="p-all-inv-|<div class="panel" id="p-g42-inv-|</main>)', re.S)
_SB_RE = re.compile(r'<div class="sb">(.*?)</div>', re.S)
_H2_RE = re.compile(r"<h2>(.*?)</h2>", re.S)
_DEF_RE = re.compile(r"<dt>(.*?)</dt><dd>(.*?)</dd>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    return _html.unescape(_TAG_RE.sub("", s)).strip()


def extract() -> list[dict]:
    text = PACK.read_text(encoding="utf-8", errors="replace")
    out = []
    for block in _PANEL_RE.findall(text):
        name_m = _SB_RE.search(block) or _H2_RE.search(block)
        if not name_m:
            continue
        name = _clean(name_m.group(1))
        # Capture the full identity + measurement deflist for each holding.
        defs = {_clean(k): _clean(v) for k, v in _DEF_RE.findall(block)}
        out.append({"name": name, **defs})
    return out


def our_holdings() -> list[str]:
    if not DB.exists():
        return []
    with sqlite3.connect(DB) as c:
        mid = pd.read_sql_query("SELECT MAX(month_id) m FROM monthly_positions", c)["m"].iloc[0]
        df = pd.read_sql_query(
            "SELECT DISTINCT deal_name FROM monthly_positions "
            f"WHERE month_id='{mid}' AND tab='Live'", c)
    return sorted(df["deal_name"].tolist())


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main() -> None:
    rows = extract()
    print(f"Extracted {len(rows)} holdings from the Pack (all-scope panels).")
    live = our_holdings()
    print(f"Our live holdings: {len(live)}")

    pack_norm = { _norm(r["name"]): r for r in rows }
    matched, unmatched = [], []
    for h in live:
        key = _norm(h)
        hit = pack_norm.get(key)
        if not hit:
            hit = next((r for k, r in pack_norm.items() if key in k or k in key), None)
        if hit:
            matched.append((h, hit))
        else:
            unmatched.append(h)

    print(f"\nMATCHED {len(matched)}/{len(live)}:")
    for h, r in matched:
        print(f"  {h:42s} | IFRS={r.get('IFRS classification','?'):8s} | "
              f"Val={r.get('Valuation method','?')}")
    print(f"\nUNMATCHED (need pointer / pending) {len(unmatched)}:")
    for h in unmatched:
        print(f"  {h}")

    Path("data/outputs/accounts_team").mkdir(parents=True, exist_ok=True)
    outp = Path("data/outputs/accounts_team/accounts_attributes.json")
    outp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nWrote {outp}")


if __name__ == "__main__":
    main()
