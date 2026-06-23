"""pages/6_Invoices.py — Invoice listing, manual/bulk generation, detail actions."""
from datetime import date

import pandas as pd
import streamlit as st

from rms.invoicing import generate_invoices_for_month
from rms.models import Invoice, InvoiceStatus, LeaseStatus
from rms.pdf import generate_invoice_pdf
from rms.sms_templates import send_invoice_sms
from rms.ui_helpers import get_db_session, money, sidebar_sms_credentials

st.set_page_config(page_title="Invoices", page_icon="🧾", layout="wide")
session = get_db_session()
api_key, sms_username, sandbox = sidebar_sms_credentials()

st.title("🧾 Invoices")

tab_generate, tab_list, tab_detail = st.tabs(["⚙️ Generate Invoices", "📋 All Invoices", "🔍 Invoice Detail"])

with tab_generate:
    st.subheader("Bulk-Generate Invoices for a Month")
    st.caption(
        "Generation is idempotent — running this twice for the same month will not create "
        "duplicate invoices for a lease that already has one."
    )

    c1, c2 = st.columns(2)
    year = c1.number_input("Year", min_value=2020, max_value=2100, value=date.today().year, step=1)
    month = c2.number_input("Month", min_value=1, max_value=12, value=date.today().month, step=1)

    if st.button("Generate Invoices Now", type="primary"):
        invoices = generate_invoices_for_month(session, int(year), int(month))
        session.commit()
        newly_created = [i for i in invoices if i is not None]
        st.success(f"✅ Processed {len(newly_created)} active lease(s) for {int(year)}-{int(month):02d}. "
                   f"Existing invoices for this period were skipped, not duplicated.")

with tab_list:
    filter_status = st.selectbox("Filter by status", ["All"] + [s.value for s in InvoiceStatus])
    query = session.query(Invoice).order_by(Invoice.created_at.desc())
    invoices = query.all()
    if filter_status != "All":
        invoices = [i for i in invoices if i.status.value == filter_status]

    if not invoices:
        st.info("No invoices match this filter.")
    else:
        df = pd.DataFrame([
            {
                "Invoice #": i.invoice_number,
                "Tenant": i.tenant.full_name,
                "Unit": i.unit.code,
                "Period": i.period_start.strftime("%Y-%m"),
                "Due": i.due_date,
                "Total": float(i.total),
                "Outstanding": i.outstanding_balance,
                "Status": i.status.value,
            }
            for i in invoices
        ])
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode()
        st.download_button("⬇️ Download CSV", data=csv, file_name="invoices_export.csv", mime="text/csv")

with tab_detail:
    all_invoices = session.query(Invoice).order_by(Invoice.created_at.desc()).all()
    if not all_invoices:
        st.info("No invoices yet — generate some in the first tab.")
    else:
        labels = [f"{i.invoice_number} — {i.tenant.full_name} ({i.unit.code})" for i in all_invoices]
        choice = st.selectbox("Select invoice", labels)
        invoice = all_invoices[labels.index(choice)]

        st.write(f"**Tenant:** {invoice.tenant.full_name}  |  **Unit:** {invoice.unit.code}")
        st.write(f"**Period:** {invoice.period_start} – {invoice.period_end}  |  **Due:** {invoice.due_date}")
        st.write(f"**Status:** {invoice.status.value}")

        st.write("**Line Items**")
        st.dataframe(
            [{"Description": l.description, "Qty": float(l.quantity),
              "Unit Price": money(l.unit_price), "Total": money(l.total_amount)} for l in invoice.lines],
            use_container_width=True,
        )

        m1, m2, m3 = st.columns(3)
        m1.metric("Total", money(invoice.total))
        m2.metric("Paid", money(invoice.amount_paid))
        m3.metric("Outstanding", money(invoice.outstanding_balance))

        st.divider()
        a1, a2, a3, a4 = st.columns(4)

        with a1:
            if invoice.status != InvoiceStatus.PAID:
                if st.button("✅ Mark as Paid"):
                    invoice.status = InvoiceStatus.PAID
                    session.commit()
                    st.success("Marked as paid.")
                    st.rerun()

        with a2:
            pdf_bytes = generate_invoice_pdf(invoice)
            st.download_button(
                "📄 Download PDF", data=pdf_bytes,
                file_name=f"{invoice.invoice_number}.pdf", mime="application/pdf",
            )

        with a3:
            if st.button("📲 Send Invoice SMS"):
                if not api_key or not sms_username:
                    st.error("Enter SMS credentials in the sidebar first.")
                else:
                    result = send_invoice_sms(session, invoice, api_key, sms_username, sandbox, reminder=False)
                    session.commit()
                    if result.success:
                        st.success("SMS sent.")
                    else:
                        st.error(f"SMS failed: {result.message}")

        with a4:
            if st.button("⏰ Send Reminder SMS"):
                if not api_key or not sms_username:
                    st.error("Enter SMS credentials in the sidebar first.")
                else:
                    result = send_invoice_sms(session, invoice, api_key, sms_username, sandbox, reminder=True)
                    session.commit()
                    if result.success:
                        st.success("Reminder sent.")
                    else:
                        st.error(f"Reminder failed: {result.message}")
