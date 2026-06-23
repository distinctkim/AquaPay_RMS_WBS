"""
message.py — Generate personalised SMS messages from billing row data.
"""

from __future__ import annotations

import pandas as pd


# Maximum GSM-7 characters per SMS segment (160).  Africa's Talking concatenates
# multi-part messages automatically, but keeping under 160 reduces cost.
MAX_SMS_LENGTH = 320  # Allow up to 2 segments


def generate_message(row: pd.Series) -> str:
    """
    Build a customer-friendly water-bill SMS from a DataFrame row.

    Args:
        row: A pandas Series with the billing columns.

    Returns:
        Formatted SMS string ready to send.
    """
    try:
        prev    = float(row["Previous Reading"])
        curr    = float(row["Current Reading"])
        units   = float(row["Units Consumed"])
        cpu     = float(row["Cost per Unit"])
        total   = float(row["Total Cost"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric data in row: {exc}") from exc

    message = (
        f"Dear Customer, your water bill summary:\n"
        f"Prev Reading : {prev:.1f} m3\n"
        f"Curr Reading : {curr:.1f} m3\n"
        f"Units Used   : {units:.1f} m3\n"
        f"Rate         : KES {cpu:.2f}/m3\n"
        f"TOTAL DUE    : KES {total:,.2f}\n"
        f"Pay via M-Pesa or visit our offices. Thank you!"
    )

    if len(message) > MAX_SMS_LENGTH:
        # Fallback: compact version
        message = (
            f"Water Bill: {units:.1f}m3 @ KES{cpu:.2f}/m3. "
            f"Total Due: KES{total:,.2f}. "
            f"Pay via M-Pesa. Thank you!"
        )

    return message
