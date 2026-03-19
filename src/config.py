from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Input file paths (override via environment variables or UI upload)
# ---------------------------------------------------------------------------
APPLICANTS_XLS: str = os.getenv("Debtor Defence. Debt Record. Reconciliation.xls", "")
BANK: str = os.getenv("Bank.xls", "")

# ---------------------------------------------------------------------------
# Sheet configuration
# ---------------------------------------------------------------------------
APPLICANTS_SHEET: str = os.getenv("APPLICANTS_SHEET", "6406")
APPLICANTS_START_ROW: int = int(os.getenv("APPLICANTS_START_ROW", "107"))
APPLICANTS_END_ROW: int = int(os.getenv("APPLICANTS_END_ROW", "154"))

CO_FINANCING_SHEET: str = os.getenv("CO_FINANCING_SHEET", "CO-FINANCING ACCOUNT")
TRANSFER_SHEET: str = os.getenv("TRANSFER_SHEET", "TRANSFER ACCOUNT")

# ---------------------------------------------------------------------------
# Transaction name filter list
# Transactions with these names are excluded before matching.
# ---------------------------------------------------------------------------
FILTERED_TRANSACTION_NAMES: list[str] = [
    "Remittance Buying Foreign Currency",
    "Remittance Selling Foreign Currency",
    "EFT to Account",
    "Virement",
    "Deposit Interest Accrual",
    "Virement Cancel",
]

# ---------------------------------------------------------------------------
# RAG / embedding configuration
# ---------------------------------------------------------------------------
EMBED_MODEL: str = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-base")
CHROMA_DIR: str = str((BASE_DIR / "indexes" / "chroma_txns").resolve())
RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "12"))

# ---------------------------------------------------------------------------
# LLM providers — loaded exclusively from environment variables
# ---------------------------------------------------------------------------
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
QWEN_MODEL: str = os.getenv("QWEN_MODEL", "qwen/qwen3-32b")

# ---------------------------------------------------------------------------
# Output configuration
# ---------------------------------------------------------------------------
OUTPUT_DIR: Path = Path(
    os.getenv("OUTPUT_DIR", str(BASE_DIR / "outputs"))
).resolve()

OUTPUT_PREFIX: str = os.getenv("OUTPUT_PREFIX", "reconciliation_result")


# ---------------------------------------------------------------------------
# Model specification dataclass
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ModelSpec:
    """Immutable specification for a single LLM provider."""

    name: str
    base_url: str
    api_key: str
    model: str

    def __str__(self) -> str:
        return f"ModelSpec(name={self.name!r}, model={self.model!r})"
