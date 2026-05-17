import json
import logging
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

MAX_COLUMNS_FOR_ANALYSIS = 50
DEFAULT_MAX_PROMPT_TOKENS = 3000
DEFAULT_MAX_RESPONSE_TOKENS = 1024
CHARS_PER_TOKEN_ESTIMATE = 4


def build_insight_prompt(
    column_profiles: list,
    raw_dataframe_sample: list,
    max_tokens_budget: int = DEFAULT_MAX_PROMPT_TOKENS,
) -> dict:
    """
    Construct the structured prompt payload for the Claude API call.
    Returns: {system_prompt_sections, user_prompt_body, estimated_token_count, rows_included, error}
    """
    if len(column_profiles) > MAX_COLUMNS_FOR_ANALYSIS:
        return {
            "system_prompt_sections": [],
            "user_prompt_body": "",
            "estimated_token_count": 0,
            "rows_included": 0,
            "error": "CSV has too many columns to analyze — reduce to under 50 columns.",
        }

    system_prompt_sections = [
        "You are a data analyst producing insights for non-technical business analysts.",
        (
            "Your response must contain exactly 3 to 5 numbered observations. "
            "Each observation must be a single plain-English sentence. "
            "Do not use bullet points, markdown headers, or technical jargon."
        ),
        (
            "Constraints: Do not invent data not present in the sample. "
            "Do not reference column names in a way the user would not understand. "
            "If the sample is too small to draw conclusions, say so explicitly."
        ),
    ]

    # Build metadata block
    meta_lines = ["Dataset Overview:"]
    for p in column_profiles:
        null_info = f", {p['null_count']} nulls" if p["null_count"] > 0 else ""
        meta_lines.append(f"  - {p['name']} ({p['inferred_type']}{null_info})")
    metadata_block = "\n".join(meta_lines)

    # Build stats block
    stat_lines = ["Statistical Summary:"]
    for p in column_profiles:
        if p["inferred_type"] == "numeric":
            stat_lines.append(
                f"  - {p['name']}: min={p['min']}, max={p['max']}, unique_values={p['nunique']}"
            )
        elif p["inferred_type"] == "categorical" and p["top_values"]:
            top = ", ".join(str(v) for v in p["top_values"][:5])
            stat_lines.append(f"  - {p['name']}: top values = [{top}]")
    stats_block = "\n".join(stat_lines)

    task_instruction = (
        "Task: Identify 3 to 5 key insights from this data. "
        "Cover trends, outliers, and top or bottom performers where applicable."
    )

    # Estimate base token budget
    base_body = metadata_block + "\n\n" + stats_block + "\n\n" + task_instruction
    base_tokens = len(base_body) // CHARS_PER_TOKEN_ESTIMATE

    if base_tokens > max_tokens_budget:
        return {
            "system_prompt_sections": system_prompt_sections,
            "user_prompt_body": "",
            "estimated_token_count": base_tokens,
            "rows_included": 0,
            "error": "CSV has too many columns to analyze — reduce to under 50 columns.",
        }

    # Fit as many sample rows as possible within budget
    rows_included = 0
    sample_block = ""
    remaining_budget = max_tokens_budget - base_tokens

    for i, row in enumerate(raw_dataframe_sample[:20]):
        row_str = ", ".join(f"{k}={v}" for k, v in row.items())
        row_tokens = len(row_str) // CHARS_PER_TOKEN_ESTIMATE + 1
        if row_tokens > remaining_budget:
            break
        sample_block += row_str + "\n"
        remaining_budget -= row_tokens
        rows_included += 1

    sample_section = ""
    if rows_included > 0:
        total_rows = len(raw_dataframe_sample)
        sample_section = (
            f"Sample Rows ({rows_included} of {total_rows} total):\n" + sample_block
        )

    user_prompt_body = metadata_block
    user_prompt_body += "\n\n" + stats_block
    if sample_section:
        user_prompt_body += "\n\n" + sample_section
    user_prompt_body += "\n\n" + task_instruction

    estimated_token_count = len(user_prompt_body) // CHARS_PER_TOKEN_ESTIMATE

    return {
        "system_prompt_sections": system_prompt_sections,
        "user_prompt_body": user_prompt_body,
        "estimated_token_count": estimated_token_count,
        "rows_included": rows_included,
        "error": None,
    }


def generate_insights(
    prompt_payload: dict,
    api_key: str,
    max_response_tokens: int = DEFAULT_MAX_RESPONSE_TOKENS,
) -> dict:
    """
    Send the structured prompt to Claude and return the plain-English insight summary.
    Returns: {summary, raw_response, error}
    """
    if prompt_payload.get("error"):
        return {
            "summary": "",
            "raw_response": None,
            "error": prompt_payload["error"],
        }

    system_text = "\n".join(prompt_payload["system_prompt_sections"])
    user_text = prompt_payload["user_prompt_body"]

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=max_response_tokens,
            system=system_text,
            messages=[{"role": "user", "content": user_text}],
        )
    except anthropic.APITimeoutError as e:
        logger.error("Claude API timeout: %s", e)
        return {"summary": "", "raw_response": None, "error": "Request timed out — please retry."}
    except anthropic.APIStatusError as e:
        logger.error("Claude API status error %s: %s", e.status_code, e.message)
        return {
            "summary": "",
            "raw_response": None,
            "error": f"AI service returned an error (HTTP {e.status_code}) — please retry.",
        }
    except anthropic.APIConnectionError as e:
        logger.error("Claude API connection error: %s", e)
        return {
            "summary": "",
            "raw_response": None,
            "error": "Could not connect to AI service — check your internet connection.",
        }

    if not response.content or len(response.content) == 0:
        return {
            "summary": "",
            "raw_response": response,
            "error": "AI service returned an empty response.",
        }

    summary = response.content[0].text.strip()

    if not summary:
        return {
            "summary": "",
            "raw_response": response,
            "error": "AI service returned an empty response.",
        }

    return {"summary": summary, "raw_response": response, "error": None}


def validate_summary_columns(summary: str, column_profiles: list) -> str:
    """
    Check if the summary references non-existent columns.
    Appends a disclaimer if mismatches are found.
    """
    known_columns = {p["name"].lower() for p in column_profiles}
    import re
    quoted = re.findall(r"'([^']+)'", summary)
    mismatches = [q for q in quoted if q.lower() not in known_columns]
    if mismatches:
        logger.warning("Summary references unknown columns: %s", mismatches)
        summary += "\n\nNote: Some references may not match your data exactly."
    return summary
