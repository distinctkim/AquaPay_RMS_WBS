"""
processor.py — Excel file loading, column validation, and phone number validation.
"""

from __future__ import annotations

import re
import pandas as pd
from io import BytesIO

# ── Constants ──────────────────────────────────────────────────────────────────

REQUIRED_COLUMNS = [
    "Phone Number",
    "Previous Reading",
    "Current Reading",
    "Units Consumed",
    "Cost per Unit",
    "Total Cost",
]

# Kenya phone number: starts with 2547 or 2541, followed by 8 digits (total 12 digits).
# Supports Safaricom (2547XX), Airtel (2541X), Telkom (2577X), etc.
KENYA_PHONE_RE = re.compile(r"^254(7\d{8}|1\d{8})$")


# ── Phone validation ───────────────────────────────────────────────────────────

def validate_kenya_phone(raw: str) -> tuple[bool, str]:
    """
    Validate and normalise a Kenyan phone number.

    Accepted inputs  →  normalised output (E.164 without '+'):
        0712345678   →  254712345678
        +254712345678→  254712345678
        254712345678 →  254712345678

    Returns:
        (True,  normalised_number)  if valid
        (False, error_message)      if invalid
    """
    phone = str(raw).strip().replace(" ", "").replace("-", "")

    # Strip leading '+' 
    if phone.startswith("+"):
        phone = phone[1:]

    # Convert local format (07… / 01…) to international
    if phone.startswith("0") and len(phone) == 10:
        phone = "254" + phone[1:]

    if KENYA_PHONE_RE.match(phone):
        return True, phone

    return False, f"'{raw}' is not a valid Kenyan phone number (expected 2547XXXXXXXX format)"


# ── Numeric validation ─────────────────────────────────────────────────────────

def _is_non_negative_number(value) -> bool:
    """Return True if value can be converted to a non-negative float."""
    try:
        return float(value) >= 0
    except (TypeError, ValueError):
        return False


# ── Main loader ────────────────────────────────────────────────────────────────

def load_and_validate_excel(
    source: str | BytesIO,
) -> tuple[pd.DataFrame | None, list[str]]:
    """
    Load an Excel file and validate its structure and row-level data.

    Args:
        source: File path string or BytesIO object.

    Returns:
        (DataFrame, warnings_list) on success — DataFrame includes a '_valid'
        boolean column indicating rows safe to send.
        (None, [error_message])   on fatal failure (missing file, missing columns).
    """
    # ── Load ──────────────────────────────────────────────────────────────────
    try:
        df = pd.read_excel(source, dtype={"Phone Number": str})
    except Exception as exc:
        return None, [f"Could not read Excel file: {exc}"]

    if df.empty:
        return None, ["The uploaded file contains no data rows."]

    # ── Column check ──────────────────────────────────────────────────────────
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        return None, [f"Missing required column(s): {', '.join(missing)}"]

    # Strip whitespace from string columns
    df["Phone Number"] = df["Phone Number"].astype(str).str.strip()

    # ── Row-level validation ──────────────────────────────────────────────────
    warnings: list[str] = []
    valid_flags: list[bool] = []

    numeric_cols = ["Previous Reading", "Current Reading", "Units Consumed", "Cost per Unit", "Total Cost"]

    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel row number (1-indexed header + 1)
        row_errors: list[str] = []

        # Phone
        ok, result = validate_kenya_phone(row["Phone Number"])
        if ok:
            df.at[idx, "Phone Number"] = result  # store normalised
        else:
            row_errors.append(result)

        # Numeric fields
        for col in numeric_cols:
            if not _is_non_negative_number(row[col]):
                row_errors.append(f"'{col}' has invalid value: {row[col]!r}")

        if row_errors:
            warnings.append(f"Row {row_num}: " + "; ".join(row_errors))
            valid_flags.append(False)
        else:
            valid_flags.append(True)

    df["_valid"] = valid_flags
    return df, warnings
