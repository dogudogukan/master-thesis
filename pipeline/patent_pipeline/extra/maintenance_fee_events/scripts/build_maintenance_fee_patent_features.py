"""
Build patent-level maintenance-fee features from the USPTO event dump.

The script reads the latest maintenance archive under `raw/` and writes a
compact codebook plus a patent-level feature table under `results/`.
"""

from __future__ import annotations

import csv
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "raw"
CODEBOOK_CSV = ROOT / "results/maintenance_fee_codebook.csv"
FEATURES_PARQUET = ROOT / "results/maintenance_fee_patent_features.parquet"

STAGE4_CODES = {"M1551", "M2551", "M3551", "F170", "F173", "F273"}
STAGE8_CODES = {"M1552", "M2552", "M3552", "F171", "F174", "F274"}
STAGE12_CODES = {"M1553", "M2553", "M3553", "F172", "F175", "F275"}
LAPSE_CODES = {"EXP", "LAPS"}
REINSTATE_CODES = {"EXPX"}


def resolve_raw_zip() -> Path:
    """Use the most recent maintenance archive under `raw/`."""
    archives = sorted(RAW_DIR.glob("MaintFeeEvents_*.zip"))
    if not archives:
        raise FileNotFoundError(f"No maintenance archive found under {RAW_DIR}")
    return archives[-1]


def normalize_code(code: str) -> str:
    """Trim whitespace and trailing punctuation from event codes."""
    return code.strip().rstrip(".")


def patent_sort_key(value: str) -> tuple[int, int | str]:
    """Sort numeric patent IDs numerically and other values last."""
    if value.isdigit():
        return (0, int(value))
    return (1, value)


def parse_codebook(archive: zipfile.ZipFile) -> dict[str, str]:
    """Read the event-code description file bundled with the archive."""
    name = next(item for item in archive.namelist() if item.endswith(".txt") and "Desc" in item)
    codebook: dict[str, str] = {}
    with archive.open(name) as handle:
        for raw_line in handle:
            line = raw_line.decode("latin-1").strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                continue
            raw_code, description = parts
            codebook[normalize_code(raw_code)] = description.strip()
    return codebook


def build_features(archive: zipfile.ZipFile) -> list[dict[str, int | str]]:
    """Collapse raw event rows to one patent-level feature row per patent."""
    event_name = next(item for item in archive.namelist() if item.endswith(".txt") and "Desc" not in item)
    counts = defaultdict(lambda: Counter())
    with archive.open(event_name) as handle:
        for raw_line in handle:
            line = raw_line.decode("latin-1").strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 7:
                continue
            patent_id = parts[0].lstrip("0") or "0"
            code = normalize_code(parts[-1])
            counts[patent_id]["maintenance_event_count"] += 1
            if code in STAGE4_CODES:
                counts[patent_id]["maint_paid_3_5"] = 1
            if code in STAGE8_CODES:
                counts[patent_id]["maint_paid_7_5"] = 1
            if code in STAGE12_CODES:
                counts[patent_id]["maint_paid_11_5"] = 1
            if code in LAPSE_CODES:
                counts[patent_id]["maintenance_expired_flag"] = 1
            if code in REINSTATE_CODES:
                counts[patent_id]["maintenance_reinstated_flag"] = 1

    rows: list[dict[str, int | str]] = []
    for patent_id in sorted(counts, key=patent_sort_key):
        row = counts[patent_id]
        rows.append(
            {
                "patent_id": patent_id,
                "maint_paid_3_5": int(row.get("maint_paid_3_5", 0)),
                "maint_paid_7_5": int(row.get("maint_paid_7_5", 0)),
                "maint_paid_11_5": int(row.get("maint_paid_11_5", 0)),
                "maintenance_stage_count": int(
                    row.get("maint_paid_3_5", 0) + row.get("maint_paid_7_5", 0) + row.get("maint_paid_11_5", 0)
                ),
                "maintenance_expired_flag": int(row.get("maintenance_expired_flag", 0)),
                "maintenance_reinstated_flag": int(row.get("maintenance_reinstated_flag", 0)),
                "maintenance_event_count": int(row.get("maintenance_event_count", 0)),
            }
        )
    return rows


def write_codebook(path: Path, codebook: dict[str, str]) -> None:
    """Write a compact codebook for the normalized event codes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["event_code", "description"])
        writer.writeheader()
        for event_code in sorted(codebook):
            writer.writerow({"event_code": event_code, "description": codebook[event_code]})


def main() -> None:
    raw_zip = resolve_raw_zip()
    with zipfile.ZipFile(raw_zip) as archive:
        codebook = parse_codebook(archive)
        features = build_features(archive)

    write_codebook(CODEBOOK_CSV, codebook)
    pd.DataFrame(features).to_parquet(FEATURES_PARQUET, index=False)

    print(f"Read maintenance archive {raw_zip}")
    print(f"Wrote maintenance codebook to {CODEBOOK_CSV}")
    print(f"Wrote {len(features)} patent-level maintenance rows to {FEATURES_PARQUET}")


if __name__ == "__main__":
    main()
