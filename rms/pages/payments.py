"""
rms/pages/payments.py — Payments page: record payment, list with filters/export.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from rms.database import get_session
from rms.models import Payment, Invoice
from rms.invoice_logic import record_payment
from rms.ui_helpers import tenant_selector, unit_selector


def render():
    st.header("💵 Payments")

    tab_record, tab_list = st.tabs(["Record Payment", "Payment List"])

    with tab_record:
        st.subheader("Record a New Payment")
        with get_session() as session:
            tenant = tenant_selector(session, key="payment_tenant")

            if tenant:
                unit = unit_selector(session, key="payment_unit") if st.checkbox("Specify unit (optional)") else None

                tenant_invoices = [i for i in tenant.invoices if i.status != "paid"]
                invoice_choice_map = {
                    f"{i.invoice_number} — {i.period_start.strftime('%Y-%m')} (Outstanding: KES {i.outstanding:,.2f})": i.id
                    for i in tenant_invoices
                }
                invoice_options = ["(Unallocated — apply later)"] + list(invoice_choice_map.keys())

                with st.form("record_payment_form", clear_on_submit=True):
                    selected_invoice_label = st.selectbox("Apply to Invoice (optional)", invoice_options)
                    amount = st.number_input("Amount (KES) *", min_value=0.0, step=100.0)
                    payment_date = st.date_input("Payment Date", value=date.today())
                    payment_method = st.selectbox("Payment Method", ["M-Pesa", "Bank Transfer", "Cash", "Cheque", "Other"])
                    reference = st.text_input("Reference / Transaction Code")
                    notes = st.text_area("Notes (optional)")
                    submitted = st.form_submit_button("Record Payment", type="primary")

                    if submitted:
                        if amount <= 0:
                            st.error("Amount must be greater than 0.")
                        else:
                            invoice_id = None
                            if selected_invoice_label != "(Unallocated — apply later)":
                                invoice_id = invoice_choice_map[selected_invoice_label]

                            record_payment(
                                session, tenant_id=tenant.id, amount=amount,
                                payment_date=payment_date, unit_id=unit.id if unit else None,
                                invoice_id=invoice_id, payment_method=payment_method,
                                reference=reference.strip() or None, notes=notes.strip() or None,
                            )
                            st.success(f"✅ Payment of KES {amount:,.2f} recorded for {tenant.full_name}.")
                            if invoice_id:
                                st.rerun()

    with tab_list:
        st.subheader("All Payments")
        with get_session() as session:
            f1, f2 = st.columns(2)
            start = f1.date_input("From", value=date(date.today().year, 1, 1), key="pay_filter_start")
            end = f2.date_input("To", value=date.today(), key="pay_filter_end")

            payments = (
                session.query(Payment)
                .filter(Payment.payment_date >= start, Payment.payment_date <= end)
                .order_by(Payment.payment_date.desc())
                .all()
            )

            if not payments:
                st.info("No payments found in this date range.")
            else:
                rows = [{
                    "Date": p.payment_date, "Tenant": p.tenant.full_name,
                    "Unit": p.unit.code if p.unit else "—",
                    "Amount (KES)": float(p.amount), "Method": p.payment_method or "—",
                    "Reference": p.reference or "—",
                    "Invoice": p.invoice.invoice_number if p.invoice else "Unallocated",
                } for p in payments]
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)

                csv = df.to_csv(index=False).encode()
                st.download_button("⬇️ Export Payments CSV", data=csv, file_name="payments_export.csv", mime="text/csv")
