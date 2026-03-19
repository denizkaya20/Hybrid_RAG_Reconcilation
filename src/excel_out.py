"""
excel_out.py
------------
Writes the reconciliation results to a multi-sheet Excel workbook.

Output sheets
-------------
MATCHED             – Applicants successfully matched to a transaction.
REVIEW              – Ambiguous matches requiring manual review.
UNMATCHED_APPLICANTS – Applicants with no matching transaction found.
UNMATCHED_TXNS      – Transactions not claimed by any applicant.
STATS               – High-level run statistics.

Deduplication is applied per sheet (on ``stmt`` + ``row_id`` + ``amount``)
before writing so that multi-model runs do not inflate row counts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from text_norm import normalize_upper, person_name_tokens, org_core_tokens, tr_to_ascii


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _txn_id(txn: Dict[str, Any]) -> str:
    return f"{txn.get('stmt_name', '')}|{txn.get('row_id', '')}"


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _name_similarity_score(applicant: Dict, narrative: str) -> float:
    """
    Lightweight heuristic similarity score in [0, 1].

    Used only to annotate unmatched transactions with the best-guess
    applicant name for debugging purposes.
    """
    nar = normalize_upper(narrative)
    name = applicant.get("name", "") or ""

    if applicant.get("is_person"):
        tokens_tr = person_name_tokens(name)
        tokens_en = person_name_tokens(tr_to_ascii(name))
        if not tokens_tr and not tokens_en:
            return 0.0
        hits_tr = sum(1 for t in tokens_tr if t in nar)
        hits_en = sum(1 for t in tokens_en if t in nar)
        denominator = max(len(tokens_tr), len(tokens_en), 1)
        return max(hits_tr, hits_en) / denominator

    core = org_core_tokens(name)
    if not core:
        return 0.0
    hits = sum(1 for t in core if t in nar)
    return hits / max(len(core), 1)


def _best_guess_applicant(applicants: List[Dict], txn: Dict[str, Any]) -> Tuple[str, float]:
    """Return the name and score of the highest-scoring applicant for *txn*."""
    narrative = txn.get("narrative", "") or ""
    best_name, best_score = "", 0.0
    for app in applicants:
        score = _name_similarity_score(app, narrative)
        if score > best_score:
            best_score = score
            best_name = _safe_str(app.get("name", ""))
    return best_name, best_score


def _build_txn_row(
    model_name: str,
    applicant: Dict,
    decision: str,
    confidence: float,
    reason: str,
    query: str,
    txn: Dict,
    txn_id: str,
) -> Dict[str, Any]:
    """Build a single result row combining applicant and transaction fields."""
    return {
        "model": model_name,
        "name": _safe_str(applicant.get("name")),
        "tc_vkn": _safe_str(applicant.get("tc_vkn")),
        "application_no": _safe_str(applicant.get("application_no") or applicant.get("basvuru_no")),
        "is_person": bool(applicant.get("is_person", False)),
        "source_row": applicant.get("source_row") or applicant.get("src_row"),
        "decision": decision,
        "confidence": confidence,
        "reason": reason,
        "_query": query,
        "txn_id": txn_id,
        "statement": _safe_str(txn.get("stmt_name")),
        "row_id": txn.get("row_id"),
        "date": _safe_str(txn.get("date_str")),
        "amount": txn.get("amount"),
        "txn_name": _safe_str(txn.get("txn_name")),
        "narrative": _safe_str(txn.get("narrative")),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_excel(
    out_path: Path,
    model_name: str,
    applicants: List[Dict],
    all_txns: List[Dict],
    decisions: List[Optional[Dict]],
    annotate_unmatched: bool = False,
) -> None:
    """
    Persist reconciliation results to a multi-sheet ``.xlsx`` workbook.

    Args:
        out_path: Destination file path (parent directory is created if absent).
        model_name: Label for the ``model`` column (e.g. ``"deepseek"``).
        applicants: Applicant list in the same order as *decisions*.
        all_txns: Complete transaction list (used to build ``UNMATCHED_TXNS``).
        decisions: Per-applicant decision dicts (``None`` → no decision).
        annotate_unmatched: When ``True``, adds ``best_candidate_name`` /
                            ``best_candidate_score`` columns to ``UNMATCHED_TXNS``.
    """
    txn_by_id: Dict[str, Dict] = {_txn_id(t): t for t in all_txns}
    used_txn_ids: set[str] = set()

    matched_rows: List[Dict[str, Any]] = []
    review_rows: List[Dict[str, Any]] = []
    unmatched_applicant_rows: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Build per-applicant rows
    # ------------------------------------------------------------------
    for applicant, decision_dict in zip(applicants, decisions):
        if decision_dict is None:
            unmatched_applicant_rows.append(
                {
                    "model": model_name,
                    "name": _safe_str(applicant.get("name")),
                    "tc_vkn": _safe_str(applicant.get("tc_vkn")),
                    "application_no": _safe_str(
                        applicant.get("application_no") or applicant.get("basvuru_no")
                    ),
                    "is_person": bool(applicant.get("is_person", False)),
                    "source_row": applicant.get("source_row") or applicant.get("src_row"),
                    "decision": "UNMATCHED",
                    "confidence": 0.0,
                    "reason": "No decision produced.",
                }
            )
            continue

        decision = _safe_str(decision_dict.get("decision", "REVIEW")).upper().strip()
        matched_ids: List[str] = decision_dict.get("matched_ids", []) or []
        if not isinstance(matched_ids, list):
            matched_ids = [_safe_str(matched_ids)]

        try:
            confidence = float(decision_dict.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        reason = _safe_str(decision_dict.get("reason", ""))
        query = _safe_str(decision_dict.get("_query", ""))

        # Track used transactions only for confirmed matches
        if decision == "MATCH":
            for tid in matched_ids:
                used_txn_ids.add(_safe_str(tid))

        if decision == "MATCH":
            if not matched_ids:
                # MATCH declared but no IDs — escalate to REVIEW
                review_rows.append(
                    {
                        "model": model_name,
                        "name": _safe_str(applicant.get("name")),
                        "tc_vkn": _safe_str(applicant.get("tc_vkn")),
                        "application_no": _safe_str(
                            applicant.get("application_no") or applicant.get("basvuru_no")
                        ),
                        "is_person": bool(applicant.get("is_person", False)),
                        "source_row": applicant.get("source_row") or applicant.get("src_row"),
                        "decision": "REVIEW",
                        "confidence": confidence,
                        "reason": "MATCH declared but no matched_ids provided.",
                        "_query": query,
                        "txn_id": "",
                        "statement": "",
                        "row_id": None,
                        "date": "",
                        "amount": None,
                        "txn_name": "",
                        "narrative": "",
                    }
                )
            else:
                for tid in matched_ids:
                    txn = txn_by_id.get(_safe_str(tid), {})
                    matched_rows.append(
                        _build_txn_row(
                            model_name, applicant, decision,
                            confidence, reason, query, txn, _safe_str(tid),
                        )
                    )
        else:
            # REVIEW / CONFLICT / NO_MATCH / unknown
            effective_decision = decision if decision in {"REVIEW", "CONFLICT", "NO_MATCH"} else "REVIEW"
            effective_reason = reason if decision in {"REVIEW", "CONFLICT", "NO_MATCH"} else f"Unknown decision '{decision}'. {reason}".strip()

            if not matched_ids:
                review_rows.append(
                    {
                        "model": model_name,
                        "name": _safe_str(applicant.get("name")),
                        "tc_vkn": _safe_str(applicant.get("tc_vkn")),
                        "application_no": _safe_str(
                            applicant.get("application_no") or applicant.get("basvuru_no")
                        ),
                        "is_person": bool(applicant.get("is_person", False)),
                        "source_row": applicant.get("source_row") or applicant.get("src_row"),
                        "decision": effective_decision,
                        "confidence": confidence,
                        "reason": effective_reason,
                        "_query": query,
                        "txn_id": "",
                        "statement": "",
                        "row_id": None,
                        "date": "",
                        "amount": None,
                        "txn_name": "",
                        "narrative": "",
                    }
                )
            else:
                for tid in matched_ids:
                    txn = txn_by_id.get(_safe_str(tid), {})
                    review_rows.append(
                        _build_txn_row(
                            model_name, applicant, effective_decision,
                            confidence, effective_reason, query, txn, _safe_str(tid),
                        )
                    )

    # ------------------------------------------------------------------
    # Build unmatched-transaction rows
    # ------------------------------------------------------------------
    unmatched_txn_rows: List[Dict[str, Any]] = []
    for txn in all_txns:
        tid = _txn_id(txn)
        if tid in used_txn_ids:
            continue

        row: Dict[str, Any] = {
            "model": model_name,
            "txn_id": tid,
            "statement": _safe_str(txn.get("stmt_name")),
            "row_id": txn.get("row_id"),
            "date": _safe_str(txn.get("date_str")),
            "amount": txn.get("amount"),
            "txn_name": _safe_str(txn.get("txn_name")),
            "narrative": _safe_str(txn.get("narrative")),
        }

        if annotate_unmatched:
            best_name, best_score = _best_guess_applicant(applicants, txn)
            row["best_candidate_name"] = best_name
            row["best_candidate_score"] = round(best_score, 4)

        unmatched_txn_rows.append(row)

    # ------------------------------------------------------------------
    # Deduplication (stmt + row_id + amount as unique key)
    # ------------------------------------------------------------------
    def _dedup(rows: List[Dict], subset: List[str], label: str) -> pd.DataFrame:
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        # Only apply subset dedup when all columns are present
        valid_subset = [c for c in subset if c in df.columns]
        before = len(df)
        df = df.drop_duplicates(subset=valid_subset if valid_subset else None, keep="first")
        removed = before - len(df)
        if removed:
            print(f"   ⚠️  [{label}] {removed} duplicate rows removed")
        return df

    _TXN_DEDUP_COLS = ["statement", "row_id", "amount"]
    _APP_DEDUP_COLS = ["name", "tc_vkn", "application_no"]

    matched_df = _dedup(matched_rows, _TXN_DEDUP_COLS, "MATCHED")
    review_df = _dedup(review_rows, _TXN_DEDUP_COLS, "REVIEW")
    unmatched_app_df = _dedup(unmatched_applicant_rows, _APP_DEDUP_COLS, "UNMATCHED_APPLICANTS")
    unmatched_txn_df = _dedup(unmatched_txn_rows, _TXN_DEDUP_COLS, "UNMATCHED_TXNS")

    # ------------------------------------------------------------------
    # Statistics sheet
    # ------------------------------------------------------------------
    matched_source_rows = {
        r["source_row"]
        for _, r in matched_df.iterrows()
        if r.get("source_row") is not None
    }
    stats_df = pd.DataFrame(
        [
            {
                "model": model_name,
                "applicants_total": len(applicants),
                "matched_applicants": len(matched_source_rows),
                "matched_rows": len(matched_df),
                "review_rows": len(review_df),
                "unmatched_applicants": len(unmatched_app_df),
                "transactions_total": len(all_txns),
                "transactions_used": len(used_txn_ids),
                "transactions_unmatched": len(unmatched_txn_df),
            }
        ]
    )

    # ------------------------------------------------------------------
    # Write workbook
    # ------------------------------------------------------------------
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        matched_df.to_excel(writer, sheet_name="MATCHED", index=False)
        review_df.to_excel(writer, sheet_name="REVIEW", index=False)
        unmatched_app_df.to_excel(writer, sheet_name="UNMATCHED_APPLICANTS", index=False)
        unmatched_txn_df.to_excel(writer, sheet_name="UNMATCHED_TXNS", index=False)
        stats_df.to_excel(writer, sheet_name="STATS", index=False)

    print(f"✅ Workbook written: {out_path}")
