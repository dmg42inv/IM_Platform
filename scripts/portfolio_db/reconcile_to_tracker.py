"""Full Aug'26 reconciliation: IM Platform database vs the certified accounts tracker.

Compares every live position on carrying value, invested, committed and distributions.
The tracker reports MGX I LP and its Denali AIV as one line; the database holds them
separately, so they are combined here to compare like with like.
"""
import csv
import sqlite3
from decimal import Decimal as D
from pathlib import Path

DB = Path(r"C:\Users\divyesh.mahajan\Documents\3. Portfolio Reporting\IM_Platform\data\portfolio\portfolio.sqlite")
CERT = Path(
    r"C:\Users\divyesh.mahajan\Documents\3. Portfolio Reporting\IM_Platform Accounts team"
    r"\investment-dashboard\data\processed\aug26_certified_position_layer.csv"
)
TOL = D("0.0005")

ALIAS = {"MGX I LP": "MGX I LP + Denali", "MGX I Denali Holding LP": "MGX I LP + Denali"}

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
im: dict[str, dict[str, D]] = {}
for name, cmt, inv, dist, cv in con.execute(
    "select deal_name, committed, invested, distributions, carrying_value"
    " from monthly_positions where month_id='2026-08' and tab='Live'"
):
    key = ALIAS.get(name, name)
    b = im.setdefault(key, {"committed": D(0), "invested": D(0), "distributions": D(0), "carrying_value": D(0)})
    for f, v in (("committed", cmt), ("invested", inv), ("distributions", dist), ("carrying_value", cv)):
        b[f] += D(str(v or 0))

cert: dict[str, dict[str, D]] = {}
with CERT.open(encoding="utf-8-sig", newline="") as fh:
    for r in csv.DictReader(fh):
        cert[r["investment_name"]] = {
            "committed": D(r["committed_usdm"] or 0),
            "invested": D(r["invested_usdm"] or 0),
            "distributions": D(r["distributions_usdm"] or 0),
            "carrying_value": D(r["carrying_value_usdm"] or 0),
        }

names = sorted(set(im) | set(cert), key=lambda n: -float(cert.get(n, im.get(n, {})).get("carrying_value", 0)))
print(f"{'Position':<34}{'IM carrying':>13}{'Tracker':>13}{'Diff':>12}   Other differences")
print("-" * 108)
agree = 0
diffs: list[tuple[str, str, D, D]] = []
for n in names:
    a, b = im.get(n), cert.get(n)
    if a is None:
        print(f"{n[:33]:<34}{'not in DB':>13}{float(b['carrying_value']):>13,.3f}{'':>12}   MISSING FROM DATABASE")
        continue
    if b is None:
        print(f"{n[:33]:<34}{float(a['carrying_value']):>13,.3f}{'not in tracker':>13}{'':>12}   EXTRA IN DATABASE")
        continue
    dcv = a["carrying_value"] - b["carrying_value"]
    others = [f"{f} {float(a[f]):,.3f} vs {float(b[f]):,.3f}"
              for f in ("committed", "invested", "distributions") if abs(a[f] - b[f]) > TOL]
    if abs(dcv) <= TOL and not others:
        agree += 1
        continue
    diffs.append((n, "; ".join(others), a["carrying_value"], b["carrying_value"]))
    print(f"{n[:33]:<34}{float(a['carrying_value']):>13,.3f}{float(b['carrying_value']):>13,.3f}"
          f"{float(dcv):>12,.3f}   {'; '.join(others)}")

if not diffs:
    print("  (no position-level differences)")

print("-" * 108)
print(f"\n  positions agreeing on every metric : {agree} of {len(names)}")
for label, field in (("Carrying value", "carrying_value"), ("Invested", "invested"),
                     ("Committed", "committed"), ("Distributions", "distributions")):
    ia = sum((v[field] for v in im.values()), D(0))
    ca = sum((v[field] for v in cert.values()), D(0))
    flag = "" if abs(ia - ca) <= TOL else "   <-- DIFFERS"
    print(f"  {label:<20} IM {float(ia):>12,.3f}   tracker {float(ca):>12,.3f}   diff {float(ia-ca):>10,.3f}{flag}")
