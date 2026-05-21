from __future__ import annotations

import csv
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATENT_PIPELINE_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "raw"
SAMPLE_PATENTS_CSV = PATENT_PIPELINE_ROOT / "results/latest/03_final/patents.csv"
EVENT_HITS_CSV = ROOT / "results/assignment_event_hits.csv"
PATENT_FLAGS_CSV = ROOT / "results/assignment_patent_flags.csv"
KEYWORD_SUMMARY_CSV = ROOT / "results/assignment_keyword_summary.csv"

TAG_VALUE_PATTERN = re.compile(r"<(?P<tag>[A-Za-z0-9-]+)>(?P<value>.*?)</(?P=tag)>")
KEYWORD_PATTERNS = {
    "assignment_of_assignor_interest": re.compile(r"ASSIGNMENT OF ASSIGNORS? INTEREST", re.IGNORECASE),
    "merger": re.compile(r"\bMERGER\b", re.IGNORECASE),
    "license": re.compile(r"\bLICEN[CS](?:E|ES|ED|ING)?\b", re.IGNORECASE),
    "confirmatory": re.compile(r"\bCONFIRMATORY\b", re.IGNORECASE),
    "exclusive": re.compile(r"\bEXCLUSIVE\b", re.IGNORECASE),
    "security": re.compile(r"\bSECURITY (?:INTEREST|AGREEMENT)\b", re.IGNORECASE),
    "sale": re.compile(r"\bSALE\b", re.IGNORECASE),
    "litigation": re.compile(r"\bLITIGATION\b|\bPATENT SUIT\b", re.IGNORECASE),
}


def load_sample_rows() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with SAMPLE_PATENTS_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            patent_id = row["patent_id"].strip()
            rows[patent_id] = {
                "canonical_bank_name": row.get("canonical_bank_name", "").strip(),
                "parent_bank_group": row.get("parent_bank_group", "").strip(),
                "patent_title": row.get("patent_title", "").strip(),
            }
    return rows


def keyword_flags(text: str) -> dict[str, int]:
    return {name: int(bool(pattern.search(text))) for name, pattern in KEYWORD_PATTERNS.items()}


def empty_assignment() -> dict[str, object]:
    return {
        "reel_no": "",
        "frame_no": "",
        "recorded_date": "",
        "conveyance_text": "",
        "assignor_names": [],
        "assignee_names": [],
        "patent_ids": set(),
    }


def extract_tag_value(line: str) -> tuple[str, str] | None:
    match = TAG_VALUE_PATTERN.search(line)
    if not match:
        return None
    return match.group("tag"), match.group("value").strip()


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    sample_rows = load_sample_rows()
    sample_set = set(sample_rows)
    patent_flags = defaultdict(lambda: Counter())
    keyword_event_counts = Counter()
    keyword_patent_counts = defaultdict(set)

    event_fieldnames = [
        "patent_id",
        "canonical_bank_name",
        "parent_bank_group",
        "patent_title",
        "source_zip",
        "source_xml",
        "reel_no",
        "frame_no",
        "recorded_date",
        "conveyance_text",
        "assignor_names",
        "assignee_names",
        "has_assignment_of_assignor_interest_text",
        "has_assignment_merger_text",
        "has_assignment_license_text",
        "has_assignment_confirmatory_text",
        "has_assignment_exclusive_text",
        "has_assignment_security_text",
        "has_assignment_sale_text",
        "has_assignment_litigation_text",
    ]
    EVENT_HITS_CSV.parent.mkdir(parents=True, exist_ok=True)
    event_tmp = EVENT_HITS_CSV.with_name(f"{EVENT_HITS_CSV.name}.tmp")
    event_row_count = 0
    with event_tmp.open("w", newline="", encoding="utf-8") as event_handle:
        event_writer = csv.DictWriter(event_handle, fieldnames=event_fieldnames)
        event_writer.writeheader()

        for zip_path in sorted(RAW_DIR.glob("*.zip")):
            with zipfile.ZipFile(zip_path) as archive:
                for member_name in archive.namelist():
                    if not member_name.endswith(".xml"):
                        continue
                    with archive.open(member_name) as handle:
                        assignment = empty_assignment()
                        in_assignment = False
                        in_recorded_date = False
                        current_party: str | None = None
                        current_doc: dict[str, str] | None = None

                        for raw_line in handle:
                            line = raw_line.decode("utf-8", "ignore").strip()
                            if not line:
                                continue

                            if line == "<patent-assignment>":
                                assignment = empty_assignment()
                                in_assignment = True
                                in_recorded_date = False
                                current_party = None
                                current_doc = None
                                continue

                            if not in_assignment:
                                continue

                            if line == "</patent-assignment>":
                                patent_ids = sorted(assignment["patent_ids"])
                                if patent_ids:
                                    conveyance_text = str(assignment["conveyance_text"])
                                    flags = keyword_flags(conveyance_text)
                                    for keyword, hit in flags.items():
                                        if hit:
                                            keyword_event_counts[keyword] += 1
                                            for patent_id in patent_ids:
                                                keyword_patent_counts[keyword].add(patent_id)

                                    assignor_names = " | ".join(assignment["assignor_names"])
                                    assignee_names = " | ".join(assignment["assignee_names"])
                                    for patent_id in patent_ids:
                                        sample_info = sample_rows[patent_id]
                                        event_writer.writerow(
                                            {
                                                "patent_id": patent_id,
                                                "canonical_bank_name": sample_info["canonical_bank_name"],
                                                "parent_bank_group": sample_info["parent_bank_group"],
                                                "patent_title": sample_info["patent_title"],
                                                "source_zip": zip_path.name,
                                                "source_xml": member_name,
                                                "reel_no": str(assignment["reel_no"]),
                                                "frame_no": str(assignment["frame_no"]),
                                                "recorded_date": str(assignment["recorded_date"]),
                                                "conveyance_text": conveyance_text,
                                                "assignor_names": assignor_names,
                                                "assignee_names": assignee_names,
                                                "has_assignment_of_assignor_interest_text": str(flags["assignment_of_assignor_interest"]),
                                                "has_assignment_merger_text": str(flags["merger"]),
                                                "has_assignment_license_text": str(flags["license"]),
                                                "has_assignment_confirmatory_text": str(flags["confirmatory"]),
                                                "has_assignment_exclusive_text": str(flags["exclusive"]),
                                                "has_assignment_security_text": str(flags["security"]),
                                                "has_assignment_sale_text": str(flags["sale"]),
                                                "has_assignment_litigation_text": str(flags["litigation"]),
                                            }
                                        )
                                        event_row_count += 1

                                        patent_flags[patent_id]["assignment_event_count"] += 1
                                        patent_flags[patent_id]["has_assignment"] = 1
                                        if flags["merger"]:
                                            patent_flags[patent_id]["has_assignment_merger_text"] = 1
                                        if flags["license"]:
                                            patent_flags[patent_id]["has_assignment_license_text"] = 1
                                        if flags["confirmatory"]:
                                            patent_flags[patent_id]["has_assignment_confirmatory_text"] = 1
                                        if flags["exclusive"]:
                                            patent_flags[patent_id]["has_assignment_exclusive_text"] = 1
                                        if flags["security"]:
                                            patent_flags[patent_id]["has_assignment_security_text"] = 1
                                        if flags["sale"]:
                                            patent_flags[patent_id]["has_assignment_sale_text"] = 1
                                        if flags["litigation"]:
                                            patent_flags[patent_id]["has_assignment_litigation_text"] = 1

                                in_assignment = False
                                in_recorded_date = False
                                current_party = None
                                current_doc = None
                                continue

                            if line == "<recorded-date>":
                                in_recorded_date = True
                                continue
                            if line == "</recorded-date>":
                                in_recorded_date = False
                                continue
                            if line == "<patent-assignor>":
                                current_party = "assignor"
                                continue
                            if line == "</patent-assignor>":
                                current_party = None
                                continue
                            if line == "<patent-assignee>":
                                current_party = "assignee"
                                continue
                            if line == "</patent-assignee>":
                                current_party = None
                                continue
                            if line == "<document-id>":
                                current_doc = {}
                                continue
                            if line == "</document-id>":
                                if current_doc:
                                    country = current_doc.get("country", "").upper()
                                    kind = current_doc.get("kind", "").upper()
                                    doc_number = re.sub(r"\D", "", current_doc.get("doc-number", ""))
                                    if country == "US" and doc_number and kind != "X0" and doc_number in sample_set:
                                        assignment["patent_ids"].add(doc_number)
                                current_doc = None
                                continue

                            tag_value = extract_tag_value(line)
                            if not tag_value:
                                continue
                            tag, value = tag_value

                            if tag == "reel-no":
                                assignment["reel_no"] = value
                            elif tag == "frame-no":
                                assignment["frame_no"] = value
                            elif tag == "conveyance-text":
                                assignment["conveyance_text"] = value
                            elif tag == "date" and in_recorded_date:
                                assignment["recorded_date"] = value
                            elif tag == "name" and current_party == "assignor":
                                assignment["assignor_names"].append(value)
                            elif tag == "name" and current_party == "assignee":
                                assignment["assignee_names"].append(value)
                            elif current_doc is not None and tag in {"country", "doc-number", "kind"}:
                                current_doc[tag] = value

    event_tmp.replace(EVENT_HITS_CSV)

    patent_rows: list[dict[str, str]] = []
    for patent_id in sample_rows:
        info = sample_rows[patent_id]
        flags = patent_flags[patent_id]
        patent_rows.append(
            {
                "patent_id": patent_id,
                "canonical_bank_name": info["canonical_bank_name"],
                "parent_bank_group": info["parent_bank_group"],
                "patent_title": info["patent_title"],
                "assignment_event_count": str(flags.get("assignment_event_count", 0)),
                "has_assignment": str(flags.get("has_assignment", 0)),
                "has_assignment_merger_text": str(flags.get("has_assignment_merger_text", 0)),
                "has_assignment_license_text": str(flags.get("has_assignment_license_text", 0)),
                "has_assignment_confirmatory_text": str(flags.get("has_assignment_confirmatory_text", 0)),
                "has_assignment_exclusive_text": str(flags.get("has_assignment_exclusive_text", 0)),
                "has_assignment_security_text": str(flags.get("has_assignment_security_text", 0)),
                "has_assignment_sale_text": str(flags.get("has_assignment_sale_text", 0)),
                "has_assignment_litigation_text": str(flags.get("has_assignment_litigation_text", 0)),
            }
        )

    patent_fieldnames = [
        "patent_id",
        "canonical_bank_name",
        "parent_bank_group",
        "patent_title",
        "assignment_event_count",
        "has_assignment",
        "has_assignment_merger_text",
        "has_assignment_license_text",
        "has_assignment_confirmatory_text",
        "has_assignment_exclusive_text",
        "has_assignment_security_text",
        "has_assignment_sale_text",
        "has_assignment_litigation_text",
    ]
    write_csv(PATENT_FLAGS_CSV, patent_rows, patent_fieldnames)

    summary_rows = []
    for keyword in sorted(KEYWORD_PATTERNS):
        summary_rows.append(
            {
                "keyword": keyword,
                "event_row_count": str(keyword_event_counts.get(keyword, 0)),
                "unique_patent_count": str(len(keyword_patent_counts.get(keyword, set()))),
            }
        )
    write_csv(
        KEYWORD_SUMMARY_CSV,
        summary_rows,
        ["keyword", "event_row_count", "unique_patent_count"],
    )

    print(f"Wrote {event_row_count} assignment event rows to {EVENT_HITS_CSV}")
    print(f"Wrote {len(patent_rows)} patent-level assignment rows to {PATENT_FLAGS_CSV}")
    print(f"Wrote assignment keyword summary to {KEYWORD_SUMMARY_CSV}")


if __name__ == "__main__":
    main()
