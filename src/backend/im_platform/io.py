from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import REQUIRED_FILES


SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xlsm")


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def find_file_for_dataset(input_root: Path, dataset_key: str) -> Path:
    base_name = REQUIRED_FILES[dataset_key].lower()
    candidates = []
    for ext in SUPPORTED_EXTENSIONS:
        candidates.extend(input_root.rglob(f"*{base_name}*{ext}"))

    if not candidates:
        raise FileNotFoundError(f"No file found for dataset '{dataset_key}' under {input_root}")

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def load_datasets(input_root: Path) -> dict[str, pd.DataFrame]:
    datasets: dict[str, pd.DataFrame] = {}
    for key in REQUIRED_FILES:
        path = find_file_for_dataset(input_root, key)
        df = _read_table(path)
        df.columns = [str(c).strip() for c in df.columns]
        datasets[key] = df
    return datasets
