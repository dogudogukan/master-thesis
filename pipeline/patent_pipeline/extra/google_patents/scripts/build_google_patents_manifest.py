from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATENT_PIPELINE_ROOT = ROOT.parents[1]
PATENTS_CSV = PATENT_PIPELINE_ROOT / "results/latest/03_final/patents.csv"
OUTPUT_TSV = ROOT / "results/google_patents_manifest.tsv"


FIELDNAMES = [
    "patent_id",
    "google_patents_id",
    "google_patents_url",
    "canonical_bank_name",
    "parent_bank_group",
    "patent_title",
    "filing_date",
    "grant_date",
]


def main() -> None:
    rows: list[dict[str, str]] = []
    with PATENTS_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            patent_id = row["patent_id"].strip()
            google_patents_id = f"US{patent_id}"
            rows.append(
                {
                    "patent_id": patent_id,
                    "google_patents_id": google_patents_id,
                    "google_patents_url": f"https://patents.google.com/patent/{google_patents_id}/en",
                    "canonical_bank_name": row["canonical_bank_name"].strip(),
                    "parent_bank_group": row["parent_bank_group"].strip(),
                    "patent_title": row["patent_title"].strip(),
                    "filing_date": row["filing_date"].strip(),
                    "grant_date": row["grant_date"].strip(),
                }
            )

    OUTPUT_TSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} Google Patents manifest rows to {OUTPUT_TSV}")


if __name__ == "__main__":
    main()
