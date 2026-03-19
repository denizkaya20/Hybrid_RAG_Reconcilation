"""
filters.py
----------
Transaction-level filter predicates.
"""

from __future__ import annotations


def _normalize_txn_name(name: str) -> str:
    return (name or "").strip().lower()


def should_exclude_transaction(txn_name: str, excluded_names: list[str]) -> bool:
    """
    Return ``True`` when *txn_name* is in the exclusion list.

    Comparison is case-insensitive and strips surrounding whitespace.

    Args:
        txn_name: Raw transaction name from the bank statement.
        excluded_names: List of names to filter out (e.g. ``"Virement"``).

    Returns:
        ``True`` if the transaction should be excluded, ``False`` otherwise.
    """
    if not txn_name:
        return False
    normalised = _normalize_txn_name(txn_name)
    excluded_set = {_normalize_txn_name(n) for n in excluded_names}
    return normalised in excluded_set


# Legacy alias
should_filter_txn_name = should_exclude_transaction
