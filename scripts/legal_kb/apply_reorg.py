"""Apply the proposed reorganisation: build a clean, logically-foldered copy of
a deal's documents.

Safe by construction:
- COPIES from the untouched 99_Archive (originals are never moved/altered).
- Creates only the buckets that actually receive files (no empty folders).
- Renames the deal folder to a proper name; drops the SR / archive layers.
- Handles name collisions; writes REORG_MANIFEST.csv recording every
  source -> destination mapping for full provenance.

Usage:
    python -m scripts.legal_kb.apply_reorg --db data/legal_kb/legal_kb.sqlite \
        --transaction ont --sr-root "<...>/ONT/SR" \
        --dest-root "<...>/_RS/CLEAN/0_Equity" --name "Oxford Nanopore"
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
from pathlib import Path

if __package__:
    from .reorg_proposal import build_proposal
else:  # pragma: no cover
    from reorg_proposal import build_proposal


# Proper display names per deal (inferred; easy to tweak - reorg is a copy).
NAME_MAP = {
    "aaico_desktop": "Applied AI (AAICO)",
    "beyond_limits": "Beyond Limits",
    "cerebras": "Cerebras Systems",
    "drivenets": "DriveNets",
    "endless_matt_dalio_and_e_line": "Endless (E-Line)",
    "esyasoft": "EsyaSoft",
    "flyr": "FLYR",
    "glass_earth": "Glass Earth",
    "heygears": "HeyGears",
    "instadeep": "InstaDeep",
    "inveniam": "Inveniam",
    "jysan_technologies": "Jysan Technologies",
    "life_biosciences": "Life Biosciences",
    "liquid_ai": "Liquid AI",
    "menamobile": "Mena Mobile",
    "neuralink_project_cortex": "Neuralink",
    "ont": "Oxford Nanopore",
    "school_hack": "School Hack (AIREV)",
    "tfh_worldcoin": "Tools for Humanity (Worldcoin)",
    "vtvt_vtv_therapeutics": "vTv Therapeutics",
    "verses_project_bayes": "Verses AI",
    "e_space": "E-Space",
    "1_new_space_capital_fund": "NewSpace Capital Fund",
    "2_north_summit_capital_fund": "North Summit Capital Fund",
    "2_sinovation_disrupt_fund": "Sinovation Disrupt Fund",
    "3_acies": "ACIES",
    "4_mgx": "MGX",
}


def long_path(p: str) -> str:
    p = os.path.abspath(p)
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def _unique(dest_dir: Path, filename: str, used: set) -> Path:
    stem, ext = os.path.splitext(filename)
    candidate = dest_dir / filename
    i = 2
    while str(candidate).lower() in used:
        candidate = dest_dir / f"{stem} ({i}){ext}"
        i += 1
    used.add(str(candidate).lower())
    return candidate


def apply_reorg(db_path: Path, transaction_id: str, sr_root: Path, dest_root: Path,
                name: str, dry_run: bool = False) -> dict:
    rows = build_proposal(db_path, transaction_id)
    archive = sr_root / "99_Archive"
    deal_dir = dest_root / name
    # Idempotent: regenerate the clean deal folder fresh each run.
    if not dry_run and os.path.exists(long_path(str(deal_dir))):
        shutil.rmtree(long_path(str(deal_dir)), ignore_errors=True)
    used: set = set()
    manifest: list[dict] = []
    copied = 0
    missing = 0
    skipped = 0
    bucket_counts: dict[str, int] = {}

    for r in rows:
        rel = r["original_path"]
        bucket = r["proposed_bucket"]
        # Synthetic zip-member rows point inside an archive, not to a real file;
        # the .zip container itself is copied as its own row.
        if "__unzipped" in rel.lower():
            skipped += 1
            continue
        src = archive / rel
        if not os.path.exists(long_path(str(src))):
            missing += 1
            manifest.append({**r, "dest": "", "status": "SOURCE_MISSING"})
            continue
        dest_dir = deal_dir / bucket
        dst = _unique(dest_dir, r["filename"], used)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        manifest.append({
            "filename": r["filename"], "original_path": rel, "doc_kind": r["doc_kind"],
            "proposed_bucket": bucket, "reason": r["reason"],
            "dest": str(dst.relative_to(deal_dir)), "status": "copied",
        })
        if not dry_run:
            os.makedirs(long_path(str(dest_dir)), exist_ok=True)
            shutil.copy2(long_path(str(src)), long_path(str(dst)))
        copied += 1

    if not dry_run:
        os.makedirs(long_path(str(deal_dir)), exist_ok=True)
        man_path = deal_dir / "REORG_MANIFEST.csv"
        with open(long_path(str(man_path)), "w", encoding="utf-8", newline="") as h:
            w = csv.DictWriter(h, fieldnames=["filename", "original_path", "doc_kind",
                                              "proposed_bucket", "reason", "dest", "status"])
            w.writeheader()
            w.writerows(manifest)

    return {"deal_dir": str(deal_dir), "copied": copied, "missing": missing,
            "skipped_zip_members": skipped, "buckets": dict(sorted(bucket_counts.items()))}


def run_all(db_path: Path, dest_base: Path) -> dict:
    """Reorganise every transaction into <dest_base>/<0_Equity|1_Funds>/<Name>."""
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    txns = conn.execute("SELECT transaction_id, folder_path FROM transactions ORDER BY folder_path").fetchall()
    conn.close()

    results = []
    for tid, folder_path in txns:
        category = "1_Funds" if "1_F_U_N_D" in folder_path else "0_Equity"
        name = NAME_MAP.get(tid, tid)
        sr_root = Path(folder_path)
        dest_root = dest_base / category
        try:
            res = apply_reorg(db_path, tid, sr_root, dest_root, name)
            total = res["copied"]
            results.append({"transaction": tid, "name": name, "category": category,
                            "copied": total, "missing": res["missing"],
                            "skipped_zip_members": res["skipped_zip_members"]})
            print(f"[ok]   {name:34} {category}  copied={total} missing={res['missing']} skipped_zip={res['skipped_zip_members']}")
        except Exception as exc:  # isolate per-deal failure
            results.append({"transaction": tid, "name": name, "error": f"{type(exc).__name__}: {exc}"})
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    return {"dest_base": str(dest_base), "deals": len(results),
            "total_copied": sum(r.get("copied", 0) for r in results), "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply the clean reorganisation (copies from 99_Archive).")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--all", action="store_true", help="Reorganise all transactions.")
    parser.add_argument("--dest-base", type=Path, default=None, help="Base for --all (e.g. .../_RS/CLEAN).")
    parser.add_argument("--transaction", type=str, default=None)
    parser.add_argument("--sr-root", type=Path, default=None)
    parser.add_argument("--dest-root", type=Path, default=None)
    parser.add_argument("--name", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    import json
    if args.all:
        if not args.dest_base:
            raise SystemExit("--all requires --dest-base")
        print(json.dumps(run_all(args.db, args.dest_base), indent=2)[:400])
        return 0
    result = apply_reorg(args.db, args.transaction, args.sr_root, args.dest_root,
                         args.name, args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
