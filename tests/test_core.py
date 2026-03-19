"""
tests/test_core.py
------------------
Unit tests for core normalisation and rule-matching logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from text_norm import (
    normalize_digits,
    normalize_text,
    normalize_upper,
    normalize_application_number,
    tr_to_ascii,
    person_name_tokens,
    org_core_tokens,
    has_weak_context,
    has_recipient_context,
    has_strong_sender_context,
)
from filters import should_exclude_transaction
from token_stats import build_token_stats, TokenStats


# ---------------------------------------------------------------------------
# text_norm
# ---------------------------------------------------------------------------

class TestNormalizeDigits:
    def test_strips_non_digits(self):
        assert normalize_digits("12 345 678 901") == "12345678901"

    def test_handles_none(self):
        assert normalize_digits(None) == ""

    def test_handles_float_nan(self):
        import math
        assert normalize_digits(float("nan")) == ""


class TestNormalizeText:
    def test_collapses_whitespace(self):
        assert normalize_text("  hello   world  ") == "hello world"

    def test_handles_none(self):
        assert normalize_text(None) == ""


class TestNormalizeApplicationNumber:
    def test_slash_to_dash(self):
        assert normalize_application_number("TR-2023/00123") == "2023-00123"

    def test_strips_letters(self):
        assert normalize_application_number("TR2023-00123") == "2023-00123"

    def test_deduplicates_dashes(self):
        assert normalize_application_number("2023--00123") == "2023-00123"


class TestTrToAscii:
    def test_turkish_chars(self):
        assert tr_to_ascii("Çiğdem Şahin") == "Cigdem Sahin"

    def test_uppercase_i(self):
        assert tr_to_ascii("İstanbul") == "Istanbul"


class TestNormalizeUpper:
    def test_upper_and_translit(self):
        assert normalize_upper("şahin") == "SAHIN"


class TestPersonNameTokens:
    def test_two_tokens(self):
        tokens = person_name_tokens("Ayşe Yılmaz")
        assert "AYSE" in tokens
        assert "YILMAZ" in tokens

    def test_single_initial_excluded(self):
        tokens = person_name_tokens("A. Yılmaz")
        assert "A" not in tokens
        assert "YILMAZ" in tokens


class TestOrgCoreTokens:
    def test_removes_stopwords(self):
        tokens = org_core_tokens("ÖZKAN GIDA SANAYİ TİCARET A.Ş.")
        assert "SANAYI" not in tokens
        assert "TICARET" not in tokens
        assert "OZKAN" in tokens
        assert "GIDA" in tokens

    def test_short_tokens_removed(self):
        tokens = org_core_tokens("AB GIDA LTD")
        assert "AB" not in tokens


class TestContextKeywords:
    def test_weak_adina(self):
        assert has_weak_context("MEHMET YILMAZ ADINA HAVALE") is True

    def test_strong_tarafindan(self):
        assert has_strong_sender_context("AYSE YILMAZ TARAFINDAN GELEN EFT") is True

    def test_recipient_alici(self):
        assert has_recipient_context("ALICI FATMA DEMIR") is True

    def test_clean_narrative(self):
        assert has_weak_context("AYSE YILMAZ IPARD 2023-00123") is False
        assert has_recipient_context("AYSE YILMAZ IPARD 2023-00123") is False


# ---------------------------------------------------------------------------
# filters
# ---------------------------------------------------------------------------

class TestShouldExcludeTransaction:
    def test_excludes_known_name(self):
        assert should_exclude_transaction("Virement", ["Virement", "EFT to Account"]) is True

    def test_case_insensitive(self):
        assert should_exclude_transaction("virement", ["Virement"]) is True

    def test_allows_unknown(self):
        assert should_exclude_transaction("EFT Payment", ["Virement"]) is False

    def test_empty_name(self):
        assert should_exclude_transaction("", ["Virement"]) is False


# ---------------------------------------------------------------------------
# token_stats
# ---------------------------------------------------------------------------

class TestTokenStats:
    def _make_stats(self, texts):
        return build_token_stats(texts)

    def test_idf_rare_higher(self):
        stats = self._make_stats(["AYSE YILMAZ", "AYSE DEMIR", "MEHMET KAYA"])
        # AYSE appears in 2/3 docs, KAYA in 1/3 — KAYA should have higher IDF
        assert stats.idf("KAYA") > stats.idf("AYSE")

    def test_is_common(self):
        stats = self._make_stats(["AYSE YILMAZ"] * 10 + ["MEHMET"])
        assert stats.is_common("AYSE", threshold=0.5) is True
        assert stats.is_common("MEHMET", threshold=0.5) is False

    def test_top_rare_tokens(self):
        stats = self._make_stats(["OZKAN GIDA"] * 5 + ["OZKAN NAKLIYAT LOJISTIK"] * 1)
        rare = stats.top_rare_tokens(["OZKAN", "LOJISTIK", "GIDA"], k=2)
        assert "LOJISTIK" in rare
