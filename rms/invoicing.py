"""
rms/invoicing.py — Invoice generation logic.

Idempotency
-----------
Invoice has a unique constraint on (tenant_id, unit_id, period_start). Before
creating a new invoice for a lease+period, generate_invoice_for_lease() checks
for an existing row first. This means running the monthly batch job twice for
the same month is always safe — it will skip leases that already have an
invoice for that period rather than creating a duplicate, satisfying the
spec's idempotency requirement (section 14) without relying on database-level
constraint violations as the only safety net.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from sqlalchemy.orm import Session

from rms.models import Invoice, InvoiceLine, InvoiceStatus, Lease, WaterCharge


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)
    return start, end


def _next_invoice_number(session: Session, period_start: date) -> str:
    """
    Generate a sequential, human-readable invoice number, e.g. INV-2026-06-0001.
    Sequence resets per calendar month based on existing invoice count for
    that period prefix — simple and adequate for single-instance deployments.
    """
    prefix = f"INV-{period_start.strftime('%Y-%m')}"
    existing_count = (
        session.query(Invoice)
        .filter(Invoice.invoice_number.like(f"{prefix}-%"))
        .count()
    )
    return f"{prefix}-{existing_count + 1:04d}"


def build_invoice_lines(lease: Lease, period_start: date, water_charge: WaterCharge | None) -> list[dict]:
    """
    Compose the itemised charges for one lease/period: rent + water + garbage
    + security, matching the composition rules in spec section 4.
    Returns a list of dicts (not ORM objects yet) so this can be unit-tested
    without touching the database.
    """
    unit = lease.unit
    lines = [
        {"description": "House Rent", "quantity": 1, "unit_price": lease.effective_rent()},
    ]

    water_amount = float(water_charge.charge_amount) if water_charge else 0.0
    if water_charge is not None:
        lines.append({"description": "Water Charge", "quantity": 1, "unit_price": water_amount})

    if float(unit.garbage_fee) > 0:
        lines.append({"description": "Garbage Collection Fee", "quantity": 1, "unit_price": float(unit.garbage_fee)})

    if float(unit.security_fee) > 0:
        lines.append({"description": "Security Fee", "quantity": 1, "unit_price": float(unit.security_fee)})

    for line in lines:
        line["total_amount"] = round(line["quantity"] * line["unit_price"], 2)

    return lines


def generate_invoice_for_lease(
    session: Session,
    lease: Lease,
    year: int,
    month: int,
    due_in_days: int = 7,
) -> Invoice | None:
    """
    Generate (and persist) one invoice for a single lease/period.

    Returns the existing Invoice if one already exists for this lease+period
    (idempotent no-op), or the newly created Invoice otherwise.
    """
    period_start, period_end = _month_bounds(year, month)

    existing = (
        session.query(Invoice)
        .filter_by(tenant_id=lease.tenant_id, unit_id=lease.unit_id, period_start=period_start)
        .first()
    )
    if existing:
        return existing

    water_charge = (
        session.query(WaterCharge)
        .filter_by(unit_id=lease.unit_id, month=period_start.strftime("%Y-%m"))
        .first()
    )

    line_dicts = build_invoice_lines(lease, period_start, water_charge)
    subtotal = round(sum(l["total_amount"] for l in line_dicts), 2)

    invoice = Invoice(
        invoice_number=_next_invoice_number(session, period_start),
        tenant_id=lease.tenant_id,
        unit_id=lease.unit_id,
        period_start=period_start,
        period_end=period_end,
        due_date=period_end + timedelta(days=due_in_days),
        subtotal=subtotal,
        total=subtotal,  # no taxes/discounts in this spec; total == subtotal
        status=InvoiceStatus.ISSUED,
    )
    invoice.lines = [InvoiceLine(**l) for l in line_dicts]

    session.add(invoice)
    session.flush()  # populate invoice.id for callers that need it immediately
    return invoice


def generate_invoices_for_month(session: Session, year: int, month: int) -> list[Invoice]:
    """
    Generate invoices for every active lease for the given month.
    Skips (returns existing, does not duplicate) any lease that already has
    an invoice for this period — see module docstring on idempotency.
    """
    from rms.models import LeaseStatus

    active_leases = session.query(Lease).filter_by(status=LeaseStatus.ACTIVE).all()
    return [generate_invoice_for_lease(session, lease, year, month) for lease in active_leases]
