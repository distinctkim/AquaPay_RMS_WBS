"""
rms/pages/leases.py — Leases page: create new lease, terminate, view history.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from rms.database import get_session
from rms.models import Lease, LeaseStatus
from rms.ui_helpers import tenant_selector, unit_selector, status_badge


def render():
    st.header("📄 Leases")

    tab_create, tab_manage, tab_history = st.tabs(["Create Lease", "Terminate Lease", "Lease History"])

    with tab_create:
        st.subheader("Create New Lease (assign tenant to unit)")
        with get_session() as session:
            tenant = tenant_selector(session, key="lease_create_tenant")
            unit = unit_selector(session, key="lease_create_unit", only_vacant=True)

            if tenant and unit:
                already_leased = tenant.current_unit is not None
                if already_leased:
                    st.warning(f"⚠️ {tenant.full_name} already has an active lease on unit {tenant.current_unit.code}. Terminate it first if you want to move them.")

                with st.form("create_lease_form"):
                    start_date = st.date_input("Lease Start Date", value=date.today())
                    override_rent = st.checkbox("Override unit's default monthly rent for this lease?")
                    rent_amount = None
                    if override_rent:
                        rent_amount = st.number_input("Custom Rent Amount (KES)", min_value=0.0, value=float(unit.monthly_rent), step=500.0)
                    submitted = st.form_submit_button("Create Lease", type="primary", disabled=already_leased)

                    if submitted:
                        lease = Lease(
                            tenant_id=tenant.id, unit_id=unit.id, start_date=start_date,
                            rent_amount=rent_amount, status=LeaseStatus.ACTIVE.value,
                        )
                        session.add(lease)
                        session.commit()
                        st.success(f"✅ Lease created: {tenant.full_name} → {unit.code}")
                        st.rerun()

    with tab_manage:
        st.subheader("Terminate an Active Lease")
        with get_session() as session:
            active_leases = session.query(Lease).filter(Lease.status == LeaseStatus.ACTIVE.value).all()
            if not active_leases:
                st.info("No active leases to terminate.")
            else:
                options = {f"{l.tenant.full_name} — {l.unit.code} (since {l.start_date})": l.id for l in active_leases}
                choice = st.selectbox("Select active lease", list(options.keys()))
                lease_id = options[choice]
                lease = session.get(Lease, lease_id)

                end_date_input = st.date_input("Termination (End) Date", value=date.today())
                if st.button("⚠️ Terminate This Lease", type="primary"):
                    if end_date_input < lease.start_date:
                        st.error("End date cannot be before the lease start date.")
                    else:
                        lease.end_date = end_date_input
                        lease.status = LeaseStatus.TERMINATED.value
                        session.commit()
                        st.success(f"✅ Lease terminated: {lease.tenant.full_name} — {lease.unit.code}")
                        st.rerun()

    with tab_history:
        st.subheader("All Leases")
        with get_session() as session:
            all_leases = session.query(Lease).order_by(Lease.start_date.desc()).all()
            if not all_leases:
                st.caption("No leases on record.")
            else:
                rows = [{
                    "Tenant": l.tenant.full_name, "Unit": l.unit.code,
                    "Start": l.start_date, "End": l.end_date or "—",
                    "Rent (KES)": l.effective_rent(),
                    "Status": status_badge(l.status),
                } for l in all_leases]
                st.dataframe(rows, use_container_width=True, hide_index=True)
