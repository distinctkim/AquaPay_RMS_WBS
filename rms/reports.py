"""
rms/reports.py — Configurable reporting (spec section 9).

Supports:
  - granularity: day / week / month / year (via explicit date range — the
    Streamlit Reports page resolves a quick-option choice into start/end
    dates and passes them in here, keeping date-math out of this module)
  - scope: a single tenant, or all houses (aggregate)

Each function returns a pandas DataFrame so it can be displayed directly
in Streamlit (st.dataframe) and exported to CSV/PDF without reshaping.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from rms.models import Invoice, Payment, Tenant


def payments_summary(
    session: Session,
    start: date,
    end: date,
    tenant_id: int | None = None,
) -> pd.DataFrame:
    """Total payments received per tenant within [start, end]."""
    q = (
        session.query(Payment)
        .filter(Payment.payment_date >= start, Payment.payment_date <= end)
    )
    if tenant_id is not None:
        q = q.filter(Payment.tenant_id == tenant_id)

    rows = []
    for p in q.all():
        rows.append({
            "tenant_id": p.tenant_id,
            "tenant_name": p.tenant.full_name,
            "amount": float(p.amount),
            "payment_date": p.payment_date,
            "method": p.payment_method,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return (
        df.groupby(["tenant_id", "tenant_name"], as_index=False)["amount"]
        .sum()
        .rename(columns={"amount": "total_paid"})
        .sort_values("total_paid", ascending=False)
    )


def charges_vs_payments(
    session: Session,
    start: date,
    end: date,
    tenant_id: int | None = None,
) -> pd.DataFrame:
    """
    Per-tenant (or single-tenant) comparison of total charges (invoiced)
    vs. total payments received, plus outstanding balance, for invoices
    whose period falls within [start, end].
    """
    q = session.query(Invoice).filter(
        Invoice.period_start >= start, Invoice.period_start <= end
    )
    if tenant_id is not None:
        q = q.filter(Invoice.tenant_id == tenant_id)

    rows = []
    for inv in q.all():
        rows.append({
            "tenant_id": inv.tenant_id,
            "tenant_name": inv.tenant.full_name,
            "unit_code": inv.unit.code,
            "invoice_number": inv.invoice_number,
            "period": inv.period_start.strftime("%Y-%m"),
            "charged": float(inv.total),
            "paid": inv.amount_paid,
            "outstanding": inv.outstanding_balance,
            "status": inv.status.value,
        })

    return pd.DataFrame(rows)


def outstanding_balances(session: Session, as_of: date | None = None) -> pd.DataFrame:
    """All invoices with a non-zero outstanding balance, across all tenants/units."""
    q = session.query(Invoice)
    if as_of is not None:
        q = q.filter(Invoice.period_start <= as_of)

    rows = []
    for inv in q.all():
        if inv.outstanding_balance > 0:
            rows.append({
                "tenant_name": inv.tenant.full_name,
                "unit_code": inv.unit.code,
                "invoice_number": inv.invoice_number,
                "due_date": inv.due_date,
                "total": float(inv.total),
                "paid": inv.amount_paid,
                "outstanding": inv.outstanding_balance,
                "status": inv.status.value,
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("outstanding", ascending=False)
    return df


def pivot_tenant_by_month(session: Session, year: int) -> pd.DataFrame:
    """
    Pivot-style report: tenants as rows, months (Jan..Dec of `year`) as
    columns, invoice totals as values — matches spec section 9's example
    "months as columns, tenants as rows" output.
    """
    q = session.query(Invoice).filter(
        Invoice.period_start >= date(year, 1, 1),
        Invoice.period_start <= date(year, 12, 31),
    )

    rows = [
        {
            "tenant_name": inv.tenant.full_name,
            "month": inv.period_start.strftime("%b"),
            "total": float(inv.total),
        }
        for inv in q.all()
    ]
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    pivot = df.pivot_table(index="tenant_name", columns="month", values="total", aggfunc="sum", fill_value=0)
    month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    existing_cols = [m for m in month_order if m in pivot.columns]
    return pivot[existing_cols]
