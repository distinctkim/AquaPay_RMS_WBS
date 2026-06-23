"""tests/test_invoicing.py — Invoice generation correctness and idempotency."""
from __future__ import annotations

from datetime import date

from rms.invoicing import generate_invoice_for_lease, generate_invoices_for_month
from rms.models import Invoice, InvoiceStatus, WaterCharge


def test_invoice_composes_correct_items_and_totals(session, sample_lease):
    """
    Matches the worked example in the job spec, section 12 exactly:
    Unit A (monthly_rent=100), water=15, garbage_fee=5, security_fee=10
    -> items: rent 100, water 15, garbage 5, security 10, subtotal 130, total 130.
    """
    session.add(WaterCharge(unit_id=sample_lease.unit_id, month="2026-01", charge_amount=15))
    session.commit()

    invoice = generate_invoice_for_lease(session, sample_lease, 2026, 1)
    session.commit()

    descriptions = {l.description: float(l.total_amount) for l in invoice.lines}
    assert descriptions["House Rent"] == 100
    assert descriptions["Water Charge"] == 15
    assert descriptions["Garbage Collection Fee"] == 5
    assert descriptions["Security Fee"] == 10
    assert float(invoice.subtotal) == 130
    assert float(invoice.total) == 130
    assert invoice.status == InvoiceStatus.ISSUED


def test_invoice_without_water_charge_omits_water_line(session, sample_lease):
    """If no WaterCharge row exists for the period, no water line should appear at all."""
    invoice = generate_invoice_for_lease(session, sample_lease, 2026, 1)
    session.commit()

    descriptions = [l.description for l in invoice.lines]
    assert "Water Charge" not in descriptions
    assert float(invoice.total) == 100 + 5 + 10  # rent + garbage + security only


def test_lease_rent_override_takes_precedence(session, sample_lease):
    """A lease-level rent_amount overrides the unit's default monthly_rent."""
    sample_lease.rent_amount = 150
    session.commit()

    invoice = generate_invoice_for_lease(session, sample_lease, 2026, 1)
    session.commit()

    rent_line = next(l for l in invoice.lines if l.description == "House Rent")
    assert float(rent_line.total_amount) == 150


def test_generation_is_idempotent_for_same_period(session, sample_lease):
    """
    Spec section 14: running invoice generation twice for the same period
    must not create duplicate invoices.
    """
    first = generate_invoice_for_lease(session, sample_lease, 2026, 1)
    session.commit()
    first_id = first.id

    second = generate_invoice_for_lease(session, sample_lease, 2026, 1)
    session.commit()

    assert second.id == first_id
    count = session.query(Invoice).filter_by(
        tenant_id=sample_lease.tenant_id, unit_id=sample_lease.unit_id, period_start=date(2026, 1, 1)
    ).count()
    assert count == 1


def test_generate_invoices_for_month_processes_only_active_leases(session, sample_lease):
    """A terminated lease should not receive a new invoice."""
    from rms.models import LeaseStatus
    sample_lease.status = LeaseStatus.TERMINATED
    session.commit()

    invoices = generate_invoices_for_month(session, 2026, 1)
    session.commit()

    assert invoices == []


def test_invoice_number_is_sequential_per_month(session, sample_lease):
    invoice = generate_invoice_for_lease(session, sample_lease, 2026, 6)
    session.commit()
    assert invoice.invoice_number == "INV-2026-06-0001"
