import io
import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10MB


def _infer_type(series: pd.Series) -> str:
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    # Try parsing as date
    if series.dtype == object:
        try:
            parsed = pd.to_datetime(series.dropna().head(20), infer_datetime_format=True)
            if len(parsed) > 0:
                return "date"
        except (ValueError, TypeError):
            pass
    return "categorical"


def _profile_column(series: pd.Series, inferred_type: str) -> dict:
    profile = {
        "name": series.name,
        "inferred_type": inferred_type,
        "nunique": int(series.nunique()),
        "null_count": int(series.isna().sum()),
        "min": None,
        "max": None,
        "top_values": [],
    }
    try:
        if inferred_type == "numeric":
            profile["min"] = float(series.min()) if not series.isna().all() else None
            profile["max"] = float(series.max()) if not series.isna().all() else None
        elif inferred_type == "date":
            dt = pd.to_datetime(series, errors="coerce")
            profile["min"] = str(dt.min()) if not dt.isna().all() else None
            profile["max"] = str(dt.max()) if not dt.isna().all() else None
        else:
            vc = series.value_counts().head(5)
            profile["top_values"] = list(vc.index.astype(str))
    except Exception as e:
        logger.warning("Could not compute min/max for column %s: %s", series.name, e)
    return profile


def parse_csv(csv_bytes: bytes, max_size_bytes: int = MAX_SIZE_BYTES) -> dict:
    """
    Parse raw CSV bytes. Returns dict with keys:
      column_profiles, row_count, dataframe, error
    """
    if len(csv_bytes) > max_size_bytes:
        return {
            "column_profiles": [],
            "row_count": 0,
            "dataframe": None,
            "error": f"File exceeds maximum allowed size of {max_size_bytes // (1024*1024)}MB.",
        }

    try:
        df = pd.read_csv(io.BytesIO(csv_bytes))
    except pd.errors.EmptyDataError:
        return {
            "column_profiles": [],
            "row_count": 0,
            "dataframe": None,
            "error": "The uploaded file is empty or has no readable content.",
        }
    except pd.errors.ParserError as e:
        logger.error("CSV parse error: %s", e)
        return {
            "column_profiles": [],
            "row_count": 0,
            "dataframe": None,
            "error": f"Could not parse CSV: {e}",
        }
    except UnicodeDecodeError as e:
        logger.error("CSV encoding error: %s", e)
        return {
            "column_profiles": [],
            "row_count": 0,
            "dataframe": None,
            "error": "File encoding not supported. Please upload a UTF-8 encoded CSV.",
        }

    if df.empty or len(df) == 0:
        return {
            "column_profiles": [],
            "row_count": 0,
            "dataframe": df,
            "error": "The uploaded file appears to be empty — please upload a CSV with at least one data row.",
        }

    if df.columns.duplicated().any():
        return {
            "column_profiles": [],
            "row_count": 0,
            "dataframe": None,
            "error": "CSV contains duplicate column headers. Please ensure all column names are unique.",
        }

    column_profiles = []
    for col in df.columns:
        inferred_type = _infer_type(df[col])
        # Coerce date columns
        if inferred_type == "date" and df[col].dtype == object:
            df[col] = pd.to_datetime(df[col], errors="coerce")
        profile = _profile_column(df[col], inferred_type)
        column_profiles.append(profile)

    return {
        "column_profiles": column_profiles,
        "row_count": len(df),
        "dataframe": df,
        "error": None,
    }
