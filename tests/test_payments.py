"""tests/test_payments.py — Payment allocation, partial/overpayment handling."""
from __future__ import annotations

from datetime import date

import pytest

from rms.invoicing import generate_invoice_for_lease
from rms.models import InvoiceStatus
from rms.payments import record_payment, tenant_credit_balance


def test_partial_payment_sets_status_partial_and_correct_balance(session, sample_lease):
    """
    Spec section 12 worked example: invoice total 130, payment 50
    -> outstanding 80, status partial.
    """
    invoice = generate_invoice_for_lease(session, sample_lease, 2026, 1)
    session.commit()

    result = record_payment(
        session=session, tenant_id=sample_lease.tenant_id, amount=50,
        payment_date=date(2026, 1, 5), invoice_id=invoice.id,
    )
    session.commit()

    assert result.invoice_status == InvoiceStatus.PARTIAL
    assert result.outstanding_balance == pytest.approx(invoice.total - 50)
    assert invoice.outstanding_balance == pytest.approx(invoice.total - 50)


def test_full_payment_sets_status_paid(session, sample_lease):
    invoice = generate_invoice_for_lease(session, sample_lease, 2026, 1)
    session.commit()

    result = record_payment(
        session=session, tenant_id=sample_lease.tenant_id, amount=float(invoice.total),
        payment_date=date(2026, 1, 5), invoice_id=invoice.id,
    )
    session.commit()

    assert result.invoice_status == InvoiceStatus.PAID
    assert result.outstanding_balance == 0


def test_multiple_partial_payments_accumulate_to_paid(session, sample_lease):
    invoice = generate_invoice_for_lease(session, sample_lease, 2026, 1)
    session.commit()
    total = float(invoice.total)

    record_payment(session=session, tenant_id=sample_lease.tenant_id, amount=total / 2,
                    payment_date=date(2026, 1, 5), invoice_id=invoice.id)
    session.commit()
    assert invoice.status == InvoiceStatus.PARTIAL

    result = record_payment(session=session, tenant_id=sample_lease.tenant_id, amount=total / 2,
                             payment_date=date(2026, 1, 10), invoice_id=invoice.id)
    session.commit()
    assert result.invoice_status == InvoiceStatus.PAID
    assert invoice.outstanding_balance == 0


def test_overpayment_is_tracked_as_credit_not_lost(session, sample_lease):
    invoice = generate_invoice_for_lease(session, sample_lease, 2026, 1)
    session.commit()
    total = float(invoice.total)

    result = record_payment(
        session=session, tenant_id=sample_lease.tenant_id, amount=total + 20,
        payment_date=date(2026, 1, 5), invoice_id=invoice.id,
    )
    session.commit()

    assert result.invoice_status == InvoiceStatus.PAID
    assert result.overpayment_credit == pytest.approx(20)
    assert tenant_credit_balance(session, sample_lease.tenant_id) == pytest.approx(20)


def test_unallocated_payment_does_not_touch_any_invoice(session, sample_lease):
    invoice = generate_invoice_for_lease(session, sample_lease, 2026, 1)
    session.commit()

    result = record_payment(
        session=session, tenant_id=sample_lease.tenant_id, amount=50,
        payment_date=date(2026, 1, 5), invoice_id=None,
    )
    session.commit()

    assert result.invoice_status is None
    assert invoice.status == InvoiceStatus.ISSUED  # unchanged
    assert invoice.outstanding_balance == float(invoice.total)


def test_zero_payment_amount_rejected(session, sample_lease):
    with pytest.raises(ValueError):
        record_payment(session=session, tenant_id=sample_lease.tenant_id, amount=0,
                        payment_date=date(2026, 1, 5))
