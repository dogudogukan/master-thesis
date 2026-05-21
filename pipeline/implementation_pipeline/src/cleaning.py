"""Text cleanup for LexisNexis article exports."""

from __future__ import annotations

import re
import unicodedata


COMMON_LINE_PATTERNS = [
    re.compile(r"^\|\s*About LexisNexis", re.IGNORECASE),
    re.compile(r"^About LexisNexis\b", re.IGNORECASE),
    re.compile(r"^Privacy Policy\b", re.IGNORECASE),
    re.compile(r"^Terms\s*&\s*Conditions\b", re.IGNORECASE),
    re.compile(r"^Copyright\s+[0-9© ]+LexisNexis", re.IGNORECASE),
    re.compile(r"^User Name:", re.IGNORECASE),
    re.compile(r"^Date and Time:", re.IGNORECASE),
    re.compile(r"^Job Number:", re.IGNORECASE),
    re.compile(r"^Documents\s*\(\d+\)", re.IGNORECASE),
    re.compile(r"^Client/Matter:", re.IGNORECASE),
    re.compile(r"^Search Terms:", re.IGNORECASE),
    re.compile(r"^Search Type:", re.IGNORECASE),
    re.compile(r"^Content Type Narrowed by", re.IGNORECASE),
    re.compile(r"^news Source Name:", re.IGNORECASE),
    re.compile(r"^Results list$", re.IGNORECASE),
    re.compile(r"^Search Document$", re.IGNORECASE),
    re.compile(r"^Dili Secin$", re.IGNORECASE),
    re.compile(r"Dili Se", re.IGNORECASE),
    re.compile(r"^Go to", re.IGNORECASE),
    re.compile(r"Results list", re.IGNORECASE),
    re.compile(r"Search Document", re.IGNORECASE),
    re.compile(r"Disclaimer", re.IGNORECASE),
    re.compile(r"^This translated text is provided solely", re.IGNORECASE),
    re.compile(r"^Load-Date:", re.IGNORECASE),
    re.compile(r"^End of Document$", re.IGNORECASE),
    re.compile(r"^Document \d+ of \d+$", re.IGNORECASE),
    re.compile(r"^Page \d+ of \d+$", re.IGNORECASE),
    re.compile(r"^Highlight", re.IGNORECASE),
    re.compile(r"Export Citation", re.IGNORECASE),
    re.compile(r"Nexis Uni", re.IGNORECASE),
    re.compile(r"advance-lexis", re.IGNORECASE),
    re.compile(r"Sign In Register", re.IGNORECASE),
    re.compile(r"View original content", re.IGNORECASE),
    re.compile(r"^Classification\b", re.IGNORECASE),
    re.compile(r"^Publication-Type:\b", re.IGNORECASE),
    re.compile(r"^Subject:\b", re.IGNORECASE),
    re.compile(r"^Company:\b", re.IGNORECASE),
    re.compile(r"^Ticker:\b", re.IGNORECASE),
    re.compile(r"^Industry:\b", re.IGNORECASE),
    re.compile(r"^Geographic:\b", re.IGNORECASE),
    re.compile(r"^Person:\b", re.IGNORECASE),
    re.compile(r"^For more information,", re.IGNORECASE)
]

METADATA_LINE_PATTERNS = [
    re.compile(r"^Copyright\s+\d{4}", re.IGNORECASE),
    re.compile(r"^Length:\s*", re.IGNORECASE),
    re.compile(r"^Dateline:\s*", re.IGNORECASE),
    re.compile(r"^Byline:\s*", re.IGNORECASE),
    re.compile(r"^Section:\s*", re.IGNORECASE),
    re.compile(r"^Column:\s*", re.IGNORECASE),
    re.compile(r"^URL:\s*", re.IGNORECASE),
    re.compile(r"^Language:\s*", re.IGNORECASE),
    re.compile(r"^Graphic:\s*", re.IGNORECASE)
]

SOURCE_LABELS = {
    "american_banker": "American Banker",
    "pr_newswire": "PR Newswire",
    "business_wire": "Business Wire"
}

TAIL_CUTOFF_PATTERNS = [
    re.compile(r"Export Citation.*", re.IGNORECASE),
    re.compile(r"Publication-Type:.*", re.IGNORECASE),
    re.compile(r"Classification.*", re.IGNORECASE),
    re.compile(r"Subject:.*", re.IGNORECASE),
    re.compile(r"Company:.*", re.IGNORECASE),
    re.compile(r"Ticker:.*", re.IGNORECASE),
    re.compile(r"Industry:.*", re.IGNORECASE),
    re.compile(r"Geographic:.*", re.IGNORECASE),
    re.compile(r"Person:.*", re.IGNORECASE),
    re.compile(r"\bSOURCE\b.*", re.IGNORECASE),
    re.compile(r"View original content.*", re.IGNORECASE),
    re.compile(r"For more information,.*", re.IGNORECASE),
    re.compile(r"\bContacts?:.*", re.IGNORECASE),
    re.compile(r"\b\d{1,2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}\b.*", re.IGNORECASE),
]


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_noise_line(line: str) -> bool:
    if not line.strip():
        return False
    return any(pattern.search(line) for pattern in COMMON_LINE_PATTERNS)


def _separate_embedded_source_label(text: str, source_label: str) -> str:
    escaped = re.escape(source_label)
    return re.sub(rf"(?<=\S)({escaped})", r"\n\1", text)


def meaningful_lines(text: str, source: str) -> list[str]:
    source_label = SOURCE_LABELS[source]
    normalized = _separate_embedded_source_label(normalize_text(text), source_label)
    lines = [line.strip() for line in normalized.splitlines()]
    filtered: list[str] = []
    for line in lines:
        if not line:
            continue
        if _is_noise_line(line):
            continue
        if line.lower() == source_label.lower():
            filtered.append(source_label)
            continue
        filtered.append(line)
    return filtered


def clean_article_page(raw_text: str, source: str, is_first_page: bool) -> str:
    source_label = SOURCE_LABELS[source]
    normalized = _separate_embedded_source_label(normalize_text(raw_text), source_label)
    lines = [line.strip() for line in normalized.splitlines()]
    filtered: list[str] = []
    body_seen = False
    for line in lines:
        if not line:
            continue
        if _is_noise_line(line):
            continue
        if line == "Body":
            body_seen = True
            continue
        if not body_seen and is_first_page:
            continue
        if source == "pr_newswire" and line.startswith("PR Newswire") and len(line) > len("PR Newswire"):
            line = line[len("PR Newswire") :].strip()
        if any(pattern.search(line) for pattern in METADATA_LINE_PATTERNS):
            continue
        if line in SOURCE_LABELS.values():
            continue
        filtered.append(line)
    if not filtered and not is_first_page:
        for line in lines:
            if not line or _is_noise_line(line):
                continue
            if any(pattern.search(line) for pattern in METADATA_LINE_PATTERNS):
                continue
            if line in SOURCE_LABELS.values():
                continue
            filtered.append(line)
    text = " ".join(filtered)
    text = re.sub(r"https?://\S+", "", text, flags=re.IGNORECASE)
    for pattern in TAIL_CUTOFF_PATTERNS:
        text = pattern.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
