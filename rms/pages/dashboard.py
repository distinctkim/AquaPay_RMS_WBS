"""
rms/pages/dashboard.py — RMS Dashboard (landing page): KPIs and quick actions.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from rms.database import get_session
from rms.models import Unit, Tenant, Invoice, InvoiceStatus
from rms.invoice_logic import generate_monthly_invoices


def render():
    st.header("📊 RMS Dashboard")

    with get_session() as session:
        total_units = session.query(Unit).filter(Unit.is_active == True).count()  # noqa: E712
        all_units = session.query(Unit).filter(Unit.is_active == True).all()  # noqa: E712
        occupied_units = sum(1 for u in all_units if u.is_occupied)
        active_tenants = session.query(Tenant).filter(Tenant.is_active == True).count()  # noqa: E712

        today = date.today()
        this_month_invoices = session.query(Invoice).filter(
            Invoice.period_start >= today.replace(day=1)
        ).all()
        invoices_this_month = len(this_month_invoices)
        outstanding_this_month = sum(inv.outstanding for inv in this_month_invoices)

        # KPI row
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Units", total_units)
        c2.metric("Occupied Units", occupied_units)
        c3.metric("Active Tenants", active_tenants)
        c4.metric("Outstanding (This Month)", f"KES {outstanding_this_month:,.2f}")
        c5.metric("Invoices Generated (This Month)", invoices_this_month)

        st.divider()
        st.subheader("Quick Actions")

        qa1, qa2, qa3, qa4 = st.columns(4)

        with qa1:
            if st.button("➕ New Tenant", use_container_width=True):
                st.session_state["rms_nav"] = "Tenants"
                st.rerun()
        with qa2:
            if st.button("🏠 New Unit", use_container_width=True):
                st.session_state["rms_nav"] = "Units"
                st.rerun()
        with qa3:
            if st.button("🧾 Generate Invoices Now", use_container_width=True):
                result = generate_monthly_invoices(session, today.year, today.month)
                st.success(f"Created {len(result.created)} invoice(s). Skipped {len(result.skipped)} (already exist).")
        with qa4:
            if st.button("📈 View Reports", use_container_width=True):
                st.session_state["rms_nav"] = "Reports"
                st.rerun()

        st.divider()
        st.subheader("Recent Invoices")
        recent = (
            session.query(Invoice)
            .order_by(Invoice.created_at.desc())
            .limit(10)
            .all()
        )
        if not recent:
            st.caption("No invoices yet. Generate your first batch above, or add tenants/units/leases first.")
        else:
            rows = [{
                "Invoice #": inv.invoice_number,
                "Tenant": inv.tenant.full_name,
                "Unit": inv.unit.code,
                "Period": inv.period_start.strftime("%Y-%m"),
                "Total (KES)": float(inv.total),
                "Status": inv.status,
            } for inv in recent]
            st.dataframe(rows, use_container_width=True, hide_index=True)
