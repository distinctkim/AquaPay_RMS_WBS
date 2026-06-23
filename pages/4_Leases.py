"""pages/4_Leases.py — Create/terminate leases, view lease history."""
from datetime import date

import streamlit as st

from rms.models import Lease, LeaseStatus, Tenant, Unit
from rms.ui_helpers import get_db_session, money

st.set_page_config(page_title="Leases", page_icon="📄", layout="wide")
session = get_db_session()

st.title("📄 Leases")

tab_create, tab_terminate, tab_history = st.tabs(["➕ New Lease", "🛑 Terminate Lease", "📜 Lease History"])

with tab_create:
    st.subheader("Assign a Tenant to a Unit")

    tenants = session.query(Tenant).filter_by(is_active=True).all()
    vacant_units = [u for u in session.query(Unit).filter_by(is_active=True).all() if not u.is_occupied]

    if not tenants:
        st.warning("No active tenants exist yet. Create one on the Tenants page first.")
    elif not vacant_units:
        st.warning("No vacant units available. All active units are currently occupied.")
    else:
        with st.form("create_lease_form", clear_on_submit=True):
            tenant_choice = st.selectbox("Tenant *", [t.full_name for t in tenants])
            unit_choice = st.selectbox("Vacant Unit *", [u.code for u in vacant_units])
            start_date = st.date_input("Lease Start Date *", value=date.today())
            override_rent = st.checkbox("Override unit's default rent for this lease")
            rent_amount = None
            if override_rent:
                rent_amount = st.number_input("Override Rent Amount (KES)", min_value=0.0, step=500.0)

            submitted = st.form_submit_button("Create Lease", type="primary")
            if submitted:
                tenant = next(t for t in tenants if t.full_name == tenant_choice)
                unit = next(u for u in vacant_units if u.code == unit_choice)

                # Idempotency / sanity guard: a tenant shouldn't hold two
                # simultaneous active leases under this simplified model.
                if any(l.status == LeaseStatus.ACTIVE for l in tenant.leases):
                    st.error(f"{tenant.full_name} already has an active lease. Terminate it first.")
                else:
                    lease = Lease(
                        tenant_id=tenant.id,
                        unit_id=unit.id,
                        start_date=start_date,
                        rent_amount=rent_amount if override_rent else None,
                        status=LeaseStatus.ACTIVE,
                    )
                    session.add(lease)
                    session.commit()
                    st.success(f"✅ Lease created: {tenant.full_name} → Unit {unit.code}")

with tab_terminate:
    st.subheader("Terminate an Active Lease")
    active_leases = session.query(Lease).filter_by(status=LeaseStatus.ACTIVE).all()

    if not active_leases:
        st.info("No active leases to terminate.")
    else:
        labels = [f"{l.tenant.full_name} — Unit {l.unit.code} (since {l.start_date})" for l in active_leases]
        choice = st.selectbox("Select active lease", labels)
        lease = active_leases[labels.index(choice)]

        end_date = st.date_input("End Date", value=date.today())
        if st.button("Terminate Lease", type="primary"):
            if end_date < lease.start_date:
                st.error("End date cannot be before the lease start date.")
            else:
                lease.end_date = end_date
                lease.status = LeaseStatus.TERMINATED
                session.commit()
                st.success(f"Lease for {lease.tenant.full_name} (Unit {lease.unit.code}) terminated as of {end_date}.")

with tab_history:
    st.subheader("All Leases")
    all_leases = session.query(Lease).order_by(Lease.start_date.desc()).all()
    if all_leases:
        st.dataframe(
            [
                {
                    "Tenant": l.tenant.full_name,
                    "Unit": l.unit.code,
                    "Start": l.start_date,
                    "End": l.end_date or "—",
                    "Rent": money(l.effective_rent()),
                    "Status": l.status.value,
                }
                for l in all_leases
            ],
            use_container_width=True,
        )
    else:
        st.info("No leases recorded yet.")
