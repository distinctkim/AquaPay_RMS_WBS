"""
rms/sms_templates.py — RMS-specific SMS templates and send helpers.

This module deliberately does NOT reimplement SMS sending. It imports and
calls the existing `send_sms()` from the app's own sms.py (Africa's Talking
integration with the certifi/EXTRA_CA_BUNDLE handling already in place), per
spec section 7 ("Reuse the existing SMS notification integration") and
section 14 ("reuse water-charge logic rather than duplicating").
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from rms.models import Invoice, SmsLog
from sms import SMSResult, send_sms

INVOICE_TEMPLATE = (
    "Dear {tenant_name}, your invoice {invoice_number} for unit {unit_code} "
    "is ready. Total due: KES {total_due:,.2f} by {due_date}. "
    "Pay via M-Pesa. Thank you!"
)

REMINDER_TEMPLATE = (
    "Dear {tenant_name}, reminder: invoice {invoice_number} (unit {unit_code}) "
    "of KES {total_due:,.2f} is due {due_date}. Outstanding balance: "
    "KES {outstanding:,.2f}. Please settle via M-Pesa. Thank you!"
)


def render_template(template: str, invoice: Invoice) -> str:
    return template.format(
        tenant_name=invoice.tenant.full_name,
        invoice_number=invoice.invoice_number,
        unit_code=invoice.unit.code,
        total_due=float(invoice.total),
        due_date=invoice.due_date.strftime("%d %b %Y"),
        outstanding=invoice.outstanding_balance,
    )


def send_invoice_sms(
    session: Session,
    invoice: Invoice,
    api_key: str,
    username: str,
    sandbox: bool = True,
    reminder: bool = False,
) -> SMSResult:
    """
    Send (or re-send as a reminder) an SMS for the given invoice, log the
    attempt in SmsLog, and mark invoice.sent_sms = True on success.
    """
    template = REMINDER_TEMPLATE if reminder else INVOICE_TEMPLATE
    message = render_template(template, invoice)

    result = send_sms(
        phone=invoice.tenant.phone_number,
        message=message,
        api_key=api_key,
        username=username,
        sandbox=sandbox,
    )

    session.add(SmsLog(
        invoice_id=invoice.id,
        tenant_id=invoice.tenant_id,
        phone=invoice.tenant.phone_number,
        message=message,
        status="success" if result.success else "failed",
        provider_response=result.message,
    ))

    if result.success and not reminder:
        invoice.sent_sms = True

    session.flush()
    return result
