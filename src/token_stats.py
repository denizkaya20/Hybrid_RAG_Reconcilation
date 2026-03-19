"""
token_stats.py
--------------
Corpus-level token frequency statistics used to identify rare (informative)
tokens when building name-matching queries.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set

from text_norm import tokenize_upper


@dataclass(frozen=True)
class TokenStats:
    """
    Lightweight TF-IDF-style token statistics over a transaction corpus.

    Attributes:
        total: Total number of documents (transactions) in the corpus.
        doc_freq: Mapping of token → number of documents containing it.
    """

    total: int
    doc_freq: Dict[str, int]

    def idf(self, token: str) -> float:
        """Smoothed IDF score for *token* (higher = rarer)."""
        freq = self.doc_freq.get(token, 0)
        return math.log((self.total + 1.0) / (freq + 1.0)) + 1.0

    def is_common(self, token: str, threshold: float = 0.15) -> bool:
        """Return ``True`` when *token* appears in ≥ *threshold* fraction of docs."""
        if self.total <= 0:
            return False
        return (self.doc_freq.get(token, 0) / self.total) >= threshold

    def top_rare_tokens(self, tokens: Iterable[str], k: int = 4) -> List[str]:
        """
        Return the *k* rarest tokens from *tokens*, ranked by IDF descending.

        Duplicates are removed while preserving first-occurrence order.
        """
        unique = list(dict.fromkeys(t for t in tokens if t))
        unique.sort(key=lambda t: self.idf(t), reverse=True)
        return unique[:k]


def build_token_stats(texts: Iterable[str]) -> TokenStats:
    """
    Build :class:`TokenStats` from an iterable of raw text strings.

    Args:
        texts: Any iterable of strings (e.g. transaction narratives).

    Returns:
        A :class:`TokenStats` instance populated with document-frequency counts.
    """
    doc_freq: Dict[str, int] = {}
    total = 0
    for text in texts:
        total += 1
        seen: Set[str] = set(tokenize_upper(text))
        for token in seen:
            doc_freq[token] = doc_freq.get(token, 0) + 1
    return TokenStats(total=total, doc_freq=doc_freq)


def build_token_stats_from_txns(transactions: List[Dict]) -> TokenStats:
    """
    Build :class:`TokenStats` from a list of transaction dicts.

    Reads the ``"narrative"`` field of each transaction.
    """
    texts = [(t.get("narrative") or "") for t in transactions]
    return build_token_stats(texts)
