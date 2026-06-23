"""
rms/payments.py — Payment recording and allocation logic.

Business rules implemented (spec section 4):
- A payment can be linked to a specific invoice, or left unallocated
  (invoice_id=None) for later reconciliation.
- Partial payments are allowed; invoice.status becomes PAID only once
  total payments >= invoice.total.
- Overpayments are not silently dropped — record_payment() returns the
  credit amount so the caller (UI layer) can surface it; spec section 4
  says this should be "tracked as credit for a tenant," which in this
  minimal implementation means: it's visible and reportable, rather than
  silently absorbed into the invoice with no trace.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from rms.models import Invoice, InvoiceStatus, Payment


@dataclass
class PaymentResult:
    payment: Payment
    invoice_status: InvoiceStatus | None
    outstanding_balance: float | None
    overpayment_credit: float = 0.0


def _refresh_invoice_status(invoice: Invoice) -> None:
    """Recompute and set invoice.status based on total payments received."""
    paid = invoice.amount_paid
    total = float(invoice.total)

    if paid <= 0:
        invoice.status = InvoiceStatus.ISSUED
    elif paid < total:
        invoice.status = InvoiceStatus.PARTIAL
    else:
        invoice.status = InvoiceStatus.PAID


def record_payment(
    session: Session,
    tenant_id: int,
    amount: float,
    payment_date: date,
    payment_method: str = "M-Pesa",
    unit_id: int | None = None,
    invoice_id: int | None = None,
    reference: str | None = None,
    notes: str | None = None,
) -> PaymentResult:
    """
    Record a payment and, if linked to an invoice, update that invoice's
    status. Returns a PaymentResult with the resulting balance/credit info
    so the calling Streamlit page can display an accurate confirmation.
    """
    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero.")

    payment = Payment(
        tenant_id=tenant_id,
        unit_id=unit_id,
        invoice_id=invoice_id,
        amount=amount,
        payment_date=payment_date,
        payment_method=payment_method,
        reference=reference,
        notes=notes,
    )
    session.add(payment)
    session.flush()

    if invoice_id is None:
        return PaymentResult(payment=payment, invoice_status=None, outstanding_balance=None)

    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise ValueError(f"Invoice id {invoice_id} not found.")

    _refresh_invoice_status(invoice)
    session.flush()

    overpayment = max(0.0, invoice.amount_paid - float(invoice.total))

    return PaymentResult(
        payment=payment,
        invoice_status=invoice.status,
        outstanding_balance=invoice.outstanding_balance,
        overpayment_credit=round(overpayment, 2),
    )


def tenant_credit_balance(session: Session, tenant_id: int) -> float:
    """
    Sum of overpayment credit across all of a tenant's invoices — i.e. total
    paid minus total invoiced, floored at 0 per invoice so an outstanding
    balance on one invoice never cancels out a credit on another silently.
    """
    invoices = session.query(Invoice).filter_by(tenant_id=tenant_id).all()
    return round(sum(max(0.0, inv.amount_paid - float(inv.total)) for inv in invoices), 2)
