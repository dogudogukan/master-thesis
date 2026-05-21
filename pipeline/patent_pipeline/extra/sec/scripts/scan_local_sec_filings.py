"""
Scan locally cached SEC filings for exact patent/application mentions and
broader keyword hits.
"""

from __future__ import annotations

import argparse
import csv
import html
import re
from dataclasses import dataclass
from pathlib import Path


SEC_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS_CSV = SEC_ROOT / "results/sec_patent_targets.csv"
DEFAULT_FILINGS_DIR = SEC_ROOT / "raw/sec_filings"
DEFAULT_EXACT_HITS_CSV = SEC_ROOT / "results/sec_exact_hits.csv"
DEFAULT_KEYWORD_HITS_CSV = SEC_ROOT / "results/sec_keyword_file_hits.csv"
TEXT_SUFFIXES = {".txt", ".htm", ".html", ".xml", ".json"}
TAG_PATTERN = re.compile(r"<[^>]+>")
KEYWORD_PATTERNS = {
    "license": re.compile(r"\blicen[sc](?:e|es|ed|ing)\b", re.IGNORECASE),
    "infringement": re.compile(r"\binfring(?:e|ed|ement|ing)\b", re.IGNORECASE),
    "settlement": re.compile(r"\bsettlement\b", re.IGNORECASE),
    "technology_agreement": re.compile(r"\btechnology agreement\b", re.IGNORECASE),
    "intellectual_property": re.compile(r"\bintellectual property\b", re.IGNORECASE),
    "patent": re.compile(r"\bpatent(?:s)?\b", re.IGNORECASE),
}
FORM_TYPE_PATTERN = re.compile(r"(?:^|[^A-Z0-9])(10-K|10-Q|8-K|20-F|40-F|6-K)(?:[^A-Z0-9]|$)", re.IGNORECASE)


@dataclass
class Target:
    bank_display_name: str
    patent_canonical_bank_name: str
    sec_search_entity: str
    sec_search_aliases: list[str]
    patent_id: str
    application_id: str
    marker_specs: list[tuple[str, str, bool]]


def patent_patterns(patent_id: str, patent_with_commas: str) -> list[tuple[str, str, bool]]:
    """Build exact-match patterns for one granted patent number."""
    return [
        ("patent_plain", patent_id.lower(), True),
        ("patent_commas", patent_with_commas.lower(), True),
        ("us_patent_plain", f"us {patent_id}".lower(), False),
        ("us_patent_commas", f"us {patent_with_commas}".lower(), False),
        ("us_patent_no_commas", f"u.s. patent no. {patent_with_commas}".lower(), False),
        ("us_patent_no_plain", f"us patent no. {patent_with_commas}".lower(), False),
    ]


def application_patterns(application_id: str, application_slash: str) -> list[tuple[str, str, bool]]:
    """Build exact-match patterns for one application number."""
    stripped = application_id.lstrip("0")
    return [
        ("application_plain", stripped.lower(), True),
        ("application_slash", application_slash.lower(), True),
    ]


def load_targets(path: Path) -> tuple[list[Target], dict[str, list[Target]]]:
    """Load patent-level SEC targets and index them by bank."""
    targets: list[Target] = []
    by_bank: dict[str, list[Target]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            aliases = [value.strip() for value in row["sec_search_aliases"].split("|") if value.strip()]
            aliases.extend([row["sec_search_entity"], row["bank_display_name"]])
            specs = patent_patterns(row["patent_id"], row["patent_number_with_commas"])
            specs.extend(application_patterns(row["application_id"], row["application_number_slash"]))
            target = Target(
                bank_display_name=row["bank_display_name"],
                patent_canonical_bank_name=row["patent_canonical_bank_name"],
                sec_search_entity=row["sec_search_entity"],
                sec_search_aliases=sorted(set(alias.lower() for alias in aliases)),
                patent_id=row["patent_id"],
                application_id=row["application_id"],
                marker_specs=specs,
            )
            targets.append(target)
            by_bank.setdefault(target.bank_display_name, []).append(target)
    return targets, by_bank


def safe_name(value: str) -> str:
    """Sanitize a string for use in path-based bank matching."""
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value)


def read_text(path: Path) -> str:
    """Read filing text and strip tags from HTML/XML-like files."""
    raw_text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() in {".htm", ".html", ".xml"}:
        raw_text = TAG_PATTERN.sub(" ", raw_text)
        raw_text = html.unescape(raw_text)
    return " ".join(raw_text.split())


def detect_form_type(path: Path, text: str) -> str:
    """Infer the SEC form type from the path first, then the file text."""
    match = FORM_TYPE_PATTERN.search(str(path))
    if match:
        return match.group(1).upper()
    match = FORM_TYPE_PATTERN.search(text[:2000])
    return match.group(1).upper() if match else ""


def keyword_flags(text: str) -> dict[str, int]:
    """Return keyword flags used for broad exploratory hits."""
    return {name: int(bool(pattern.search(text))) for name, pattern in KEYWORD_PATTERNS.items()}


def context_snippet(text: str, start: int, end: int, width: int = 160) -> str:
    """Cut a short readable snippet around a match."""
    left = max(0, start - width)
    right = min(len(text), end + width)
    return " ".join(text[left:right].split())


def has_digit_boundary(text: str, start: int, end: int) -> bool:
    """Avoid partial matches inside longer numeric strings."""
    left_ok = start == 0 or not text[start - 1].isdigit()
    right_ok = end >= len(text) or not text[end].isdigit()
    return left_ok and right_ok


def find_marker(text_lower: str, marker: str, needs_digit_boundary: bool) -> tuple[int, int] | None:
    """Find the first valid exact marker match in the filing text."""
    start = text_lower.find(marker)
    while start != -1:
        end = start + len(marker)
        if not needs_digit_boundary or has_digit_boundary(text_lower, start, end):
            return start, end
        start = text_lower.find(marker, start + 1)
    return None


def candidate_banks(path: Path, text_lower: str, by_bank: dict[str, list[Target]]) -> list[str]:
    """Narrow the bank search space using the path or bank aliases in text."""
    path_parts = {part.lower() for part in path.parts}
    path_matches = [
        bank_name
        for bank_name in by_bank
        if safe_name(bank_name).lower() in path_parts
    ]
    if path_matches:
        return path_matches
    matches = []
    for bank_name, targets in by_bank.items():
        aliases = targets[0].sec_search_aliases
        if any(alias and alias in text_lower for alias in aliases):
            matches.append(bank_name)
    return matches or list(by_bank.keys())


def scan_file(path: Path, by_bank: dict[str, list[Target]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Scan one local filing and return exact-hit and keyword-hit rows."""
    text = read_text(path)
    text_lower = text.lower()
    form_type = detect_form_type(path, text)
    flags = keyword_flags(text)
    candidate_bank_names = candidate_banks(path, text_lower, by_bank)

    exact_hits: list[dict[str, str]] = []
    keyword_hits: list[dict[str, str]] = []
    if any(flags.values()):
        for bank_name in candidate_bank_names:
            keyword_hits.append(
                {
                    "file_path": str(path),
                    "form_type": form_type,
                    "bank_display_name": bank_name,
                    **{name: str(value) for name, value in flags.items()},
                }
            )

    seen_exact: set[tuple[str, str, str]] = set()
    for bank_name in candidate_bank_names:
        for target in by_bank[bank_name]:
            for pattern_name, marker, needs_digit_boundary in target.marker_specs:
                location = find_marker(text_lower, marker, needs_digit_boundary)
                if not location:
                    continue
                dedupe_key = (target.patent_id, target.application_id, pattern_name)
                if dedupe_key in seen_exact:
                    continue
                seen_exact.add(dedupe_key)
                start, end = location
                exact_hits.append(
                    {
                        "file_path": str(path),
                        "form_type": form_type,
                        "bank_display_name": target.bank_display_name,
                        "patent_canonical_bank_name": target.patent_canonical_bank_name,
                        "patent_id": target.patent_id,
                        "application_id": target.application_id,
                        "match_pattern": pattern_name,
                        "snippet": context_snippet(text, start, end),
                        **{name: str(value) for name, value in flags.items()},
                    }
                )
    return exact_hits, keyword_hits


def write_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    """Write one result CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    """Parse optional target, input, and output overrides."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS_CSV)
    parser.add_argument("--filings-dir", type=Path, default=DEFAULT_FILINGS_DIR)
    parser.add_argument("--exact-out", type=Path, default=DEFAULT_EXACT_HITS_CSV)
    parser.add_argument("--keyword-out", type=Path, default=DEFAULT_KEYWORD_HITS_CSV)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    targets, by_bank = load_targets(args.targets)
    filing_paths = sorted(
        path for path in args.filings_dir.rglob("*") if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES
    )

    exact_hits: list[dict[str, str]] = []
    keyword_hits: list[dict[str, str]] = []
    for path in filing_paths:
        file_exact, file_keyword = scan_file(path, by_bank)
        exact_hits.extend(file_exact)
        keyword_hits.extend(file_keyword)

    exact_fields = [
        "file_path",
        "form_type",
        "bank_display_name",
        "patent_canonical_bank_name",
        "patent_id",
        "application_id",
        "match_pattern",
        "snippet",
        "license",
        "infringement",
        "settlement",
        "technology_agreement",
        "intellectual_property",
        "patent",
    ]
    keyword_fields = [
        "file_path",
        "form_type",
        "bank_display_name",
        "license",
        "infringement",
        "settlement",
        "technology_agreement",
        "intellectual_property",
        "patent",
    ]
    write_rows(args.exact_out, exact_hits, exact_fields)
    write_rows(args.keyword_out, keyword_hits, keyword_fields)

    print(f"Loaded {len(targets)} patent targets")
    print(f"Scanned {len(filing_paths)} local filing files")
    print(f"Wrote {len(exact_hits)} exact hits")
    print(f"Wrote {len(keyword_hits)} keyword-level file hits")


if __name__ == "__main__":
    main()
