#!/usr/bin/env python3
"""
Demo script for CSV Insights Generator.
Runs the full pipeline (parse -> chart selection -> insight generation) on a sample sales CSV.
Requires ANTHROPIC_API_KEY in .env file.
"""

import io
import os
import sys
import logging

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# Build a realistic sample sales CSV in-memory
# ---------------------------------------------------------------------------
SAMPLE_CSV = """date,region,product,units_sold,revenue,cost
2024-01-01,North,Widget A,120,4800,2400
2024-01-01,South,Widget B,85,5100,2550
2024-01-01,East,Widget A,200,8000,4000
2024-01-01,West,Widget C,60,1800,900
2024-02-01,North,Widget B,140,8400,4200
2024-02-01,South,Widget A,95,3800,1900
2024-02-01,East,Widget C,180,5400,2700
2024-02-01,West,Widget A,220,8800,4400
2024-03-01,North,Widget A,160,6400,3200
2024-03-01,South,Widget C,110,3300,1650
2024-03-01,East,Widget B,145,8700,4350
2024-03-01,West,Widget B,90,5400,2700
2024-04-01,North,Widget C,75,2250,1125
2024-04-01,South,Widget A,130,5200,2600
2024-04-01,East,Widget A,210,8400,4200
2024-04-01,West,Widget C,55,1650,825
2024-05-01,North,Widget B,155,9300,4650
2024-05-01,South,Widget B,100,6000,3000
2024-05-01,East,Widget C,170,5100,2550
2024-05-01,West,Widget A,240,9600,4800
"""


def main():
    print("=" * 60)
    print(" CSV Insights Generator — Demo")
    print("=" * 60)
    print("Sample input: 20-row sales CSV with columns:")
    print("  date, region, product, units_sold, revenue, cost")
    print()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to .env and retry.")
        sys.exit(1)

    csv_bytes = SAMPLE_CSV.encode("utf-8")

    # --- Step 1: Parse CSV ---
    from src.csv_parser import parse_csv
    print("[1/4] Parsing CSV...")
    parse_result = parse_csv(csv_bytes)
    if parse_result["error"]:
        print(f"ERROR during parsing: {parse_result['error']}")
        sys.exit(1)

    df = parse_result["dataframe"]
    column_profiles = parse_result["column_profiles"]
    print(f"      Parsed {parse_result['row_count']} rows, {len(column_profiles)} columns.")
    for p in column_profiles:
        print(f"      - {p['name']}: {p['inferred_type']}")
    print()

    # --- Step 2: Select chart specs ---
    from src.chart_engine import select_chart_specs, render_charts
    print("[2/4] Selecting chart specs...")
    chart_result = select_chart_specs(column_profiles)
    chart_specs = chart_result["chart_specs"]
    print(f"      {chart_result['count']} chart(s) selected:")
    for spec in chart_specs:
        print(f"      - [{spec['chart_type'].upper()}] {spec['title']}")
    print()

    # --- Step 3: Render charts (validate only, no display in CLI) ---
    print("[3/4] Building Plotly figures...")
    render_result = render_charts(chart_specs, df)
    print(f"      {len(render_result['figures'])} figure(s) built successfully.")
    if render_result["errors"]:
        for err in render_result["errors"]:
            print(f"      WARNING: {err['reason']}")
    print()

    # --- Step 4: Generate insights ---
    from src.insight_generator import build_insight_prompt, generate_insights, validate_summary_columns
    print("[4/4] Generating AI insights (calling Claude API)...")
    sample_rows = df.head(20).to_dict(orient="records")
    prompt_payload = build_insight_prompt(column_profiles, sample_rows)

    if prompt_payload.get("error"):
        print(f"ERROR building prompt: {prompt_payload['error']}")
        sys.exit(1)

    print(f"      Prompt built. Rows included: {prompt_payload['rows_included']}, "
          f"estimated tokens: {prompt_payload['estimated_token_count']}")

    insight_result = generate_insights(prompt_payload, api_key)
    if insight_result["error"]:
        print(f"ERROR from AI: {insight_result['error']}")
        sys.exit(1)

    summary = validate_summary_columns(insight_result["summary"], column_profiles)

    print()
    print("=" * 60)
    print(" AI-Generated Insights")
    print("=" * 60)
    print(summary)
    print()
    print("Demo complete. Run 'streamlit run app.py' to launch the full web UI.")


if __name__ == "__main__":
    main()
