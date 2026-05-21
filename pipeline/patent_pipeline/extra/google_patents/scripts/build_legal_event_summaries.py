from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "raw" / "google_patents_legal_events"
OUT_DIR = BASE_DIR / "results"

ACCLAIMIP_URL = "https://help.acclaimip.com/m/acclaimip_help/l/378003-legal-event-code-lgl_code"

OBSERVED_CODE_RULES = {
    "AS": {
        "category": "assignment_governance",
        "l_signal_role": "governance_only",
        "research_note": (
            "Generic assignment bucket. In this sample the detail text is overwhelmingly "
            "inventor-to-assignee transfer language; two events contain MERGER text and no "
            "license/security text was observed."
        ),
        "source_url": ACCLAIMIP_URL,
    },
    "CC": {
        "category": "correction",
        "l_signal_role": "none",
        "research_note": "Certificate of correction. Administrative cleanup rather than an external-use signal.",
        "source_url": "",
    },
    "FEPP": {
        "category": "fee_admin",
        "l_signal_role": "none",
        "research_note": "Entity-status and fee-procedure events, typically showing large/small/micro status setup.",
        "source_url": "",
    },
    "FP": {
        "category": "maintenance_lapse",
        "l_signal_role": "none",
        "research_note": "Patent lapsed due to failure to pay maintenance fees.",
        "source_url": ACCLAIMIP_URL,
    },
    "FPAY": {
        "category": "maintenance_payment",
        "l_signal_role": "none",
        "research_note": "Fee payment event. In this sample it is maintenance-related rather than licensing-related.",
        "source_url": ACCLAIMIP_URL,
    },
    "LAPS": {
        "category": "maintenance_lapse",
        "l_signal_role": "none",
        "research_note": "Lapse for failure to pay maintenance fees.",
        "source_url": ACCLAIMIP_URL,
    },
    "MAFP": {
        "category": "maintenance_payment",
        "l_signal_role": "none",
        "research_note": "Maintenance fee payment event with year-of-fee information in the detail text.",
        "source_url": ACCLAIMIP_URL,
    },
    "STCB": {
        "category": "application_discontinuation",
        "l_signal_role": "none",
        "research_note": "Application discontinuation, typically abandonment after failure to respond.",
        "source_url": "",
    },
    "STCC": {
        "category": "application_revival",
        "l_signal_role": "none",
        "research_note": "Application revival or withdrawal of abandonment.",
        "source_url": "",
    },
    "STCF": {
        "category": "grant_status",
        "l_signal_role": "none",
        "research_note": "Patent grant event.",
        "source_url": "",
    },
    "STCH": {
        "category": "patent_discontinuation",
        "l_signal_role": "none",
        "research_note": "Patent discontinuation status. In this sample it is tied to nonpayment-based expiry.",
        "source_url": "",
    },
    "STCV": {
        "category": "appeal_status",
        "l_signal_role": "none",
        "research_note": "Appeal-procedure status event, such as a notice of appeal.",
        "source_url": "",
    },
    "STPP": {
        "category": "prosecution_status",
        "l_signal_role": "none",
        "research_note": (
            "Generic prosecution-status bucket covering office actions, responses, issue-fee processing, "
            "and other application/granting milestones."
        ),
        "source_url": "",
    },
    "ZAAA": {
        "category": "allowance_status",
        "l_signal_role": "none",
        "research_note": "Notice of allowance and fees due.",
        "source_url": "",
    },
    "ZAAB": {
        "category": "allowance_status",
        "l_signal_role": "none",
        "research_note": "Notice of allowance mailed.",
        "source_url": "",
    },
}

WATCHLIST_CODES = {
    "AS03": {
        "title": "Merger",
        "category": "external_use_watchlist",
        "l_signal_role": "strong_if_present",
        "research_note": "Could support L when the patent right moves through an external merger or acquisition boundary.",
        "source_url": ACCLAIMIP_URL,
    },
    "AS04": {
        "title": "License",
        "category": "external_use_watchlist",
        "l_signal_role": "strong_if_present",
        "research_note": "Direct licensing signal if it appears.",
        "source_url": ACCLAIMIP_URL,
    },
    "AS06": {
        "title": "Security interest",
        "category": "finance_watchlist",
        "l_signal_role": "sidecar_only",
        "research_note": "Collateral or financing signal, not a core leveraging measure.",
        "source_url": ACCLAIMIP_URL,
    },
    "AS24": {
        "title": "Release of security agreement",
        "category": "finance_watchlist",
        "l_signal_role": "sidecar_only",
        "research_note": "Release of collateral/security agreement.",
        "source_url": ACCLAIMIP_URL,
    },
    "AS25": {
        "title": "Release of security interest",
        "category": "finance_watchlist",
        "l_signal_role": "sidecar_only",
        "research_note": "Release of security interest.",
        "source_url": ACCLAIMIP_URL,
    },
    "AS31": {
        "title": "Confirmatory license",
        "category": "external_use_watchlist",
        "l_signal_role": "strong_if_present",
        "research_note": "Observed licensing signal if it appears.",
        "source_url": ACCLAIMIP_URL,
    },
    "AS33": {
        "title": "Exclusive license",
        "category": "external_use_watchlist",
        "l_signal_role": "strong_if_present",
        "research_note": "Observed exclusive-license signal if it appears.",
        "source_url": ACCLAIMIP_URL,
    },
    "PA": {
        "title": "Patent available for license or sale",
        "category": "external_use_watchlist",
        "l_signal_role": "strong_if_present",
        "research_note": "Direct commercialization or marketing-for-technology signal.",
        "source_url": ACCLAIMIP_URL,
    },
    "PS": {
        "title": "Patent suit(s) filed",
        "category": "litigation_watchlist",
        "l_signal_role": "sidecar_only",
        "research_note": "Litigation or enforcement signal; useful as a sidecar rather than core L.",
        "source_url": ACCLAIMIP_URL,
    },
}

ASSIGNMENT_KEYWORDS = {
    "assignment_of_assignor_interest": [r"ASSIGNMENT OF ASSIGNORS? INTEREST"],
    "merger": [r"\bMERGER\b"],
    "license": [r"\bLICEN[CS]E\b"],
    "confirmatory": [r"\bCONFIRMATORY\b"],
    "exclusive": [r"\bEXCLUSIVE\b"],
    "security_interest": [r"\bSECURITY INTEREST\b", r"\bSECURITY AGREEMENT\b"],
    "litigation": [r"\bPATENT SUIT\b", r"\bLITIGATION\b"],
    "sale": [r"\bSALE\b"],
}


def cleaned_text(details: list[dict]) -> str:
    parts: list[str] = []
    for detail in details:
        value = (detail.get("value") or "").strip()
        if value:
            parts.append(value)
    return " | ".join(parts)


def keyword_hits(text_upper: str) -> dict[str, int]:
    hits: dict[str, int] = {}
    for key, patterns in ASSIGNMENT_KEYWORDS.items():
        hits[key] = int(any(re.search(pattern, text_upper) for pattern in patterns))
    return hits


def parse_original_event_codes(text: str) -> list[str]:
    marker = "ORIGINAL EVENT CODE:"
    if marker not in text:
        return []
    values: list[str] = []
    for piece in text.split(marker)[1:]:
        values.append(piece.split(")", 1)[0].strip(" ;."))
    return [value for value in values if value]


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    code_event_count = Counter()
    code_patents = defaultdict(set)
    code_banks = defaultdict(set)
    code_titles = Counter()
    code_examples: dict[str, dict] = {}
    orig_event_count = Counter()

    assignment_keyword_rows = Counter()
    assignment_keyword_patents = defaultdict(set)
    patent_rows: list[dict] = []
    bank_rollup = defaultdict(lambda: Counter())

    for path in sorted(RAW_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        patent_id = data["patent_id"]
        bank = data.get("canonical_bank_name", "")
        patent_url = data.get("google_patents_url", "")
        legal_events = data.get("legal_events", [])
        worldwide_apps = data.get("worldwide_applications", [])

        codes_for_patent = set()
        assignment_texts: list[str] = []
        assignment_merger_count = 0
        observed_external_code = 0

        for event in legal_events:
            code = (event.get("code") or "").strip()
            title = (event.get("title") or "").strip()
            if not code:
                continue
            codes_for_patent.add(code)
            code_event_count[code] += 1
            code_patents[code].add(patent_id)
            code_banks[code].add(bank)
            code_titles[(code, title)] += 1

            detail_text = cleaned_text(event.get("details", []))
            detail_upper = detail_text.upper()

            if code not in code_examples:
                code_examples[code] = {
                    "patent_id": patent_id,
                    "canonical_bank_name": bank,
                    "google_patents_url": patent_url,
                    "date": event.get("date", ""),
                    "title": title,
                    "detail_text": detail_text,
                }

            for original_code in parse_original_event_codes(detail_text):
                orig_event_count[original_code] += 1

            if code == "AS":
                assignment_texts.append(detail_text)
                hits = keyword_hits(detail_upper)
                if hits["merger"]:
                    assignment_merger_count += 1
                for keyword, hit in hits.items():
                    if hit:
                        assignment_keyword_rows[keyword] += 1
                        assignment_keyword_patents[keyword].add(patent_id)

            if code in WATCHLIST_CODES:
                observed_external_code = 1

        all_assignment_text = " || ".join(assignment_texts)
        assignment_text_upper = all_assignment_text.upper()
        assignment_text_flags = keyword_hits(assignment_text_upper)

        countries = {entry.get("country", "") for entry in worldwide_apps if entry.get("country")}
        non_us_count = sum(1 for entry in worldwide_apps if entry.get("country") and entry.get("country") != "US")

        row = {
            "patent_id": patent_id,
            "canonical_bank_name": bank,
            "google_patents_url": patent_url,
            "legal_event_count": len(legal_events),
            "legal_event_codes": "|".join(sorted(codes_for_patent)),
            "has_assignment": int("AS" in codes_for_patent),
            "has_assignment_merger_text": assignment_text_flags["merger"],
            "has_assignment_license_text": assignment_text_flags["license"],
            "has_assignment_confirmatory_text": assignment_text_flags["confirmatory"],
            "has_assignment_exclusive_text": assignment_text_flags["exclusive"],
            "has_assignment_security_text": assignment_text_flags["security_interest"],
            "has_assignment_sale_text": assignment_text_flags["sale"],
            "has_assignment_litigation_text": assignment_text_flags["litigation"],
            "has_correction": int("CC" in codes_for_patent),
            "has_fee_admin": int("FEPP" in codes_for_patent),
            "has_maintenance_payment": int(bool({"MAFP", "FPAY"} & codes_for_patent)),
            "has_maintenance_lapse": int(bool({"FP", "LAPS", "STCH"} & codes_for_patent)),
            "has_grant": int("STCF" in codes_for_patent),
            "has_prosecution_status": int("STPP" in codes_for_patent),
            "has_allowance": int(bool({"ZAAB", "ZAAA"} & codes_for_patent)),
            "has_appeal": int("STCV" in codes_for_patent),
            "has_application_discontinuation": int("STCB" in codes_for_patent),
            "has_application_revival": int("STCC" in codes_for_patent),
            "has_observed_external_l_code": observed_external_code,
            "worldwide_application_count": len(worldwide_apps),
            "non_us_worldwide_application_count": non_us_count,
            "worldwide_country_count": len(countries),
            "has_foreign_family": int(non_us_count > 0),
        }
        patent_rows.append(row)

        bank_rollup[bank]["patent_count"] += 1
        for key, value in row.items():
            if key.startswith("has_"):
                bank_rollup[bank][key] += value
        bank_rollup[bank]["worldwide_application_count"] += row["worldwide_application_count"]
        bank_rollup[bank]["non_us_worldwide_application_count"] += row["non_us_worldwide_application_count"]
        bank_rollup[bank]["worldwide_country_count_total"] += row["worldwide_country_count"]
        bank_rollup[bank]["foreign_family_patent_count"] += row["has_foreign_family"]

    codebook_rows: list[dict] = []
    all_codes = sorted(set(code_event_count) | set(WATCHLIST_CODES))
    total_patents = len(patent_rows)

    for code in all_codes:
        observed = code in code_event_count
        title_counter = Counter(
            {title: count for (code_key, title), count in code_titles.items() if code_key == code}
        )
        title = title_counter.most_common(1)[0][0] if title_counter else WATCHLIST_CODES.get(code, {}).get("title", "")
        rule = OBSERVED_CODE_RULES.get(code, WATCHLIST_CODES.get(code, {}))
        example = code_examples.get(code, {})
        codebook_rows.append(
            {
                "code": code,
                "observed_in_sample": int(observed),
                "title": title,
                "category": rule.get("category", "unclassified"),
                "l_signal_role": rule.get("l_signal_role", "unknown"),
                "event_count": code_event_count.get(code, 0),
                "unique_patent_count": len(code_patents.get(code, set())),
                "unique_bank_count": len(code_banks.get(code, set())),
                "patent_share": round(len(code_patents.get(code, set())) / total_patents, 6) if total_patents else 0,
                "research_note": rule.get("research_note", ""),
                "example_patent_id": example.get("patent_id", ""),
                "example_bank": example.get("canonical_bank_name", ""),
                "example_date": example.get("date", ""),
                "example_detail_text": example.get("detail_text", ""),
                "source_url": rule.get("source_url", "") or example.get("google_patents_url", ""),
            }
        )

    assignment_keyword_summary_rows = []
    for keyword in sorted(ASSIGNMENT_KEYWORDS):
        assignment_keyword_summary_rows.append(
            {
                "keyword_bucket": keyword,
                "event_row_count": assignment_keyword_rows.get(keyword, 0),
                "unique_patent_count": len(assignment_keyword_patents.get(keyword, set())),
                "research_note": (
                    "Key check for whether the generic AS bucket hides a cleaner leveraging-type signal."
                ),
            }
        )

    original_event_rows = [
        {"original_event_code": code, "event_count": count}
        for code, count in orig_event_count.most_common()
    ]

    bank_rows = []
    for bank in sorted(bank_rollup):
        counts = bank_rollup[bank]
        patent_count = counts["patent_count"] or 1
        bank_rows.append(
            {
                "canonical_bank_name": bank,
                "patent_count": counts["patent_count"],
                "patents_with_assignment": counts["has_assignment"],
                "patents_with_assignment_merger_text": counts["has_assignment_merger_text"],
                "patents_with_assignment_license_text": counts["has_assignment_license_text"],
                "patents_with_assignment_security_text": counts["has_assignment_security_text"],
                "patents_with_maintenance_payment": counts["has_maintenance_payment"],
                "patents_with_maintenance_lapse": counts["has_maintenance_lapse"],
                "patents_with_prosecution_status": counts["has_prosecution_status"],
                "patents_with_appeal": counts["has_appeal"],
                "patents_with_observed_external_l_code": counts["has_observed_external_l_code"],
                "foreign_family_patent_count": counts["foreign_family_patent_count"],
                "foreign_family_share": round(counts["foreign_family_patent_count"] / patent_count, 6),
                "avg_worldwide_application_count": round(counts["worldwide_application_count"] / patent_count, 4),
                "avg_non_us_worldwide_application_count": round(
                    counts["non_us_worldwide_application_count"] / patent_count, 4
                ),
            }
        )

    watchlist_rows = []
    for code, meta in WATCHLIST_CODES.items():
        watchlist_rows.append(
            {
                "code": code,
                "title": meta["title"],
                "category": meta["category"],
                "l_signal_role": meta["l_signal_role"],
                "event_count_in_sample": code_event_count.get(code, 0),
                "unique_patent_count_in_sample": len(code_patents.get(code, set())),
                "research_note": meta["research_note"],
                "source_url": meta["source_url"],
            }
        )

    write_csv(
        OUT_DIR / "google_patents_legal_event_codebook.csv",
        codebook_rows,
        [
            "code",
            "observed_in_sample",
            "title",
            "category",
            "l_signal_role",
            "event_count",
            "unique_patent_count",
            "unique_bank_count",
            "patent_share",
            "research_note",
            "example_patent_id",
            "example_bank",
            "example_date",
            "example_detail_text",
            "source_url",
        ],
    )

    write_csv(
        OUT_DIR / "google_patents_assignment_keyword_scan.csv",
        assignment_keyword_summary_rows,
        ["keyword_bucket", "event_row_count", "unique_patent_count", "research_note"],
    )

    write_csv(
        OUT_DIR / "google_patents_original_event_codes.csv",
        original_event_rows,
        ["original_event_code", "event_count"],
    )

    write_csv(
        OUT_DIR / "google_patents_legal_event_patent_flags.csv",
        patent_rows,
        [
            "patent_id",
            "canonical_bank_name",
            "google_patents_url",
            "legal_event_count",
            "legal_event_codes",
            "has_assignment",
            "has_assignment_merger_text",
            "has_assignment_license_text",
            "has_assignment_confirmatory_text",
            "has_assignment_exclusive_text",
            "has_assignment_security_text",
            "has_assignment_sale_text",
            "has_assignment_litigation_text",
            "has_correction",
            "has_fee_admin",
            "has_maintenance_payment",
            "has_maintenance_lapse",
            "has_grant",
            "has_prosecution_status",
            "has_allowance",
            "has_appeal",
            "has_application_discontinuation",
            "has_application_revival",
            "has_observed_external_l_code",
            "worldwide_application_count",
            "non_us_worldwide_application_count",
            "worldwide_country_count",
            "has_foreign_family",
        ],
    )

    write_csv(
        OUT_DIR / "google_patents_legal_event_bank_summary.csv",
        bank_rows,
        [
            "canonical_bank_name",
            "patent_count",
            "patents_with_assignment",
            "patents_with_assignment_merger_text",
            "patents_with_assignment_license_text",
            "patents_with_assignment_security_text",
            "patents_with_maintenance_payment",
            "patents_with_maintenance_lapse",
            "patents_with_prosecution_status",
            "patents_with_appeal",
            "patents_with_observed_external_l_code",
            "foreign_family_patent_count",
            "foreign_family_share",
            "avg_worldwide_application_count",
            "avg_non_us_worldwide_application_count",
        ],
    )

    write_csv(
        OUT_DIR / "google_patents_legal_event_watchlist.csv",
        watchlist_rows,
        [
            "code",
            "title",
            "category",
            "l_signal_role",
            "event_count_in_sample",
            "unique_patent_count_in_sample",
            "research_note",
            "source_url",
        ],
    )


if __name__ == "__main__":
    main()
