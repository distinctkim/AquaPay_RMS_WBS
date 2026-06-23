"""
rms/invoice_logic.py — Invoice generation and payment allocation logic.

Key design decisions
---------------------
- Invoice generation is IDEMPOTENT: a unique constraint on
  (tenant_id, unit_id, period_start) means re-running the monthly job for a
  period that already has an invoice will simply skip that lease rather than
  creating a duplicate. We check explicitly before insert (rather than relying
  solely on the DB constraint) so we can report "skipped" vs "created" cleanly.
- Water charge is reused from WaterCharge if a record exists for the period;
  otherwise the FeeType('water').default_amount is used as a fallback (0 if
  no default is configured). No water-billing logic is duplicated here.
- Payments may be allocated directly to an invoice (invoice_id set) or left
  unallocated (invoice_id=None). Allocating a payment recalculates the
  invoice's status (draft/issued -> partial -> paid). Overpayments are not
  silently discarded -- the excess remains attributed to the tenant's payment
  record and is visible via get_tenant_credit().
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from rms.models import (
    Unit, Tenant, Lease, FeeType, WaterCharge, Payment, Invoice, InvoiceLine,
    LeaseStatus, InvoiceStatus,
)


@dataclass
class InvoiceGenerationResult:
    created: list[int]   # invoice IDs created
    skipped: list[str]   # human-readable reasons for skipped leases


def month_period(year: int, month: int) -> tuple[date, date]:
    """Return (period_start, period_end) for a given year/month."""
    period_start = date(year, month, 1)
    period_end = period_start + relativedelta(months=1) - timedelta(days=1)
    return period_start, period_end


def _next_invoice_number(session: Session) -> str:
    """Generate a sequential invoice number like INV-000123."""
    count = session.query(Invoice).count()
    return f"INV-{count + 1:06d}"


def _get_water_charge_amount(session: Session, unit_id: int, period_start: date) -> float:
    """Look up the WaterCharge for this unit/month; fall back to FeeType default."""
    month_str = period_start.strftime("%Y-%m")
    wc = (
        session.query(WaterCharge)
        .filter(WaterCharge.unit_id == unit_id, WaterCharge.month == month_str)
        .first()
    )
    if wc is not None:
        return float(wc.charge_amount)

    fee = session.query(FeeType).filter(FeeType.name == "water").first()
    return float(fee.default_amount) if fee else 0.0


def generate_invoice_for_lease(
    session: Session, lease: Lease, period_start: date, period_end: date, due_in_days: int = 7
) -> Invoice | None:
    """
    Generate a single invoice for one active lease for the given period.

    Returns the created Invoice, or None if an invoice for this
    tenant/unit/period already exists (idempotency check).
    """
    existing = (
        session.query(Invoice)
        .filter(
            Invoice.tenant_id == lease.tenant_id,
            Invoice.unit_id == lease.unit_id,
            Invoice.period_start == period_start,
        )
        .first()
    )
    if existing is not None:
        return None  # idempotent: do not create a duplicate

    unit = lease.unit
    rent = lease.effective_rent()
    water = _get_water_charge_amount(session, unit.id, period_start)
    garbage = float(unit.garbage_fee)
    security = float(unit.security_fee)

    lines_data = [
        ("House Rent", rent),
        ("Water Charge", water),
        ("Garbage Collection Fee", garbage),
        ("Security Fee", security),
    ]
    # Only include non-zero lines, except rent which is always shown even if 0.
    lines_data = [(desc, amt) for desc, amt in lines_data if amt != 0 or desc == "House Rent"]

    subtotal = sum(amt for _, amt in lines_data)

    invoice = Invoice(
        invoice_number=_next_invoice_number(session),
        tenant_id=lease.tenant_id,
        unit_id=lease.unit_id,
        period_start=period_start,
        period_end=period_end,
        due_date=period_end + timedelta(days=due_in_days),
        subtotal=Decimal(str(subtotal)),
        total=Decimal(str(subtotal)),
        status=InvoiceStatus.ISSUED.value,
    )
    session.add(invoice)
    session.flush()  # assign invoice.id before adding lines

    for desc, amt in lines_data:
        session.add(InvoiceLine(
            invoice_id=invoice.id,
            description=desc,
            quantity=Decimal("1"),
            unit_price=Decimal(str(amt)),
            total_amount=Decimal(str(amt)),
        ))

    return invoice


def generate_monthly_invoices(
    session: Session, year: int, month: int, due_in_days: int = 7
) -> InvoiceGenerationResult:
    """
    Generate invoices for every active lease for the given year/month.

    Idempotent: leases that already have an invoice for this period are
    skipped (not duplicated), so this is safe to re-run.
    """
    period_start, period_end = month_period(year, month)

    active_leases = (
        session.query(Lease)
        .filter(Lease.status == LeaseStatus.ACTIVE.value)
        .all()
    )

    created: list[int] = []
    skipped: list[str] = []

    for lease in active_leases:
        invoice = generate_invoice_for_lease(session, lease, period_start, period_end, due_in_days)
        if invoice is not None:
            created.append(invoice.id)
        else:
            skipped.append(
                f"Lease #{lease.id} (tenant_id={lease.tenant_id}, unit_id={lease.unit_id}) "
                f"already has an invoice for {period_start.strftime('%Y-%m')}"
            )

    session.commit()
    return InvoiceGenerationResult(created=created, skipped=skipped)


def _recalculate_invoice_status(invoice: Invoice) -> None:
    """Update invoice.status based on total payments allocated to it."""
    paid = invoice.amount_paid
    total = float(invoice.total)

    if paid <= 0:
        invoice.status = InvoiceStatus.ISSUED.value
    elif paid < total:
        invoice.status = InvoiceStatus.PARTIAL.value
    else:
        invoice.status = InvoiceStatus.PAID.value  # paid >= total (overpayment also counts as paid)


def record_payment(
    session: Session,
    tenant_id: int,
    amount: float,
    payment_date: date,
    unit_id: int | None = None,
    invoice_id: int | None = None,
    payment_method: str | None = None,
    reference: str | None = None,
    notes: str | None = None,
) -> Payment:
    """
    Record a payment. If invoice_id is given, the payment is allocated to that
    invoice immediately and the invoice's status is recalculated (handles
    partial payments and overpayments -- overpayment is simply recorded as a
    payment greater than the remaining balance; the excess is visible via
    get_tenant_credit()).
    """
    payment = Payment(
        tenant_id=tenant_id,
        unit_id=unit_id,
        amount=Decimal(str(amount)),
        payment_date=payment_date,
        payment_method=payment_method,
        reference=reference,
        invoice_id=invoice_id,
        notes=notes,
    )
    session.add(payment)
    session.flush()

    if invoice_id is not None:
        invoice = session.get(Invoice, invoice_id)
        if invoice is not None:
            _recalculate_invoice_status(invoice)

    session.commit()
    return payment


def allocate_payment_to_invoice(session: Session, payment_id: int, invoice_id: int) -> Payment:
    """Allocate a previously-unallocated payment to an invoice."""
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise ValueError(f"Payment #{payment_id} not found")

    payment.invoice_id = invoice_id
    session.flush()

    invoice = session.get(Invoice, invoice_id)
    if invoice is not None:
        _recalculate_invoice_status(invoice)

    session.commit()
    return payment


def get_tenant_credit(session: Session, tenant_id: int) -> float:
    """
    Return a tenant's net credit balance: total payments made minus total
    invoiced amount, across all of their invoices and payments. A positive
    value means the tenant has overpaid / has credit; 0 or negative means
    no credit.
    """
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        return 0.0

    total_paid = sum(float(p.amount) for p in tenant.payments)
    total_invoiced = sum(float(i.total) for i in tenant.invoices)
    credit = total_paid - total_invoiced
    return max(credit, 0.0)


def mark_overdue_invoices(session: Session, as_of: date | None = None) -> int:
    """
    Mark issued/partial invoices whose due_date has passed as 'overdue'.
    Returns the number of invoices updated. Safe to run repeatedly (idempotent
    in effect, since invoices already 'overdue' or 'paid' are simply skipped).
    """
    as_of = as_of or date.today()
    candidates = (
        session.query(Invoice)
        .filter(
            Invoice.status.in_([InvoiceStatus.ISSUED.value, InvoiceStatus.PARTIAL.value]),
            Invoice.due_date < as_of,
        )
        .all()
    )
    for inv in candidates:
        inv.status = InvoiceStatus.OVERDUE.value
    session.commit()
    return len(candidates)
