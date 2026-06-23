"""
rms/pages/invoices.py — Invoices page: list/filter, manual create, bulk
generate, detail view with PDF download and SMS send.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from rms.database import get_session
from rms.models import Invoice
from rms.invoice_logic import generate_monthly_invoices, generate_invoice_for_lease, month_period
from rms.pdf_invoice import generate_invoice_pdf
from rms.sms_templates import send_invoice_sms
from rms.ui_helpers import status_badge


def render():
    st.header("🧾 Invoices")

    tab_list, tab_generate, tab_detail = st.tabs(["Invoice List", "Generate Invoices", "Invoice Detail / Actions"])

    with tab_list:
        with get_session() as session:
            f1, f2, f3 = st.columns(3)
            status_filter = f1.selectbox("Status", ["All", "draft", "issued", "partial", "paid", "overdue"])
            period_filter = f2.text_input("Period (YYYY-MM, optional)", placeholder="2026-06")

            query = session.query(Invoice)
            if status_filter != "All":
                query = query.filter(Invoice.status == status_filter)
            invoices = query.order_by(Invoice.created_at.desc()).all()

            if period_filter.strip():
                invoices = [i for i in invoices if i.period_start.strftime("%Y-%m") == period_filter.strip()]

            if not invoices:
                st.info("No invoices match the current filters.")
            else:
                rows = [{
                    "Invoice #": i.invoice_number, "Tenant": i.tenant.full_name, "Unit": i.unit.code,
                    "Period": i.period_start.strftime("%Y-%m"), "Total (KES)": float(i.total),
                    "Outstanding (KES)": i.outstanding, "Status": status_badge(i.status),
                    "SMS Sent": "Yes" if i.sent_sms else "No",
                } for i in invoices]
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)

                csv = df.to_csv(index=False).encode()
                st.download_button("⬇️ Export Invoices CSV", data=csv, file_name="invoices_export.csv", mime="text/csv")

    with tab_generate:
        st.subheader("Bulk Generate Invoices for Current Month")
        st.caption("Idempotent: re-running this for a period that already has invoices will skip those leases rather than duplicate them.")
        with get_session() as session:
            today = date.today()
            gen_year = st.number_input("Year", min_value=2020, max_value=2100, value=today.year)
            gen_month = st.number_input("Month", min_value=1, max_value=12, value=today.month)

            if st.button("🧾 Generate Invoices for This Period", type="primary"):
                result = generate_monthly_invoices(session, int(gen_year), int(gen_month))
                st.success(f"✅ Created {len(result.created)} invoice(s).")
                if result.skipped:
                    with st.expander(f"⚠️ {len(result.skipped)} lease(s) skipped (already invoiced)"):
                        for s in result.skipped:
                            st.caption(s)

    with tab_detail:
        st.subheader("Invoice Detail & Actions")
        with get_session() as session:
            invoices = session.query(Invoice).order_by(Invoice.created_at.desc()).all()
            if not invoices:
                st.info("No invoices yet.")
                return

            options = {f"{i.invoice_number} — {i.tenant.full_name} ({i.period_start.strftime('%Y-%m')})": i.id for i in invoices}
            choice = st.selectbox("Select invoice", list(options.keys()))
            invoice = session.get(Invoice, options[choice])

            d1, d2, d3 = st.columns(3)
            d1.metric("Total", f"KES {float(invoice.total):,.2f}")
            d2.metric("Paid", f"KES {invoice.amount_paid:,.2f}")
            d3.metric("Outstanding", f"KES {invoice.outstanding:,.2f}")

            st.write(f"**Status:** {status_badge(invoice.status)}  |  **Due:** {invoice.due_date}")

            st.write("**Items:**")
            line_rows = [{
                "Description": l.description, "Qty": float(l.quantity),
                "Unit Price (KES)": float(l.unit_price), "Total (KES)": float(l.total_amount),
            } for l in invoice.lines]
            st.dataframe(line_rows, use_container_width=True, hide_index=True)

            st.write("**Payments Applied:**")
            if invoice.payments:
                pay_rows = [{"Date": p.payment_date, "Amount (KES)": float(p.amount), "Method": p.payment_method or "—"} for p in invoice.payments]
                st.dataframe(pay_rows, use_container_width=True, hide_index=True)
            else:
                st.caption("No payments applied to this invoice yet.")

            st.divider()
            a1, a2, a3 = st.columns(3)

            with a1:
                if invoice.status != "paid":
                    if st.button("✅ Mark as Paid (manual)"):
                        from rms.models import InvoiceStatus
                        invoice.status = InvoiceStatus.PAID.value
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
                with st.popover("📲 Send SMS"):
                    st.caption("Reuses the existing Africa's Talking integration from the Water Billing module.")
                    api_key = st.text_input("API Key", type="password", key=f"sms_key_{invoice.id}")
                    username = st.text_input("Username", key=f"sms_user_{invoice.id}")
                    sandbox = st.checkbox("Use Sandbox", value=True, key=f"sms_sandbox_{invoice.id}")
                    if st.button("Send Now", key=f"sms_send_{invoice.id}"):
                        if not api_key or not username:
                            st.error("API Key and Username are required.")
                        else:
                            result = send_invoice_sms(session, invoice, api_key, username, sandbox, sms_type="invoice")
                            if result.success:
                                st.success("✅ SMS sent.")
                            else:
                                st.error(f"❌ Failed: {result.message}")
