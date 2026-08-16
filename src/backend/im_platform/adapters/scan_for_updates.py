"""Real, functional "has anything changed?" check: compares the current
document folder structure against what's already captured in the register,
so a human (or a future scheduled run) can see what needs fresh research.
This does NOT run automatically from the HTML dashboard - a static HTML file
cannot invoke a local Python process from a browser button. Run it from the
terminal (`python -m im_platform.cli scan-for-updates`) and refresh the
dashboard afterward.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from .document_intake import discover_company_folders, discover_fund_folders

RECENT_DAYS = 30

# Folders whose name no longer matches the register's entity_id after a
# rename (e.g. "AAICO (desktop)" -> "Applied AI") - suppress the false
# "new investment" positive this would otherwise cause on every scan.
KNOWN_FOLDER_ALIASES = {
    "AAICO (desktop)": "Applied AI",
}


def _folder_last_modified(folder: Path) -> datetime | None:
    latest = None
    for p in folder.rglob("*"):
        if p.is_file():
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            if latest is None or mtime > latest:
                latest = mtime
    return latest


def scan_for_new_investments(investments_root: Path, intake_path: Path) -> dict:
    draft = pd.read_excel(intake_path, sheet_name="Investment_Register_Draft").fillna("")
    known_entities = set(draft["entity_id"].astype(str).str.strip())

    company_folders = discover_company_folders(investments_root)
    fund_folders = discover_fund_folders(investments_root)

    def _is_known(name: str) -> bool:
        return name in known_entities or KNOWN_FOLDER_ALIASES.get(name) in known_entities

    new_company_folders = [f.name for f in company_folders if not _is_known(f.name)]
    new_fund_folders = [f.name for f in fund_folders if not _is_known(f.name)]

    cutoff = datetime.now() - timedelta(days=RECENT_DAYS)
    recently_modified = []
    for f in company_folders + fund_folders:
        mtime = _folder_last_modified(f)
        if mtime and mtime > cutoff:
            recently_modified.append({"folder": f.name, "last_modified": mtime.isoformat(timespec="seconds")})

    return {
        "scan_date": datetime.now().isoformat(timespec="seconds"),
        "new_company_folders": new_company_folders,
        "new_fund_folders": new_fund_folders,
        "recently_modified_folders": sorted(recently_modified, key=lambda r: r["last_modified"], reverse=True),
        "total_company_folders_scanned": len(company_folders),
        "total_fund_folders_scanned": len(fund_folders),
    }


def write_scan_report(result: dict, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return output_path
