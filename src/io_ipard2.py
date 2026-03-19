"""
io_ipard2.py
------------
Reads IPARD II bank statement Excel sheets and returns normalised
transaction records.

The header row is auto-detected by scanning the first *N* rows for the
required column names:
    - TRANSACTION DATE
    - AMOUNT
    - NARRATIVE
    - TRANSACTION NAME

Only positive-amount (incoming) transactions are returned; rows with an
empty narrative or a filtered transaction name are dropped.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd

from filters import should_exclude_transaction
from text_norm import normalize_text, normalize_upper


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_header_row(
    excel_path: str,
    sheet: str,
    max_search_rows: int = 15,
) -> Optional[Tuple[int, pd.DataFrame]]:
    """
    Scan up to *max_search_rows* rows to locate the column-header row.

    All four required column names must be present:
    ``TRANSACTION DATE``, ``AMOUNT``, ``NARRATIVE``, ``TRANSACTION NAME``.

    Returns:
        ``(header_row_1based, dataframe)`` on success, ``None`` on failure.
    """
    for row_guess in range(max_search_rows):
        for engine in ("xlrd", "openpyxl"):
            try:
                df = pd.read_excel(
                    excel_path,
                    sheet_name=sheet,
                    header=row_guess,
                    engine=engine,
                )
            except Exception:
                continue

            col_names_upper = [normalize_upper(str(c)) for c in df.columns]

            has_date = any("TRANSACTION" in c and "DATE" in c for c in col_names_upper)
            has_amount = any("AMOUNT" in c for c in col_names_upper)
            has_narrative = any("NARRATIVE" in c for c in col_names_upper)
            has_txn_name = any("TRANSACTION" in c and "NAME" in c for c in col_names_upper)

            if has_date and has_amount and has_narrative and has_txn_name:
                return (row_guess + 1, df)  # return 1-based row number

    return None


def _find_column_indices(df: pd.DataFrame) -> Optional[Dict[str, int]]:
    """
    Map logical column roles to their positional indices in *df*.

    Returns:
        Dict with keys ``DATE``, ``AMOUNT``, ``NARRATIVE``, ``TXN_NAME``
        or ``None`` if any required column is missing.
    """
    upper_cols = [normalize_upper(str(c)) for c in df.columns]
    result: Dict[str, int] = {}

    for idx, col in enumerate(upper_cols):
        if "TRANSACTION" in col and "DATE" in col:
            result["DATE"] = idx
            break
    if "DATE" not in result:
        # Fallback: first column containing "DATE"
        for idx, col in enumerate(upper_cols):
            if "DATE" in col:
                result["DATE"] = idx
                break

    for idx, col in enumerate(upper_cols):
        if "AMOUNT" in col:
            result["AMOUNT"] = idx
            break

    for idx, col in enumerate(upper_cols):
        if "NARRATIVE" in col:
            result["NARRATIVE"] = idx
            break

    for idx, col in enumerate(upper_cols):
        if "TRANSACTION" in col and "NAME" in col:
            result["TXN_NAME"] = idx
            break

    required = {"DATE", "AMOUNT", "NARRATIVE", "TXN_NAME"}
    if not required.issubset(result):
        return None
    return result


def _parse_amount(value: object) -> float:
    """
    Coerce an Excel cell value to a float amount.

    Handles both Turkish (``1.234,56``) and English (``1,234.56``) formats.
    """
    if pd.isna(value):  # type: ignore[arg-type]
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    # "1.234,56" → "1234.56"
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_statement(
    excel_path: str,
    sheet_name: str,
    filtered_txn_names: List[str],
    statement_tag: str,
) -> List[Dict]:
    """
    Parse one bank-statement worksheet into a list of transaction dicts.

    Processing steps:

    1. Auto-detect the header row.
    2. Auto-detect column positions.
    3. Drop transactions whose ``TRANSACTION NAME`` is in *filtered_txn_names*.
    4. Drop rows with empty narrative or non-positive amount.
    5. Normalise and return.

    Args:
        excel_path: Path to the Excel file.
        sheet_name: Worksheet name (e.g. ``" EŞ-FİNANSMAN HESABI"``).
        filtered_txn_names: Transaction names to exclude.
        statement_tag: Short label used in log messages and returned dicts
                       (e.g. ``"CO_FINANCING"``).

    Returns:
        List of dicts with keys:
        ``statement_tag``, ``sheet_name``, ``row_id``, ``date_str``,
        ``amount``, ``txn_name``, ``narrative``, ``header_row_used``.

    Raises:
        RuntimeError: When auto-detection of header or required columns fails.
    """
    print(f"   🔍 [{statement_tag}] Auto-detecting header and columns …")

    detection = _find_header_row(excel_path, sheet_name)
    if detection is None:
        raise RuntimeError(
            f"[{statement_tag}] Header auto-detection failed. "
            f"Sheet '{sheet_name}' does not contain the required columns: "
            "TRANSACTION DATE, AMOUNT, NARRATIVE, TRANSACTION NAME."
        )

    header_row, df = detection
    print(f"   ✅ [{statement_tag}] Header at row {header_row} (0-based pandas index {header_row - 1})")

    col_map = _find_column_indices(df)
    if col_map is None:
        raise RuntimeError(
            f"[{statement_tag}] Required columns not found in sheet '{sheet_name}'. "
            f"Detected columns: {list(df.columns)}"
        )

    print(
        f"   ✅ [{statement_tag}] Column indices – "
        f"DATE={col_map['DATE']}, AMOUNT={col_map['AMOUNT']}, "
        f"NARRATIVE={col_map['NARRATIVE']}, TXN_NAME={col_map['TXN_NAME']}"
    )

    # Apply transaction-name filter
    txn_name_col = df.columns[col_map["TXN_NAME"]] if df.shape[1] > col_map["TXN_NAME"] else None
    if txn_name_col is not None:
        rows_before = len(df)
        df["_txn_name"] = df[txn_name_col].astype(str).str.strip()
        df = df[
            ~df["_txn_name"].apply(lambda x: should_exclude_transaction(x, filtered_txn_names))
        ]
        print(f"   ✅ [{statement_tag}] Filtered {rows_before - len(df)} excluded transaction names")
    else:
        print(f"   ⚠️  [{statement_tag}] TXN_NAME column not found at index {col_map['TXN_NAME']}; skipping filter")

    transactions: List[Dict] = []
    for row_idx, row in df.iterrows():
        try:
            date_val = row.iloc[col_map["DATE"]]
            amount_val = row.iloc[col_map["AMOUNT"]]
            narrative_val = row.iloc[col_map["NARRATIVE"]]
        except Exception:
            continue

        narrative = normalize_text(narrative_val)
        if not narrative:
            continue

        amount = _parse_amount(amount_val)
        if amount < 2:
            continue

        date = pd.to_datetime(date_val, errors="coerce")
        date_str = date.strftime("%d.%m.%Y") if not pd.isna(date) else ""

        txn_name = normalize_text(row.get("_txn_name", "")) if txn_name_col else ""

        transactions.append(
            {
                "statement_tag": statement_tag,
                # Legacy key kept for backward compatibility
                "stmt_name": statement_tag,
                "sheet_name": sheet_name,
                "row_id": int(row_idx),
                "date_str": date_str,
                "amount": float(amount),
                "txn_name": txn_name,
                "narrative": narrative,
                "header_row_used": int(header_row),
            }
        )

    print(f"✅ [{statement_tag}] {len(transactions)} transactions loaded (header 0-based: {header_row - 1})")
    return transactions
