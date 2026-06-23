"""
tests/test_invoice_logic.py — Unit tests for invoice generation, idempotency,
payment allocation, and overdue marking.

Run with: pytest tests/test_invoice_logic.py -v
Uses an in-memory SQLite DB per test (fast, isolated, no rms.db side effects).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rms.models import Base, Unit, Tenant, Lease, FeeType, WaterCharge, LeaseStatus, InvoiceStatus
from rms.invoice_logic import (
    generate_monthly_invoices, generate_invoice_for_lease, month_period,
    record_payment, get_tenant_credit, mark_overdue_invoices,
)


@pytest.fixture
def session():
    """Fresh in-memory SQLite DB for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    s = SessionLocal()
    # seed default fee types (water defaults to 0 unless a WaterCharge exists)
    s.add(FeeType(name="water", calculation_method="custom", default_amount=0))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def unit_tenant_lease(session):
    """Matches the spec's worked example: rent=100, garbage=5, security=10."""
    unit = Unit(code="A1", address="123 Test St", unit_type="house",
                monthly_rent=100, garbage_fee=5, security_fee=10)
    tenant = Tenant(first_name="John", last_name="Doe", phone_number="254712345678")
    session.add_all([unit, tenant])
    session.commit()

    lease = Lease(tenant_id=tenant.id, unit_id=unit.id,
                   start_date=date(2026, 1, 1), status=LeaseStatus.ACTIVE.value)
    session.add(lease)
    session.commit()
    return unit, tenant, lease


class TestInvoiceGeneration:
    def test_invoice_composes_correct_items_and_total(self, session, unit_tenant_lease):
        """Matches spec example: rent 100 + water 15 + garbage 5 + security 10 = 130."""
        unit, tenant, lease = unit_tenant_lease
        # Add a water charge for the period (spec example: water cost = 15)
        session.add(WaterCharge(unit_id=unit.id, month="2026-06", charge_amount=15))
        session.commit()

        period_start, period_end = month_period(2026, 6)
        invoice = generate_invoice_for_lease(session, lease, period_start, period_end)
        session.commit()

        assert invoice is not None
        assert float(invoice.total) == 130.0
        assert float(invoice.subtotal) == 130.0

        descriptions = {line.description: float(line.total_amount) for line in invoice.lines}
        assert descriptions["House Rent"] == 100.0
        assert descriptions["Water Charge"] == 15.0
        assert descriptions["Garbage Collection Fee"] == 5.0
        assert descriptions["Security Fee"] == 10.0

    def test_invoice_uses_lease_rent_override(self, session, unit_tenant_lease):
        """Lease.rent_amount should override Unit.monthly_rent when set."""
        unit, tenant, lease = unit_tenant_lease
        lease.rent_amount = 150  # override
        session.commit()

        period_start, period_end = month_period(2026, 6)
        invoice = generate_invoice_for_lease(session, lease, period_start, period_end)
        session.commit()

        rent_line = next(l for l in invoice.lines if l.description == "House Rent")
        assert float(rent_line.total_amount) == 150.0

    def test_generate_monthly_invoices_creates_one_per_active_lease(self, session, unit_tenant_lease):
        unit, tenant, lease = unit_tenant_lease
        result = generate_monthly_invoices(session, 2026, 6)
        assert len(result.created) == 1
        assert len(result.skipped) == 0

    def test_generate_monthly_invoices_skips_terminated_leases(self, session, unit_tenant_lease):
        unit, tenant, lease = unit_tenant_lease
        lease.status = LeaseStatus.TERMINATED.value
        session.commit()

        result = generate_monthly_invoices(session, 2026, 6)
        assert len(result.created) == 0


class TestIdempotency:
    def test_running_invoice_job_twice_does_not_duplicate(self, session, unit_tenant_lease):
        """Core acceptance criterion: idempotent invoice generation."""
        unit, tenant, lease = unit_tenant_lease

        result1 = generate_monthly_invoices(session, 2026, 6)
        assert len(result1.created) == 1

        result2 = generate_monthly_invoices(session, 2026, 6)
        assert len(result2.created) == 0
        assert len(result2.skipped) == 1

        # Confirm only one invoice actually exists in the DB
        from rms.models import Invoice
        count = session.query(Invoice).filter(
            Invoice.tenant_id == tenant.id, Invoice.unit_id == unit.id
        ).count()
        assert count == 1

    def test_different_months_create_separate_invoices(self, session, unit_tenant_lease):
        unit, tenant, lease = unit_tenant_lease
        r1 = generate_monthly_invoices(session, 2026, 6)
        r2 = generate_monthly_invoices(session, 2026, 7)
        assert len(r1.created) == 1
        assert len(r2.created) == 1


class TestPaymentAllocation:
    def test_partial_payment_sets_status_partial(self, session, unit_tenant_lease):
        """Matches spec example: John pays 50 of 130 -> outstanding 80, status partial."""
        unit, tenant, lease = unit_tenant_lease
        session.add(WaterCharge(unit_id=unit.id, month="2026-06", charge_amount=15))
        session.commit()

        result = generate_monthly_invoices(session, 2026, 6)
        invoice_id = result.created[0]

        record_payment(session, tenant_id=tenant.id, amount=50,
                        payment_date=date(2026, 6, 5), invoice_id=invoice_id)

        from rms.models import Invoice
        invoice = session.get(Invoice, invoice_id)
        assert invoice.outstanding == 80.0
        assert invoice.status == InvoiceStatus.PARTIAL.value

    def test_full_payment_sets_status_paid(self, session, unit_tenant_lease):
        unit, tenant, lease = unit_tenant_lease
        result = generate_monthly_invoices(session, 2026, 6)
        invoice_id = result.created[0]

        from rms.models import Invoice
        invoice = session.get(Invoice, invoice_id)
        full_amount = float(invoice.total)

        record_payment(session, tenant_id=tenant.id, amount=full_amount,
                        payment_date=date(2026, 6, 5), invoice_id=invoice_id)

        session.refresh(invoice)
        assert invoice.outstanding == 0.0
        assert invoice.status == InvoiceStatus.PAID.value

    def test_overpayment_recorded_as_credit(self, session, unit_tenant_lease):
        """Overpayments are tracked as tenant credit, not silently discarded."""
        unit, tenant, lease = unit_tenant_lease
        result = generate_monthly_invoices(session, 2026, 6)
        invoice_id = result.created[0]

        from rms.models import Invoice
        invoice = session.get(Invoice, invoice_id)
        total = float(invoice.total)
        overpay_amount = total + 50

        record_payment(session, tenant_id=tenant.id, amount=overpay_amount,
                        payment_date=date(2026, 6, 5), invoice_id=invoice_id)

        session.refresh(invoice)
        assert invoice.status == InvoiceStatus.PAID.value

        credit = get_tenant_credit(session, tenant.id)
        assert credit == 50.0

    def test_unallocated_payment_does_not_affect_invoice(self, session, unit_tenant_lease):
        unit, tenant, lease = unit_tenant_lease
        result = generate_monthly_invoices(session, 2026, 6)
        invoice_id = result.created[0]

        record_payment(session, tenant_id=tenant.id, amount=50, payment_date=date(2026, 6, 5))

        from rms.models import Invoice
        invoice = session.get(Invoice, invoice_id)
        assert invoice.outstanding == float(invoice.total)  # unaffected
        assert invoice.status == InvoiceStatus.ISSUED.value


class TestOverdueMarking:
    def test_overdue_invoice_marked_correctly(self, session, unit_tenant_lease):
        unit, tenant, lease = unit_tenant_lease
        period_start, period_end = month_period(2026, 1)  # long past
        invoice = generate_invoice_for_lease(session, lease, period_start, period_end, due_in_days=7)
        session.commit()

        n_marked = mark_overdue_invoices(session, as_of=date(2026, 6, 22))

        session.refresh(invoice)
        assert n_marked == 1
        assert invoice.status == InvoiceStatus.OVERDUE.value

    def test_paid_invoice_not_marked_overdue(self, session, unit_tenant_lease):
        unit, tenant, lease = unit_tenant_lease
        period_start, period_end = month_period(2026, 1)
        invoice = generate_invoice_for_lease(session, lease, period_start, period_end, due_in_days=7)
        session.commit()

        record_payment(session, tenant_id=tenant.id, amount=float(invoice.total),
                        payment_date=date(2026, 1, 10), invoice_id=invoice.id)

        n_marked = mark_overdue_invoices(session, as_of=date(2026, 6, 22))
        session.refresh(invoice)
        assert n_marked == 0
        assert invoice.status == InvoiceStatus.PAID.value
