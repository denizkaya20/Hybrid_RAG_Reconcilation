"""
text_norm.py
------------
Text normalisation utilities for Turkish banking narratives.

Handles:
- Turkish → ASCII transliteration
- Digit extraction / application-number normalisation
- Tokenisation for person names and organisation names
- Context keyword detection (sender / recipient / ambiguous)
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List

import pandas as pd

# ---------------------------------------------------------------------------
# Turkish → ASCII transliteration table
# ---------------------------------------------------------------------------
_TR_TO_ASCII = str.maketrans(
    {
        "Ç": "C", "Ğ": "G", "İ": "I", "Ö": "O", "Ş": "S", "Ü": "U",
        "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    }
)

# ---------------------------------------------------------------------------
# Organisation legal-suffix stop-words (removed before matching)
# ---------------------------------------------------------------------------
_ORG_STOPWORDS: frozenset[str] = frozenset(
    {
        # Legal entity suffixes
        "AS", "A.S", "A.Ş", "AS.", "AŞ",
        "LTD", "LTD.", "LIMITED",
        "STI", "ŞTI", "ŞTİ",
        "SIRKETI", "ŞİRKETİ", "SIRKET", "ŞİRKET",
        "ANONIM", "ANONİM",
        "KOOP", "KOOPERATIF", "KOOPERATİF",
        "DER", "DERNEGI", "DERNEĞİ",
        "VAKFI", "VAKIF",
        # Conjunctions / prepositions
        "VE", "ILE", "İLE", "CO", "COMPANY", "THE", "OF",
        # Very common sector terms (too ambiguous on their own)
        "SAN", "SAN.", "SANAYI", "SANAYİ",
        "TIC", "TIC.", "TICARET", "TİCARET",
        "DIS", "DIŞ",
        "ITH", "İTH", "IHR", "İHR",
        "ITHALAT", "İTHALAT", "IHRACAT", "İHRACAT",
    }
)

# ---------------------------------------------------------------------------
# Token alias / abbreviation normalisation map
# ---------------------------------------------------------------------------
_ALIAS: Dict[str, str] = {
    "AŞ": "A.Ş", "AS": "A.Ş", "AŞ.": "A.Ş",
    "ANONIM": "ANONIM", "ANONİM": "ANONIM",
    "LIM": "LIMITED", "LTD": "LIMITED", "LTD.": "LIMITED",
    "ŞTİ": "ŞTI", "ŞTI": "ŞTI",
    "SAN.": "SANAYI",
    "TIC.": "TICARET", "TİC": "TICARET", "TİCARET": "TICARET",
    "İNŞAAT": "INSAAT",
    "NAKLİYAT": "NAKLIYAT",
    "TURİZM": "TURIZM",
    "KOOPERATİF": "KOOPERATIF",
    "DERNEĞİ": "DERNEGI",
}

# ---------------------------------------------------------------------------
# Context-keyword sets for sender / recipient detection
# ---------------------------------------------------------------------------

# Strong sender keywords → direct sender confirmed, high confidence
_STRONG_SENDER_KEYWORDS: frozenset[str] = frozenset(
    {"TARAFINDAN", "HESABINDAN", "GONDERICI", "GONDEREN"}
)

# Weak / ambiguous keywords → "on behalf of" scenario, needs review
_WEAK_CONTEXT_KEYWORDS: frozenset[str] = frozenset(
    {"ADINA", "ICIN", "NAMINA", "HESABINA"}
)

# Recipient keywords → subject is receiving, not sending
_RECIPIENT_KEYWORDS: frozenset[str] = frozenset({"ALICI", "ALAN"})


# ===========================================================================
# Core normalisation helpers
# ===========================================================================

def normalize_digits(value: object) -> str:
    """Strip everything except ASCII digits from *value*."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\D", "", str(value))


def normalize_text(value: object) -> str:
    """Strip leading/trailing whitespace and collapse internal whitespace."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def tr_to_ascii(text: str) -> str:
    """Transliterate Turkish characters to their ASCII equivalents."""
    return normalize_text(text).translate(_TR_TO_ASCII)


def normalize_upper(text: str) -> str:
    """Return *text* in upper-case ASCII (Turkish chars transliterated)."""
    return tr_to_ascii(text).upper().strip()


def normalize_application_number(value: object) -> str:
    s = normalize_text(value)
    if not s:
        return ""
    s = s.replace("/", "-")
    s = re.sub(r"[^0-9\-]", "", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-")  # ← BU SATIRI EKLE
    return s



# ===========================================================================
# Tokenisation
# ===========================================================================

def tokenize_upper(text: str) -> List[str]:
    """
    Tokenise *text* into upper-case ASCII tokens.

    Splits on any non-alphanumeric character and discards empty tokens.
    """
    t = normalize_upper(text)
    if not t:
        return []
    return [tok for tok in re.split(r"[^A-Z0-9]+", t) if tok]


def _apply_alias(tokens: Iterable[str]) -> List[str]:
    return [_ALIAS.get(tok, tok) for tok in tokens]


def person_name_tokens(name: str) -> List[str]:
    """
    Return meaningful tokens from a person's full name.

    Keeps tokens of length ≥ 2 (single initials excluded).
    """
    tokens = _apply_alias(tokenize_upper(name))
    return [t for t in tokens if len(t) >= 2]


def org_core_tokens(name: str) -> List[str]:
    """
    Return informative tokens from an organisation name.

    Removes legal-suffix stop-words and tokens shorter than 3 characters.
    """
    tokens = _apply_alias(tokenize_upper(name))
    return [t for t in tokens if len(t) >= 3 and t not in _ORG_STOPWORDS]


# ===========================================================================
# Context keyword helpers
# ===========================================================================

def has_strong_sender_context(narrative: str) -> bool:
    """Return ``True`` when the narrative contains a strong sender keyword."""
    text = normalize_upper(narrative)
    return any(kw in text for kw in _STRONG_SENDER_KEYWORDS)


def has_weak_context(narrative: str) -> bool:
    """
    Return ``True`` when the narrative contains a weak / ambiguous keyword.

    Weak keywords (e.g. *adına* = "on behalf of") suggest that the named
    entity may not be the actual transaction sender.
    """
    text = normalize_upper(narrative)
    return any(kw in text for kw in _WEAK_CONTEXT_KEYWORDS)


def has_recipient_context(narrative: str) -> bool:
    """Return ``True`` when the narrative contains a recipient keyword."""
    text = normalize_upper(narrative)
    return any(kw in text for kw in _RECIPIENT_KEYWORDS)


# ---------------------------------------------------------------------------
# Legacy aliases (backward compatibility)
# ---------------------------------------------------------------------------
norm_text = normalize_text
norm_digits = normalize_digits
norm_upper = normalize_upper
norm_bno = normalize_application_number
tr_to_en = tr_to_ascii
person_tokens = person_name_tokens
