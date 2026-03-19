---
title: Hybrid RAG Reconciliation
emoji: 🏦
colorFrom: blue
colorTo: green
sdk: docker
sdk_version: 4.36.0
app_file: app.py
pinned: false
---

🏦 IPARD II - LLM & RAG Hybrid Matching System
An intelligent reconciliation system that automatically matches bank transactions with applicants.

📋 Table of Contents
Features

Installation

Usage

Settings

Outputs

Troubleshooting

✨ Features
🤖 4-Stage Intelligent Matching
Phase 1: TR ID / Tax ID Matching (Most Reliable)

Automatic matching via ID number or tax registration number.

99% Reliability.

Phase 2: Application No. Matching (Highly Reliable)

Automatic matching via unique application numbers.

97% Reliability.

Phase 3: Secure Name/Company Matching (Reliable)

Token-based intelligent name matching.

Verification through rare word analysis.

88-90% Reliability.

Phase 4: LLM + RAG Matching (AI Powered)

Vector-based semantic search (RAG).

LLM-driven decision making (DeepSeek, Qwen, GPT-OSS).

Designed for complex or ambiguous cases.

🎯 Automated Features
✅ Automatic detection of Excel headers and column positions.

✅ Turkish character normalization.

✅ Transaction filtering (virement, interest accruals, etc.).

✅ Comparative results using 3 different LLM models.

✅ Detailed Excel reporting.

🚀 Installation
1. Requirements
Bash
Python 3.8+
2. Create Virtual Environment
Bash
cd C:\Users\deniz\Desktop\MUTABAKAT\Hybrid_Approach
python -m venv myenv
myenv\Scripts\activate
3. Install Dependencies
Bash
pip install pandas openpyxl xlrd chromadb sentence-transformers requests python-dotenv
4. Configure API Keys
Create (or edit) the .env file:

Code snippet
# LLM APIs
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_API_KEY=your-deepseek-api-key
DEEPSEEK_MODEL=deepseek-chat

GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_API_KEY=your-groq-api-key

QWEN_MODEL=qwen/qwen3-32b
GPTOSS_MODEL=openai/gpt-oss-20b

# RAG Settings
EMBED_MODEL=intfloat/multilingual-e5-base
RAG_TOPK=12
⚠️ IMPORTANT: Never upload your API keys to GitHub!

📝 Usage
1. Set File Paths
Open src/config.py and edit the file paths at the very top:

Python
# =========================================================================
# 📁 FILE PATHS - Change them easily here!
# =========================================================================

APPLICANTS_XLS = r"C:\Users\deniz\Desktop\MUTABAKAT\6-JUNE\IPARD II\6406_Debtor_Ledger_Reconciliation_JUNE_2023.xls"
IPARD2_XLS = r"C:\Users\deniz\Desktop\MUTABAKAT\6-JUNE\IPARD II\IPARD2.xls"

# =========================================================================
💡 Tip: To process a different month, just change these two lines (e.g., 6-JUNE → 7-JULY).

2. Set Applicant Row Range
In the same src/config.py file:

Python
# Sheet Settings
APPLICANTS_SHEET = "6406"
APPLICANTS_START_ROW = 81    # 👈 Start row
APPLICANTS_END_ROW = 113      # 👈 End row
📌 Note: Use the actual row numbers as seen in Excel (starting from 1).

3. Run the Program
Bash
cd src
python runner.py
⚙️ Settings
📂 File Structure
Plaintext
Hybrid_Approach/
├── src/
│   ├── runner.py          # Main entry point
│   ├── config.py          # 👈 ALL SETTINGS ARE HERE
│   ├── io_applicants.py   # Applicant reading logic
│   ├── io_ipard2.py       # Bank statement reading logic
│   ├── rule_candidates.py # Rule-based matching
│   ├── rag_store.py       # Vector database
│   ├── llm_client.py      # LLM API client
│   ├── hybrid_matcher.py  # LLM decision logic
│   ├── excel_out.py       # Excel output generation
│   ├── text_norm.py       # Text normalization
│   ├── token_stats.py     # Token statistics
│   └── filters.py         # Transaction filters
├── .env                   # 👈 API KEYS HERE
├── indexes/               # RAG vector indices (auto-generated)
└── llm_rag_hybrid/        # 👈 OUTPUT FILES HERE
📊 Outputs
📋 Excel Sheets
Each output file contains 5 sheets:

MATCHED: Successfully matched records.

REVIEW: Records requiring manual inspection (CONFLICT, NO_MATCH, or low confidence).

UNMATCHED_APPLICANTS: Applicants with no corresponding transaction.

UNMATCHED_TXNS: Transactions with no corresponding applicant.

STATS: Summary statistics (Total counts, match rates, etc.).

🔧 Troubleshooting
❌ "Header not found" Error
Cause: The system cannot find the header row in the Excel file.
Solution: Ensure the following columns exist exactly: TRANSACTION DATE, AMOUNT, NARRATIVE, TRANSACTION NAME.

❌ API Error (429, 500, etc.)
Cause: LLM API issues or rate limits.
Solution: Check .env keys. llm_client.py includes automatic retries; if it persists, check your Groq/DeepSeek quota.

❌ ChromaDB Error
Cause: Corrupted vector database index.
Solution: Delete the indexes/chroma_txns folder; the system will regenerate it on the next run.

🎓 How It Works
Normalization: Converts Turkish characters (ş→s, ğ→g) and cleans whitespace.

Rule-Based (Phases 1-3): Immediately matches high-confidence data like ID numbers or exact name tokens.

RAG (Retrieval-Augmented Generation): For remaining items, the system generates a query and retrieves the top 12 most similar transactions from the vector database.

LLM Decision: The AI analyzes the candidate list and makes a final determination (MATCH/REVIEW/NO_MATCH) with a confidence score.

🔄 Versioning
v1.0 - January 2025

First stable release.

Automated header/column detection.

Multi-LLM support.

4-stage hybrid matching pipeline.
