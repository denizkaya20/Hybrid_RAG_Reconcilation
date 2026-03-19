"""
rule_candidates.py
------------------
Rule-based candidate generation for the reconciliation pipeline.

Each function returns a list of transaction IDs (``"<statement_tag>|<row_id>"``)
that are *candidate matches* for the given applicant based on deterministic rules.

Phase 1 – TC / VKN  (hard match – highest confidence)
Phase 2 – Application number  (hard match)
Phase 3a – Person full-name tokens  (≥ 2 token overlap required)
Phase 3b – Organisation prefix-2 tokens  (first 2 core tokens required)
"""

from __future__ import annotations

from typing import Dict, List

from text_norm import (
    normalize_digits,
    normalize_application_number,
    normalize_upper,
    tr_to_ascii,
    person_name_tokens,
    org_core_tokens,
)


def _transaction_id(txn: Dict) -> str:
    """Return the canonical transaction identifier string."""
    return f"{txn['stmt_name']}|{txn['row_id']}"


# ---------------------------------------------------------------------------
# Phase 1 – TC identity / tax registration number
# ---------------------------------------------------------------------------

def match_by_id_number(applicant: Dict, transactions: List[Dict]) -> List[str]:
    """
    Return transactions whose narrative contains the applicant's TC/VKN number.

    Args:
        applicant: Applicant record with a ``tc_vkn`` field.
        transactions: Candidate transaction list.

    Returns:
        List of matching transaction IDs.
    """
    id_number = normalize_digits(applicant.get("tc_vkn", ""))
    if not id_number:
        return []

    return [
        _transaction_id(t)
        for t in transactions
        if id_number in normalize_digits(t.get("narrative", ""))
    ]


# ---------------------------------------------------------------------------
# Phase 2 – Application number
# ---------------------------------------------------------------------------

def match_by_application_number(applicant: Dict, transactions: List[Dict]) -> List[str]:
    """
    Return transactions whose narrative contains the applicant's application number.

    Args:
        applicant: Applicant record with a ``basvuru_no`` / ``application_no`` field.
        transactions: Candidate transaction list.

    Returns:
        List of matching transaction IDs.
    """
    app_no = normalize_application_number(
        applicant.get("application_no") or applicant.get("basvuru_no", "")
    )
    if not app_no:
        return []

    return [
        _transaction_id(t)
        for t in transactions
        if app_no in normalize_application_number(t.get("narrative", ""))
    ]


# ---------------------------------------------------------------------------
# Phase 3a – Person name token matching
# ---------------------------------------------------------------------------

def match_by_person_name(applicant: Dict, transactions: List[Dict]) -> List[str]:
    """
    Return transactions with ≥ 2 name-token matches in the narrative.

    Uses both Turkish and ASCII-transliterated token sets to handle
    inconsistent encoding in bank narratives.

    Args:
        applicant: Applicant record; skipped if ``is_person`` is falsy.
        transactions: Candidate transaction list.

    Returns:
        List of matching transaction IDs.
    """
    if not applicant.get("is_person"):
        return []

    name = applicant.get("name", "") or ""
    tokens_tr = person_name_tokens(name)
    tokens_en = person_name_tokens(tr_to_ascii(name))

    if not tokens_tr and not tokens_en:
        return []

    hits: List[str] = []
    for txn in transactions:
        narrative_upper = normalize_upper(txn.get("narrative", ""))

        tr_hits = sum(1 for tok in tokens_tr if tok in narrative_upper)
        en_hits = sum(1 for tok in tokens_en if tok in narrative_upper)

        if max(tr_hits, en_hits) >= 2:
            hits.append(_transaction_id(txn))
            continue

        # Edge case: very short names (single token) — require full-string match
        if len(tokens_tr) < 2:
            full_tr = normalize_upper(name)
            full_en = normalize_upper(tr_to_ascii(name))
            if (full_tr and full_tr in narrative_upper) or (full_en and full_en in narrative_upper):
                hits.append(_transaction_id(txn))

    return hits


# ---------------------------------------------------------------------------
# Phase 3b – Organisation name prefix matching
# ---------------------------------------------------------------------------

def match_by_company_prefix(applicant: Dict, transactions: List[Dict]) -> List[str]:
    """
    Return transactions containing the first two core tokens of the company name.

    Args:
        applicant: Applicant record; skipped if ``is_person`` is truthy.
        transactions: Candidate transaction list.

    Returns:
        List of matching transaction IDs.
    """
    if applicant.get("is_person"):
        return []

    name = applicant.get("name", "") or ""
    core_tokens = org_core_tokens(name)
    if not core_tokens:
        return []

    # Conservative: require first two distinctive tokens only
    prefix = core_tokens[:2]

    return [
        _transaction_id(t)
        for t in transactions
        if all(tok in normalize_upper(t.get("narrative", "")) for tok in prefix)
    ]


# ---------------------------------------------------------------------------
# Legacy aliases (backward compatibility with runner.py)
# ---------------------------------------------------------------------------
match_tc_vkn = match_by_id_number
match_basvuru_no = match_by_application_number
match_person_name = match_by_person_name
match_company_prefix2 = match_by_company_prefix
