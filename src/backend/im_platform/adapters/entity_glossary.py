"""Curated display-name glossary: maps the register's internal entity_id
(often derived from OneDrive folder names, sometimes with internal deal
codenames or numeric ordering prefixes) to the actual, clean company/fund
name that should be shown to a reader, plus the full legal name and a note
explaining any difference. entity_id itself is kept stable for internal
joins; only display changes here.
"""

from __future__ import annotations

import pandas as pd

# entity_id -> (display_name, full_legal_name, note)
GLOSSARY: dict[str, tuple[str, str, str]] = {
    "Applied AI": ("Applied AI", "Applied AI Corporation Limited", "Renamed from 'AAICO' - source folder is still named 'AAICO (desktop)'."),
    "Beyond Limits": ("Beyond Limits", "Beyond Limits, Inc.", ""),
    "Cerebras": ("Cerebras", "Cerebras Systems, Inc.", "Tracker splits this into '(1)' (original Series F, held via Mozn) and '(2)' (2026 warrant exercises, held via G42 Capital) - same underlying company."),
    "DriveNets": ("DriveNets", "DriveNets Ltd", ""),
    "e-space": ("e-space", "e-Space, Inc.", ""),
    "Endless Studios": ("Endless Studios", "Endless Studios LLC", "Two rounds via MOZN Holding RSC Ltd: $3M (Oct 2021, signed Issuance Letter) + $5M (Jul 2023, signed SPA) = $8M total."),
    "E-Line Ventures": ("E-Line Ventures", "E-Line Ventures LLC", "A New Jersey LLC, legally distinct from Endless Studios LLC (though E-Line is itself a shareholder in Endless Studios). $6M via MOZN Holding RSC Ltd (2023, signed SPA)."),
    "EsyaSoft": ("Esyasoft", "Esyasoft Holding", ""),
    "Flyr": ("Flyr", "Flyr Inc", ""),
    "Glass Earth": ("Glass Earth", "Glass Earth Holdings LLC", "Defaulted promissory note, fully written off."),
    "Heygears": ("Heygears", "Guangdong Heygears Innovation Technology Co., Ltd.", ""),
    "InstaDeep": ("InstaDeep", "InstaDeep Limited", ""),
    "Inveniam": ("Inveniam", "Inveniam Capital Partners, Inc.", "Held via a Stock Appreciation Rights (SAR) instrument, not direct equity."),
    "Jysan Technologies": ("Jysan Technologies", "Jysan Technologies", ""),
    "Life Biosciences": ("Life Biosciences", "Life Biosciences LLC", ""),
    "Liquid AI": ("Liquid AI", "Liquid AI, Inc.", ""),
    "MenaMobile": ("Mena Mobile", "Mena Mobile Inc", ""),
    "Neuralink (Project Cortex)": ("Neuralink", "Neuralink Corp.", "'Project Cortex' was G42's internal deal codename, not part of the company's name."),
    "ONT": ("Oxford Nanopore (ONT)", "Oxford Nanopore Technologies plc", "LSE-listed (IPO Sep 2021)."),
    "School Hack": ("School Hack", "AIREV Holding Limited (operating as 'School Hack')", ""),
    "TFH - Worldcoin": ("Tools for Humanity", "Tools for Humanity Corporation", "'Worldcoin' is the product/protocol brand name; Tools for Humanity Corporation is the legal investee entity."),
    "Verses (Project Bayes)": ("Verses AI", "Verses AI Inc", "'Project Bayes' was G42's internal deal codename, not part of the company's name."),
    "VTVT - vTv Therapeutics": ("vTv Therapeutics", "vTv Therapeutics Inc.", "'VTVT' is the Nasdaq ticker symbol, not part of the legal name."),
    "X-fusion": ("X-fusion", "X-fusion", "Tracker-only entity - no primary transaction documents located; name not independently verified."),
    "Honor Device Co Ltd": ("Honor Device", "Honor Device Co., Ltd.", "Tracker-only entity - no primary transaction documents located."),
    "Jollychic Holding Limited": ("Jollychic Holding", "Jollychic Holding Limited", "Tracker-only entity - no primary transaction documents located."),
    "1. New Space Capital Fund": ("New Space Capital Fund", "NewSpace Capital Fund S.C.S.", "Leading '1.' is a register/folder ordering artifact, not part of the fund's name. Originally structured as 'NewSpace Capital Fund S.C.A., SICAV-RAIF' and converted to a simple partnership (S.C.S.) in 2021 - all Capital Account Statements/Drawdown Notices from 2022 onward (and the fund's own current NAV/Partner Statements) use the S.C.S. name. Not to be confused with the separate 'NewSpace Capital GP Com SCSp' vehicle (a distinct legal entity, GP-economics only)."),
    "2. Sinovation Disrupt Fund": ("Sinovation Disrupt Fund", "Sinovation Disrupt Fund, L.P.", "Leading '2.' is a register/folder ordering artifact, not part of the fund's name."),
    "2. North Summit Capital Fund": ("North Summit Capital Fund", "North Summit Capital Fund", "Leading '2.' is a register/folder ordering artifact, not part of the fund's name."),
    "3. ACIES": ("Acies", "Acies Ventures Fund I, L.P.", "Leading '3.' is a register/folder ordering artifact, not part of the fund's name."),
    "4. MGX": ("MGX", "MGX (via GX Investments Ltd / GX Investments US LLC)", "Leading '4.' is a register/folder ordering artifact, not part of the fund's name. Covers 4 distinct vehicles: MGX I LP, MGX I Strategic Co-Invest LP, MGX I Denali Holding LP, MGX Group Holding 1 Ltd (GP)."),
}


def display_name(entity_id: str) -> str:
    return GLOSSARY.get(entity_id, (entity_id, entity_id, ""))[0]


def build_glossary_table() -> pd.DataFrame:
    rows = [
        {"entity_id": eid, "display_name": d, "full_legal_name": full, "note": note}
        for eid, (d, full, note) in GLOSSARY.items()
    ]
    return pd.DataFrame(rows).sort_values("display_name").reset_index(drop=True)


# Tracker's own short "Investing Entity" grouping codes (a different namespace
# from the investee-company GLOSSARY above) -> full holding company name.
# The tracker sometimes appends a trailing footnote-reference digit to these
# (e.g. "Mozn 4") - that is NOT a different entity, just a footnote pointer
# into the tracker's own "9. All deals (a)" tab (not yet individually read).
INVESTING_ENTITY_GLOSSARY: dict[str, str] = {
    "Mozn": "MOZN Holding RSC Ltd",
    "G42 Investments": "G42 Investments AI Holding RSC Ltd",
    "G42 Capital": "G42 Capital SPV RSC Ltd",
    "Core42": "Core42 Holding RSC Ltd",
    "G42 Holding": "GX Investments Ltd / GX Investments US LLC (MGX vehicles)",
}


def investing_entity_full_name(short_code: str) -> str:
    return INVESTING_ENTITY_GLOSSARY.get(short_code, short_code)
