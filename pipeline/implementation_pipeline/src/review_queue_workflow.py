"""Implementation review-queue workflow."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
import shutil

from bank_config import load_bank_matcher
from models import Article, ScoredArticle
from parsing import parse_business_wire_batch, parse_single_article_pdf
from scoring import ArticleScorer


ARTICLE_REVIEW_COLUMNS = [
    "rank",
    "article_id",
    "source",
    "pdf_path",
    "title",
    "published_at",
    "normalized_banks",
    "article_score",
    "top_sentence_1",
    "top_sentence_1_score",
    "top_sentence_2",
    "top_sentence_2_score",
    "top_sentence_3",
    "top_sentence_3_score",
    "page_refs",
    "review_status",
    "review_notes",
]

KNOWN_SOURCES = ["american_banker", "pr_newswire", "business_wire"]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _discover_source_pdfs(data_dir: Path, source: str) -> list[Path]:
    source_dir = data_dir / source
    discovered = {path.resolve(): path for path in source_dir.glob("*.pdf")}
    discovered.update({path.resolve(): path for path in source_dir.glob("*.PDF")})
    return sorted(discovered.values())


def _prepare_output_dir(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    for file_name in [
        "articles.jsonl",
        "sentence_evidence.csv",
        "parse_failures.csv",
        "bw_segmentation_review.csv",
        "article_review_queue.csv",
        "run_summary.json",
    ]:
        output_path = output_dir / file_name
        if output_path.exists():
            output_path.unlink()
    bw_segment_dir = output_dir / "business_wire_segments"
    if bw_segment_dir.exists():
        shutil.rmtree(bw_segment_dir)
    bw_segment_dir.mkdir(parents=True, exist_ok=True)
    return bw_segment_dir


def run_pipeline(
    data_dir: Path,
    config_path: Path,
    output_dir: Path,
    repo_root: Path,
    review_count: int = 400,
    max_files_per_source: int | None = None,
    bw_article_limit: int | None = None,
    sources: list[str] | None = None,
) -> dict[str, object]:
    matcher = load_bank_matcher(config_path)
    scorer = ArticleScorer(matcher)
    bw_segment_dir = _prepare_output_dir(output_dir)

    selected_sources = sources or KNOWN_SOURCES
    unknown_sources = sorted(set(selected_sources) - set(KNOWN_SOURCES))
    if unknown_sources:
        raise ValueError(f"Unsupported sources: {', '.join(unknown_sources)}")

    articles: list[Article] = []
    parse_failures: list[dict[str, str]] = []
    bw_review_rows: list[dict[str, str]] = []
    source_counts: Counter[str] = Counter()

    for source in [item for item in selected_sources if item != "business_wire"]:
        pdf_paths = _discover_source_pdfs(data_dir, source)
        if max_files_per_source is not None:
            pdf_paths = pdf_paths[:max_files_per_source]
        for pdf_path in pdf_paths:
            try:
                article = parse_single_article_pdf(pdf_path, source, matcher, repo_root)
                articles.append(article)
                source_counts[source] += 1
            except Exception as exc:  # pragma: no cover
                parse_failures.append(
                    {
                        "source": source,
                        "pdf_path": str(pdf_path.relative_to(repo_root)),
                        "error": str(exc),
                    }
                )

    if "business_wire" in selected_sources:
        bw_pdf_paths = _discover_source_pdfs(data_dir, "business_wire")
        if max_files_per_source is not None:
            bw_pdf_paths = bw_pdf_paths[:max_files_per_source]
        for pdf_path in bw_pdf_paths:
            try:
                batch_articles, review_rows = parse_business_wire_batch(
                    pdf_path=pdf_path,
                    bank_matcher=matcher,
                    repo_root=repo_root,
                    output_dir=bw_segment_dir,
                    article_limit=bw_article_limit,
                )
                articles.extend(batch_articles)
                bw_review_rows.extend(review_rows)
                source_counts["business_wire"] += len(batch_articles)
            except Exception as exc:  # pragma: no cover
                parse_failures.append(
                    {
                        "source": "business_wire",
                        "pdf_path": str(pdf_path.relative_to(repo_root)),
                        "error": str(exc),
                    }
                )

    scored_articles: list[ScoredArticle] = []
    sentence_rows: list[dict[str, str]] = []
    for article in articles:
        scored_article, evidence_rows = scorer.score_article(article)
        scored_articles.append(scored_article)
        sentence_rows.extend(item.to_csv_row() for item in evidence_rows)

    scored_articles.sort(
        key=lambda item: (
            item.article_score,
            len(item.top_sentences),
            len(item.article.bank_hits),
            item.article.title,
        ),
        reverse=True,
    )
    shortlisted = [item for item in scored_articles if item.top_sentences and item.top_sentences[0].score > 0]
    shortlisted = shortlisted[:review_count]

    with (output_dir / "articles.jsonl").open("w", encoding="utf-8") as handle:
        for article in articles:
            handle.write(json.dumps(article.to_json_dict(), ensure_ascii=False) + "\n")

    _write_csv(
        output_dir / "sentence_evidence.csv",
        [
            "article_id",
            "source",
            "pdf_path",
            "page_number",
            "sentence_index",
            "sentence",
            "sentence_score",
            "normalized_banks",
            "positive_hits",
            "negative_hits",
        ],
        sentence_rows,
    )
    _write_csv(output_dir / "parse_failures.csv", ["source", "pdf_path", "error"], parse_failures)
    _write_csv(
        output_dir / "bw_segmentation_review.csv",
        ["pdf_path", "segment_index", "page_start", "page_end", "toc_title", "detected_title", "match_ratio", "status"],
        bw_review_rows,
    )

    review_rows: list[dict[str, str]] = []
    for rank, item in enumerate(shortlisted, start=1):
        padded = item.top_sentences + [None, None, None]
        review_rows.append(
            {
                "rank": str(rank),
                "article_id": item.article.article_id,
                "source": item.article.source,
                "pdf_path": item.article.pdf_path,
                "title": item.article.title,
                "published_at": item.article.published_at,
                "normalized_banks": "; ".join(item.article.bank_hits),
                "article_score": f"{item.article_score:.3f}",
                "top_sentence_1": padded[0].sentence if padded[0] else "",
                "top_sentence_1_score": f"{padded[0].score:.3f}" if padded[0] else "",
                "top_sentence_2": padded[1].sentence if padded[1] else "",
                "top_sentence_2_score": f"{padded[1].score:.3f}" if padded[1] else "",
                "top_sentence_3": padded[2].sentence if padded[2] else "",
                "top_sentence_3_score": f"{padded[2].score:.3f}" if padded[2] else "",
                "page_refs": item.page_refs,
                "review_status": "",
                "review_notes": "",
            }
        )
    _write_csv(output_dir / "article_review_queue.csv", ARTICLE_REVIEW_COLUMNS, review_rows)

    summary = {
        "output_dir": str(output_dir),
        "sources": selected_sources,
        "articles_total": len(articles),
        "articles_by_source": dict(source_counts),
        "parse_failures": len(parse_failures),
        "business_wire_review_rows": len(bw_review_rows),
        "sentence_evidence_rows": len(sentence_rows),
        "review_queue_count": len(review_rows),
        "requested_review_count": review_count,
    }
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary
