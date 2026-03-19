"""
app.py
------
Gradio web interface for the IPARD II Bank Reconciliation system.

Features
--------
- Upload both Excel files directly from the browser
- Configure sheet ranges and LLM provider (DeepSeek / Groq)
- Real-time progress logging
- Interactive results table with MATCHED / REVIEW / NO_MATCH breakdown
- Statistics dashboard
- One-click Excel report download
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import gradio as gr
import pandas as pd

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from src.app import build_ui

ui = build_ui()
ui.launch(server_name="0.0.0.0", server_port=7860)



# Ensure src/ is importable when running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from config import (
    DEEPSEEK_BASE_URL, DEEPSEEK_API_KEY, DEEPSEEK_MODEL,
    GROQ_BASE_URL, QWEN_MODEL,
    ModelSpec,
)
from io_applicants import read_applicants
from io_ipard2 import read_statement
from runner import run_reconciliation
from excel_out import write_excel
from config import FILTERED_TRANSACTION_NAMES


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROVIDERS = {
    "DeepSeek": {"base_url": DEEPSEEK_BASE_URL, "default_model": DEEPSEEK_MODEL},
    "Groq (Qwen)": {"base_url": GROQ_BASE_URL, "default_model": QWEN_MODEL},
}

_DECISION_COLORS = {
    "MATCH": "✅",
    "REVIEW": "⚠️",
    "NO_MATCH": "❌",
    "CONFLICT": "🔀",
    "UNMATCHED": "—",
}


# ---------------------------------------------------------------------------
# Core run function (called by Gradio)
# ---------------------------------------------------------------------------

def run_reconciliation_ui(
    applicants_file,
    ipard2_file,
    applicants_sheet: str,
    start_row: int,
    end_row: int,
    co_financing_sheet: str,
    transfer_sheet: str,
    provider_name: str,
    api_key: str,
    model_name: str,
    progress=gr.Progress(track_tqdm=True),
):
    """
    Main Gradio handler. Runs the full pipeline and returns UI-ready outputs.
    """
    logs: list[str] = []

    def log(msg: str) -> str:
        logs.append(msg)
        return "\n".join(logs)

    # ---- Validate inputs ----
    if applicants_file is None:
        return "❌ Please upload the Applicants Excel file.", None, None, None, None

    if ipard2_file is None:
        return "❌ Please upload the bank statement Excel file.", None, None, None, None

    if not api_key.strip():
        return "❌ API key is required.", None, None, None, None

    progress(0, desc="Loading files …")

    # ---- Load applicants ----
    try:
        log(f"📂 Loading applicants from sheet '{applicants_sheet}' rows {start_row}–{end_row} …")
        applicants = read_applicants(
            excel_path=applicants_file.name,
            sheet_name=applicants_sheet,
            start_row=int(start_row),
            end_row=int(end_row),
        )
        log(f"  ✅ {len(applicants)} applicants loaded.")
    except Exception as exc:
        return f"❌ Failed to load applicants: {exc}", None, None, None, None

    # ---- Load transactions ----
    try:
        log(f"📂 Loading co-financing sheet '{co_financing_sheet}' …")
        co_financing_txns = read_statement(
            excel_path=ipard2_file.name,
            sheet_name=co_financing_sheet,
            filtered_txn_names=FILTERED_TRANSACTION_NAMES,
            statement_tag="CO_FINANCING",
        )
        log(f"  ✅ {len(co_financing_txns)} co-financing transactions.")

        log(f"📂 Loading transfer sheet '{transfer_sheet}' …")
        transfer_txns = read_statement(
            excel_path=ipard2_file.name,
            sheet_name=transfer_sheet,
            filtered_txn_names=FILTERED_TRANSACTION_NAMES,
            statement_tag="TRANSFER",
        )
        log(f"  ✅ {len(transfer_txns)} transfer transactions.")
    except Exception as exc:
        return f"❌ Failed to load transactions: {exc}", None, None, None, None

    all_transactions = co_financing_txns + transfer_txns
    log(f"📊 Total transactions: {len(all_transactions)}")

    # ---- Build model spec ----
    provider_cfg = _PROVIDERS.get(provider_name, list(_PROVIDERS.values())[0])
    model_spec = ModelSpec(
        name=provider_name.lower().replace(" ", "_"),
        base_url=provider_cfg["base_url"],
        api_key=api_key.strip(),
        model=model_name.strip() or provider_cfg["default_model"],
    )

    # ---- Run pipeline ----
    progress(0.10, desc="Running Phase 1–3 (rule-based) …")
    log(f"\n🚀 Starting reconciliation with {model_spec.name} …")

    def progress_cb(msg: str, pct: int) -> None:
        nonlocal logs
        logs.append(msg)
        progress(pct / 100, desc=msg)

    try:
        decisions = run_reconciliation(
            model_spec=model_spec,
            applicants=applicants,
            all_transactions=all_transactions,
            progress_callback=progress_cb,
        )
    except Exception as exc:
        return f"❌ Pipeline error: {exc}", None, None, None, None

    log("\n✅ Pipeline complete.")
    progress(0.96, desc="Writing report …")

    # ---- Write Excel output ----
    out_dir = Path(tempfile.mkdtemp())
    out_path = out_dir / f"reconciliation_{model_spec.name}.xlsx"
    try:
        write_excel(
            out_path=out_path,
            model_name=model_spec.name,
            applicants=applicants,
            all_txns=all_transactions,
            decisions=decisions,
        )
        log(f"📄 Report saved: {out_path.name}")
    except Exception as exc:
        log(f"⚠️  Could not write Excel: {exc}")
        out_path = None

    # ---- Build display tables ----
    results_rows = []
    for app, dec in zip(applicants, decisions):
        if dec is None:
            verdict, confidence, reason, matched = "—", 0.0, "No decision", ""
        else:
            verdict = dec.get("decision", "REVIEW")
            confidence = dec.get("confidence", 0.0)
            reason = dec.get("reason", "")
            matched = ", ".join(dec.get("matched_ids", []))

        icon = _DECISION_COLORS.get(verdict, "")
        results_rows.append(
            {
                "Applicant": app.get("name", ""),
                "TC/VKN": app.get("tc_vkn", ""),
                "App No": app.get("application_no") or app.get("basvuru_no", ""),
                "Decision": f"{icon} {verdict}",
                "Confidence": f"{confidence:.0%}",
                "Reason": reason[:120] + ("…" if len(reason) > 120 else ""),
                "Matched IDs": matched,
            }
        )

    results_df = pd.DataFrame(results_rows)

    # ---- Statistics ----
    counts = results_df["Decision"].str.extract(r"([A-Z_]+)")[0].value_counts()
    stats_rows = [{"Metric": k, "Count": v} for k, v in counts.items()]
    stats_rows += [
        {"Metric": "Total applicants", "Count": len(applicants)},
        {"Metric": "Total transactions", "Count": len(all_transactions)},
    ]
    stats_df = pd.DataFrame(stats_rows)

    progress(1.0, desc="Done ✅")
    return "\n".join(logs), results_df, stats_df, str(out_path) if out_path else None


# ---------------------------------------------------------------------------
# Build Gradio interface
# ---------------------------------------------------------------------------

def build_ui() -> gr.Blocks:
    with gr.Blocks(
        title="Reconciliation",
        theme=gr.themes.Soft(primary_hue="blue"),
    ) as demo:

        gr.Markdown(
            """
# 🏦 Bank Reconciliation
**Hybrid rule + RAG + LLM pipeline** for matching grant applicants to bank transactions.

Upload both Excel files, configure settings, and click **Run Reconciliation**.
            """
        )

        with gr.Row():
            # ---- Left column: inputs ----
            with gr.Column(scale=1):
                gr.Markdown("### 📁 Input Files")
                applicants_file = gr.File(
                    label="Applicants Excel (.xls / .xlsx)",
                    file_types=[".xls", ".xlsx"],
                )
                ipard2_file = gr.File(
                    label="Bank Statement (.xls / .xlsx)",
                    file_types=[".xls", ".xlsx"],
                )

                gr.Markdown("### 📋 Sheet Configuration")
                with gr.Row():
                    applicants_sheet = gr.Textbox(label="Applicants sheet name", value="6406")
                    co_financing_sheet = gr.Textbox(
                        label="Co-financing sheet name", value="CO-FINANCING ACCOUNT"
                    )
                with gr.Row():
                    transfer_sheet = gr.Textbox(
                        label="Transfer sheet name", value="TRANSFER ACCOUNT"
                    )
                with gr.Row():
                    start_row = gr.Number(label="Applicants start row (1-based)", value=132, precision=0)
                    end_row = gr.Number(label="Applicants end row (1-based)", value=168, precision=0)

                gr.Markdown("### 🤖 LLM Provider (Phase 4)")
                provider_dropdown = gr.Dropdown(
                    choices=list(_PROVIDERS.keys()),
                    value="DeepSeek",
                    label="Provider",
                )
                api_key_input = gr.Textbox(
                    label="API Key",
                    type="password",
                    placeholder="sk-…",
                    value=DEEPSEEK_API_KEY,
                )
                model_input = gr.Textbox(
                    label="Model name (leave blank for provider default)",
                    value=DEEPSEEK_MODEL,
                    placeholder="deepseek-chat",
                )

                # Update default model name when provider changes
                def _on_provider_change(provider: str):
                    return _PROVIDERS[provider]["default_model"]

                provider_dropdown.change(
                    _on_provider_change, inputs=provider_dropdown, outputs=model_input
                )

                run_btn = gr.Button("▶ Run Reconciliation", variant="primary", size="lg")

            # ---- Right column: outputs ----
            with gr.Column(scale=2):
                gr.Markdown("### 📊 Results")

                with gr.Tabs():
                    with gr.Tab("Decisions"):
                        results_table = gr.DataFrame(
                            label="Per-Applicant Decisions",
                            interactive=False,
                            wrap=True,
                        )
                    with gr.Tab("Statistics"):
                        stats_table = gr.DataFrame(
                            label="Run Statistics",
                            interactive=False,
                        )
                    with gr.Tab("Log"):
                        log_output = gr.Textbox(
                            label="Pipeline log",
                            lines=25,
                            max_lines=60,
                            interactive=False,
                        )

                download_btn = gr.File(label="⬇ Download Excel Report", interactive=False)

        run_btn.click(
            fn=run_reconciliation_ui,
            inputs=[
                applicants_file,
                ipard2_file,
                applicants_sheet,
                start_row,
                end_row,
                co_financing_sheet,
                transfer_sheet,
                provider_dropdown,
                api_key_input,
                model_input,
            ],
            outputs=[log_output, results_table, stats_table, download_btn],
        )

    return demo


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ui = build_ui()
    ui.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
    )