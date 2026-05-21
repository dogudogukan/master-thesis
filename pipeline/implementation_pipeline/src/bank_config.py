"""Bank alias matching for implementation retrieval."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


def _alias_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias.strip())
    escaped = escaped.replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


@dataclass(frozen=True)
class BankEntry:
    name: str
    aliases: tuple[str, ...]


class BankMatcher:
    def __init__(self, entries: list[BankEntry]) -> None:
        self.entries = entries
        self._name_order = {entry.name: index for index, entry in enumerate(entries)}
        alias_records: list[tuple[str, re.Pattern[str]]] = []
        for entry in entries:
            for alias in sorted(entry.aliases, key=len, reverse=True):
                alias_records.append((entry.name, _alias_pattern(alias)))
        self._alias_records = alias_records

    def find_banks(self, text: str) -> list[str]:
        hits: set[str] = set()
        for bank_name, pattern in self._alias_records:
            if pattern.search(text):
                hits.add(bank_name)
        return sorted(hits, key=self._name_order.__getitem__)


def load_bank_matcher(config_path: Path) -> BankMatcher:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    entries = [
        BankEntry(name=item["name"], aliases=tuple(item["aliases"]))
        for item in payload["banks"]
    ]
    return BankMatcher(entries)
