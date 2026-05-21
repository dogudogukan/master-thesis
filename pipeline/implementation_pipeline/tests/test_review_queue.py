from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
PHASE_A_DATA_DIR = REPO_ROOT / "data" / "phase_a"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bank_config import load_bank_matcher
from models import Article, PageText
from parsing import parse_business_wire_batch, parse_single_article_pdf
from scoring import ArticleScorer


class ReviewQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.matcher = load_bank_matcher(REPO_ROOT / "config" / "banks.json")
        cls.scorer = ArticleScorer(cls.matcher)

    def test_american_banker_parse_and_clean(self) -> None:
        pdf_path = PHASE_A_DATA_DIR / "american_banker" / "_Digital assets are here to stay__ BNY Mellon embraces crypto.pdf"
        article = parse_single_article_pdf(pdf_path, "american_banker", self.matcher, REPO_ROOT)
        self.assertIn("BNY Mellon", article.title)
        self.assertEqual(article.published_at, "2021-02-24")
        self.assertNotIn("About LexisNexis", article.clean_text)
        self.assertNotIn("Results list", article.clean_text)
        self.assertIn("BNY Mellon", article.bank_hits)

    def test_pr_newswire_parse_and_clean(self) -> None:
        pdf_path = PHASE_A_DATA_DIR / "pr_newswire" / "BNY Mellon and Goldman Sachs Settle First HQLAx Agency Securities Lending Transactions.pdf"
        article = parse_single_article_pdf(pdf_path, "pr_newswire", self.matcher, REPO_ROOT)
        self.assertIn("BNY Mellon", article.title)
        self.assertEqual(article.published_at, "2022-07-20")
        self.assertNotIn("About LexisNexis", article.clean_text)
        self.assertIn("Goldman Sachs", article.bank_hits)

    def test_business_wire_batch_segmentation(self) -> None:
        pdf_path = PHASE_A_DATA_DIR / "business_wire" / "Files (500) (1) - new.PDF"
        articles, review_rows = parse_business_wire_batch(
            pdf_path=pdf_path,
            bank_matcher=self.matcher,
            repo_root=REPO_ROOT,
            output_dir=REPO_ROOT,
            article_limit=3,
            write_segment_pdfs=False,
        )
        self.assertEqual(len(articles), 3)
        self.assertEqual(articles[0].page_start, 43)
        self.assertIn("PCI Council Publishes Tokenization Product Security Guidelines", articles[0].title)
        self.assertIn("Elavon Introduces SAFE-T Suite", articles[1].title)
        self.assertIn("Visa Opens Tokenization Services", articles[2].title)
        self.assertEqual(len(review_rows), 3)

    def test_scoring_ranks_positive_above_noise(self) -> None:
        positive_pdf = PHASE_A_DATA_DIR / "pr_newswire" / "BNY Mellon and Goldman Sachs Settle First HQLAx Agency Securities Lending Transactions.pdf"
        negative_pdf = PHASE_A_DATA_DIR / "american_banker" / "American Express turns NFTs into a credit card perk.pdf"
        positive_article = parse_single_article_pdf(positive_pdf, "pr_newswire", self.matcher, REPO_ROOT)
        negative_article = parse_single_article_pdf(negative_pdf, "american_banker", self.matcher, REPO_ROOT)
        positive_score, _ = self.scorer.score_article(positive_article)
        negative_score, _ = self.scorer.score_article(negative_article)
        self.assertGreater(positive_score.article_score, negative_score.article_score)

    def _make_article(self, title: str, body: str, bank_hits: list[str]) -> Article:
        return Article(
            article_id="test",
            source="unit",
            pdf_path="unit.pdf",
            title=title,
            published_at="2026-01-01",
            author="",
            page_start=1,
            page_end=1,
            raw_text=body,
            clean_text=body,
            bank_hits=bank_hits,
            pages=[PageText(page_number=1, raw_text=body, clean_text=body)],
        )

    def test_scoring_demotes_award_list_fragments(self) -> None:
        direct_article = self._make_article(
            "Wells Fargo launches blockchain settlement service",
            "Wells Fargo launched a blockchain settlement service for cross-border payments.",
            ["Wells Fargo"],
        )
        award_article = self._make_article(
            "BAI Announces 2018 Global Innovation Award Finalists",
            "Royal Bank of Canada (RBC): RBC Blockchain Shadow Ledger for Cross-border Payments.",
            ["RBC"],
        )
        direct_score, _ = self.scorer.score_article(direct_article)
        award_score, _ = self.scorer.score_article(award_article)
        self.assertGreater(direct_score.article_score, award_score.article_score)

    def test_scoring_demotes_multi_bank_sponsor_lists(self) -> None:
        direct_article = self._make_article(
            "Wells Fargo and HSBC settle FX transactions on blockchain network",
            "Wells Fargo and HSBC settled FX transactions on a blockchain network for cross-border payments.",
            ["Wells Fargo", "HSBC"],
        )
        noisy_article = self._make_article(
            "FinTech Innovation Lab opens call for applicants",
            "The selection committee includes Bank of America, Barclays, Citi, JPMorgan Chase and Wells Fargo. "
            "The innovation lab will support blockchain startups at demo day.",
            ["Bank of America", "Barclays", "Citi", "JPMorgan", "Wells Fargo"],
        )
        direct_score, _ = self.scorer.score_article(direct_article)
        noisy_score, _ = self.scorer.score_article(noisy_article)
        self.assertGreater(direct_score.article_score, noisy_score.article_score)

    def test_scoring_demotes_funding_announcements(self) -> None:
        direct_article = self._make_article(
            "Citi launches tokenized deposit service",
            "Citi launched a tokenized deposit service for institutional clients using blockchain infrastructure.",
            ["Citi"],
        )
        funding_article = self._make_article(
            "Citi invests in digital assets fintech",
            "Citi invests in a digital assets fintech. The funding round will be used to accelerate a blockchain network.",
            ["Citi"],
        )
        direct_score, _ = self.scorer.score_article(direct_article)
        funding_score, _ = self.scorer.score_article(funding_article)
        self.assertGreater(direct_score.article_score, funding_score.article_score)

    def test_scoring_demotes_market_reports_with_bank_lists(self) -> None:
        direct_article = self._make_article(
            "JPMorgan launches blockchain collateral platform",
            "JPMorgan launched a blockchain collateral platform for institutional clients.",
            ["JPMorgan"],
        )
        report_article = self._make_article(
            "Worldwide trade finance industry to 2026",
            "The report features Citi, HSBC, Barclays and Wells Fargo among leading players in blockchain trade finance.",
            ["Citi", "HSBC", "Barclays", "Wells Fargo"],
        )
        direct_score, _ = self.scorer.score_article(direct_article)
        report_score, _ = self.scorer.score_article(report_article)
        self.assertGreater(direct_score.article_score, report_score.article_score)

    def test_scoring_demotes_exec_appointment_and_patent_news(self) -> None:
        direct_article = self._make_article(
            "Northern Trust launches tokenized carbon platform",
            "Northern Trust launched a tokenized carbon platform built on distributed ledger technology.",
            ["Northern Trust"],
        )
        noisy_article = self._make_article(
            "Firm appoints former bank executive as chief technology officer",
            "The company appoints a former Northern Trust executive as chief technology officer after patent issuance for a blockchain settlement system.",
            ["Northern Trust"],
        )
        direct_score, _ = self.scorer.score_article(direct_article)
        noisy_score, _ = self.scorer.score_article(noisy_article)
        self.assertGreater(direct_score.article_score, noisy_score.article_score)


if __name__ == "__main__":
    unittest.main()
