"""Parse LexisNexis PDF exports into article records."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import pdfplumber
from pypdf import PdfReader, PdfWriter

from bank_config import BankMatcher
from cleaning import SOURCE_LABELS, clean_article_page, meaningful_lines, normalize_text
from models import Article, PageText


DATE_PATTERN = re.compile(
    r"\b("
    r"January|February|March|April|May|June|July|August|September|October|November|December"
    r")\s+\d{1,2},\s+\d{4}\b",
    re.IGNORECASE,
)


@dataclass
class ParsedPdf:
    page_texts: list[str]
    metadata_title: str
    reader: PdfReader


def _looks_like_title(value: str) -> bool:
    if not value:
        return False
    stripped = value.strip()
    if len(stripped) < 10:
        return False
    lowered = stripped.lower()
    if "microsoft word" in lowered or "lexisnexis" in lowered:
        return False
    return any(character.isalpha() for character in stripped)


def _stable_article_id(source: str, logical_path: str, page_start: int, page_end: int) -> str:
    digest = hashlib.sha1(f"{source}|{logical_path}|{page_start}|{page_end}".encode("utf-8")).hexdigest()
    return f"{source}_{digest[:12]}"


def _parse_date_from_lines(lines: list[str], source_label: str) -> str:
    try:
        source_index = next(
            index for index, line in enumerate(lines) if line.lower() == source_label.lower()
        )
    except StopIteration:
        source_index = 0
    search_window = lines[source_index : source_index + 8]
    for line in search_window:
        match = DATE_PATTERN.search(line)
        if not match:
            continue
        try:
            return datetime.strptime(match.group(0), "%B %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            return match.group(0)
    return ""


def _parse_author_from_lines(lines: list[str]) -> str:
    for line in lines:
        if line.lower().startswith("byline:"):
            return line.split(":", 1)[1].strip()
    return ""


def _extract_title_from_head(lines: list[str], source: str, metadata_title: str = "") -> str:
    source_label = SOURCE_LABELS[source]
    try:
        source_index = next(
            index for index, line in enumerate(lines) if line.lower() == source_label.lower()
        )
    except StopIteration:
        source_index = -1
    candidates: list[str] = []
    if source_index > 0:
        for line in lines[max(0, source_index - 4) : source_index]:
            if DATE_PATTERN.search(line):
                continue
            if ":" in line and line.split(":", 1)[0].lower() in {
                "copyright",
                "length",
                "dateline",
                "byline",
                "section",
            }:
                continue
            candidates.append(line.strip())
    unique_candidates: list[str] = []
    seen: set[str] = set()
    for line in candidates:
        normalized = re.sub(r"\s+", " ", line).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_candidates.append(line)
    title = ""
    if unique_candidates:
        joined_two = " ".join(unique_candidates[-2:]).strip()
        joined_three = " ".join(unique_candidates[-3:]).strip()
        best_single = max(unique_candidates, key=len)
        title = best_single
        if len(joined_two) > len(best_single) * 1.1:
            title = joined_two
        if len(joined_three) > len(title) * 1.1:
            title = joined_three
    if not title and _looks_like_title(metadata_title):
        title = metadata_title.strip()
    return re.sub(r"\s+", " ", title).strip()


def _extract_bw_title(lines: list[str]) -> str:
    try:
        source_index = next(
            index for index, line in enumerate(lines) if line.lower() == SOURCE_LABELS["business_wire"].lower()
        )
    except StopIteration:
        return ""
    candidates: list[str] = []
    for line in lines[1:source_index]:
        normalized = line.strip()
        if not normalized or "..." in normalized:
            continue
        candidates.append(normalized)
    if not candidates:
        return ""
    unique: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        key = re.sub(r"\s+", " ", item).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    best_single = max(unique, key=len)
    joined_two = " ".join(unique[-2:]).strip()
    joined_three = " ".join(unique[-3:]).strip()
    title = best_single
    if len(joined_two) > len(title) * 1.1:
        title = joined_two
    if len(joined_three) > len(title) * 1.1:
        title = joined_three
    return re.sub(r"\s+", " ", title).strip()


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return cleaned[:80] or "article"


def _safe_relpath(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _extract_pdf(path: Path) -> ParsedPdf:
    reader = PdfReader(str(path))
    page_texts = [normalize_text(page.extract_text() or "") for page in reader.pages]
    if not any(text.strip() for text in page_texts):
        with pdfplumber.open(str(path)) as pdf:
            page_texts = [normalize_text(page.extract_text() or "") for page in pdf.pages]
    metadata_title = ""
    if reader.metadata and reader.metadata.title:
        metadata_title = normalize_text(str(reader.metadata.title))
    return ParsedPdf(page_texts=page_texts, metadata_title=metadata_title, reader=reader)


def parse_single_article_pdf(pdf_path: Path, source: str, bank_matcher: BankMatcher, repo_root: Path) -> Article:
    parsed = _extract_pdf(pdf_path)
    head_text = "\n".join(parsed.page_texts[: min(2, len(parsed.page_texts))])
    head_lines = meaningful_lines(head_text, source)
    title = _extract_title_from_head(head_lines, source, parsed.metadata_title)
    published_at = _parse_date_from_lines(head_lines, SOURCE_LABELS[source])
    author = _parse_author_from_lines(head_lines)

    pages = [
        PageText(
            page_number=index + 1,
            raw_text=text,
            clean_text=clean_article_page(text, source, is_first_page=index == 0),
        )
        for index, text in enumerate(parsed.page_texts)
    ]
    raw_text = "\n\n".join(page.raw_text for page in pages if page.raw_text)
    clean_text = " ".join(page.clean_text for page in pages if page.clean_text).strip()
    logical_path = _safe_relpath(pdf_path, repo_root)
    article = Article(
        article_id=_stable_article_id(source, logical_path, 1, len(pages)),
        source=source,
        pdf_path=logical_path,
        title=title,
        published_at=published_at,
        author=author,
        page_start=1,
        page_end=len(pages),
        raw_text=raw_text,
        clean_text=clean_text,
        bank_hits=bank_matcher.find_banks(f"{title} {clean_text}"),
        parse_notes=[],
        pages=pages,
    )
    if not article.title:
        article.parse_notes.append("missing_title")
    if not article.published_at:
        article.parse_notes.append("missing_date")
    if not article.clean_text:
        article.parse_notes.append("missing_clean_text")
    return article


def _extract_toc_titles(page_texts: list[str]) -> list[str]:
    titles: list[str] = []
    current_title: list[str] = []
    for page_text in page_texts:
        for raw_line in normalize_text(page_text).splitlines():
            line = raw_line.strip()
            if not line:
                if current_title:
                    titles.append(" ".join(current_title).strip())
                    current_title = []
                continue
            if re.match(r"^\d+\.\s+", line):
                if current_title:
                    titles.append(" ".join(current_title).strip())
                current_title = [re.sub(r"^\d+\.\s+", "", line).strip()]
                continue
            if current_title:
                if line.startswith("|") or line.startswith("User Name:"):
                    continue
                current_title.append(line)
        if current_title:
            titles.append(" ".join(current_title).strip())
            current_title = []
    return [re.sub(r"\s+", " ", title).strip() for title in titles if title.strip()]


def _title_match_ratio(left: str, right: str) -> float:
    def normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    return SequenceMatcher(None, normalize(left), normalize(right)).ratio()


def parse_business_wire_batch(
    pdf_path: Path,
    bank_matcher: BankMatcher,
    repo_root: Path,
    output_dir: Path,
    article_limit: int | None = None,
    write_segment_pdfs: bool = True,
) -> tuple[list[Article], list[dict[str, str]]]:
    parsed = _extract_pdf(pdf_path)
    start_pages = [
        index + 1
        for index, text in enumerate(parsed.page_texts)
        if re.match(r"^\s*Page\s+1\s+of\s+\d+", text)
    ]
    toc_end = max(start_pages[0] - 1, 0) if start_pages else min(len(parsed.page_texts), 60)
    toc_titles = _extract_toc_titles(parsed.page_texts[:toc_end])

    segments: list[tuple[int, int]] = []
    for index, start_page in enumerate(start_pages):
        end_page = start_pages[index + 1] - 1 if index + 1 < len(start_pages) else len(parsed.page_texts)
        segments.append((start_page, end_page))
    if article_limit is not None:
        segments = segments[:article_limit]

    batch_output_dir = output_dir / _slugify(pdf_path.stem)
    if write_segment_pdfs:
        batch_output_dir.mkdir(parents=True, exist_ok=True)

    articles: list[Article] = []
    review_rows: list[dict[str, str]] = []
    for index, (start_page, end_page) in enumerate(segments, start=1):
        segment_texts = parsed.page_texts[start_page - 1 : end_page]
        head_lines = meaningful_lines(segment_texts[0], "business_wire")
        title = _extract_bw_title(head_lines)
        published_at = _parse_date_from_lines(head_lines, SOURCE_LABELS["business_wire"])
        author = _parse_author_from_lines(head_lines)

        safe_title = _slugify(title or f"segment-{index:03d}")
        if write_segment_pdfs:
            writer = PdfWriter()
            for page_index in range(start_page - 1, end_page):
                writer.add_page(parsed.reader.pages[page_index])
            segment_pdf_path = batch_output_dir / f"{index:03d}_{safe_title}.pdf"
            with segment_pdf_path.open("wb") as handle:
                writer.write(handle)
            segment_pdf_ref = _safe_relpath(segment_pdf_path, repo_root)
        else:
            segment_pdf_ref = f"{_safe_relpath(pdf_path, repo_root)}#p{start_page}-{end_page}"

        pages: list[PageText] = []
        for offset, text in enumerate(segment_texts):
            page_number = start_page + offset
            pages.append(
                PageText(
                    page_number=page_number,
                    raw_text=text,
                    clean_text=clean_article_page(text, "business_wire", is_first_page=offset == 0),
                )
            )
        raw_text = "\n\n".join(page.raw_text for page in pages if page.raw_text)
        clean_text = " ".join(page.clean_text for page in pages if page.clean_text).strip()
        logical_source = f"{_safe_relpath(pdf_path, repo_root)}#p{start_page}"
        article = Article(
            article_id=_stable_article_id("business_wire", logical_source, start_page, end_page),
            source="business_wire",
            pdf_path=segment_pdf_ref,
            title=title,
            published_at=published_at,
            author=author,
            page_start=start_page,
            page_end=end_page,
            raw_text=raw_text,
            clean_text=clean_text,
            bank_hits=bank_matcher.find_banks(f"{title} {clean_text}"),
            parse_notes=[f"batch_source={_safe_relpath(pdf_path, repo_root)}"],
            pages=pages,
        )
        if not article.title:
            article.parse_notes.append("missing_title")
        if not article.published_at:
            article.parse_notes.append("missing_date")
        if not article.clean_text:
            article.parse_notes.append("missing_clean_text")

        toc_title = toc_titles[index - 1] if index - 1 < len(toc_titles) else ""
        ratio = _title_match_ratio(toc_title, title) if toc_title and title else 0.0
        status = "matched"
        if toc_title and title and ratio < 0.72:
            status = "review"
            article.parse_notes.append("low_toc_match")
        elif toc_title and not title:
            status = "review"
            article.parse_notes.append("missing_segment_title")
        elif title and not toc_title:
            status = "extra_segment"
        review_rows.append(
            {
                "pdf_path": _safe_relpath(pdf_path, repo_root),
                "segment_index": str(index),
                "page_start": str(start_page),
                "page_end": str(end_page),
                "toc_title": toc_title,
                "detected_title": title,
                "match_ratio": f"{ratio:.3f}",
                "status": status,
            }
        )
        articles.append(article)

    if article_limit is None:
        for extra_index in range(len(segments) + 1, len(toc_titles) + 1):
            review_rows.append(
                {
                    "pdf_path": _safe_relpath(pdf_path, repo_root),
                    "segment_index": str(extra_index),
                    "page_start": "",
                    "page_end": "",
                    "toc_title": toc_titles[extra_index - 1],
                    "detected_title": "",
                    "match_ratio": "0.000",
                    "status": "missing_segment",
                }
            )
    return articles, review_rows
