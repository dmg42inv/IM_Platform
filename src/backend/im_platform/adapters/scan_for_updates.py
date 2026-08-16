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
# rename or split (e.g. "AAICO (desktop)" -> "Applied AI"; one folder split
# into 2 entities) - suppress the false "new investment" positive this would
# otherwise cause on every scan. Value is a list since a folder can map to
# more than one entity_id after a split.
KNOWN_FOLDER_ALIASES: dict[str, list[str]] = {
    "AAICO (desktop)": ["Applied AI"],
    "Endless (Matt Dalio) and E-line": ["Endless Studios", "E-Line Ventures"],
}


def _folder_last_modified(folder: Path) -> datetime | None:
    latest = None
    for p in folder.rglob("*"):
        if p.is_file():
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            if latest is None or mtime > latest:
                latest = mtime
    return latest


# Filename keyword -> plain-English note on what part of the report a new or
# changed document of that kind is likely to affect, so a human reviewing the
# scan knows what to go re-check rather than just "something changed".
_IMPACT_KEYWORDS = [
    (("cap table", "capitalization", "captable"), "May affect Ownership %% / Cap Table"),
    (("capital account", "nav", "quarterly report"), "May affect Carrying Value / NAV"),
    (("purchase agreement", "spa", "subscription agreement", "safe"), "May affect Investing Entity / Committed amount"),
    (("capital call", "drawdown", "contribution notice"), "May affect Invested / Distributions (fund cash flow)"),
    (("distribution notice",), "May affect Distributions"),
    (("amendment", "restructuring", "novation"), "May affect structural terms - re-read before trusting other fields"),
    (("side letter",), "May affect governance/economic rights (board seat, carry, etc.)"),
]


def _impact_note(filename: str) -> str:
    lowered = filename.lower()
    for keywords, note in _IMPACT_KEYWORDS:
        if any(k in lowered for k in keywords):
            return note
    return "Impact unclear from filename - review manually"


def _build_file_manifest(folders: list[Path]) -> dict[str, dict]:
    manifest: dict[str, dict] = {}
    for folder in folders:
        for p in folder.rglob("*"):
            if p.is_file():
                stat = p.stat()
                manifest[str(p)] = {"size": stat.st_size, "mtime": stat.st_mtime}
    return manifest


def _diff_manifests(old: dict[str, dict], new: dict[str, dict]) -> tuple[list[str], list[str]]:
    added = [p for p in new if p not in old]
    modified = [
        p for p in new
        if p in old and (new[p]["size"] != old[p]["size"] or new[p]["mtime"] != old[p]["mtime"])
    ]
    return added, modified


def load_manifest(manifest_path: Path) -> dict[str, dict]:
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {}


def save_manifest(manifest: dict[str, dict], manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def scan_for_new_investments(investments_root: Path, intake_path: Path, manifest_path: Path | None = None) -> dict:
    draft = pd.read_excel(intake_path, sheet_name="Investment_Register_Draft").fillna("")
    known_entities = set(draft["entity_id"].astype(str).str.strip())

    company_folders = discover_company_folders(investments_root)
    fund_folders = discover_fund_folders(investments_root)

    def _is_known(name: str) -> bool:
        return name in known_entities or any(alias in known_entities for alias in KNOWN_FOLDER_ALIASES.get(name, []))

    new_company_folders = [f.name for f in company_folders if not _is_known(f.name)]
    new_fund_folders = [f.name for f in fund_folders if not _is_known(f.name)]

    cutoff = datetime.now() - timedelta(days=RECENT_DAYS)
    recently_modified = []
    for f in company_folders + fund_folders:
        mtime = _folder_last_modified(f)
        if mtime and mtime > cutoff:
            recently_modified.append({"folder": f.name, "last_modified": mtime.isoformat(timespec="seconds")})

    all_folders = company_folders + fund_folders
    new_manifest = _build_file_manifest(all_folders)
    added_files: list[dict] = []
    modified_files: list[dict] = []
    if manifest_path is not None:
        old_manifest = load_manifest(manifest_path)
        if old_manifest:
            added, modified = _diff_manifests(old_manifest, new_manifest)
            added_files = [{"file": p, "impact": _impact_note(Path(p).name)} for p in sorted(added)]
            modified_files = [{"file": p, "impact": _impact_note(Path(p).name)} for p in sorted(modified)]
        save_manifest(new_manifest, manifest_path)

    return {
        "scan_date": datetime.now().isoformat(timespec="seconds"),
        "new_company_folders": new_company_folders,
        "new_fund_folders": new_fund_folders,
        "recently_modified_folders": sorted(recently_modified, key=lambda r: r["last_modified"], reverse=True),
        "added_files": added_files,
        "modified_files": modified_files,
        "total_company_folders_scanned": len(company_folders),
        "total_fund_folders_scanned": len(fund_folders),
    }


def write_scan_report(result: dict, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return output_path
