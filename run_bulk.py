"""
run_bulk.py — Read customers_sample.xlsx and send water bill SMS notifications.

Usage:
    # Sandbox test (no real messages sent):
    python run_bulk.py --sandbox

    # Live (real messages, requires approved sender ID and funded AT account):
    python run_bulk.py

Environment variables required:
    AT_API_KEY    — your Africa's Talking API key
    AT_USERNAME   — your Africa's Talking account username
    AT_SENDER_ID  — your approved sender ID e.g. WATERCO (optional)
    BILLS_FILE    — path to your Excel file (default: customers_sample.xlsx)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import openpyxl

from sms import send_bulk_sms

# ── Config ─────────────────────────────────────────────────────────────────────

DEFAULT_FILE = "customers_sample.xlsx"

MESSAGE_TEMPLATE = (
    "Dear {name}, your water bill for this period:\n"
    "Prev reading: {prev} | Curr reading: {curr}\n"
    "Units used: {units} | Rate: KES {rate}/unit\n"
    "Total due: KES {total}. Please pay promptly. Thank you."
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def load_rows(filepath: str) -> list[dict]:
    """Read the Excel file and return a list of SMS-ready dicts."""
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active

    rows = []
    headers = None

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            headers = [str(h).strip() for h in row]
            continue

        if not any(row):          # skip completely empty rows
            continue

        record = dict(zip(headers, row))

        phone = str(record.get("Phone Number", "")).strip()
        if not phone:
            print(f"  ⚠  Row {i+1}: no phone number — skipped.")
            continue

        # Ensure phone is in international format (+254...)
        if not phone.startswith("+"):
            phone = "+" + phone

        # Use customer name if available, fall back to "customer"
        name = str(record.get("Customer Name", "")).strip()
        if not name or name.lower() == "none":
            name = "customer"

        message = MESSAGE_TEMPLATE.format(
            name=name,
            prev=record.get("Previous Reading", "?"),
            curr=record.get("Current Reading", "?"),
            units=record.get("Units Consumed", "?"),
            rate=record.get("Cost per Unit", "?"),
            total=record.get("Total Cost", "?"),
        )

        rows.append({"phone": phone, "message": message})

    wb.close()
    return rows


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Send water bill SMS notifications.")
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Use AT sandbox (no real messages sent, no charge).",
    )
    parser.add_argument(
        "--file",
        default=os.environ.get("BILLS_FILE", DEFAULT_FILE),
        help=f"Path to Excel file (default: {DEFAULT_FILE}).",
    )
    args = parser.parse_args()

    # ── Credentials ──
    api_key = os.environ.get("AT_API_KEY", "")
    username = os.environ.get("AT_USERNAME", "")
    sender_id = os.environ.get("AT_SENDER_ID", "")

    if not api_key:
        print("ERROR: AT_API_KEY environment variable not set.")
        sys.exit(1)
    if not username:
        print("ERROR: AT_USERNAME environment variable not set.")
        sys.exit(1)

    # ── Load data ──
    filepath = args.file
    if not Path(filepath).is_file():
        print(f"ERROR: File not found: {filepath}")
        sys.exit(1)

    print(f"Loading {filepath} ...")
    rows = load_rows(filepath)

    if not rows:
        print("No valid rows found in file. Nothing to send.")
        sys.exit(0)

    mode = "SANDBOX" if args.sandbox else "LIVE"
    print(f"\n{mode} mode — sending {len(rows)} message(s)...")
    if sender_id and not args.sandbox:
        print(f"Sender ID: {sender_id}")
    print()

    # ── Send ──
    results = send_bulk_sms(
        rows=rows,
        api_key=api_key,
        username=username,
        sandbox=args.sandbox,
        sender_id=sender_id,
    )

    # ── Report ──
    sent = failed = 0
    for r in results:
        if r.success:
            print(f"  ✓  {r.phone}")
            sent += 1
        else:
            print(f"  ✗  {r.phone}: {r.message}")
            failed += 1

    print(f"\nDone. {sent} sent, {failed} failed.")


if __name__ == "__main__":
    main()