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
    "Endless (Matt Dalio) and E-line": ("Endless Studios / E-line Ventures", "Endless Studios LLC and E-line Ventures LLC", "Register currently holds these as ONE entity, but the tracker treats them as 2 distinct deals (Endless Studios LLC, 2021, $8M; E-line Ventures LLC, 2023, $6M) - register split not yet done, IRR shown is blended across both."),
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
    "1. New Space Capital Fund": ("New Space Capital Fund", "NewSpace Capital Fund S.C.A., SICAV-RAIF (ICEYE Sub-Fund)", "Leading '1.' is a register/folder ordering artifact, not part of the fund's name."),
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
