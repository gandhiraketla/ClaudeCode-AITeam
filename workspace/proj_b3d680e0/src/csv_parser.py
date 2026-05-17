"""
csv_parser.py — CSV validation, parsing, and column profiling.

Reads raw CSV bytes, enforces size limits, infers column types,
and computes per-column statistics for downstream chart and insight generation.
"""

from __future__ import annotations

import io
import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_CATEGORICAL_UNIQUE_RATIO = 0.5  # if nunique/row_count > this, treat as non-categorical


def _infer_column_type(series: pd.Series) -> str:
    """Return 'numeric', 'date', or 'categorical' for a pandas Series."""
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    # Attempt date parse on a sample to avoid full-column cost
    sample = series.dropna().head(50)
    if len(sample) > 0:
        try:
            parsed = pd.to_datetime(sample, infer_datetime_format=True, errors="coerce")
            if parsed.notna().sum() / len(sample) >= 0.8:
                return "date"
        except Exception:
            pass
    return "categorical"


def _profile_column(series: pd.Series, inferred_type: str, row_count: int) -> dict[str, Any]:
    """Build a statistics profile dict for a single column."""
    null_count = int(series.isna().sum())
    nunique = int(series.nunique(dropna=True))

    profile: dict[str, Any] = {
        "name": series.name,
        "inferred_type": inferred_type,
        "nunique": nunique,
        "null_count": null_count,
        "min": None,
        "max": None,
        "top_values": [],
    }

    if inferred_type == "numeric":
        numeric = pd.to_numeric(series, errors="coerce")
        profile["min"] = None if numeric.dropna().empty else float(numeric.min())
        profile["max"] = None if numeric.dropna().empty else float(numeric.max())
        profile["top_values"] = []

    elif inferred_type == "date":
        parsed = pd.to_datetime(series, errors="coerce")
        valid = parsed.dropna()
        profile["min"] = str(valid.min()) if not valid.empty else None
        profile["max"] = str(valid.max()) if not valid.empty else None
        profile["top_values"] = []

    else:  # categorical
        top = series.value_counts(dropna=True).head(5)
        profile["top_values"] = [str(v) for v in top.index.tolist()]
        profile["min"] = None
        profile["max"] = None

    return profile


def _validate_csv_bytes(csv_bytes: bytes, max_size_bytes: int) -> str | None:
    """
    Return an error string if the bytes are invalid, else None.
    Checks: size limit, non-empty, starts with printable ASCII (text guard).
    """
    if len(csv_bytes) > max_size_bytes:
        mb = max_size_bytes // (1024 * 1024)
        return f"File exceeds the {mb} MB size limit. Please upload a smaller CSV."

    if len(csv_bytes) == 0:
        return "The uploaded file is empty. Please upload a CSV with data."

    # Reject files whose first 512 bytes contain non-text content (binary/executable guard)
    sample = csv_bytes[:512]
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        try:
            sample.decode("latin-1")
        except UnicodeDecodeError:
            return "File does not appear to be a valid text CSV. Please check the file and try again."

    # Rough magic-byte check: reject if >30% of first 512 bytes are null bytes
    null_ratio = sample.count(b"\x00") / len(sample)
    if null_ratio > 0.30:
        return "File appears to be a binary file, not a CSV. Please upload a plain-text CSV."

    return None


def parse_csv(
    csv_bytes: bytes,
    max_size_bytes: int = MAX_SIZE_BYTES,
) -> dict[str, Any]:
    """
    Parse and profile a CSV from raw bytes.

    Returns a dict with keys:
        column_profiles: list[dict]  — per-column type + stats
        row_count: int               — number of data rows (excluding header)
        dataframe: pd.DataFrame      — parsed DataFrame (for downstream use)
        error: str | None            — non-None if parsing failed
    """
    # --- Size and content validation ---
    validation_error = _validate_csv_bytes(csv_bytes, max_size_bytes)
    if validation_error:
        return {"column_profiles": [], "row_count": 0, "dataframe": None, "error": validation_error}

    # --- Parse CSV ---
    try:
        df = pd.read_csv(
            io.BytesIO(csv_bytes),
            encoding="utf-8",
            on_bad_lines="warn",
        )
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(
                io.BytesIO(csv_bytes),
                encoding="latin-1",
                on_bad_lines="warn",
            )
        except pd.errors.ParserError as exc:
            logger.error("CSV parse error (latin-1 fallback): %s", exc)
            return {
                "column_profiles": [],
                "row_count": 0,
                "dataframe": None,
                "error": "The file could not be parsed as a CSV. Please check it is a valid comma-separated file.",
            }
    except pd.errors.ParserError as exc:
        logger.error("CSV parse error: %s", exc)
        return {
            "column_profiles": [],
            "row_count": 0,
            "dataframe": None,
            "error": "The file could not be parsed as a CSV. Please check it is a valid comma-separated file.",
        }
    except pd.errors.EmptyDataError:
        return {
            "column_profiles": [],
            "row_count": 0,
            "dataframe": None,
            "error": "The uploaded file appears to be empty — please upload a CSV with at least one data row.",
        }

    # --- Header-only guard ---
    if df.empty or len(df) == 0:
        return {
            "column_profiles": [],
            "row_count": 0,
            "dataframe": df,
            "error": "The uploaded file appears to be empty — please upload a CSV with at least one data row.",
        }

    # --- Column validation ---
    if len(df.columns) == 0:
        return {
            "column_profiles": [],
            "row_count": 0,
            "dataframe": df,
            "error": "No columns detected. Please ensure the CSV has a valid header row.",
        }

    row_count = len(df)

    # --- Profile each column ---
    column_profiles: list[dict[str, Any]] = []
    for col in df.columns:
        series = df[col]
        inferred_type = _infer_column_type(series)

        # Downgrade high-cardinality text columns: not useful as categorical axis
        if inferred_type == "categorical" and row_count > 0:
            ratio = series.nunique(dropna=True) / row_count
            if ratio > MAX_CATEGORICAL_UNIQUE_RATIO and series.nunique(dropna=True) > 20:
                # Keep as categorical but mark high-cardinality for chart engine to skip
                pass  # chart_engine will check nunique against row_count itself

        profile = _profile_column(series, inferred_type, row_count)
        column_profiles.append(profile)

    logger.info(
        "CSV parsed: %d rows, %d columns (%d numeric, %d date, %d categorical)",
        row_count,
        len(column_profiles),
        sum(1 for p in column_profiles if p["inferred_type"] == "numeric"),
        sum(1 for p in column_profiles if p["inferred_type"] == "date"),
        sum(1 for p in column_profiles if p["inferred_type"] == "categorical"),
    )

    return {
        "column_profiles": column_profiles,
        "row_count": row_count,
        "dataframe": df,
        "error": None,
    }