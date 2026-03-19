"""
io_applicants.py
----------------
Reads the applicant list from the reconciliation Excel workbook.

Expected sheet layout (no header row):
    Column A – Full name
    Column B – TC identity number or tax registration number (VKN)
    Column C – IPARD application number
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd

from text_norm import normalize_text, normalize_digits, normalize_application_number


def read_applicants(
    excel_path: str,
    sheet_name: str,
    start_row: int,
    end_row: int,
) -> List[Dict]:
    """
    Load applicant records from a fixed-layout Excel sheet.

    Args:
        excel_path: Absolute path to the source ``.xls`` / ``.xlsx`` file.
        sheet_name: Worksheet name (e.g. ``"6406"``).
        start_row: 1-based first data row (inclusive).
        end_row:   1-based last  data row (inclusive).

    Returns:
        List of applicant dicts with keys:
        ``name``, ``tc_vkn``, ``application_no``, ``is_person``, ``source_row``.
    """
    n_rows = end_row - start_row + 1
    df = pd.read_excel(
        excel_path,
        sheet_name=sheet_name,
        usecols="A:C",
        skiprows=start_row - 1,
        nrows=n_rows,
        header=None,
        names=["name", "tc_vkn", "application_no"],
        engine="xlrd",
    )

    df = df.dropna(subset=["name"])

    applicants: List[Dict] = []
    for idx, row in df.iterrows():
        name = normalize_text(row.get("name"))
        tc_vkn = normalize_digits(row.get("tc_vkn"))
        application_no = normalize_application_number(row.get("application_no"))

        # Turkish TC numbers are exactly 11 digits; VKN numbers are 10 digits.
        is_person = len(tc_vkn) == 11

        applicants.append(
            {
                "name": name,
                "tc_vkn": tc_vkn,
                "application_no": application_no,
                # Legacy key kept for backward compatibility with rule_candidates
                "basvuru_no": application_no,
                "is_person": is_person,
                "source_row": int(start_row + idx),
            }
        )

    print(f"✅ Applicants loaded: {len(applicants)} | rows {start_row}–{end_row}")
    return applicants


# Legacy alias
read_applicants_6406 = read_applicants
