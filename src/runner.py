"""
runner.py
---------
Orchestrates the full four-phase hybrid reconciliation pipeline.

Pipeline overview
-----------------
Phase 1 – TC / VKN hard match (confidence 0.99)
Phase 2 – Application-number hard match (confidence 0.97)
Phase 3a – Safe person-name token match (confidence 0.90)
Phase 3b – Safe company-name token match (confidence 0.88)
Phase 4 – LLM + RAG semantic match (confidence from LLM)

Each phase operates only on applicants not yet resolved and transactions
not yet claimed. Resolved transactions are removed from the pool after
each phase to prevent double-assignment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from config import (
    APPLICANTS_XLS,
    BANK,
    APPLICANTS_SHEET,
    APPLICANTS_START_ROW,
    APPLICANTS_END_ROW,
    CO_FINANCING_SHEET,
    TRANSFER_SHEET,
    FILTERED_TRANSACTION_NAMES,
    EMBED_MODEL,
    CHROMA_DIR,
    RAG_TOP_K,
    OUTPUT_DIR,
    OUTPUT_PREFIX,
    ModelSpec,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
)
from io_applicants import read_applicants
from io_ipard2 import read_statement
from rule_candidates import (
    match_by_id_number,
    match_by_application_number,
    match_by_person_name,
    match_by_company_prefix,
)
from rag_store import TransactionVectorStore
from llm_client import OpenAICompatClient
from hybrid_matcher import decide_with_llm
from text_norm import (
    org_core_tokens,
    person_name_tokens,
    normalize_upper,
    tr_to_ascii,
    has_weak_context,
    has_recipient_context,
)
from token_stats import TokenStats, build_token_stats_from_txns
from excel_out import write_excel


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _txn_id(txn: Dict) -> str:
    return f"{txn['stmt_name']}|{txn['row_id']}"


def _remove_used_transactions(
    transactions: List[Dict], used_ids: List[str]
) -> List[Dict]:
    used = set(used_ids)
    return [t for t in transactions if _txn_id(t) not in used]


def _build_txn_index(transactions: List[Dict]) -> Dict[str, Dict]:
    return {_txn_id(t): t for t in transactions}


def load_all_transactions() -> List[Dict]:
    """Load and merge transactions from both statement sheets."""
    co_financing = read_statement(
        excel_path=BANK,
        sheet_name=CO_FINANCING_SHEET,
        filtered_txn_names=FILTERED_TRANSACTION_NAMES,
        statement_tag="CO_FINANCING",
    )
    transfer = read_statement(
        excel_path=BANK,
        sheet_name=TRANSFER_SHEET,
        filtered_txn_names=FILTERED_TRANSACTION_NAMES,
        statement_tag="TRANSFER",
    )
    return co_financing + transfer


# ---------------------------------------------------------------------------
# Phase 3 safety gates
# ---------------------------------------------------------------------------

def _person_has_strong_evidence(applicant: Dict, narrative: str) -> bool:
    """
    Determine whether a person-name match is safe to auto-confirm.

    Safety criteria:
    - ≥ 2 name tokens must appear in the narrative.
    - No weak-context keywords (adına / için / namına) — these indicate
      "on behalf of" scenarios where the named person is NOT the sender.
    - No recipient keywords (alıcı / alan).
    """
    name = applicant.get("name", "") or ""
    narrative_upper = normalize_upper(narrative)

    tokens_tr = person_name_tokens(name)
    tokens_en = person_name_tokens(tr_to_ascii(name))

    hits_tr = len({t for t in tokens_tr if t in narrative_upper})
    hits_en = len({t for t in tokens_en if t in narrative_upper})

    if has_weak_context(narrative):
        return False  # Ambiguous sender; escalate to Phase 4
    if has_recipient_context(narrative):
        return False  # Named person is the recipient, not sender

    return max(hits_tr, hits_en) >= 2


def _company_has_strong_evidence(
    applicant: Dict, narrative: str, stats: TokenStats
) -> bool:
    """
    Determine whether a company-name match is safe to auto-confirm.

    Safety criteria:
    - ≥ 3 core token overlaps (strict), OR
    - First 2 core tokens present + at least 1 rare token (IDF-based).
    - No weak-context or recipient keywords (unless overlap ≥ 4).
    """
    name = applicant.get("name", "") or ""
    core_tokens = org_core_tokens(name)
    if not core_tokens:
        return False

    narrative_upper = normalize_upper(narrative)
    overlap = [t for t in core_tokens if t in narrative_upper]

    if has_weak_context(narrative) and len(overlap) < 4:
        return False
    if has_recipient_context(narrative) and len(overlap) < 4:
        return False

    if len(overlap) >= 3:
        return True

    prefix = core_tokens[:2]
    if len(prefix) == 2 and all(t in narrative_upper for t in prefix):
        extra = [t for t in overlap if t not in prefix]
        if any(not stats.is_common(t, threshold=0.15) for t in extra):
            return True

    return False


def _try_safe_auto_match(
    applicant: Dict,
    candidate_ids: List[str],
    txn_index: Dict[str, Dict],
    stats: TokenStats,
) -> List[str]:
    """
    Return *candidate_ids* only when the single hit passes the safety gate.

    Phase 3 auto-matching is intentionally conservative:
    - Requires exactly 1 candidate (ambiguous multi-hits go to Phase 4).
    - Passes the candidate's narrative through the appropriate safety gate.
    """
    if len(candidate_ids) != 1:
        return []

    txn = txn_index.get(candidate_ids[0])
    if txn is None:
        return []

    narrative = txn.get("narrative", "") or ""
    if applicant.get("is_person"):
        return candidate_ids if _person_has_strong_evidence(applicant, narrative) else []
    return candidate_ids if _company_has_strong_evidence(applicant, narrative, stats) else []


# ---------------------------------------------------------------------------
# RAG query builder
# ---------------------------------------------------------------------------

def _build_rag_query(applicant: Dict, stats: TokenStats) -> str:
    """Compose a rich free-text query for semantic retrieval."""
    name = (applicant.get("name") or "").strip()
    app_no = (applicant.get("application_no") or applicant.get("basvuru_no") or "").strip()
    id_number = (applicant.get("tc_vkn") or "").strip()

    parts: List[str] = []
    if name:
        parts.append(name)

    if applicant.get("is_person"):
        tokens = person_name_tokens(name)
        if len(tokens) >= 2:
            parts.append(" ".join(reversed(tokens)))
    else:
        core = org_core_tokens(name)
        rare = stats.top_rare_tokens(core, k=4)
        if rare:
            parts.append(" ".join(rare))

    if app_no:
        parts.append(app_no)
    if id_number:
        parts.append(id_number)

    return " ".join(p for p in parts if p).strip()


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def run_reconciliation(
    model_spec: ModelSpec,
    applicants: List[Dict],
    all_transactions: List[Dict],
    progress_callback=None,
) -> List[Optional[Dict]]:
    """
    Run the full reconciliation pipeline for one LLM model.

    Args:
        model_spec: Provider configuration for the LLM Phase 4.
        applicants: List of applicant dicts.
        all_transactions: Combined transaction list from all statements.
        progress_callback: Optional callable(step: str, percent: int) for UI updates.

    Returns:
        List of decision dicts in the same order as *applicants*.
        ``None`` entries indicate applicants that received no decision.
    """

    def _log(msg: str, pct: int = -1) -> None:
        print(msg)
        if progress_callback and pct >= 0:
            progress_callback(msg, pct)

    remaining = list(all_transactions)
    decisions: List[Optional[Dict]] = [None] * len(applicants)

    # --- Phase 1: TC / VKN ---
    _log(f"[{model_spec.name}] Phase 1: ID-number matching …", 10)
    phase1_count = 0
    for i, app in enumerate(applicants):
        hits = match_by_id_number(app, remaining)
        if hits:
            decisions[i] = {
                "decision": "MATCH",
                "matched_ids": hits,
                "confidence": 0.99,
                "reason": "Rule: TC/VKN number found in narrative.",
                "_query": "",
            }
            remaining = _remove_used_transactions(remaining, hits)
            phase1_count += 1
    _log(f"  ✅ Phase 1 matches: {phase1_count}", 20)

    # --- Phase 2: Application number ---
    _log(f"[{model_spec.name}] Phase 2: Application-number matching …", 25)
    phase2_count = 0
    for i, app in enumerate(applicants):
        if decisions[i] is not None:
            continue
        hits = match_by_application_number(app, remaining)
        if hits:
            decisions[i] = {
                "decision": "MATCH",
                "matched_ids": hits,
                "confidence": 0.97,
                "reason": "Rule: Application number found in narrative.",
                "_query": "",
            }
            remaining = _remove_used_transactions(remaining, hits)
            phase2_count += 1
    _log(f"  ✅ Phase 2 matches: {phase2_count}", 35)

    # --- Phase 3a: Person name ---
    _log(f"[{model_spec.name}] Phase 3a: Person-name matching …", 38)
    stats = build_token_stats_from_txns(remaining)
    txn_index = _build_txn_index(remaining)
    phase3a_count = 0
    for i, app in enumerate(applicants):
        if decisions[i] is not None:
            continue
        hits = match_by_person_name(app, remaining)
        safe = _try_safe_auto_match(app, hits, txn_index, stats)
        if safe:
            decisions[i] = {
                "decision": "MATCH",
                "matched_ids": safe,
                "confidence": 0.90,
                "reason": "Rule: Person name — safe auto-match (≥ 2 tokens, no ambiguous context).",
                "_query": "",
            }
            remaining = _remove_used_transactions(remaining, safe)
            txn_index.pop(safe[0], None)
            phase3a_count += 1
    _log(f"  ✅ Phase 3a matches: {phase3a_count}", 48)

    # --- Phase 3b: Company name ---
    _log(f"[{model_spec.name}] Phase 3b: Company-name matching …", 50)
    stats = build_token_stats_from_txns(remaining)
    txn_index = _build_txn_index(remaining)
    phase3b_count = 0
    for i, app in enumerate(applicants):
        if decisions[i] is not None:
            continue
        hits = match_by_company_prefix(app, remaining)
        safe = _try_safe_auto_match(app, hits, txn_index, stats)
        if safe:
            decisions[i] = {
                "decision": "MATCH",
                "matched_ids": safe,
                "confidence": 0.88,
                "reason": "Rule: Company name — safe auto-match (rarity-aware).",
                "_query": "",
            }
            remaining = _remove_used_transactions(remaining, safe)
            txn_index.pop(safe[0], None)
            phase3b_count += 1
    _log(f"  ✅ Phase 3b matches: {phase3b_count}", 58)

    # --- Phase 4: LLM + RAG ---
    _log(f"[{model_spec.name}] Phase 4: LLM + RAG matching …", 60)
    stats = build_token_stats_from_txns(remaining)

    vector_store = TransactionVectorStore(persist_dir=CHROMA_DIR, embed_model=EMBED_MODEL)
    vector_store.reset()
    vector_store.index_transactions(remaining)
    _log(f"  ✅ RAG index built on {len(remaining)} remaining transactions", 65)

    llm = OpenAICompatClient(
        base_url=model_spec.base_url,
        api_key=model_spec.api_key,
        model=model_spec.model,
    )

    phase4_count = 0
    unresolved = [i for i, d in enumerate(decisions) if d is None]
    for step, i in enumerate(unresolved):
        app = applicants[i]
        query = _build_rag_query(app, stats)
        candidates = vector_store.query(query, top_k=RAG_TOP_K)

        verdict = decide_with_llm(app, candidates, llm)
        verdict["_query"] = query
        decisions[i] = verdict

        if verdict.get("decision") == "MATCH" and verdict.get("matched_ids"):
            remaining = _remove_used_transactions(remaining, verdict["matched_ids"])
            phase4_count += 1

        pct = 65 + int((step + 1) / max(len(unresolved), 1) * 30)
        if progress_callback:
            progress_callback(f"  LLM {step + 1}/{len(unresolved)}", pct)

    _log(f"  ✅ Phase 4 matches: {phase4_count}", 95)
    return decisions


def run_and_save(
    model_spec: ModelSpec,
    applicants: List[Dict],
    all_transactions: List[Dict],
    progress_callback=None,
) -> Path:
    """Run reconciliation and write the output workbook. Returns the output path."""
    decisions = run_reconciliation(model_spec, applicants, all_transactions, progress_callback)

    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{OUTPUT_PREFIX}_{model_spec.name}.xlsx"

    write_excel(
        out_path=out_path,
        model_name=model_spec.name,
        applicants=applicants,
        all_txns=all_transactions,
        decisions=decisions,
    )
    return out_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    applicants = read_applicants(
        excel_path=APPLICANTS_XLS,
        sheet_name=APPLICANTS_SHEET,
        start_row=APPLICANTS_START_ROW,
        end_row=APPLICANTS_END_ROW,
    )
    print(f"✅ Applicants: {len(applicants)} | rows {APPLICANTS_START_ROW}–{APPLICANTS_END_ROW}")

    all_transactions = load_all_transactions()
    print(f"✅ Transactions loaded: {len(all_transactions)}")

    models = [
        ModelSpec(
            name="deepseek",
            base_url=DEEPSEEK_BASE_URL,
            api_key=DEEPSEEK_API_KEY,
            model=DEEPSEEK_MODEL,
        ),
        # Uncomment to enable Groq / Qwen:
        # ModelSpec(name="qwen_groq", base_url=GROQ_BASE_URL, api_key=GROQ_API_KEY, model=QWEN_MODEL),
    ]

    for model_spec in models:
        out_path = run_and_save(model_spec, applicants, all_transactions)
        print(f"✅ Output: {out_path}")


if __name__ == "__main__":
    main()
