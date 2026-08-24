"""Roll the citation-grade KB build across ALL investment folders.

Discovers every folder that has extraction outputs (extraction_status.csv) under
the sandbox root and builds each into the single central SQLite knowledge base,
so all investments / all files are captured under one queryable, cited store.

Per-folder failures are isolated (one bad folder cannot halt the run) and a
summary is written at the sandbox root.

Usage:
    python -m scripts.legal_kb.rollout --root "<...>/_RS/AF"
    python -m scripts.legal_kb.rollout --root "<...>/_RS/AF" --no-embeddings
    python -m scripts.legal_kb.rollout --root "<...>/_RS/AF" --only ONT DriveNets
"""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from . import build_kb, embeddings as embeddings_mod
else:  # pragma: no cover
    import build_kb
    import embeddings as embeddings_mod


def long_path(path: Path) -> str:
    resolved = str(path.resolve(strict=False))
    return resolved if resolved.startswith("\\\\?\\") else "\\\\?\\" + resolved


def discover_folders(root: Path) -> list[Path]:
    """Return every SR root under `root` that has an extraction_status.csv."""
    folders: list[Path] = []
    for csv_path in root.rglob("00_Index/Document_Intelligence/extraction_status.csv"):
        sr_root = csv_path.parents[2]
        folders.append(sr_root)
    return sorted(set(folders), key=lambda p: str(p).lower())


def run(root: Path, db_path: Path, with_embeddings: bool, model_name: str,
        only: list[str] | None) -> dict:
    folders = discover_folders(root)
    if only:
        wanted = {name.lower() for name in only}
        folders = [f for f in folders if any(w in str(f).lower() for w in wanted)]

    results: list[dict] = []
    for folder in folders:
        label = folder.parent.name
        try:
            outcome = build_kb.build(folder, db_path, with_embeddings, model_name)
            results.append({"folder": label, "ok": True,
                            "stats": outcome["folder_stats"]})
            print(f"[ok]   {label}: {outcome['folder_stats']}")
        except Exception as exc:  # isolate per-folder failure
            results.append({"folder": label, "ok": False,
                            "error": f"{type(exc).__name__}: {exc}",
                            "traceback": traceback.format_exc()[-1500:]})
            print(f"[FAIL] {label}: {type(exc).__name__}: {exc}")

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sandbox_root": str(root),
        "db_path": str(db_path),
        "with_embeddings": with_embeddings,
        "model": model_name if with_embeddings else None,
        "folder_count": len(results),
        "ok_count": sum(1 for r in results if r["ok"]),
        "failed": [r["folder"] for r in results if not r["ok"]],
        "results": results,
    }
    out = root / "LEGAL_KB_ROLLOUT_SUMMARY.json"
    with open(long_path(out), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(summary, indent=2))
    print(f"\nWrote {out}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the citation-grade KB for all folders.")
    parser.add_argument("--root", type=Path, required=True, help="Sandbox root (e.g. _RS/AF).")
    parser.add_argument("--db", type=Path, default=None,
                        help="SQLite DB path. Default: <root>/legal_kb/legal_kb.sqlite")
    parser.add_argument("--no-embeddings", action="store_true")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--only", nargs="*", default=None,
                        help="Only build folders whose path contains one of these names.")
    args = parser.parse_args()

    model_name = args.model or embeddings_mod.DEFAULT_MODEL
    db_path = args.db or (args.root / "legal_kb" / "legal_kb.sqlite")
    summary = run(args.root, db_path, not args.no_embeddings, model_name, args.only)
    print(f"\n{summary['ok_count']}/{summary['folder_count']} folders built; "
          f"failed: {summary['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
