"""Shared models for parsing and scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PageText:
    page_number: int
    raw_text: str
    clean_text: str


@dataclass
class Article:
    article_id: str
    source: str
    pdf_path: str
    title: str
    published_at: str
    author: str
    page_start: int
    page_end: int
    raw_text: str
    clean_text: str
    bank_hits: list[str] = field(default_factory=list)
    parse_notes: list[str] = field(default_factory=list)
    pages: list[PageText] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "source": self.source,
            "pdf_path": self.pdf_path,
            "title": self.title,
            "published_at": self.published_at,
            "author": self.author,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "raw_text": self.raw_text,
            "clean_text": self.clean_text,
            "bank_hits": self.bank_hits,
            "parse_notes": self.parse_notes,
        }


@dataclass
class SentenceEvidence:
    article_id: str
    source: str
    pdf_path: str
    page_number: int
    sentence_index: int
    sentence: str
    score: float
    bank_hits: list[str] = field(default_factory=list)
    positive_hits: list[str] = field(default_factory=list)
    negative_hits: list[str] = field(default_factory=list)

    def to_csv_row(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "source": self.source,
            "pdf_path": self.pdf_path,
            "page_number": self.page_number,
            "sentence_index": self.sentence_index,
            "sentence": self.sentence,
            "sentence_score": f"{self.score:.3f}",
            "normalized_banks": "; ".join(self.bank_hits),
            "positive_hits": "; ".join(self.positive_hits),
            "negative_hits": "; ".join(self.negative_hits),
        }


@dataclass
class ScoredArticle:
    article: Article
    article_score: float
    top_sentences: list[SentenceEvidence] = field(default_factory=list)

    @property
    def page_refs(self) -> str:
        page_numbers = sorted({item.page_number for item in self.top_sentences})
        return ";".join(str(item) for item in page_numbers)
