"""Export grounded domicile candidates per tracker company to a JSON the
dashboard can read.

Domicile is a legal fact, so it must come from the original documents in the
legal knowledge base - never the tracker. This script maps each tracker
(consolidated) company name to its knowledge-base transaction, runs the
grounded `find_domicile` extraction, keeps only results that resolve to a
recognised jurisdiction (suppressing noisy captures), and writes each with its
citation and a `candidate` status so the analyst can confirm before it is
treated as final.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.legal_kb.domicile import _CANON, _KNOWN_LOWER, find_domicile

# Consolidated (lowercased) tracker company name -> KB transaction_id.
# Companies with no legal-KB folder are omitted (they fall back to the
# tracker value, flagged, on the dashboard).
DEAL_TO_TRANSACTION: dict[str, str] = {
    "school hack (airev holding limited)": "school_hack",
    "inveniam ltd": "inveniam",
    "life biosciences llc": "life_biosciences",
    "liquid ai": "liquid_ai",
    "neuralink": "neuralink_project_cortex",
    "verses ai inc": "verses_project_bayes",
    "acies investments fund i, l.p.": "3_acies",
    "drivenets": "drivenets",
    "new space capital fund i": "1_new_space_capital_fund",
    "new space capital gp com scsp": "1_new_space_capital_fund",
    "north summit capital fund": "2_north_summit_capital_fund",
    "vtv therapeutics inc.": "vtvt_vtv_therapeutics",
    "mgx 1 strategic co-invest": "4_mgx",
    "mgx group holding 1 ltd (gp)": "4_mgx",
    "mgx i denali holding lp": "4_mgx",
    "mgx i lp": "4_mgx",
    "applied ai corporation limited": "aaico_desktop",
    "beyond limits": "beyond_limits",
    "cerebras systems inc": "cerebras",
    "e-line ventures llc": "endless_matt_dalio_and_e_line",
    "endless studios llc": "endless_matt_dalio_and_e_line",
    "flyr inc": "flyr",
    "heygears": "heygears",
    "ont plc": "ont",
    "tools for humanity corporation": "tfh_worldcoin",
    "espace": "e_space",
    "sinovation disrupt fund, l.p.": "2_sinovation_disrupt_fund",
    "esyasoft holding": "esyasoft",
    "glass earth holdings llc": "glass_earth",
    "instadeep limited": "instadeep",
    "jysan technologies": "jysan_technologies",
    "mena mobile inc": "menamobile",
    "wld tokens": "tfh_worldcoin",
}

# Only these canonical jurisdictions are accepted as a grounded domicile;
# anything else (e.g. a stray "Shareholders" capture) is dropped so the card
# falls back to the tracker value rather than showing noise.
_ACCEPTED = set(_KNOWN_LOWER.values()) | set(_CANON.values())

# Deals whose knowledge-base folder mixes multiple entities badly enough that the
# grounded extraction is unreliable - left to fall back to the tracker value
# (flagged) pending manual legal sourcing. TFH/Worldcoin binder contains
# BioNTech/other-entity language that mis-captures as "Germany"; Life Biosciences
# is a US operating company but its folder's term sheet describes the ADGM (GAML)
# holding SPV, so grounded extraction picks the vehicle, not the company.
_SKIP_DEALS = {
    "tools for humanity corporation",
    "wld tokens",
    "life biosciences llc",
}


def _doc_label(result: dict) -> str:
    doc = str(result.get("document") or result.get("citation") or "").strip()
    return Path(doc).name if doc else "legal doc"


def build(db_path: Path) -> dict:
    out: dict = {
        "_comment": "Grounded domicile candidates extracted from the legal "
                    "knowledge base (charters/articles/agreements). status="
                    "'candidate' means analyst confirmation is required before "
                    "it is treated as final. Keyed by lowercased consolidated "
                    "tracker company name. For fund/SPV deals the top value may "
                    "be the holding vehicle or adviser rather than the operating "
                    "company - see domicile_candidates for alternatives.",
        "_source_policy": "domicile = legal docs (cited), never the tracker.",
    }
    for deal, txn in DEAL_TO_TRANSACTION.items():
        if deal in _SKIP_DEALS:
            continue
        res = find_domicile(db_path, txn)
        jur = res.get("jurisdiction")
        if not jur or jur not in _ACCEPTED:
            continue  # suppress noisy / not-found -> card falls back to tracker
        alts = [c["jurisdiction"] for c in res.get("candidates", [])
                if c["jurisdiction"] in _ACCEPTED and c["jurisdiction"] != jur]
        note = f" (legal doc, candidate - confirm; alt: {alts[0]})" if alts else " (legal doc, candidate - confirm)"
        out[deal] = {
            "domicile": jur,
            "domicile_source": f"{_doc_label(res)}{note}",
            "domicile_status": "candidate",
            "domicile_phrase": res.get("phrase", ""),
            "domicile_candidates": [c["jurisdiction"] for c in res.get("candidates", [])],
        }
    return out


def main() -> int:
    db = Path("data/legal_kb/legal_kb.sqlite")
    data = build(db)
    dest = Path("data/source_of_truth/company_domicile_legal.json")
    dest.write_text(json.dumps(data, indent=2), encoding="utf-8")
    n = sum(1 for k in data if not k.startswith("_"))
    print(f"Wrote {n} grounded domicile entries -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
