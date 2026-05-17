import os
import logging
import streamlit as st
from dotenv import load_dotenv

from src.csv_parser import parse_csv
from src.chart_engine import select_chart_specs, render_charts
from src.insight_generator import build_insight_prompt, generate_insights, validate_summary_columns

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="CSV Insights Generator", page_icon="📊", layout="wide")


def get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return key


def reset_session_state():
    for key in ["column_profiles", "chart_specs", "figures", "insight_summary", "error_message", "insight_generated", "dataframe"]:
        if key in st.session_state:
            del st.session_state[key]


def run_pipeline(csv_bytes: bytes, filename: str, api_key: str):
    # Step 1: Parse CSV
    parse_result = parse_csv(csv_bytes)
    if parse_result["error"]:
        st.session_state["error_message"] = parse_result["error"]
        return

    if parse_result["row_count"] == 0:
        st.session_state["error_message"] = "The uploaded file appears to be empty — please upload a CSV with at least one data row."
        return

    df = parse_result["dataframe"]
    column_profiles = parse_result["column_profiles"]
    st.session_state["column_profiles"] = column_profiles
    st.session_state["dataframe"] = df

    # Step 2: Select chart specs
    chart_result = select_chart_specs(column_profiles)
    chart_specs = chart_result["chart_specs"]
    st.session_state["chart_specs"] = chart_specs

    numeric_cols = [p for p in column_profiles if p["inferred_type"] == "numeric"]
    if not numeric_cols:
        st.warning("No numeric columns found — charts cannot be generated. Proceeding with insight generation only.")

    # Step 3: Render charts
    render_result = render_charts(chart_specs, df)
    st.session_state["figures"] = render_result["figures"]
    for err in render_result["errors"]:
        logger.warning("Chart render error: %s", err["reason"])

    # Step 4: Generate insights (once per upload)
    if not st.session_state.get("insight_generated", False):
        sample_rows = df.head(20).to_dict(orient="records")
        prompt_payload = build_insight_prompt(column_profiles, sample_rows)

        if prompt_payload.get("error"):
            st.session_state["error_message"] = prompt_payload["error"]
            st.session_state["insight_summary"] = ""
        else:
            insight_result = generate_insights(prompt_payload, api_key)
            st.session_state["insight_generated"] = True
            if insight_result["error"]:
                st.session_state["insight_summary"] = ""
                st.session_state["error_message"] = f"Insight generation failed — {insight_result['error']} Charts are still available."
            else:
                summary = validate_summary_columns(insight_result["summary"], column_profiles)
                st.session_state["insight_summary"] = summary


def main():
    st.title("📊 CSV Insights Generator")
    st.caption("Upload a sales CSV to automatically generate charts and AI-powered insights.")

    api_key = get_api_key()
    if not api_key:
        st.error("ANTHROPIC_API_KEY is not set. Please add it to your .env file and restart the app.")
        st.stop()

    uploaded_file = st.file_uploader(
        "Upload your CSV file (max 10MB)",
        type=["csv"],
        help="Accepts UTF-8 encoded CSV files up to 10MB."
    )

    if uploaded_file is not None:
        last_filename = st.session_state.get("last_filename", "")
        if uploaded_file.name != last_filename:
            reset_session_state()
            st.session_state["last_filename"] = uploaded_file.name

            csv_bytes = uploaded_file.read()
            with st.spinner("Analyzing your data — this may take up to 30 seconds..."):
                run_pipeline(csv_bytes, uploaded_file.name, api_key)

    # Render results
    error_msg = st.session_state.get("error_message", "")
    if error_msg:
        st.error(error_msg)

    figures = st.session_state.get("figures", [])
    insight_summary = st.session_state.get("insight_summary", "")

    if figures or insight_summary:
        chart_col, insight_col = st.columns([3, 2])

        with chart_col:
            st.subheader("Charts")
            if figures:
                for fig_data in figures:
                    st.plotly_chart(fig_data["fig"], use_container_width=True)
            else:
                st.info("No charts could be generated for this dataset.")

        with insight_col:
            st.subheader("Key Insights")
            if insight_summary:
                st.markdown(insight_summary)
            elif not error_msg:
                st.info("Insights are being generated...")

    elif uploaded_file is None:
        st.info("Upload a CSV file above to get started.")


if __name__ == "__main__":
    main()
