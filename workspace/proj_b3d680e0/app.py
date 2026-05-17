"""
app.py — CSV Insights Generator
Streamlit single-page application entry point.

Orchestrates:
  1. CSV upload and validation
  2. Column profiling via csv_parser
  3. Chart specification and rendering via chart_engine
  4. AI insight generation via insight_generator
  5. Results rendering (charts + summary) in-browser
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.csv_parser import parse_csv
from src.chart_engine import select_chart_specs, render_charts
from src.insight_generator import build_insight_prompt, generate_insights

# ── Bootstrap ─────────────────────────────────────────────────────────────────
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
API_COOLDOWN_SECONDS = 10  # minimum seconds between successive API calls

# ── Streamlit page config ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="CSV Insights Generator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ── Session state initialisation ──────────────────────────────────────────────
def _init_session_state() -> None:
    defaults = {
        "last_filename": None,
        "column_profiles": None,
        "chart_specs": None,
        "figures": None,
        "insight_summary": None,
        "error_message": None,
        "insight_generated": False,
        "last_api_call_time": 0.0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _reset_session_state() -> None:
    """Clear all analysis state for a new upload."""
    st.session_state.last_filename = None
    st.session_state.column_profiles = None
    st.session_state.chart_specs = None
    st.session_state.figures = None
    st.session_state.insight_summary = None
    st.session_state.error_message = None
    st.session_state.insight_generated = False
    # Deliberately preserve last_api_call_time across uploads for rate-limiting


# ── Main pipeline ──────────────────────────────────────────────────────────────
def _run_pipeline(uploaded_file) -> None:
    """
    Execute the full analysis pipeline for an uploaded CSV file.
    All results are stored in st.session_state.
    """
    filename = uploaded_file.name

    # ── Cooldown guard: prevent rapid successive API calls ────────────────────
    now = time.time()
    elapsed = now - st.session_state.last_api_call_time
    if st.session_state.last_api_call_time > 0 and elapsed < API_COOLDOWN_SECONDS:
        remaining = int(API_COOLDOWN_SECONDS - elapsed) + 1
        st.session_state.error_message = (
            f"Please wait {remaining} second(s) before uploading a new file."
        )
        return

    # ── Skip re-processing if same file already analysed ─────────────────────
    if (
        st.session_state.last_filename == filename
        and st.session_state.insight_generated
        and st.session_state.figures is not None
    ):
        return

    _reset_session_state()
    st.session_state.last_filename = filename

    with st.spinner("Analysing your CSV — this may take up to 30 seconds…"):

        # Step 1: Read bytes
        csv_bytes = uploaded_file.read()

        # Step 2: Parse and profile CSV
        parse_result = parse_csv(csv_bytes, max_size_bytes=MAX_FILE_SIZE_BYTES)
        if parse_result["error"]:
            st.session_state.error_message = parse_result["error"]
            return

        df = parse_result["dataframe"]
        column_profiles = parse_result["column_profiles"]
        row_count = parse_result["row_count"]
        st.session_state.column_profiles = column_profiles

        # Step 3: Select chart specs
        chart_result = select_chart_specs(column_profiles)
        chart_specs = chart_result["chart_specs"]
        st.session_state.chart_specs = chart_specs

        if chart_result["count"] == 0:
            st.session_state.error_message = (
                "No numeric columns found — charts cannot be generated. "
                "Insight generation will still be attempted."
            )

        # Step 4: Render charts (independent of AI call)
        render_result = render_charts(chart_specs, df)
        st.session_state.figures = render_result["figures"]

        if render_result["errors"]:
            for err in render_result["errors"]:
                logger.warning("Chart render error: %s", err.get("reason"))

        # Step 5: Build insight prompt
        sample_rows = df.head(20).to_dict(orient="records")
        prompt_payload = build_insight_prompt(
            column_profiles=column_profiles,
            raw_dataframe_sample=sample_rows,
        )
        # Pass column_profiles into payload so post-processor can validate column refs
        prompt_payload["column_profiles"] = column_profiles

        if prompt_payload.get("error"):
            st.session_state.error_message = (
                (st.session_state.error_message or "") + "\n" + prompt_payload["error"]
            ).strip()
            # Charts may still be available; do not abort entirely
            return

        # Step 6: Generate insights (single API call per upload)
        if not st.session_state.insight_generated:
            st.session_state.last_api_call_time = time.time()
            insight_result = generate_insights(prompt_payload)
            st.session_state.insight_generated = True

            if insight_result["error"]:
                st.session_state.error_message = insight_result["error"]
            else:
                st.session_state.insight_summary = insight_result["summary"]

        logger.info(
            "Pipeline complete for '%s': %d rows, %d charts, insights=%s",
            filename,
            row_count,
            len(st.session_state.figures or []),
            "yes" if st.session_state.insight_summary else "no",
        )


# ── Rendering helpers ──────────────────────────────────────────────────────────
def _render_charts(figures: list) -> None:
    """Render Plotly figures in a responsive two-column grid."""
    if not figures:
        st.info("No charts could be generated for this dataset.")
        return

    st.subheader("📈 Charts")
    cols = st.columns(2)
    for idx, fig_entry in enumerate(figures):
        with cols[idx % 2]:
            st.plotly_chart(
                fig_entry["figure"],
                use_container_width=True,
                key=f"chart_{idx}",
            )


def _render_insights(summary: str) -> None:
    """Render the AI-generated insight summary."""
    st.subheader("💡 Key Insights")
    st.markdown(summary)


def _render_data_overview(column_profiles: list) -> None:
    """Render a collapsible column profile table."""
    with st.expander("📋 Column Overview", expanded=False):
        rows = []
        for p in column_profiles:
            rows.append({
                "Column": p["name"],
                "Type": p["inferred_type"],
                "Unique Values": p["nunique"],
                "Null Count": p["null_count"],
            })
        st.table(rows)


# ── App layout ─────────────────────────────────────────────────────────────────
def main() -> None:
    _init_session_state()

    # ── Header ────────────────────────────────────────────────────────────────
    st.title("📊 CSV Insights Generator")
    st.caption(
        "Upload a sales CSV and get instant charts and AI-powered insights — "
        "no configuration required."
    )

    st.divider()

    # ── File uploader ──────────────────────────────────────────────────────────
    uploaded_file = st.file_uploader(
        label="Upload your CSV file (max 10 MB)",
        type=["csv"],
        accept_multiple_files=False,
        help="Supported format: plain-text CSV with a header row.",
    )

    if uploaded_file is not None:
        _run_pipeline(uploaded_file)

    # ── Error display ──────────────────────────────────────────────────────────
    if st.session_state.error_message:
        # Display insight-specific errors differently from hard failures
        if st.session_state.figures:
            st.warning(st.session_state.error_message)
        else:
            st.error(st.session_state.error_message)

    # ── No-numeric-columns warning ─────────────────────────────────────────────
    if (
        st.session_state.column_profiles is not None
        and st.session_state.chart_specs is not None
        and len(st.session_state.chart_specs) == 0
        and not st.session_state.error_message
    ):
        st.warning(
            "No numeric columns were detected — charts cannot be generated. "
            "Insights are based on schema and categorical data only."
        )

    # ── Results ────────────────────────────────────────────────────────────────
    if st.session_state.figures is not None or st.session_state.insight_summary:
        st.divider()

        # Column overview
        if st.session_state.column_profiles:
            _render_data_overview(st.session_state.column_profiles)

        # Charts and insights side by side when both available
        if st.session_state.figures and st.session_state.insight_summary:
            chart_col, insight_col = st.columns([3, 2], gap="large")
            with chart_col:
                _render_charts(st.session_state.figures)
            with insight_col:
                _render_insights(st.session_state.insight_summary)
        elif st.session_state.figures:
            _render_charts(st.session_state.figures)
        elif st.session_state.insight_summary:
            _render_insights(st.session_state.insight_summary)

    # ── Footer ─────────────────────────────────────────────────────────────────
    st.divider()
    st.caption(
        "CSV data is sent to the Anthropic API for insight generation. "
        "Do not upload files containing sensitive personal data."
    )


if __name__ == "__main__":
    main()