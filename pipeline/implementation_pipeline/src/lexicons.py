"""Lexicons for implementation scoring."""

from __future__ import annotations

import re


def _compile(phrases: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    records: list[tuple[str, re.Pattern[str]]] = []
    for phrase in phrases:
        escaped = re.escape(phrase)
        escaped = escaped.replace(r"\ ", r"\s+")
        records.append(
            (
                phrase,
                re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE),
            )
        )
    return records


IMPLEMENTATION_VERBS = _compile(
    [
        "launch",
        "launched",
        "pilot",
        "piloted",
        "proof of concept",
        "tested",
        "test",
        "went live",
        "goes live",
        "go live",
        "live",
        "settled",
        "settlement",
        "built",
        "build",
        "developed",
        "develops",
        "integrated",
        "integrates",
        "issued",
        "issuance",
        "tokenized",
        "tokenization",
        "completed",
        "executed",
        "implemented",
        "rolled out",
        "used",
        "uses",
        "enabled",
        "enables"
    ]
)

IMPLEMENTATION_NOUNS = _compile(
    [
        "blockchain",
        "distributed ledger",
        "dlt",
        "smart contract",
        "smart contracts",
        "platform",
        "network",
        "service",
        "workflow",
        "settlement",
        "custody",
        "cash management",
        "trade finance",
        "deposit token",
        "tokenized deposit",
        "stablecoin",
        "collateral",
        "digital asset platform",
        "digital bond",
        "digital assets",
        "digital cash",
        "tokenized"
    ]
)

STAGE_SIGNALS = _compile(
    [
        "proof of concept",
        "pilot",
        "piloting",
        "tested",
        "test",
        "went live",
        "goes live",
        "live",
        "in production",
        "production",
        "first transaction",
        "first issuance",
        "first trade",
        "successfully completed",
        "completed"
    ]
)

BANK_ROLE_SIGNALS = _compile(
    [
        "institutional clients",
        "client",
        "clients",
        "treasury",
        "trade finance",
        "payments",
        "payment",
        "cash management",
        "custody",
        "securities lending",
        "issuance",
        "settlement",
        "cross-border",
        "deposits",
        "bank guarantee",
        "letter of credit"
    ]
)

COLLABORATION_SIGNALS = _compile(
    [
        "along with",
        "in collaboration with",
        "collaborated with",
        "collaborates with",
        "partnered with",
        "partnering with",
        "together with"
    ]
)

NEGATIVE_SIGNALS = _compile(
    [
        "etf",
        "nft",
        "perk",
        "loyalty",
        "conference",
        "summit",
        "forum",
        "event",
        "panel",
        "webinar",
        "agenda",
        "preview",
        "survey",
        "study",
        "report",
        "researchandmarkets.com",
        "outlook",
        "whitepaper",
        "white paper",
        "board of directors",
        "advisory board",
        "chief executive officer",
        "chief technology officer",
        "honoree",
        "honorees",
        "finalist",
        "finalists",
        "nominee",
        "nominees",
        "applicant",
        "applicants",
        "demo day",
        "innovation lab",
        "key appointments",
        "appoints",
        "appointed",
        "taps",
        "joins",
        "join",
        "member",
        "membership",
        "selection committee",
        "sponsored by",
        "sponsor",
        "hiring",
        "hired",
        "seed round",
        "series a",
        "series b",
        "funding round",
        "raised",
        "invests in",
        "investment in",
        "invested in",
        "backed by",
        "financial results",
        "call for applicants",
        "venture",
        "patent issuance",
        "patent no",
        "best global cash management bank",
        "source:",
        "according to",
        "reportedly",
        "metaverse",
        "award",
        "awards",
        "highlights"
    ]
)
