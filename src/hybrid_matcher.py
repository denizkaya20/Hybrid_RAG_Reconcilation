"""
hybrid_matcher.py
-----------------
LLM-based decision layer for the reconciliation pipeline (Phase 4).

The LLM receives an applicant's identifying fields together with a ranked
list of RAG-retrieved candidate transactions and returns a structured
JSON verdict: MATCH | REVIEW | NO_MATCH | CONFLICT.

A two-stage JSON-repair strategy handles malformed LLM output.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_DECISION_SYSTEM_PROMPT = """You are a financial reconciliation expert for Turkish banking transactions.
Your task: decide if candidate transactions belong to the given applicant.
Be conservative — return MATCH only when there is strong evidence in the narrative.

Matching rules
--------------
- TC/VKN number or Application Number present → strong evidence (MATCH).
- Full person name (at least 2 tokens) → medium evidence.
- Company name: require multiple distinctive tokens. Ignore legal suffixes (LTD, A.Ş, etc.).
- Generic words (ODEME / HAVALE / FAST) are NOT evidence on their own.

Turkish context keywords
------------------------
STRONG SENDER keywords (direct sender — good for matching):
  "tarafından"  → sent by / from
  "hesabından"  → from [their] account
  "gönderen"    → sender

WEAK / AMBIGUOUS keywords (review carefully — someone else may be the actual sender):
  "adına"    → on behalf of   ⚠ WARNING
  "için"     → for            ⚠ ambiguous
  "namına"   → on behalf of   ⚠ WARNING

RECIPIENT keywords (NOT the sender — do not match on these alone):
  "alıcı"    → recipient
  "hesabına" → to [their] account

Examples
--------
✅ MATCH: "AYŞE YILMAZ tarafından gelen EFT"
   AYŞE is the direct sender ("tarafından").

❌ NO_MATCH: "MEHMET YILMAZ adına AYŞE KAYA tarafından transfer"
   MEHMET is referenced with "adına" (on behalf of), AYŞE KAYA is the actual sender.

⚠️ REVIEW: "A. YILMAZ için ödeme"
   Only a surname with "için" — ambiguous, needs verification.

Output format
-------------
Return ONLY valid JSON. No markdown fences, no extra text.

{
  "decision": "MATCH|REVIEW|NO_MATCH|CONFLICT",
  "matched_ids": ["<statement_tag>|<row_id>", ...],
  "confidence": 0.0–1.0,
  "reason": "short explanation in English (≤ 150 words)"
}
"""

_REPAIR_SYSTEM_PROMPT = """You fix malformed JSON.
Return ONLY valid JSON that matches the provided schema. No markdown, no extra text.
"""


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------

def _extract_json_block(text: str) -> Optional[str]:
    """
    Extract the first complete JSON object or array from *text*.

    Handles cases where the LLM wraps the output in prose or markdown.
    """
    if not text:
        return None
    s = text.strip()

    # Fast path: entire string is already a JSON object/array
    if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
        return s

    start_positions = [i for i in (s.find("{"), s.find("[")) if i != -1]
    if not start_positions:
        return None

    start = min(start_positions)
    opener = s[start]
    closer = "}" if opener == "{" else "]"

    depth = 0
    in_string = False
    escaped = False

    for i in range(start, len(s)):
        ch = s[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return s[start : i + 1]

    return None


def _parse_json_tolerant(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse *text* as JSON, falling back to block extraction on failure.

    Returns the parsed dict or ``None`` on parse failure.
    """
    if not text:
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        block = _extract_json_block(text)
        if not block:
            return None
        try:
            obj = json.loads(block)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None


def _normalize_verdict(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce and clamp LLM output fields to their expected types / ranges."""
    decision = str(raw.get("decision", "REVIEW")).upper().strip()
    if decision not in {"MATCH", "REVIEW", "NO_MATCH", "CONFLICT"}:
        decision = "REVIEW"

    matched_ids = raw.get("matched_ids", [])
    if not isinstance(matched_ids, list):
        matched_ids = []

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    reason = raw.get("reason", "")
    if not isinstance(reason, str):
        reason = str(reason)

    return {
        "decision": decision,
        "matched_ids": matched_ids,
        "confidence": confidence,
        "reason": reason[:500],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decide_with_llm(
    applicant: Dict,
    candidates: List[Dict],
    llm_client: Any,
) -> Dict:
    """
    Ask the LLM to decide which (if any) candidate transactions match *applicant*.

    Two-stage strategy:
    1. Primary call with the decision prompt.
    2. If the primary response is not valid JSON, a repair call is made.

    Args:
        applicant: Applicant dict (``name``, ``tc_vkn``, ``application_no``, ``is_person``).
        candidates: RAG-retrieved candidate transactions.
        llm_client: Any object with a ``chat(messages, temperature, max_tokens)`` method.

    Returns:
        Normalised verdict dict with keys:
        ``decision``, ``matched_ids``, ``confidence``, ``reason``.
    """
    if not candidates:
        return {
            "decision": "NO_MATCH",
            "matched_ids": [],
            "confidence": 0.0,
            "reason": "No candidates retrieved from RAG.",
        }

    request_payload = {
        "applicant": {
            "name": applicant.get("name", ""),
            "tc_vkn": applicant.get("tc_vkn", ""),
            "application_no": applicant.get("application_no") or applicant.get("basvuru_no", ""),
            "is_person": bool(applicant.get("is_person", False)),
        },
        "candidates": candidates,
        "output_schema": {
            "decision": "MATCH|REVIEW|NO_MATCH|CONFLICT",
            "matched_ids": [],
            "confidence": 0.0,
            "reason": "",
        },
    }

    # --- Primary call ---
    raw_response = llm_client.chat(
        messages=[
            {"role": "system", "content": _DECISION_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(request_payload, ensure_ascii=False)},
        ],
        temperature=0.0,
        max_tokens=900,
    )

    verdict = _parse_json_tolerant(raw_response)
    if verdict is not None:
        return _normalize_verdict(verdict)

    # --- Repair call (malformed JSON) ---
    repair_payload = {
        "schema": request_payload["output_schema"],
        "bad_output": raw_response,
        "instruction": "Convert bad_output into valid JSON that exactly matches the schema. Return ONLY JSON.",
    }

    repaired_response = llm_client.chat(
        messages=[
            {"role": "system", "content": _REPAIR_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(repair_payload, ensure_ascii=False)},
        ],
        temperature=0.0,
        max_tokens=400,
    )

    verdict = _parse_json_tolerant(repaired_response)
    if verdict is not None:
        return _normalize_verdict(verdict)

    return {
        "decision": "REVIEW",
        "matched_ids": [],
        "confidence": 0.0,
        "reason": "LLM returned invalid JSON after primary call and repair attempt.",
    }
