"""pages/2_Units.py — Units/Properties: list, filter, create/edit, detail view."""
import streamlit as st

from rms.models import Unit, UnitType
from rms.ui_helpers import get_db_session, money

st.set_page_config(page_title="Units", page_icon="🏘️", layout="wide")
session = get_db_session()

st.title("🏘️ Units / Properties")

tab_list, tab_create = st.tabs(["📋 All Units", "➕ Create / Edit Unit"])

with tab_list:
    filter_col1, filter_col2 = st.columns(2)
    occupancy_filter = filter_col1.selectbox("Occupancy", ["All", "Occupied", "Vacant"])
    show_inactive = filter_col2.checkbox("Show inactive units", value=False)

    query = session.query(Unit)
    if not show_inactive:
        query = query.filter_by(is_active=True)
    units = query.all()

    if occupancy_filter == "Occupied":
        units = [u for u in units if u.is_occupied]
    elif occupancy_filter == "Vacant":
        units = [u for u in units if not u.is_occupied]

    if not units:
        st.info("No units match the current filters.")
    else:
        st.dataframe(
            [
                {
                    "Code": u.code,
                    "Address": u.address,
                    "Type": u.unit_type.value,
                    "Monthly Rent": money(u.monthly_rent),
                    "Garbage Fee": money(u.garbage_fee),
                    "Security Fee": money(u.security_fee),
                    "Occupied": "Yes" if u.is_occupied else "No",
                    "Current Tenant": u.current_lease.tenant.full_name if u.is_occupied else "—",
                }
                for u in units
            ],
            use_container_width=True,
        )

        st.divider()
        st.subheader("Unit Detail")
        selected_code = st.selectbox("Select a unit to view details", [u.code for u in units])
        unit = next(u for u in units if u.code == selected_code)

        d1, d2 = st.columns(2)
        with d1:
            st.write(f"**Address:** {unit.address}")
            st.write(f"**Type:** {unit.unit_type.value}")
            st.write(f"**Monthly Rent:** {money(unit.monthly_rent)}")
        with d2:
            st.write(f"**Garbage Fee:** {money(unit.garbage_fee)}")
            st.write(f"**Security Fee:** {money(unit.security_fee)}")
            st.write(f"**Status:** {'Occupied' if unit.is_occupied else 'Vacant'}")

        if unit.leases:
            st.write("**Lease History**")
            st.dataframe(
                [
                    {
                        "Tenant": l.tenant.full_name,
                        "Start": l.start_date,
                        "End": l.end_date or "—",
                        "Status": l.status.value,
                    }
                    for l in unit.leases
                ],
                use_container_width=True,
            )

with tab_create:
    st.subheader("Create New Unit")
    with st.form("create_unit_form", clear_on_submit=True):
        code = st.text_input("Unit Code (unique) *", placeholder="e.g. A1, HSE-12")
        address = st.text_input("Address *")
        unit_type = st.selectbox("Unit Type", [t.value for t in UnitType])
        monthly_rent = st.number_input("Monthly Rent (KES) *", min_value=0.0, step=500.0)
        garbage_fee = st.number_input("Garbage Fee (KES)", min_value=0.0, step=50.0, value=0.0)
        security_fee = st.number_input("Security Fee (KES)", min_value=0.0, step=50.0, value=0.0)

        submitted = st.form_submit_button("Create Unit", type="primary")
        if submitted:
            if not code or not address or monthly_rent <= 0:
                st.error("Unit code, address, and a positive monthly rent are required.")
            elif session.query(Unit).filter_by(code=code).first():
                st.error(f"A unit with code '{code}' already exists.")
            else:
                unit = Unit(
                    code=code,
                    address=address,
                    unit_type=UnitType(unit_type),
                    monthly_rent=monthly_rent,
                    garbage_fee=garbage_fee,
                    security_fee=security_fee,
                )
                session.add(unit)
                session.commit()
                st.success(f"✅ Unit '{code}' created.")
