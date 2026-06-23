"""
cli.py — Command-line interface alternative to the Streamlit web app.

Usage:
    python cli.py --file customers.xlsx --api-key YOUR_KEY --username YOUR_USERNAME
    python cli.py --file customers.xlsx --api-key YOUR_KEY --username sandbox --sandbox
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from processor import load_and_validate_excel
from message import generate_message
from sms import send_bulk_sms


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send water bill SMS notifications to Kenyan customers."
    )
    parser.add_argument("--file", required=True, help="Path to the Excel (.xlsx) file")
    parser.add_argument("--api-key", required=True, help="Africa's Talking API key")
    parser.add_argument("--username", required=True, help="Africa's Talking username")
    parser.add_argument("--sandbox", action="store_true", help="Use AT sandbox (no real SMS sent)")
    parser.add_argument("--sender-id", default=None, help="Optional alphanumeric sender ID")
    parser.add_argument("--dry-run", action="store_true", help="Preview messages without sending")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ── Load & validate ────────────────────────────────────────────────────────
    print(f"\n📂 Loading: {args.file}")
    df, warnings = load_and_validate_excel(args.file)

    if df is None:
        print(f"❌ Error: {warnings[0]}")
        sys.exit(1)

    if warnings:
        print(f"\n⚠️  {len(warnings)} validation warning(s):")
        for w in warnings:
            print(f"   {w}")

    valid_df = df[df["_valid"]].copy()
    skipped  = len(df) - len(valid_df)

    print(f"\n📊 Total rows : {len(df)}")
    print(f"   Valid      : {len(valid_df)}")
    print(f"   Skipped    : {skipped}")

    if valid_df.empty:
        print("\nNo valid rows to process. Exiting.")
        sys.exit(0)

    # ── Dry run preview ────────────────────────────────────────────────────────
    if args.dry_run:
        print("\n🔍 DRY RUN — messages that would be sent:\n")
        for _, row in valid_df.iterrows():
            print(f"TO: +{row['Phone Number']}")
            print(generate_message(row))
            print("-" * 50)
        return

    # ── Confirm before sending ─────────────────────────────────────────────────
    mode = "SANDBOX" if args.sandbox else "LIVE"
    confirm = input(
        f"\n🚀 Send {len(valid_df)} SMS(es) via Africa's Talking [{mode}]? (yes/no): "
    ).strip().lower()

    if confirm != "yes":
        print("Aborted.")
        sys.exit(0)

    # ── Build payload ──────────────────────────────────────────────────────────
    rows = [
        {"phone": row["Phone Number"], "message": generate_message(row)}
        for _, row in valid_df.iterrows()
    ]

    # ── Send ──────────────────────────────────────────────────────────────────
    print("\nSending…")
    results = send_bulk_sms(
        rows=rows,
        api_key=args.api_key,
        username=args.username,
        sandbox=args.sandbox,
        sender_id=args.sender_id,
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    sent   = sum(1 for r in results if r.success)
    failed = len(results) - sent

    print(f"\n✅ Sent   : {sent}")
    print(f"❌ Failed : {failed}")

    if failed:
        print("\nFailed deliveries:")
        for r in results:
            if not r.success:
                print(f"   +{r.phone} — {r.message}")


if __name__ == "__main__":
    main()
