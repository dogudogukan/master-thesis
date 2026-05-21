from __future__ import annotations

import argparse
import csv
import html
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_TSV = ROOT / "results/google_patents_manifest.tsv"
PDF_DIR = ROOT / "raw/google_patents_pdf"
HTML_DIR = ROOT / "raw/google_patents_html"
SECTION_DIR = ROOT / "raw/google_patents_legal_events"
SUMMARY_CSV = ROOT / "results/google_patents_summary.csv"
BRAVE_PATH = Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")

APPLICATION_BLOCK_PATTERN = re.compile(
    r'<span class="block style-scope application-timeline">.*?<span class="year style-scope application-timeline">(?P<year>[^<]+)</span>.*?'
    r'data-result="(?P<data_result>[^"]+)".*?<span id="cc" class="(?P<status_class>[^"]*) style-scope application-timeline".*?>(?P<country>[^<]+)</span>.*?'
    r'Application number:\s*(?P<application_number>[^<]+)</div>.*?'
    r'Filing date:\s*(?P<filing_date>[^<]+)</div>.*?'
    r'Legal status:\s*(?P<legal_status>[^<]+)</div>',
    re.DOTALL,
)
LEGAL_EVENTS_SECTION_PATTERN = re.compile(
    r'<h3 id="legalEvents" class="scroll-target style-scope patent-result">.*?</h3>(?P<section>.*?)<div id="notices" class="vertical layout center style-scope patent-result">',
    re.DOTALL,
)
LEGAL_EVENT_ROW_PATTERN = re.compile(
    r'<div class="tr style-scope patent-result">\s*'
    r'<span class="td nowrap style-scope patent-result">(?P<date>[^<]+)</span>\s*'
    r'<span class="td nowrap style-scope patent-result">(?P<code>[^<]+)</span>\s*'
    r'<span class="td nowrap style-scope patent-result">(?P<title>[^<]+)</span>\s*'
    r'<span class="td style-scope patent-result">(?P<details>.*?)</span>\s*</div>',
    re.DOTALL,
)
LEGAL_EVENT_DETAIL_PATTERN = re.compile(
    r'<p class="style-scope patent-result"><strong class="style-scope patent-result">(?P<label>[^<]+)</strong>:\s*(?P<value>.*?)</p>',
    re.DOTALL,
)
SCRIPT_STYLE_PATTERN = re.compile(r"<(script|style)\b.*?</\1>", re.DOTALL | re.IGNORECASE)
TAG_PATTERN = re.compile(r"<[^>]+>")


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def text(self) -> str:
        return " ".join(part.strip() for part in self.parts if part.strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=MANIFEST_TSV)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--patents", nargs="*", default=[])
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--virtual-time-budget-ms", type=int, default=10000)
    return parser.parse_args()


def load_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def run_brave_dump(url: str) -> str:
    result = subprocess.run(
        [
            str(BRAVE_PATH),
            "--headless=new",
            "--disable-gpu",
            "--dump-dom",
            url,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def run_brave_pdf(url: str, out_path: Path, virtual_time_budget_ms: int) -> None:
    result = subprocess.run(
        [
            str(BRAVE_PATH),
            "--headless=new",
            "--disable-gpu",
            f"--virtual-time-budget={virtual_time_budget_ms}",
            "--print-to-pdf-no-header",
            f"--print-to-pdf={out_path}",
            url,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stderr:
        stderr = result.stderr.strip()
        if stderr:
            print(stderr, file=sys.stderr)


def strip_visible_text(raw_html: str) -> str:
    cleaned = SCRIPT_STYLE_PATTERN.sub(" ", raw_html)
    parser = TextExtractor()
    parser.feed(cleaned)
    return " ".join(parser.text().split())


def section_snippet(visible_text: str, label: str, width: int = 3000) -> str:
    idx = visible_text.lower().find(label.lower())
    if idx == -1:
        return ""
    return visible_text[idx : idx + width]


def parse_worldwide_applications(raw_html: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for match in APPLICATION_BLOCK_PATTERN.finditer(raw_html):
        items.append(
            {
                "year": html.unescape(match.group("year")).strip(),
                "country": html.unescape(match.group("country")).strip(),
                "application_number": html.unescape(match.group("application_number")).strip(),
                "filing_date": html.unescape(match.group("filing_date")).strip(),
                "legal_status": html.unescape(match.group("legal_status")).strip(),
                "status_class": html.unescape(match.group("status_class")).strip(),
                "data_result": html.unescape(match.group("data_result")).strip(),
            }
        )
    return items


def normalize_html_fragment(fragment: str) -> str:
    text = TAG_PATTERN.sub(" ", fragment)
    text = html.unescape(text)
    return " ".join(text.split())


def parse_legal_events(raw_html: str) -> list[dict[str, object]]:
    section_match = LEGAL_EVENTS_SECTION_PATTERN.search(raw_html)
    if not section_match:
        return []
    section_html = section_match.group("section")
    events: list[dict[str, object]] = []
    for row_match in LEGAL_EVENT_ROW_PATTERN.finditer(section_html):
        details_html = row_match.group("details")
        details: list[dict[str, str]] = []
        for detail_match in LEGAL_EVENT_DETAIL_PATTERN.finditer(details_html):
            details.append(
                {
                    "label": normalize_html_fragment(detail_match.group("label")),
                    "value": normalize_html_fragment(detail_match.group("value")),
                }
            )
        events.append(
            {
                "date": normalize_html_fragment(row_match.group("date")),
                "code": normalize_html_fragment(row_match.group("code")),
                "title": normalize_html_fragment(row_match.group("title")),
                "details": details,
            }
        )
    return events


def output_paths(google_patents_id: str) -> tuple[Path, Path, Path]:
    return (
        PDF_DIR / f"{google_patents_id}.pdf",
        HTML_DIR / f"{google_patents_id}.html",
        SECTION_DIR / f"{google_patents_id}.json",
    )


def should_process(args: argparse.Namespace, row: dict[str, str]) -> bool:
    if args.patents and row["patent_id"] not in set(args.patents):
        return False
    return True


def main() -> None:
    if not BRAVE_PATH.exists():
        raise SystemExit(f"Brave browser not found at {BRAVE_PATH}")

    args = parse_args()
    rows = [row for row in load_manifest(args.manifest) if should_process(args, row)]
    if args.limit:
        rows = rows[: args.limit]

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    SECTION_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_CSV.parent.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, str]] = []
    for row in rows:
        google_patents_id = row["google_patents_id"]
        pdf_path, html_path, section_path = output_paths(google_patents_id)
        if args.skip_existing and pdf_path.exists() and html_path.exists() and section_path.exists():
            summary_rows.append(
                {
                    "patent_id": row["patent_id"],
                    "google_patents_id": google_patents_id,
                    "status": "skipped_existing",
                    "pdf_path": str(pdf_path),
                    "html_path": str(html_path),
                    "section_path": str(section_path),
                    "legal_event_count": "",
                    "worldwide_application_count": "",
                    "error": "",
                }
            )
            continue

        try:
            raw_html = run_brave_dump(row["google_patents_url"])
            html_path.write_text(raw_html, encoding="utf-8")
            run_brave_pdf(row["google_patents_url"], pdf_path, args.virtual_time_budget_ms)

            visible_text = strip_visible_text(raw_html)
            legal_events = parse_legal_events(raw_html)
            worldwide_applications = parse_worldwide_applications(raw_html)
            section_payload = {
                "patent_id": row["patent_id"],
                "google_patents_id": google_patents_id,
                "google_patents_url": row["google_patents_url"],
                "canonical_bank_name": row["canonical_bank_name"],
                "patent_title": row["patent_title"],
                "legal_events": legal_events,
                "worldwide_applications": worldwide_applications,
                "status_snippet": section_snippet(visible_text, "status"),
                "worldwide_applications_snippet": section_snippet(visible_text, "worldwide applications"),
                "legal_events_snippet": section_snippet(visible_text, "legal events"),
            }
            section_path.write_text(json.dumps(section_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            summary_rows.append(
                {
                    "patent_id": row["patent_id"],
                    "google_patents_id": google_patents_id,
                    "status": "captured",
                    "pdf_path": str(pdf_path),
                    "html_path": str(html_path),
                    "section_path": str(section_path),
                    "legal_event_count": str(len(legal_events)),
                    "worldwide_application_count": str(len(worldwide_applications)),
                    "error": "",
                }
            )
            print(
                f"Captured {google_patents_id}: "
                f"{len(legal_events)} legal events, "
                f"{len(worldwide_applications)} worldwide applications"
            )
        except subprocess.CalledProcessError as exc:
            summary_rows.append(
                {
                    "patent_id": row["patent_id"],
                    "google_patents_id": google_patents_id,
                    "status": "error",
                    "pdf_path": str(pdf_path),
                    "html_path": str(html_path),
                    "section_path": str(section_path),
                    "legal_event_count": "",
                    "worldwide_application_count": "",
                    "error": (exc.stderr or exc.stdout or str(exc)).strip()[:1000],
                }
            )
            print(f"Failed {google_patents_id}: {exc}", file=sys.stderr)

    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "patent_id",
            "google_patents_id",
            "status",
            "pdf_path",
            "html_path",
            "section_path",
            "legal_event_count",
            "worldwide_application_count",
            "error",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"Wrote capture summary to {SUMMARY_CSV}")


if __name__ == "__main__":
    main()
