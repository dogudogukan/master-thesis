"""
Build SEC target lists for the current patent sample.

The outputs in `results/` are small helper tables for submission caching,
filing download, and later local text scans.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pyarrow.parquet as pq


PATENT_PIPELINE_ROOT = Path(__file__).resolve().parents[3]
SEC_ROOT = Path(__file__).resolve().parents[1]
PATENTS_CSV = PATENT_PIPELINE_ROOT / "results/latest/03_final/patents.csv"
APPLICATION_PARQUET = PATENT_PIPELINE_ROOT / "data/processed/g_application.parquet"
ISSUER_SEED_CSV = SEC_ROOT / "config/sec_issuer_seed.csv"
RESULTS_DIR = SEC_ROOT / "results"
CURRENT_YEAR = 2026
SEC_KEYWORDS = "license|licensing|licensed|infringement|infringe|settlement|technology agreement|cross-license|intellectual property"


def format_patent_number(value: str) -> str:
    """Render a plain patent number with comma separators."""
    return f"{int(value):,}"


def format_application_number(value: str) -> str:
    """Render a USPTO-style application number with slashes and commas."""
    digits = value.lstrip("0")
    padded = digits.zfill(8)
    return f"{padded[:2]}/{padded[2:5]},{padded[5:]}"


def load_issuer_seed() -> dict[str, dict[str, str]]:
    """Load the hand-curated SEC issuer seed table keyed by bank name."""
    with ISSUER_SEED_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {row["patent_canonical_bank_name"]: row for row in rows}


def load_application_map(patent_ids: set[str]) -> dict[str, str]:
    """Map granted patent IDs to application IDs for the current sample."""
    table = pq.read_table(APPLICATION_PARQUET, columns=["application_id", "patent_id"])
    mapping: dict[str, str] = {}
    for application_id, patent_id in zip(table["application_id"].to_pylist(), table["patent_id"].to_pylist()):
        patent_id_str = str(patent_id)
        if patent_id_str in patent_ids:
            mapping[patent_id_str] = str(application_id)
    return mapping


def read_patent_rows() -> list[dict[str, str]]:
    """Read the current final patent sample."""
    with PATENTS_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return rows


def build_patent_targets(rows: list[dict[str, str]], issuer_seed: dict[str, dict[str, str]], application_map: dict[str, str]) -> list[dict[str, str]]:
    """Build patent-level SEC search targets."""
    targets: list[dict[str, str]] = []
    for row in rows:
        bank = row["canonical_bank_name"]
        seed = issuer_seed[bank]
        patent_id = row["patent_id"]
        application_id = application_map[patent_id]
        patent_with_commas = format_patent_number(patent_id)
        application_slash = format_application_number(application_id)
        sec_entity = seed["sec_search_entity"]
        targets.append(
            {
                "bank_display_name": seed["bank_display_name"],
                "patent_canonical_bank_name": bank,
                "parent_bank_group": row["parent_bank_group"],
                "sec_search_entity": sec_entity,
                "sec_search_aliases": seed["sec_search_aliases"],
                "sec_ticker": seed["sec_ticker"],
                "sec_cik": seed["sec_cik"],
                "sec_form_types": seed["sec_form_types"],
                "is_sec_filer_candidate": seed["is_sec_filer_candidate"],
                "manual_review_note": seed["manual_review_note"],
                "patent_id": patent_id,
                "patent_number_with_commas": patent_with_commas,
                "us_patent_plain": f"US{patent_id}",
                "us_patent_with_commas": f"US {patent_with_commas}",
                "application_id": application_id,
                "application_id_stripped": application_id.lstrip("0"),
                "application_number_slash": application_slash,
                "patent_title": row["patent_title"],
                "filing_date": row["filing_date"],
                "grant_date": row["grant_date"],
                "exact_patent_query": f"\"{patent_with_commas}\" \"{sec_entity}\"",
                "exact_application_query": f"\"{application_slash}\" \"{sec_entity}\"",
                "keyword_query": f"\"{sec_entity}\" ({SEC_KEYWORDS})",
            }
        )
    return targets


def build_bank_targets(targets: list[dict[str, str]]) -> list[dict[str, str]]:
    """Collapse patent targets to one bank-level SEC search row per bank."""
    grouped: dict[str, dict[str, object]] = {}
    for row in targets:
        bank = row["patent_canonical_bank_name"]
        info = grouped.setdefault(
            bank,
            {
                "bank_display_name": row["bank_display_name"],
                "patent_canonical_bank_name": bank,
                "sec_search_entity": row["sec_search_entity"],
                "sec_search_aliases": row["sec_search_aliases"],
                "sec_form_types": row["sec_form_types"],
                "is_sec_filer_candidate": row["is_sec_filer_candidate"],
                "manual_review_note": row["manual_review_note"],
                "patent_count": 0,
                "filing_years": [],
                "grant_years": [],
            },
        )
        info["patent_count"] = int(info["patent_count"]) + 1
        info["filing_years"].append(int(row["filing_date"][:4]))
        info["grant_years"].append(int(row["grant_date"][:4]))

    bank_targets: list[dict[str, str]] = []
    for info in grouped.values():
        filing_years = sorted(set(info["filing_years"]))
        grant_years = sorted(set(info["grant_years"]))
        recommended_start_year = max(2001, min(filing_years) - 1)
        bank_targets.append(
            {
                "bank_display_name": str(info["bank_display_name"]),
                "patent_canonical_bank_name": str(info["patent_canonical_bank_name"]),
                "sec_search_entity": str(info["sec_search_entity"]),
                "sec_search_aliases": str(info["sec_search_aliases"]),
                "sec_ticker": str(next(row["sec_ticker"] for row in targets if row["patent_canonical_bank_name"] == info["patent_canonical_bank_name"])),
                "sec_cik": str(next(row["sec_cik"] for row in targets if row["patent_canonical_bank_name"] == info["patent_canonical_bank_name"])),
                "sec_form_types": str(info["sec_form_types"]),
                "is_sec_filer_candidate": str(info["is_sec_filer_candidate"]),
                "patent_count": str(info["patent_count"]),
                "min_filing_year": str(min(filing_years)),
                "max_filing_year": str(max(filing_years)),
                "min_grant_year": str(min(grant_years)),
                "max_grant_year": str(max(grant_years)),
                "recommended_sec_start_year": str(recommended_start_year),
                "recommended_sec_end_year": str(CURRENT_YEAR),
                "manual_review_note": str(info["manual_review_note"]),
                "recommended_keyword_query": f"\"{info['sec_search_entity']}\" ({SEC_KEYWORDS})",
            }
        )
    bank_targets.sort(key=lambda row: (-int(row["patent_count"]), row["bank_display_name"]))
    return bank_targets


def build_download_plan(bank_targets: list[dict[str, str]]) -> list[dict[str, str]]:
    """Expand bank targets to a form-level download plan."""
    plan: list[dict[str, str]] = []
    for row in bank_targets:
        form_types = [value for value in row["sec_form_types"].split("|") if value]
        if row["is_sec_filer_candidate"] != "1" or not form_types:
            continue
        for form_type in form_types:
            plan.append(
                {
                    "bank_display_name": row["bank_display_name"],
                    "patent_canonical_bank_name": row["patent_canonical_bank_name"],
                    "sec_search_entity": row["sec_search_entity"],
                    "sec_ticker": row["sec_ticker"],
                    "sec_cik": row["sec_cik"],
                    "form_type": form_type,
                    "recommended_sec_start_year": row["recommended_sec_start_year"],
                    "recommended_sec_end_year": row["recommended_sec_end_year"],
                    "download_priority": "high" if form_type in {"8-K", "20-F", "40-F"} else "medium",
                    "search_focus": "Patent number exact matches, application number exact matches, license, settlement, infringement, Exhibit 10, Item 3, Item 1.01.",
                }
            )
    return plan


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Write a CSV with stable field order from the first row."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"No rows to write for {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = read_patent_rows()
    issuer_seed = load_issuer_seed()
    patent_ids = {row["patent_id"] for row in rows}
    application_map = load_application_map(patent_ids)

    missing = sorted(patent_ids - set(application_map))
    if missing:
        raise ValueError(f"Missing application_id for {len(missing)} patents")

    patent_targets = build_patent_targets(rows, issuer_seed, application_map)
    bank_targets = build_bank_targets(patent_targets)
    download_plan = build_download_plan(bank_targets)

    write_csv(RESULTS_DIR / "sec_patent_targets.csv", patent_targets)
    write_csv(RESULTS_DIR / "sec_bank_targets.csv", bank_targets)
    write_csv(RESULTS_DIR / "sec_download_plan.csv", download_plan)

    print(f"Wrote {len(patent_targets)} patent targets")
    print(f"Wrote {len(bank_targets)} bank targets")
    print(f"Wrote {len(download_plan)} download plan rows")


if __name__ == "__main__":
    main()
