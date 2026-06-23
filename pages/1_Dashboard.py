"""pages/1_Dashboard.py — RMS landing page: KPIs and quick actions."""
import streamlit as st
from datetime import date

from rms.models import Invoice, InvoiceStatus, Lease, LeaseStatus, Tenant, Unit
from rms.ui_helpers import get_db_session, money

st.set_page_config(page_title="RMS Dashboard", page_icon="🏠", layout="wide")
session = get_db_session()

st.title("🏠 Rental Management Dashboard")

today = date.today()
current_month_start = today.replace(day=1)

total_units = session.query(Unit).filter_by(is_active=True).count()
occupied_units = session.query(Lease).filter_by(status=LeaseStatus.ACTIVE).count()
active_tenants = session.query(Tenant).filter_by(is_active=True).count()

invoices_this_month = (
    session.query(Invoice)
    .filter(Invoice.period_start == current_month_start)
    .all()
)
invoices_generated = len(invoices_this_month)
outstanding_this_month = sum(inv.outstanding_balance for inv in invoices_this_month)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Units", total_units)
col2.metric("Occupied Units", occupied_units)
col3.metric("Active Tenants", active_tenants)
col4.metric("Invoices This Month", invoices_generated)
col5.metric("Outstanding This Month", money(outstanding_this_month))

st.divider()
st.subheader("Quick Actions")

c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button("➕ Create Tenant", use_container_width=True):
        st.switch_page("pages/3_Tenants.py")
with c2:
    if st.button("➕ Create Unit", use_container_width=True):
        st.switch_page("pages/2_Units.py")
with c3:
    if st.button("🧾 Generate Invoices", use_container_width=True):
        st.switch_page("pages/6_Invoices.py")
with c4:
    if st.button("📊 View Reports", use_container_width=True):
        st.switch_page("pages/7_Reports.py")

st.divider()
st.subheader("Recent Invoices")
recent = session.query(Invoice).order_by(Invoice.created_at.desc()).limit(10).all()
if recent:
    st.dataframe(
        [
            {
                "Invoice #": inv.invoice_number,
                "Tenant": inv.tenant.full_name,
                "Unit": inv.unit.code,
                "Total": money(inv.total),
                "Outstanding": money(inv.outstanding_balance),
                "Status": inv.status.value,
            }
            for inv in recent
        ],
        use_container_width=True,
    )
else:
    st.info("No invoices yet. Generate your first invoices from the Invoices page.")
