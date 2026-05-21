"""
Build a filing-level SEC download manifest from cached submission JSON files.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


SEC_ROOT = Path(__file__).resolve().parents[1]
BANK_TARGETS_CSV = SEC_ROOT / "results/sec_bank_targets.csv"
SUBMISSIONS_DIR = SEC_ROOT / "raw/sec_submissions"
OUTPUT_CSV = SEC_ROOT / "results/sec_filing_manifest.csv"


def recent_like_rows(payload: dict) -> dict[str, list]:
    """Return the row block that behaves like the SEC `recent` table."""
    if "filings" in payload and "recent" in payload["filings"]:
        return payload["filings"]["recent"]
    return payload


def iter_submission_rows(payload: dict) -> list[dict[str, str]]:
    """Flatten one SEC submissions payload to filing-level rows."""
    recent = recent_like_rows(payload)
    rows: list[dict[str, str]] = []
    accession_numbers = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    forms = recent.get("form", [])
    primary_documents = recent.get("primaryDocument", [])
    size = min(len(accession_numbers), len(filing_dates), len(forms), len(primary_documents))
    for idx in range(size):
        rows.append(
            {
                "accession_number": accession_numbers[idx],
                "filing_date": filing_dates[idx],
                "form": forms[idx],
                "primary_document": primary_documents[idx],
            }
        )
    return rows


def collect_submission_payloads(cik: str) -> list[dict]:
    """Load the cached main submission file plus any linked older chunks."""
    payloads: list[dict] = []
    main_path = SUBMISSIONS_DIR / f"CIK{int(cik):010d}.json"
    if not main_path.exists():
        return payloads
    main_payload = json.loads(main_path.read_text())
    payloads.append(main_payload)
    for item in main_payload.get("filings", {}).get("files", []):
        older_path = SUBMISSIONS_DIR / item["name"]
        if older_path.exists():
            payloads.append(json.loads(older_path.read_text()))
    return payloads


def main() -> None:
    rows: list[dict[str, str]] = []
    with BANK_TARGETS_CSV.open(newline="", encoding="utf-8") as handle:
        for bank_row in csv.DictReader(handle):
            if bank_row["is_sec_filer_candidate"] != "1" or not bank_row["sec_cik"]:
                continue
            wanted_forms = {value for value in bank_row["sec_form_types"].split("|") if value}
            start_year = int(bank_row["recommended_sec_start_year"])
            end_year = int(bank_row["recommended_sec_end_year"])
            seen_accessions: set[str] = set()
            for payload in collect_submission_payloads(bank_row["sec_cik"]):
                cik_digits = f"{int(bank_row['sec_cik']):d}"
                for filing in iter_submission_rows(payload):
                    filing_year = int(filing["filing_date"][:4])
                    if filing["form"] not in wanted_forms:
                        continue
                    if not (start_year <= filing_year <= end_year):
                        continue
                    accession = filing["accession_number"]
                    if accession in seen_accessions:
                        continue
                    seen_accessions.add(accession)
                    accession_nodash = accession.replace("-", "")
                    rows.append(
                        {
                            "bank_display_name": bank_row["bank_display_name"],
                            "patent_canonical_bank_name": bank_row["patent_canonical_bank_name"],
                            "sec_search_entity": bank_row["sec_search_entity"],
                            "sec_ticker": bank_row["sec_ticker"],
                            "sec_cik": bank_row["sec_cik"],
                            "form_type": filing["form"],
                            "filing_date": filing["filing_date"],
                            "accession_number": accession,
                            "primary_document": filing["primary_document"],
                            "document_url": f"https://www.sec.gov/Archives/edgar/data/{cik_digits}/{accession_nodash}/{filing['primary_document']}",
                            "archive_txt_url": f"https://www.sec.gov/Archives/edgar/data/{cik_digits}/{accession_nodash}/{accession}.txt",
                        }
                    )

    rows.sort(key=lambda row: (row["bank_display_name"], row["filing_date"], row["form_type"], row["accession_number"]))
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [
            "bank_display_name",
            "patent_canonical_bank_name",
            "sec_search_entity",
            "sec_ticker",
            "sec_cik",
            "form_type",
            "filing_date",
            "accession_number",
            "primary_document",
            "document_url",
            "archive_txt_url",
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} filing manifest rows")


if __name__ == "__main__":
    main()
