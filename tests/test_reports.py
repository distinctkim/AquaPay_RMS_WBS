"""tests/test_reports.py — Report generation with sample data."""
from __future__ import annotations

from datetime import date

from rms.invoicing import generate_invoice_for_lease
from rms.payments import record_payment
from rms.reports import charges_vs_payments, outstanding_balances, payments_summary


def test_payments_summary_for_single_tenant(session, sample_lease):
    invoice = generate_invoice_for_lease(session, sample_lease, 2026, 1)
    session.commit()
    record_payment(session=session, tenant_id=sample_lease.tenant_id, amount=60,
                    payment_date=date(2026, 1, 10), invoice_id=invoice.id)
    session.commit()

    df = payments_summary(session, date(2026, 1, 1), date(2026, 1, 31), tenant_id=sample_lease.tenant_id)
    assert not df.empty
    assert df.iloc[0]["total_paid"] == 60


def test_payments_summary_excludes_payments_outside_range(session, sample_lease):
    invoice = generate_invoice_for_lease(session, sample_lease, 2026, 1)
    session.commit()
    record_payment(session=session, tenant_id=sample_lease.tenant_id, amount=60,
                    payment_date=date(2026, 2, 10), invoice_id=invoice.id)  # outside Jan range
    session.commit()

    df = payments_summary(session, date(2026, 1, 1), date(2026, 1, 31))
    assert df.empty


def test_charges_vs_payments_reports_outstanding_correctly(session, sample_lease):
    invoice = generate_invoice_for_lease(session, sample_lease, 2026, 1)
    session.commit()
    record_payment(session=session, tenant_id=sample_lease.tenant_id, amount=50,
                    payment_date=date(2026, 1, 5), invoice_id=invoice.id)
    session.commit()

    df = charges_vs_payments(session, date(2026, 1, 1), date(2026, 1, 31))
    row = df.iloc[0]
    assert row["charged"] == float(invoice.total)
    assert row["paid"] == 50
    assert row["outstanding"] == float(invoice.total) - 50


def test_outstanding_balances_excludes_fully_paid_invoices(session, sample_lease):
    invoice = generate_invoice_for_lease(session, sample_lease, 2026, 1)
    session.commit()
    record_payment(session=session, tenant_id=sample_lease.tenant_id, amount=float(invoice.total),
                    payment_date=date(2026, 1, 5), invoice_id=invoice.id)
    session.commit()

    df = outstanding_balances(session)
    assert df.empty  # fully paid -> no outstanding balance rows
