"""
filters.py
----------
Transaction-level filter predicates.
"""

from __future__ import annotations


def _normalize_txn_name(name: str) -> str:
    return (str(name) if name else "").strip().lower()


def should_exclude_transaction(txn_name: str, excluded_names: list[str]) -> bool:
    if not txn_name or (isinstance(txn_name, float)):
        return False
    return _normalize_txn_name(str(txn_name)) in {_normalize_txn_name(n) for n in excluded_names}


# Legacy alias
should_filter_txn_name = should_exclude_transaction
