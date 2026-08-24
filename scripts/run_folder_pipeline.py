"""Drive the full document-graph pipeline across investment sandbox folders.

For each target folder (an ``SR`` root with 00_Index/file_readiness_inventory.csv):
  1. build_extraction_coverage.process_folder  (extract/read every file, OCR optional)
  2. build_graph_and_embeddings.build          (DGML graph + queryable vector index)

Writes a roll-up ALL_FOLDERS_GRAPH_SUMMARY.json at the sandbox root.

Usage:
    # one folder
    python scripts/run_folder_pipeline.py --only DriveNets --ocr

    # everything not already done
    python scripts/run_folder_pipeline.py --all --ocr --skip-existing
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import build_extraction_coverage as extraction
import build_graph_and_embeddings as graphing

DEFAULT_SANDBOX_ROOT = Path(
    r"C:\Users\divyesh.mahajan\OneDrive - G42\Desktop\0.1 SPPM ###\_RS\AF"
)


def find_sr_folders(sandbox_root: Path) -> list[Path]:
    folders: list[Path] = []
    for inventory in sandbox_root.rglob("00_Index/file_readiness_inventory.csv"):
        sr_root = inventory.parent.parent
        if sr_root.name == "SR":
            folders.append(sr_root)
    return sorted(folders, key=lambda p: str(p).casefold())


def folder_label(sr_root: Path) -> str:
    # .../<category_slug>/<folder_slug>/SR  ->  folder_slug
    return sr_root.parent.name


def main() -> int:
    parser = argparse.ArgumentParser(description="Run extraction + graph/embeddings across sandbox folders.")
    parser.add_argument("--sandbox-root", type=Path, default=DEFAULT_SANDBOX_ROOT)
    parser.add_argument("--only", nargs="*", default=None, help="Folder slugs to process (substring match on folder name).")
    parser.add_argument("--all", action="store_true", help="Process every folder found under the sandbox root.")
    parser.add_argument("--ocr", action="store_true", help="Enable OCR for images and scanned PDFs.")
    parser.add_argument("--skip-existing", action="store_true", help="Skip folders that already have a graph_manifest.json.")
    args = parser.parse_args()

    if not args.only and not args.all:
        parser.error("Specify --all or --only <folder> ...")

    all_folders = find_sr_folders(args.sandbox_root)
    if args.only:
        wanted = [w.casefold() for w in args.only]
        targets = [f for f in all_folders if any(w in folder_label(f).casefold() for w in wanted)]
    else:
        targets = all_folders

    if not targets:
        print("No matching folders found.")
        return 1

    summaries: list[dict[str, object]] = []
    for sr_root in targets:
        label = folder_label(sr_root)
        manifest_path = sr_root / "00_Index" / "Document_Intelligence" / "graph_manifest.json"
        if args.skip_existing and manifest_path.exists():
            print(f"SKIP existing: {label}")
            continue
        try:
            print(f"=== {label}: extracting (ocr={args.ocr}) ===")
            extract_manifest = extraction.process_folder(sr_root, args.ocr)
            print(f"    extracted_text={extract_manifest['extracted_text_count']} blocked={extract_manifest['blocked_count']}")
            print(f"=== {label}: building graph + embeddings ===")
            graph_manifest = graphing.build(sr_root)
            print(f"    text_nodes={graph_manifest['text_node_count']} blocked_nodes={graph_manifest['blocked_node_count']} passages={graph_manifest['passage_count']}")
            summaries.append({
                "folder": label,
                "sr_root": str(sr_root),
                "file_count": graph_manifest["file_count"],
                "extracted_text_count": extract_manifest["extracted_text_count"],
                "extraction_blocked_count": extract_manifest["blocked_count"],
                "text_node_count": graph_manifest["text_node_count"],
                "blocked_node_count": graph_manifest["blocked_node_count"],
                "passage_count": graph_manifest["passage_count"],
            })
        except Exception as exc:  # noqa: BLE001 - never let one folder halt an unattended run
            print(f"    ERROR processing {label}: {exc.__class__.__name__}: {exc}")
            summaries.append({
                "folder": label,
                "sr_root": str(sr_root),
                "error": f"{exc.__class__.__name__}: {exc}",
            })

    roll_up = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sandbox_root": str(args.sandbox_root),
        "processed_folder_count": len(summaries),
        "folders": summaries,
    }
    os.makedirs(extraction.long_path(args.sandbox_root), exist_ok=True)
    with open(extraction.long_path(args.sandbox_root / "ALL_FOLDERS_GRAPH_SUMMARY.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(roll_up, indent=2))
    print(json.dumps(roll_up, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
