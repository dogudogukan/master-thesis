"""Article scoring for the implementation review queue."""

from __future__ import annotations

from dataclasses import dataclass

import spacy

from bank_config import BankMatcher
from lexicons import (
    BANK_ROLE_SIGNALS,
    COLLABORATION_SIGNALS,
    IMPLEMENTATION_NOUNS,
    IMPLEMENTATION_VERBS,
    NEGATIVE_SIGNALS,
    STAGE_SIGNALS,
)
from models import Article, ScoredArticle, SentenceEvidence


def _phrase_hits(text: str, patterns: list[tuple[str, object]]) -> list[str]:
    hits: list[str] = []
    for phrase, pattern in patterns:
        if pattern.search(text):
            hits.append(phrase)
    return hits


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


LIST_CUE_PHRASES = (
    "includes ",
    "include ",
    "including ",
    "participants include",
    "program participants",
    "launch partners include",
    "joins consortium",
    "alongside ",
    "among ",
    "backed by",
    "investors include",
    "selected for",
)


@dataclass
class SentenceSignals:
    positive_hits: list[str]
    negative_hits: list[str]
    bank_hits: list[str]
    score: float


class ArticleScorer:
    def __init__(self, bank_matcher: BankMatcher) -> None:
        self.bank_matcher = bank_matcher
        self.nlp = spacy.load(
            "en_core_web_sm",
            exclude=["tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer", "ner"],
        )
        if "sentencizer" not in self.nlp.pipe_names:
            self.nlp.add_pipe("sentencizer")

    def _sentence_signals(self, sentence: str) -> SentenceSignals:
        verb_hits = _phrase_hits(sentence, IMPLEMENTATION_VERBS)
        noun_hits = _phrase_hits(sentence, IMPLEMENTATION_NOUNS)
        stage_hits = _phrase_hits(sentence, STAGE_SIGNALS)
        role_hits = _phrase_hits(sentence, BANK_ROLE_SIGNALS)
        collaboration_hits = _phrase_hits(sentence, COLLABORATION_SIGNALS)
        negative_hits = _phrase_hits(sentence, NEGATIVE_SIGNALS)
        bank_hits = self.bank_matcher.find_banks(sentence)
        bank_count = len(bank_hits)
        sentence_lower = sentence.lower()
        direct_event = bool(verb_hits and (noun_hits or role_hits or stage_hits))
        bank_event = bool(bank_hits and (verb_hits or stage_hits or role_hits))
        list_like_bank_mention = bank_count >= 3 and _contains_any(sentence_lower, LIST_CUE_PHRASES)

        positive_hits = verb_hits + noun_hits + stage_hits + role_hits + collaboration_hits
        score = 0.0
        score += len(set(verb_hits)) * 2.4
        score += len(set(noun_hits)) * 2.0
        score += len(set(stage_hits)) * 1.8
        score += len(set(role_hits)) * 1.4
        score += min(bank_count, 2) * 1.5
        if collaboration_hits and bank_count >= 1 and (direct_event or bank_count <= 2):
            score += 1.2
        if verb_hits and noun_hits:
            score += 2.2
        if bank_hits and direct_event:
            score += 2.6
        elif bank_hits and (verb_hits or noun_hits or stage_hits):
            score += 1.5
        if bank_count == 1 and bank_event:
            score += 0.7
        # Multi-bank lists usually add noise unless they also carry a clear event.
        if bank_count >= 3 and not collaboration_hits and not stage_hits:
            score -= (bank_count - 2) * 0.9
        if list_like_bank_mention and not direct_event:
            score -= 2.4
        # Awards and finalist fragments often look positive lexically but lack an event.
        if bank_hits and not verb_hits and not stage_hits and (":" in sentence or "•" in sentence):
            score -= 1.6
        if "source:" in sentence_lower or "according to" in sentence_lower:
            score -= 1.2
        if bank_count >= 2 and noun_hits and not bank_event:
            score -= 0.9
        score -= len(set(negative_hits)) * 2.8
        if len(sentence) < 35 and score > 0:
            score -= 0.5
        return SentenceSignals(
            positive_hits=positive_hits,
            negative_hits=negative_hits,
            bank_hits=bank_hits,
            score=score,
        )

    def score_article(self, article: Article) -> tuple[ScoredArticle, list[SentenceEvidence]]:
        evidence_rows: list[SentenceEvidence] = []
        sentence_counter = 0
        for page in article.pages:
            if not page.clean_text:
                continue
            doc = self.nlp(page.clean_text)
            for sent in doc.sents:
                sentence = sent.text.strip()
                if not sentence:
                    continue
                sentence_counter += 1
                signals = self._sentence_signals(sentence)
                if signals.positive_hits or signals.negative_hits or signals.bank_hits:
                    evidence_rows.append(
                        SentenceEvidence(
                            article_id=article.article_id,
                            source=article.source,
                            pdf_path=article.pdf_path,
                            page_number=page.page_number,
                            sentence_index=sentence_counter,
                            sentence=sentence,
                            score=signals.score,
                            bank_hits=signals.bank_hits,
                            positive_hits=signals.positive_hits,
                            negative_hits=signals.negative_hits,
                        )
                    )

        title_text = article.title or ""
        lead_text = article.clean_text[:1200]
        title_positive = (
            _phrase_hits(title_text, IMPLEMENTATION_VERBS)
            + _phrase_hits(title_text, IMPLEMENTATION_NOUNS)
            + _phrase_hits(title_text, STAGE_SIGNALS)
        )
        title_negative = _phrase_hits(title_text, NEGATIVE_SIGNALS)
        lead_positive = (
            _phrase_hits(lead_text, IMPLEMENTATION_VERBS)
            + _phrase_hits(lead_text, IMPLEMENTATION_NOUNS)
            + _phrase_hits(lead_text, STAGE_SIGNALS)
            + _phrase_hits(lead_text, BANK_ROLE_SIGNALS)
        )
        lead_negative = _phrase_hits(lead_text, NEGATIVE_SIGNALS)
        title_bank_hits = self.bank_matcher.find_banks(title_text)
        lead_bank_hits = self.bank_matcher.find_banks(lead_text)
        title_positive_count = len(set(title_positive))
        lead_positive_count = len(set(lead_positive))
        title_negative_count = len(set(title_negative))
        lead_negative_count = len(set(lead_negative))
        lead_text_lower = lead_text.lower()

        top_sentences = sorted(
            evidence_rows,
            key=lambda item: (item.score, len(item.bank_hits), len(item.positive_hits)),
            reverse=True,
        )[:3]
        article_score = 0.0
        article_score += min(len(lead_bank_hits), 2) * 2.2
        article_score += min(len(title_bank_hits), 2) * 1.0
        article_score += title_positive_count * (2.4 if title_bank_hits else 1.1)
        article_score += lead_positive_count * (1.3 if lead_bank_hits else 0.5)
        article_score -= title_negative_count * 3.2
        article_score -= lead_negative_count * 1.8
        if top_sentences:
            article_score += top_sentences[0].score * 1.6
            if len(top_sentences) > 1:
                article_score += top_sentences[1].score * 0.7
            if len(top_sentences) > 2:
                article_score += top_sentences[2].score * 0.4
        if title_bank_hits and title_positive:
            article_score += 1.2
        if 1 <= len(lead_bank_hits) <= 2 and lead_positive_count:
            article_score += 0.8
        if len(lead_bank_hits) >= 3 and _contains_any(lead_text_lower, LIST_CUE_PHRASES):
            article_score -= 2.4
        if len(article.bank_hits) >= 4 and not title_bank_hits and _contains_any(lead_text_lower, LIST_CUE_PHRASES):
            article_score -= 1.5
        if len(article.bank_hits) >= 4 and not title_bank_hits and not any(item.bank_hits for item in top_sentences[:1]):
            article_score -= 1.5
        return (
            ScoredArticle(article=article, article_score=article_score, top_sentences=top_sentences),
            evidence_rows,
        )
