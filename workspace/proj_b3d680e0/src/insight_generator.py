"""
insight_generator.py — AI-powered insight generation using Anthropic Claude.

Responsibilities:
  - build_insight_prompt: Construct a token-budgeted prompt from column profiles + sample rows
  - generate_insights: Call Claude claude-3-haiku-20240307 and return plain-English summary
  - PII masking and prompt injection defence applied before any data leaves the process
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

# ── Token budget ──────────────────────────────────────────────────────────────
DEFAULT_MAX_PROMPT_TOKENS = 3000
DEFAULT_MAX_RESPONSE_TOKENS = 1024
CHARS_PER_TOKEN_ESTIMATE = 4          # conservative approximation
MAX_SAMPLE_ROWS = 20
MAX_COLUMNS = 50

# ── PII patterns ─────────────────────────────────────────────────────────────
_PII_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b"), "[CARD]"),
]

# ── Prompt injection trigger phrases ─────────────────────────────────────────
_INJECTION_PHRASES: list[str] = [
    "ignore previous instructions",
    "ignore all previous",
    "disregard previous",
    "you are now",
    "new instructions",
    "system prompt",
    "forget your instructions",
    "act as",
    "jailbreak",
    "###",           # common delimiter abuse
    "---system",
    "<|im_start|>",
    "<|im_end|>",
    "[system]",
    "[user]",
    "[assistant]",
]


# ─────────────────────────────────────────────────────────────────────────────
# Sanitization helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mask_pii(value: str) -> str:
    """Replace PII patterns in a string with safe placeholders."""
    for pattern, placeholder in _PII_PATTERNS:
        value = pattern.sub(placeholder, value)
    return value


def _sanitize_cell(value: Any) -> str:
    """
    Convert a cell value to a safe string:
      1. Convert to str
      2. Mask PII
      3. Remove / neutralize prompt-injection trigger phrases
    """
    text = str(value)
    text = _mask_pii(text)
    lower = text.lower()
    for phrase in _INJECTION_PHRASES:
        if phrase in lower:
            # Replace the phrase (case-insensitive) with a neutral token
            text = re.sub(re.escape(phrase), "[REDACTED]", text, flags=re.IGNORECASE)
    return text


def _sanitize_row(row: dict[str, Any]) -> dict[str, str]:
    """Sanitize all values in a sample row dict."""
    return {k: _sanitize_cell(v) for k, v in row.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Prompt construction
# ─────────────────────────────────────────────────────────────────────────────

def build_insight_prompt(
    column_profiles: list[dict[str, Any]],
    raw_dataframe_sample: list[dict[str, Any]],
    max_tokens_budget: int = DEFAULT_MAX_PROMPT_TOKENS,
) -> dict[str, Any]:
    """
    Construct a structured prompt payload for the Claude API.

    Token budget enforcement:
      - Estimates token count using chars / CHARS_PER_TOKEN_ESTIMATE.
      - Reduces rows_included until budget is satisfied.
      - If schema alone exceeds budget, returns an error.

    Returns a dict with keys:
        system_prompt: str
        user_prompt: str
        estimated_token_count: int
        rows_included: int
        error: str | None
    """
    if len(column_profiles) > MAX_COLUMNS:
        return {
            "system_prompt": "",
            "user_prompt": "",
            "estimated_token_count": 0,
            "rows_included": 0,
            "error": (
                "CSV has too many columns to analyze — reduce to under "
                + str(MAX_COLUMNS)
                + " columns."
            ),
        }

    # ── System prompt ────────────────────────────────────────────────────────
    system_prompt = (
        "You are a data analyst producing insights for non-technical business analysts. "
        "Your response must contain exactly 3 to 5 numbered observations. "
        "Each observation must be a single plain-English sentence — no bullet points, "
        "no markdown formatting, no technical jargon. "
        "Only reference data that is present in the provided sample. "
        "Do not invent figures or reference column names the user would not understand. "
        "If the sample is too small to draw a reliable conclusion, say so explicitly."
    )

    # ── Build schema block ───────────────────────────────────────────────────
    schema_lines: list[str] = ["DATASET SCHEMA", "=" * 40]
    for p in column_profiles:
        line = (
            "  " + str(p["name"])
            + "  [" + p["inferred_type"] + "]"
            + "  nunique=" + str(p["nunique"])
            + "  nulls=" + str(p["null_count"])
        )
        if p["inferred_type"] == "numeric" and p["min"] is not None:
            line += "  min=" + str(p["min"]) + "  max=" + str(p["max"])
        elif p["inferred_type"] == "categorical" and p.get("top_values"):
            line += "  top_values=" + ", ".join(str(v) for v in p["top_values"][:5])
        elif p["inferred_type"] == "date":
            if p["min"]:
                line += "  earliest=" + str(p["min"])
            if p["max"]:
                line += "  latest=" + str(p["max"])
        schema_lines.append(line)
    schema_block = "\n".join(schema_lines)

    # ── Budget check: schema alone ───────────────────────────────────────────
    base_estimated = (len(system_prompt) + len(schema_block)) // CHARS_PER_TOKEN_ESTIMATE
    if base_estimated >= max_tokens_budget:
        return {
            "system_prompt": system_prompt,
            "user_prompt": schema_block,
            "estimated_token_count": base_estimated,
            "rows_included": 0,
            "error": (
                "CSV has too many columns to analyze — reduce to under "
                + str(MAX_COLUMNS)
                + " columns."
            ),
        }

    # ── Determine how many sample rows fit in budget ─────────────────────────
    sanitized_rows = [_sanitize_row(r) for r in raw_dataframe_sample[:MAX_SAMPLE_ROWS]]
    rows_included = 0
    sample_block = ""

    for n in range(len(sanitized_rows), -1, -1):
        if n == 0:
            sample_block = "SAMPLE ROWS\n" + "=" * 40 + "\n(No sample rows — schema only.)"
        else:
            header = ",".join(str(k) for k in sanitized_rows[0].keys())
            rows_text = "\n".join(
                ",".join(str(v) for v in row.values())
                for row in sanitized_rows[:n]
            )
            sample_block = (
                "SAMPLE ROWS (showing "
                + str(n)
                + " of "
                + str(len(raw_dataframe_sample))
                + " total)\n"
                + "=" * 40
                + "\n"
                + header
                + "\n"
                + rows_text
            )

        task_block = (
            "TASK\n"
            + "=" * 40
            + "\n"
            + "Based on the dataset schema and sample rows above, provide 3 to 5 key insights "
            + "covering: trends over time (if date columns exist), top and bottom performers, "
            + "outliers or anomalies, and any noteworthy patterns. "
            + "Write each insight as a numbered plain-English sentence."
        )

        user_prompt = "\n\n".join([schema_block, sample_block, task_block])
        estimated = (len(system_prompt) + len(user_prompt)) // CHARS_PER_TOKEN_ESTIMATE

        if estimated <= max_tokens_budget:
            rows_included = n
            break

    logger.info(
        "Prompt built: estimated %d tokens, %d sample rows included",
        estimated,
        rows_included,
    )

    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "estimated_token_count": estimated,
        "rows_included": rows_included,
        "error": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Claude API call
# ─────────────────────────────────────────────────────────────────────────────

def generate_insights(
    prompt_payload: dict[str, Any],
    max_response_tokens: int = DEFAULT_MAX_RESPONSE_TOKENS,
) -> dict[str, Any]:
    """
    Send the structured prompt to Claude claude-3-haiku-20240307 and return insights.

    API key is read directly from the environment here — never passed as a parameter.
    The Anthropic client is instantiated inside this function so the key never
    appears in call stacks, local variable dumps, or exception contexts.

    Returns a dict with keys:
        summary: str    — plain-English insights (empty string on error)
        error:   str | None
    """
    # ── Guard: propagate upstream errors without calling the API ─────────────
    if prompt_payload.get("error"):
        return {"summary": "", "error": prompt_payload["error"]}

    system_prompt = prompt_payload.get("system_prompt", "")
    user_prompt = prompt_payload.get("user_prompt", "")

    if not system_prompt or not user_prompt:
        return {"summary": "", "error": "Prompt payload is incomplete — cannot call API."}

    # ── Read API key from environment ────────────────────────────────────────
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return {
            "summary": "",
            "error": (
                "ANTHROPIC_API_KEY is not set. "
                "Please add it to your .env file and restart the app."
            ),
        }

    # ── Instantiate client and call API ─────────────────────────────────────
    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=max_response_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.AuthenticationError:
        logger.error("Anthropic authentication failed — check ANTHROPIC_API_KEY")
        return {
            "summary": "",
            "error": "Authentication failed — please check your ANTHROPIC_API_KEY.",
        }
    except anthropic.RateLimitError:
        logger.error("Anthropic rate limit exceeded")
        return {
            "summary": "",
            "error": "Rate limit reached — please wait a moment and try again.",
        }
    except anthropic.APITimeoutError:
        logger.error("Anthropic API request timed out")
        return {
            "summary": "",
            "error": "Insight generation timed out — please retry. Charts are still available.",
        }
    except anthropic.APIStatusError as exc:
        logger.error("Anthropic API error (status %s): %s", exc.status_code, exc.message)
        return {
            "summary": "",
            "error": "Insight generation failed — please retry. Charts are still available.",
        }
    except anthropic.APIConnectionError as exc:
        logger.error("Anthropic API connection error: %s", type(exc).__name__)
        return {
            "summary": "",
            "error": "Could not reach the AI service — check your internet connection and retry.",
        }

    # ── Extract and validate response ────────────────────────────────────────
    try:
        raw_text: str = message.content[0].text
    except (IndexError, AttributeError) as exc:
        logger.error("Unexpected response shape from Claude API: %s", exc)
        return {
            "summary": "",
            "error": "Received an unexpected response from the AI service — please retry.",
        }

    if not raw_text or not raw_text.strip():
        return {
            "summary": "",
            "error": "AI service returned an empty response — please retry.",
        }

    summary = raw_text.strip()

    # ── Post-process: flag confabulated column references ────────────────────
    summary = _flag_confabulated_columns(
        summary,
        column_names=[p["name"] for p in prompt_payload.get("column_profiles", [])],
    )

    logger.info(
        "Insights generated: %d characters, stop_reason=%s",
        len(summary),
        getattr(message, "stop_reason", "unknown"),
    )

    return {"summary": summary, "error": None}


# ─────────────────────────────────────────────────────────────────────────────
# Post-processing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _flag_confabulated_columns(summary: str, column_names: list[str]) -> str:
    """
    Scan the summary for quoted identifiers that look like column references.
    If any quoted word is not in column_names, append a disclaimer.

    Heuristic: looks for words in single or double quotes that are not
    common English stopwords and not present in the known column list.
    """
    if not column_names:
        return summary

    # Collect quoted tokens from the summary
    quoted_tokens = re.findall(r"['\"]([A-Za-z0-9_ ]+)['\"]", summary)
    stopwords = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "shall",
        "should", "may", "might", "must", "can", "could", "not", "and", "or",
        "but", "if", "in", "on", "at", "to", "for", "of", "with", "by", "from",
        "no", "yes", "so", "as", "up", "out", "about", "than", "then", "too",
    }

    column_names_lower = {str(c).lower() for c in column_names}
    suspect_found = False

    for token in quoted_tokens:
        token_lower = token.lower().strip()
        if token_lower in stopwords:
            continue
        # Check if it looks like a column reference (short, identifier-like)
        if len(token_lower) <= 40 and token_lower not in column_names_lower:
            suspect_found = True
            break

    if suspect_found:
        disclaimer = (
            "\n\n_Note: Some references in this summary may not exactly match "
            "the column names in your data._"
        )
        summary = summary + disclaimer

    return summary