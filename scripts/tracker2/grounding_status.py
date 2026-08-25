"""Grounding-status audit for the Company-details datapoints.

Reads the three source-of-truth company files and classifies each identity /
classification field into one of four grounding tiers, then writes a prioritised
"needs verification" queue. Read-only on inputs; writes only the report.

Tiers:
- grounded : cited to our own documents (domicile confirmed, or a
             *_grounded flag set, e.g. the Cerebras listing check).
- adopted  : the accounts pack asserted a real value we have not independently
             verified (medium confidence - adopt but confirm when convenient).
- web      : sourced from the internet (descriptive facts) - pending confirmation.
- gap      : placeholder such as "Not disclosed" / "Not assessed" / "TBC" -
             missing, needs sourcing.

Run: python -m scripts.tracker2.grounding_status
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

# Instrument qualifiers appended to a company name that we collapse so the row
# matches the consolidated domicile / descriptive-facts keys.
_QUALIFIER = re.compile(
    r"\s*\((?:\d+|warrant[^)]*|debt|equity[^)]*|tranche[^)]*|jv)\)", re.I)

SOT = Path("data/source_of_truth")
ACCOUNTS = Path("data/outputs/accounts_team/accounts_attributes.json")
DOMICILE = SOT / "company_domicile_legal.json"
FACTS = SOT / "company_descriptive_facts.json"
OUT_MD = Path("data/outputs/Grounding_Status_Report.md")
OUT_JSON = Path("data/outputs/Grounding_Status_Report.json")

# Identity / classification fields we audit (financials come from a separate
# pipeline - portfolio.sqlite / tracker - and are not audited here).
IDENTITY_FIELDS = [
    "Legal entity", "Holding type", "Sector", "Instrument", "Listed status",
    "Jurisdiction", "IFRS classification", "Valuation method",
    "Fair value hierarchy", "Influence band", "Holding", "First recognised",
]

# Substrings (lower-cased) that mark a value as a gap / placeholder.
GAP_MARKERS = (
    "not disclosed", "not covered", "not assessed", "not described",
    "pending", "tbc", "unknown", "unclear",
)
GAP_EXACT = {"", "-", "\u2014", "n/a", "na", "none", "n/d", "nd", "tbd"}


def _is_gap(value: str) -> bool:
    v = (value or "").strip().lower()
    if v in GAP_EXACT:
        return True
    return any(m in v for m in GAP_MARKERS)


def _consolidate(name: str) -> str:
    base = _QUALIFIER.sub("", name)
    return re.sub(r"\s+", " ", base).strip().rstrip(".").strip()


def _load() -> tuple[dict, dict, dict]:
    accounts_list = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    groups: dict[str, dict] = {}
    for row in accounts_list:
        name = (row.get("name") or "").strip()
        if not name or name.lower().startswith("consolidated"):
            continue
        disp = _consolidate(name)
        key = disp.lower()
        g = groups.setdefault(key, {"name": disp, "row": {}})
        # Prefer a properly-cased representative display name.
        if any(c.islower() for c in disp) and not any(c.islower() for c in g["name"]):
            g["name"] = disp
        merged = g["row"]
        for k, v in row.items():
            if k == "name":
                continue
            # Take the first non-gap value seen across the instrument rows.
            if k not in merged or (_is_gap(str(merged.get(k, ""))) and not _is_gap(str(v))):
                merged[k] = v
    domicile = json.loads(DOMICILE.read_text(encoding="utf-8"))
    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    facts = {k: v for k, v in facts.items() if not k.startswith("_")}
    return groups, domicile, facts


def audit() -> dict:
    groups, domicile, facts = _load()
    per_company: dict[str, dict] = {}
    tally = {"grounded": 0, "adopted": 0, "web": 0, "gap": 0}

    for key in sorted(groups.keys()):
        row = groups[key]["row"]
        display_name = groups[key]["name"]
        dom = domicile.get(key, {})
        fct = facts.get(key, {})
        fields: list[dict] = []

        for field in IDENTITY_FIELDS:
            if field == "Listed status" and dom.get("listed_status_grounded"):
                status, value, src = "grounded", dom["listed_status"], dom.get("listed_status_source", "our docs")
            elif field == "Jurisdiction":
                # Domicile is grounded from legal docs; confirmed vs candidate.
                dval = dom.get("domicile") or row.get("Jurisdiction", "")
                if dom.get("domicile_status") == "confirmed":
                    status, src = "grounded", dom.get("domicile_source", "legal docs")
                elif dom.get("domicile"):
                    status, src = "adopted", f"candidate: {dom.get('domicile_source', 'legal docs')}"
                else:
                    status, src = ("gap", "") if _is_gap(dval) else ("adopted", "accounts pack")
                value = dval
            else:
                value = row.get(field, "")
                if _is_gap(value):
                    status, src = "gap", ""
                else:
                    status, src = "adopted", "accounts pack"
            fields.append({"field": field, "value": value, "status": status, "source": src})
            tally[status] += 1

        # Descriptive facts (description / website / sector / hq) are web-sourced.
        if fct.get("description"):
            fields.append({"field": "Description/website", "value": fct.get("website", "(text)"),
                           "status": "web", "source": fct.get("source", "internet")})
            tally["web"] += 1

        needs = [f for f in fields if f["status"] in ("adopted", "web", "gap")]
        per_company[display_name] = {"fields": fields, "needs_verification": needs}

    return {"generated": date.today().isoformat(), "tally": tally, "companies": per_company}


def to_markdown(report: dict) -> str:
    t = report["tally"]
    total = sum(t.values())
    lines = [
        "# Grounding Status Report",
        "",
        f"Generated {report['generated']}. Read-only audit of Company-details identity / "
        "classification datapoints across our source-of-truth files.",
        "",
        "## Summary",
        "",
        f"- **{total}** identity/classification datapoints audited across "
        f"**{len(report['companies'])}** companies.",
        f"- **grounded** (cited to our own documents): **{t['grounded']}**",
        f"- **adopted** (accounts pack, unverified): **{t['adopted']}**",
        f"- **web** (internet-sourced, pending confirmation): **{t['web']}**",
        f"- **gap** (placeholder / missing): **{t['gap']}**",
        "",
        "Tiers: grounded = traceable to a cited document; adopted = taken from the "
        "accounts pack as-is; web = from the internet; gap = \"Not disclosed\" / "
        "\"Not assessed\" / \"TBC\" and similar.",
        "",
        "## Verification queue (fields that are not yet grounded)",
        "",
    ]
    # Companies with the most gaps first, then most needs.
    def _rank(item):
        needs = item[1]["needs_verification"]
        gaps = sum(1 for f in needs if f["status"] == "gap")
        return (-gaps, -len(needs), item[0])

    for name, data in sorted(report["companies"].items(), key=_rank):
        needs = data["needs_verification"]
        if not needs:
            continue
        gaps = sum(1 for f in needs if f["status"] == "gap")
        lines.append(f"### {name}  \u2014 {len(needs)} to verify ({gaps} gaps)")
        lines.append("")
        lines.append("| Field | Current value | Tier | Note |")
        lines.append("|---|---|---|---|")
        for f in needs:
            val = (f["value"] or "").replace("|", "\\|")
            src = (f["source"] or "").replace("|", "\\|")
            lines.append(f"| {f['field']} | {val or '(blank)'} | {f['status']} | {src} |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    report = audit()
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_MD.write_text(to_markdown(report), encoding="utf-8")
    t = report["tally"]
    print(f"Audited {len(report['companies'])} companies.")
    print(f"  grounded={t['grounded']}  adopted={t['adopted']}  web={t['web']}  gap={t['gap']}")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
