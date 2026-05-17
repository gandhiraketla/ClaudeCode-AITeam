"""
demo.py — CSV Insights Generator: Standalone Demo

Runs the full analysis pipeline on a synthetic sales CSV:
  1. Parses and profiles columns
  2. Selects chart specifications
  3. Builds insight prompt
  4. Calls Claude API for AI-generated insights

Prints all results to stdout. No user interaction required.
Requires ANTHROPIC_API_KEY in .env or environment.
"""

from __future__ import annotations

import io
import os
import sys
import textwrap
from pathlib import Path

# Load .env before importing project modules
from dotenv import load_dotenv
load_dotenv()

from src.csv_parser import parse_csv
from src.chart_engine import select_chart_specs, render_charts
from src.insight_generator import build_insight_prompt, generate_insights

# ── Synthetic sales CSV ────────────────────────────────────────────────────────
# Represents a realistic monthly sales report a business analyst might upload.
DEMO_CSV = """\
month,region,product,units_sold,revenue,returns
2024-01-01,North,Widget A,320,48000,12
2024-01-01,South,Widget B,210,31500,8
2024-01-01,East,Widget A,415,62250,15
2024-01-01,West,Widget C,180,27000,5
2024-02-01,North,Widget B,295,44250,11
2024-02-01,South,Widget A,330,49500,9
2024-02-01,East,Widget C,260,39000,7
2024-02-01,West,Widget A,390,58500,14
2024-03-01,North,Widget C,310,46500,10
2024-03-01,South,Widget B,275,41250,6
2024-03-01,East,Widget A,500,75000,18
2024-03-01,West,Widget B,220,33000,4
2024-04-01,North,Widget A,355,53250,13
2024-04-01,South,Widget C,290,43500,9
2024-04-01,East,Widget B,310,46500,11
2024-04-01,West,Widget A,430,64500,16
2024-05-01,North,Widget B,340,51000,12
2024-05-01,South,Widget A,360,54000,10
2024-05-01,East,Widget C,275,41250,8
2024-05-01,West,Widget B,250,37500,7
"""

DEMO_FILENAME = "sample_sales_report.csv"
AGENT_NAME = "CSV Insights Generator"


def _header(title: str) -> str:
    bar = "=" * 60
    return f"\n{bar}\n  {title}\n{bar}"


def _section(title: str) -> str:
    return f"\n--- {title} ---"


def main() -> None:
    print(_header(f"{AGENT_NAME} — Demo Run"))
    print(f"\nDemo input : {DEMO_FILENAME}")
    print(f"Rows       : {DEMO_CSV.strip().count(chr(10))} data rows")
    print(f"Columns    : month, region, product, units_sold, revenue, returns")
    print(f"AI model   : claude-3-haiku-20240307")

    # ── API key check ──────────────────────────────────────────────────────────
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print(
            "\n[ERROR] ANTHROPIC_API_KEY is not set.\n"
            "  Copy .env.example to .env and add your key:\n"
            "    cp .env.example .env\n"
            "  Then re-run: python demo.py",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Step 1: Parse CSV ──────────────────────────────────────────────────────
    print(_section("Step 1: Parsing CSV"))
    csv_bytes = DEMO_CSV.encode("utf-8")
    parse_result = parse_csv(csv_bytes)

    if parse_result["error"]:
        print(f"[PARSE ERROR] {parse_result['error']}", file=sys.stderr)
        sys.exit(1)

    df = parse_result["dataframe"]
    column_profiles = parse_result["column_profiles"]
    row_count = parse_result["row_count"]

    print(f"  Rows parsed   : {row_count}")
    print(f"  Columns found : {len(column_profiles)}")
    for p in column_profiles:
        extras = ""
        if p["inferred_type"] == "numeric":
            extras = f"  min={p['min']}  max={p['max']}"
        elif p["inferred_type"] == "categorical":
            extras = f"  top_values={p['top_values']}"
        elif p["inferred_type"] == "date":
            extras = f"  earliest={p['min']}  latest={p['max']}"
        print(f"    {p['name']:<20} [{p['inferred_type']:<11}]  nunique={p['nunique']}{extras}")

    # ── Step 2: Select chart specs ─────────────────────────────────────────────
    print(_section("Step 2: Selecting Chart Specifications"))
    chart_result = select_chart_specs(column_profiles)
    chart_specs = chart_result["chart_specs"]

    if chart_result["count"] == 0:
        print("  [WARNING] No chart specs generated — no numeric columns found.")
    else:
        print(f"  {chart_result['count']} chart(s) selected:")
        for i, spec in enumerate(chart_specs, 1):
            y_info = f"  y={spec['y_column']}" if spec.get("y_column") else ""
            print(f"    {i}. [{spec['chart_type'].upper():<4}]  x={spec['x_column']}{y_info}  → \"{spec['title']}\"")

    # ── Step 3: Render charts (in-memory only for demo) ────────────────────────
    print(_section("Step 3: Rendering Charts (in-memory)"))
    render_result = render_charts(chart_specs, df)
    figures = render_result["figures"]
    render_errors = render_result["errors"]

    print(f"  {len(figures)} chart(s) rendered successfully.")
    if render_errors:
        for err in render_errors:
            print(f"  [RENDER SKIP] {err.get('reason', 'unknown error')}")

    # ── Step 4: Build insight prompt ───────────────────────────────────────────
    print(_section("Step 4: Building Insight Prompt"))
    sample_rows = df.head(20).to_dict(orient="records")
    prompt_payload = build_insight_prompt(
        column_profiles=column_profiles,
        raw_dataframe_sample=sample_rows,
    )
    prompt_payload["column_profiles"] = column_profiles  # for column confabulation check

    if prompt_payload["error"]:
        print(f"  [PROMPT ERROR] {prompt_payload['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"  Estimated tokens : {prompt_payload['estimated_token_count']}")
    print(f"  Sample rows sent : {prompt_payload['rows_included']}")

    # ── Step 5: Generate insights ──────────────────────────────────────────────
    print(_section("Step 5: Calling Claude API for Insights"))
    print("  Sending request to claude-3-haiku-20240307…")

    insight_result = generate_insights(prompt_payload)

    if insight_result["error"]:
        print(f"\n[INSIGHT ERROR] {insight_result['error']}", file=sys.stderr)
        print(
            "\nNote: Charts were generated successfully and would be shown in the\n"
            "Streamlit UI even if insight generation fails."
        )
        sys.exit(1)

    # ── Results ────────────────────────────────────────────────────────────────
    bar = "=" * 60
    print(f"\n{bar}")
    print("  RESULTS")
    print(bar)

    print(f"\n📈 Charts Generated ({len(figures)}):")
    for fig_entry in figures:
        print(f"  • [{fig_entry['chart_type'].upper()}] {fig_entry['title']}")

    print("\n💡 AI-Generated Key Insights:")
    print()
    # Wrap each line for clean terminal output
    for line in insight_result["summary"].splitlines():
        if line.strip():
            wrapped = textwrap.fill(line.strip(), width=70, initial_indent="  ", subsequent_indent="    ")
            print(wrapped)
        else:
            print()

    print(f"\n{bar}")
    print("  Demo complete. Run `streamlit run app.py` to use the full UI.")
    print(bar)


if __name__ == "__main__":
    main()