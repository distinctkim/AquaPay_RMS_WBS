"""pages/7_Reports.py — Configurable reports: day/week/month/year, single tenant or all houses."""
from datetime import date, timedelta

import streamlit as st

from rms.models import Tenant
from rms.reports import charges_vs_payments, outstanding_balances, payments_summary, pivot_tenant_by_month
from rms.ui_helpers import get_db_session, money

st.set_page_config(page_title="Reports", page_icon="📊", layout="wide")
session = get_db_session()

st.title("📊 Reports")

# ── Scope & range selection ──────────────────────────────────────────────────
c1, c2 = st.columns(2)
with c1:
    scope = st.radio("Scope", ["All Houses (Aggregate)", "Single Tenant"], horizontal=True)
    tenant_id = None
    if scope == "Single Tenant":
        tenants = session.query(Tenant).all()
        if tenants:
            chosen = st.selectbox("Tenant", [t.full_name for t in tenants])
            tenant_id = next(t.id for t in tenants if t.full_name == chosen)
        else:
            st.warning("No tenants exist yet.")

with c2:
    granularity = st.selectbox("Quick Range", ["Today", "This Week", "This Month", "This Year", "Custom"])

    today = date.today()
    if granularity == "Today":
        start, end = today, today
    elif granularity == "This Week":
        start, end = today - timedelta(days=today.weekday()), today
    elif granularity == "This Month":
        start, end = today.replace(day=1), today
    elif granularity == "This Year":
        start, end = today.replace(month=1, day=1), today
    else:
        custom_range = st.date_input("Custom Date Range", value=(today.replace(day=1), today))
        start, end = custom_range if isinstance(custom_range, tuple) and len(custom_range) == 2 else (today, today)

st.caption(f"Showing data from **{start}** to **{end}**.")
st.divider()

report_type = st.selectbox(
    "Report Type",
    ["Payments Summary", "Charges vs Payments", "Outstanding Balances", "Tenant-by-Month Pivot (Yearly)"],
)

if report_type == "Payments Summary":
    df = payments_summary(session, start, end, tenant_id)
    if df.empty:
        st.info("No payments found for this range/scope.")
    else:
        st.dataframe(df, use_container_width=True)
        st.bar_chart(df.set_index("tenant_name")["total_paid"])
        st.metric("Total Payments", money(df["total_paid"].sum()))

elif report_type == "Charges vs Payments":
    df = charges_vs_payments(session, start, end, tenant_id)
    if df.empty:
        st.info("No invoices found for this range/scope.")
    else:
        st.dataframe(df, use_container_width=True)
        chart_df = df.set_index("tenant_name")[["charged", "paid", "outstanding"]]
        st.bar_chart(chart_df)

elif report_type == "Outstanding Balances":
    df = outstanding_balances(session, as_of=end)
    if tenant_id is not None and not df.empty:
        tenant_name = next(t.full_name for t in session.query(Tenant).all() if t.id == tenant_id)
        df = df[df["tenant_name"] == tenant_name]
    if df.empty:
        st.info("No outstanding balances for this range/scope.")
    else:
        st.dataframe(df, use_container_width=True)
        st.metric("Total Outstanding", money(df["outstanding"].sum()))

elif report_type == "Tenant-by-Month Pivot (Yearly)":
    year = st.number_input("Year", min_value=2020, max_value=2100, value=date.today().year, step=1)
    df = pivot_tenant_by_month(session, int(year))
    if df.empty:
        st.info(f"No invoices found for {int(year)}.")
    else:
        st.dataframe(df, use_container_width=True)

st.divider()
st.caption(
    "To export: use the ⤓ download icon in the top-right corner of any table above "
    "(built into Streamlit's dataframe widget), or use the CSV buttons on the Invoices/Payments pages "
    "for raw transactional exports."
)
