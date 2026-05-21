"""
Download local SEC filing copies from the filing manifest.
"""

from __future__ import annotations

import argparse
import csv
import urllib.request
from pathlib import Path


SEC_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_CSV = SEC_ROOT / "results/sec_filing_manifest.csv"
OUTPUT_DIR = SEC_ROOT / "raw/sec_filings"
USER_AGENT = "research@local.test"


def fetch_bytes(url: str) -> bytes:
    """Download one SEC filing resource with the configured user agent."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        return response.read()


def safe_name(value: str) -> str:
    """Sanitize a string for use in output paths."""
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value)


def parse_args() -> argparse.Namespace:
    """Parse optional bank, form, year, and source filters."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--banks", nargs="*", default=[])
    parser.add_argument("--forms", nargs="*", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--year-from", type=int, default=0)
    parser.add_argument("--year-to", type=int, default=0)
    parser.add_argument("--source", choices=["document", "archive"], default="document")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    only_banks = set(args.banks)
    only_forms = set(args.forms)

    with MANIFEST_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    downloaded = 0
    for row in rows:
        if only_banks and row["bank_display_name"] not in only_banks:
            continue
        if only_forms and row["form_type"] not in only_forms:
            continue
        filing_year = int(row["filing_date"][:4])
        if args.year_from and filing_year < args.year_from:
            continue
        if args.year_to and filing_year > args.year_to:
            continue
        out_dir = OUTPUT_DIR / safe_name(row["bank_display_name"]) / row["form_type"]
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.source == "archive":
            source_url = row["archive_txt_url"]
            suffix = ".txt"
            stem = f"{row['accession_number'].replace('-', '')}_archive"
        else:
            source_url = row["document_url"]
            suffix = Path(row["primary_document"]).suffix or ".txt"
            stem = safe_name(Path(row["primary_document"]).stem)
        out_name = f"{row['filing_date']}_{row['accession_number'].replace('-', '')}_{stem}{suffix}"
        out_path = out_dir / out_name
        if out_path.exists():
            continue
        out_path.write_bytes(fetch_bytes(source_url))
        downloaded += 1
        print(f"Downloaded {out_path}")
        if args.limit and downloaded >= args.limit:
            break

    print(f"Downloaded {downloaded} filing documents")


if __name__ == "__main__":
    main()
