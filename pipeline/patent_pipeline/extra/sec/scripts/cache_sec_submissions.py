"""
Cache SEC submissions JSON files for the selected bank targets.
"""

from __future__ import annotations

import argparse
import csv
import json
import urllib.request
from pathlib import Path


SEC_ROOT = Path(__file__).resolve().parents[1]
BANK_TARGETS_CSV = SEC_ROOT / "results/sec_bank_targets.csv"
OUTPUT_DIR = SEC_ROOT / "raw/sec_submissions"
USER_AGENT = "research@local.test"


def fetch_bytes(url: str) -> bytes:
    """Download one SEC resource with the configured user agent."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        return response.read()


def load_bank_rows(path: Path, only_banks: set[str] | None) -> list[dict[str, str]]:
    """Load the subset of bank targets that should be cached."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    filtered = []
    for row in rows:
        if row["is_sec_filer_candidate"] != "1" or not row["sec_cik"]:
            continue
        if only_banks and row["bank_display_name"] not in only_banks:
            continue
        filtered.append(row)
    return filtered


def parse_args() -> argparse.Namespace:
    """Parse optional bank filters."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--banks", nargs="*", default=[])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    only_banks = set(args.banks) if args.banks else None
    bank_rows = load_bank_rows(BANK_TARGETS_CSV, only_banks)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    for row in bank_rows:
        cik = f"{int(row['sec_cik']):010d}"
        main_name = f"CIK{cik}.json"
        main_url = f"https://data.sec.gov/submissions/{main_name}"
        main_bytes = fetch_bytes(main_url)
        main_path = OUTPUT_DIR / main_name
        main_path.write_bytes(main_bytes)
        downloaded += 1

        payload = json.loads(main_bytes)
        start_year = int(row["recommended_sec_start_year"])
        for item in payload.get("filings", {}).get("files", []):
            if int(item["filingTo"][:4]) < start_year:
                continue
            older_name = item["name"]
            older_url = f"https://data.sec.gov/submissions/{older_name}"
            older_path = OUTPUT_DIR / older_name
            if older_path.exists():
                continue
            older_path.write_bytes(fetch_bytes(older_url))
            downloaded += 1
        print(f"Cached submissions for {row['bank_display_name']}")

    print(f"Downloaded {downloaded} submission JSON files")


if __name__ == "__main__":
    main()
