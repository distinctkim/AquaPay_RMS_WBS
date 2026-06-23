"""
rms/pages/settings_page.py — Settings page: fee defaults, SMS config,
invoice scheme/scheduling info, data export.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd

from rms.database import get_session
from rms.models import FeeType, Invoice, Payment, Tenant, Unit, Lease


def render():
    st.header("⚙️ Settings")

    tab_fees, tab_sms, tab_sched, tab_export = st.tabs(
        ["Fee Defaults", "SMS Settings", "Scheduling Info", "Data Export"]
    )

    with tab_fees:
        st.subheader("Default Fee Amounts")
        st.caption("Unit-level fees override these defaults; these apply when a unit doesn't set its own.")
        with get_session() as session:
            fee_types = session.query(FeeType).all()
            for fee in fee_types:
                new_val = st.number_input(
                    f"{fee.name.capitalize()} default amount (KES)",
                    min_value=0.0, value=float(fee.default_amount), step=50.0, key=f"fee_{fee.id}",
                )
                if new_val != float(fee.default_amount):
                    fee.default_amount = new_val
                    session.commit()
                    st.success(f"Updated {fee.name} default to KES {new_val:,.2f}")

    with tab_sms:
        st.subheader("SMS Settings")
        st.caption(
            "SMS credentials are entered directly on the Invoices page when sending, "
            "consistent with the existing Water Billing module — they are never stored in the database."
        )
        st.info(
            "Reused integration: Africa's Talking (same provider as the Water Billing SMS Notifier). "
            "Phone numbers must be in Kenyan format 2547XXXXXXXX (validated automatically)."
        )
        st.write("**SMS Templates in use:**")
        st.code(
            "Invoice: \"Dear {tenant_name}, your invoice {invoice_number} for unit {unit_code} "
            "is ready. Total due: KES {total_due}. Due date: {due_date}...\"\n\n"
            "Reminder (7 days before): \"...is due on {due_date}, in 7 days...\"\n"
            "Reminder (due today): \"...is due TODAY ({due_date})...\"\n"
            "Reminder (overdue): \"...was due on {due_date} and is now OVERDUE...\"",
            language=None,
        )

    with tab_sched:
        st.subheader("Scheduling Configuration")
        st.caption(
            "The scheduler (rms/scheduler.py) is started separately from the Streamlit UI — "
            "see README_RMS.md for how to run it locally or in production."
        )
        invoice_day = st.number_input("Generate invoices on day of month", min_value=1, max_value=28, value=28)
        st.caption(f"Configured day: {invoice_day}. Restart the scheduler process for this to take effect (see README_RMS.md).")
        st.write("**Reminder schedule (fixed, documented in rms/scheduler.py):**")
        st.markdown(
            "- 7 days before due date\n"
            "- On the due date\n"
            "- Daily for invoices already marked overdue"
        )

    with tab_export:
        st.subheader("Export All Data")
        with get_session() as session:
            exp_col1, exp_col2, exp_col3 = st.columns(3)

            with exp_col1:
                tenants = session.query(Tenant).all()
                df = pd.DataFrame([{"name": t.full_name, "phone": t.phone_number, "email": t.email} for t in tenants])
                st.download_button("⬇️ Tenants CSV", df.to_csv(index=False).encode(), "tenants_export.csv", "text/csv")

            with exp_col2:
                invoices = session.query(Invoice).all()
                df = pd.DataFrame([{"invoice_number": i.invoice_number, "tenant": i.tenant.full_name, "total": float(i.total), "status": i.status} for i in invoices])
                st.download_button("⬇️ Invoices CSV", df.to_csv(index=False).encode(), "invoices_export.csv", "text/csv")

            with exp_col3:
                payments = session.query(Payment).all()
                df = pd.DataFrame([{"tenant": p.tenant.full_name, "amount": float(p.amount), "date": p.payment_date} for p in payments])
                st.download_button("⬇️ Payments CSV", df.to_csv(index=False).encode(), "payments_export.csv", "text/csv")
