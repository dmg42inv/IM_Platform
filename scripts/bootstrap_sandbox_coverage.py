from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".html", ".htm"}
PDF_EXTENSIONS = {".pdf"}
OFFICE_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".msg"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
ARCHIVE_EXTENSIONS = {".zip", ".7z", ".rar"}

DEFAULT_ACTIVE_FOLDERS = [
    "00_Index",
    "01_Primary_Source_Documents",
    "02_Board_and_Investment_Committee",
    "03_Closing_and_Legal",
    "04_Capitalization_and_Securities",
    "05_Cashflows_and_Funding",
    "06_Milestones_and_Corporate_Actions",
    "07_Monitoring_and_Financials",
    "08_Exit_and_Public_Markets",
    "08_Valuation_Support",
    "09_Analysis",
    "10_Due_Diligence",
    "99_Archive",
]


@dataclass
class FileRecord:
    relative_path: str
    size_bytes: int
    sha256: str
    extension: str
    copy_status: str
    content_readiness_status: str
    review_note: str


def long_path(path: Path) -> str:
    resolved = str(path.resolve(strict=False))
    if resolved.startswith("\\\\?\\"):
        return resolved
    return "\\\\?\\" + resolved


def iter_files(root: Path) -> list[Path]:
    return sorted([p for p in root.rglob("*") if p.is_file()], key=lambda p: str(p.relative_to(root)).casefold())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(long_path(path), "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return slug[:80] or "folder"


def readiness_for(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return "text_readable_pending_parse", "Plain-text-like file; can be directly parsed in a later semantic pass."
    if ext in PDF_EXTENSIONS:
        return "pdf_text_or_ocr_required", "PDF requires text extraction and possible OCR before clause-level review."
    if ext in OFFICE_EXTENSIONS:
        return "office_parser_required", "Office/email file requires a document parser or manual review."
    if ext in IMAGE_EXTENSIONS:
        return "ocr_required", "Image file requires OCR or manual visual review."
    if ext in ARCHIVE_EXTENSIONS:
        return "archive_expansion_required", "Archive/package must be expanded or inspected before contents can be reviewed."
    return "binary_or_unknown_review_required", "Unsupported or unknown file type; manual classification required."


def copy_tree_and_verify(source: Path, sandbox_root: Path, category: str, dry_run: bool) -> dict[str, object]:
    source_files = iter_files(source)
    target_root = sandbox_root / slugify(category) / slugify(source.name) / "SR"
    archive_root = target_root / "99_Archive"
    index_root = target_root / "00_Index"
    intelligence_root = index_root / "Document_Intelligence"

    records: list[FileRecord] = []
    errors: list[dict[str, str]] = []
    missing: list[str] = []
    mismatches: list[dict[str, str]] = []

    if not dry_run:
        for folder in DEFAULT_ACTIVE_FOLDERS:
            os.makedirs(long_path(target_root / folder), exist_ok=True)
        os.makedirs(long_path(intelligence_root), exist_ok=True)
        os.makedirs(long_path(intelligence_root / "embeddings"), exist_ok=True)

    for source_file in source_files:
        relative = source_file.relative_to(source)
        target_file = archive_root / relative
        try:
            source_hash = sha256_file(source_file)
            source_size = source_file.stat().st_size
            if not dry_run:
                os.makedirs(long_path(target_file.parent), exist_ok=True)
                shutil.copy2(long_path(source_file), long_path(target_file))
                target_hash = sha256_file(target_file)
                target_size = target_file.stat().st_size
                if target_hash != source_hash or target_size != source_size:
                    mismatches.append({"relative_path": str(relative), "source_sha256": source_hash, "target_sha256": target_hash})
                    copy_status = "hash_mismatch"
                else:
                    copy_status = "copied_hash_verified"
            else:
                copy_status = "dry_run_not_copied"
            readiness, note = readiness_for(source_file)
            records.append(
                FileRecord(
                    relative_path=str(relative),
                    size_bytes=source_size,
                    sha256=source_hash,
                    extension=source_file.suffix.lower(),
                    copy_status=copy_status,
                    content_readiness_status=readiness,
                    review_note=note,
                )
            )
        except OSError as exc:
            errors.append({"relative_path": str(relative), "error": f"{exc.__class__.__name__}: {exc}"})

    if not dry_run:
        copied_files = iter_files(archive_root) if archive_root.exists() else []
        copied_relatives = {str(p.relative_to(archive_root)) for p in copied_files}
        source_relatives = {str(p.relative_to(source)) for p in source_files}
        missing = sorted(source_relatives - copied_relatives)

        with (index_root / "file_readiness_inventory.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(asdict(records[0]).keys()) if records else ["relative_path"])
            writer.writeheader()
            for record in records:
                writer.writerow(asdict(record))

        verification = {
            "investment": source.name,
            "category": category,
            "source": str(source),
            "sandbox": str(target_root),
            "archive_reference_copy": str(archive_root),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_file_count": len(source_files),
            "copied_file_count": len(copied_files),
            "source_total_bytes": sum(r.size_bytes for r in records),
            "copied_total_bytes": sum(p.stat().st_size for p in copied_files),
            "copy_error_count": len(errors),
            "copy_errors": errors,
            "missing_count": len(missing),
            "mismatch_count": len(mismatches),
            "missing": missing,
            "mismatches": mismatches,
            "readiness_counts": {},
        }
        for record in records:
            verification["readiness_counts"][record.content_readiness_status] = verification["readiness_counts"].get(record.content_readiness_status, 0) + 1
        with open(long_path(index_root / "source_copy_verification.json"), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(verification, indent=2))
        with open(long_path(index_root / "COVERAGE_STATUS.md"), "w", encoding="utf-8") as handle:
            handle.write(render_coverage_status(verification))
    else:
        verification = {
            "investment": source.name,
            "category": category,
            "source": str(source),
            "sandbox": str(target_root),
            "source_file_count": len(source_files),
            "source_total_bytes": sum(r.size_bytes for r in records),
            "copy_error_count": len(errors),
            "copy_errors": errors,
            "readiness_counts": {},
        }
        for record in records:
            verification["readiness_counts"][record.content_readiness_status] = verification["readiness_counts"].get(record.content_readiness_status, 0) + 1

    return verification


def render_coverage_status(verification: dict[str, object]) -> str:
    lines = [
        f"# Coverage Status - {verification['investment']}",
        "",
        "## Copy Verification",
        "",
        f"- Source file count: {verification['source_file_count']}",
        f"- Copied file count: {verification['copied_file_count']}",
        f"- Copy errors: {verification['copy_error_count']}",
        f"- Missing files: {verification['missing_count']}",
        f"- Hash mismatches: {verification['mismatch_count']}",
        "",
        "## Readiness Classification",
        "",
    ]
    for status, count in sorted(verification.get("readiness_counts", {}).items()):
        lines.append(f"- {status}: {count}")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "Every copied file is byte-hash verified when missing files and hash mismatches are zero.",
        "This does not mean every page or workbook cell has been legally interpreted.",
        "The file_readiness_inventory.csv file tracks the next extraction/review requirement for each individual file.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create sandbox archive copies and per-file coverage inventories for investment folders.")
    parser.add_argument("--investments-root", type=Path, required=True)
    parser.add_argument("--sandbox-root", type=Path, required=True)
    parser.add_argument("--categories", nargs="*", default=["0. E Q U I T Y", "1. F U N D - I N V E S T M E N T"])
    parser.add_argument("--only", nargs="*", default=None, help="Optional folder names to process exactly.")
    parser.add_argument("--skip-existing", action="store_true", help="Skip a target if its source_copy_verification.json already exists.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    summaries: list[dict[str, object]] = []
    for category in args.categories:
        category_root = args.investments_root / category
        if not category_root.exists():
            print(f"Skipping missing category: {category_root}")
            continue
        for source in sorted([p for p in category_root.iterdir() if p.is_dir()], key=lambda p: p.name.casefold()):
            if args.only and source.name not in args.only:
                continue
            target_root = args.sandbox_root / slugify(category) / slugify(source.name) / "SR"
            verification_path = target_root / "00_Index" / "source_copy_verification.json"
            if args.skip_existing and verification_path.exists():
                print(f"SKIP existing: {source.name}")
                continue
            summary = copy_tree_and_verify(source, args.sandbox_root, category, args.dry_run)
            summaries.append(summary)
            print(f"{source.name}: files={summary['source_file_count']} errors={summary['copy_error_count']} target={summary['sandbox']}")

    if not args.dry_run:
        os.makedirs(long_path(args.sandbox_root), exist_ok=True)
        with open(long_path(args.sandbox_root / "ALL_FOLDERS_COVERAGE_SUMMARY.json"), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(summaries, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
