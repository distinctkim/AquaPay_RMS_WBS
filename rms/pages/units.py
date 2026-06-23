"""
rms/pages/units.py — Units / Properties page: list, filter, create/edit units.
"""
from __future__ import annotations

import streamlit as st

from rms.database import get_session
from rms.models import Unit
from rms.ui_helpers import status_badge


def render():
    st.header("🏠 Units / Properties")

    tab_list, tab_create = st.tabs(["List Units", "Create / Edit Unit"])

    with tab_list:
        with get_session() as session:
            filter_col1, filter_col2 = st.columns(2)
            occupancy_filter = filter_col1.selectbox("Occupancy", ["All", "Occupied", "Vacant"])
            min_rent = filter_col2.number_input("Minimum rent (KES)", min_value=0, value=0, step=500)

            units = session.query(Unit).order_by(Unit.code).all()

            filtered = []
            for u in units:
                if occupancy_filter == "Occupied" and not u.is_occupied:
                    continue
                if occupancy_filter == "Vacant" and u.is_occupied:
                    continue
                if float(u.monthly_rent) < min_rent:
                    continue
                filtered.append(u)

            if not filtered:
                st.info("No units match the current filters.")
            else:
                rows = [{
                    "Code": u.code,
                    "Address": u.address or "—",
                    "Type": u.unit_type,
                    "Monthly Rent (KES)": float(u.monthly_rent),
                    "Garbage Fee": float(u.garbage_fee),
                    "Security Fee": float(u.security_fee),
                    "Status": "🟢 Occupied" if u.is_occupied else "⚪ Vacant",
                    "Current Tenant": u.current_lease.tenant.full_name if u.current_lease else "—",
                } for u in filtered]
                st.dataframe(rows, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("Unit Detail")
            if filtered:
                detail_choice = st.selectbox("Select a unit to view details", [u.code for u in filtered])
                unit = next(u for u in filtered if u.code == detail_choice)

                d1, d2 = st.columns(2)
                with d1:
                    st.write(f"**Address:** {unit.address or '—'}")
                    st.write(f"**Type:** {unit.unit_type}")
                    st.write(f"**Monthly Rent:** KES {float(unit.monthly_rent):,.2f}")
                with d2:
                    st.write(f"**Garbage Fee:** KES {float(unit.garbage_fee):,.2f}")
                    st.write(f"**Security Fee:** KES {float(unit.security_fee):,.2f}")
                    st.write(f"**Active:** {'Yes' if unit.is_active else 'No'}")

                st.write("**Lease History:**")
                if unit.leases:
                    lease_rows = [{
                        "Tenant": l.tenant.full_name,
                        "Start": l.start_date,
                        "End": l.end_date or "—",
                        "Status": status_badge(l.status),
                    } for l in unit.leases]
                    st.dataframe(lease_rows, use_container_width=True, hide_index=True)
                else:
                    st.caption("No lease history for this unit.")

                st.write("**Water Consumption History:**")
                if unit.water_charges:
                    wc_rows = [{
                        "Month": wc.month,
                        "Consumption": float(wc.consumption) if wc.consumption is not None else "—",
                        "Charge (KES)": float(wc.charge_amount),
                    } for wc in unit.water_charges]
                    st.dataframe(wc_rows, use_container_width=True, hide_index=True)
                else:
                    st.caption("No water charge records for this unit yet.")

    with tab_create:
        st.subheader("Create New Unit")
        with st.form("create_unit_form", clear_on_submit=True):
            code = st.text_input("Unit Code / Name *", placeholder="e.g. A1, House-12")
            address = st.text_input("Address")
            unit_type = st.selectbox("Unit Type", ["house", "room"])
            monthly_rent = st.number_input("Monthly Rent (KES) *", min_value=0.0, step=500.0)
            garbage_fee = st.number_input("Garbage Fee (KES)", min_value=0.0, step=50.0, value=0.0)
            security_fee = st.number_input("Security Fee (KES)", min_value=0.0, step=50.0, value=0.0)
            submitted = st.form_submit_button("Create Unit", type="primary")

            if submitted:
                if not code.strip():
                    st.error("Unit Code / Name is required.")
                elif monthly_rent <= 0:
                    st.error("Monthly Rent must be greater than 0.")
                else:
                    with get_session() as session:
                        existing = session.query(Unit).filter(Unit.code == code.strip()).first()
                        if existing:
                            st.error(f"A unit with code '{code}' already exists.")
                        else:
                            unit = Unit(
                                code=code.strip(), address=address.strip() or None,
                                unit_type=unit_type, monthly_rent=monthly_rent,
                                garbage_fee=garbage_fee, security_fee=security_fee,
                            )
                            session.add(unit)
                            session.commit()
                            st.success(f"✅ Unit '{code}' created.")

        st.divider()
        st.subheader("Edit Existing Unit")
        with get_session() as session:
            units = session.query(Unit).order_by(Unit.code).all()
            if not units:
                st.caption("No units to edit yet.")
            else:
                edit_choice = st.selectbox("Select unit to edit", [u.code for u in units], key="edit_unit_choice")
                unit = next(u for u in units if u.code == edit_choice)

                with st.form("edit_unit_form"):
                    new_address = st.text_input("Address", value=unit.address or "")
                    new_rent = st.number_input("Monthly Rent (KES)", min_value=0.0, value=float(unit.monthly_rent), step=500.0)
                    new_garbage = st.number_input("Garbage Fee (KES)", min_value=0.0, value=float(unit.garbage_fee), step=50.0)
                    new_security = st.number_input("Security Fee (KES)", min_value=0.0, value=float(unit.security_fee), step=50.0)
                    new_active = st.checkbox("Active", value=unit.is_active)
                    update_submitted = st.form_submit_button("Save Changes", type="primary")

                    if update_submitted:
                        unit.address = new_address.strip() or None
                        unit.monthly_rent = new_rent
                        unit.garbage_fee = new_garbage
                        unit.security_fee = new_security
                        unit.is_active = new_active
                        session.commit()
                        st.success("✅ Unit updated.")
                        st.rerun()
