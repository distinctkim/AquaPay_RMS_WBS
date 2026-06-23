"""pages/5_Payments.py — Record payments, list/filter, export."""
from datetime import date

import pandas as pd
import streamlit as st

from rms.models import Invoice, InvoiceStatus, Payment, Tenant
from rms.payments import record_payment
from rms.ui_helpers import get_db_session, money

st.set_page_config(page_title="Payments", page_icon="💵", layout="wide")
session = get_db_session()

st.title("💵 Payments")

tab_record, tab_list = st.tabs(["➕ Record Payment", "📋 Payment List"])

with tab_record:
    tenants = session.query(Tenant).filter_by(is_active=True).all()
    if not tenants:
        st.warning("No tenants exist yet.")
    else:
        tenant_choice = st.selectbox("Tenant *", [t.full_name for t in tenants], key="pay_tenant")
        tenant = next(t for t in tenants if t.full_name == tenant_choice)

        open_invoices = [
            i for i in tenant.invoices
            if i.status in (InvoiceStatus.ISSUED, InvoiceStatus.PARTIAL, InvoiceStatus.OVERDUE)
        ]
        invoice_labels = ["— Unallocated (apply later) —"] + [
            f"{i.invoice_number}  (Outstanding: {money(i.outstanding_balance)})" for i in open_invoices
        ]

        with st.form("record_payment_form", clear_on_submit=True):
            invoice_choice = st.selectbox("Apply to Invoice (optional)", invoice_labels)
            amount = st.number_input("Amount (KES) *", min_value=0.0, step=100.0)
            payment_date = st.date_input("Payment Date *", value=date.today())
            payment_method = st.selectbox("Payment Method", ["M-Pesa", "Bank Transfer", "Cash", "Cheque", "Other"])
            reference = st.text_input("Reference (e.g. M-Pesa code)")
            notes = st.text_area("Notes (optional)")

            submitted = st.form_submit_button("Record Payment", type="primary")
            if submitted:
                if amount <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    invoice_id = None
                    if invoice_choice != invoice_labels[0]:
                        selected_invoice = open_invoices[invoice_labels.index(invoice_choice) - 1]
                        invoice_id = selected_invoice.id

                    result = record_payment(
                        session=session,
                        tenant_id=tenant.id,
                        amount=amount,
                        payment_date=payment_date,
                        payment_method=payment_method,
                        invoice_id=invoice_id,
                        reference=reference or None,
                        notes=notes or None,
                    )
                    session.commit()

                    st.success(f"✅ Payment of {money(amount)} recorded for {tenant.full_name}.")
                    if result.invoice_status is not None:
                        st.info(f"Invoice status is now **{result.invoice_status.value}**. "
                                f"Outstanding balance: {money(result.outstanding_balance)}.")
                    if result.overpayment_credit > 0:
                        st.warning(f"⚠️ This payment exceeds the invoice total by "
                                   f"{money(result.overpayment_credit)}. This is tracked as tenant credit.")

with tab_list:
    f1, f2 = st.columns(2)
    start = f1.date_input("From", value=date.today().replace(day=1))
    end = f2.date_input("To", value=date.today())

    payments = (
        session.query(Payment)
        .filter(Payment.payment_date >= start, Payment.payment_date <= end)
        .order_by(Payment.payment_date.desc())
        .all()
    )

    if not payments:
        st.info("No payments recorded in this date range.")
    else:
        df = pd.DataFrame([
            {
                "Date": p.payment_date,
                "Tenant": p.tenant.full_name,
                "Amount": float(p.amount),
                "Method": p.payment_method,
                "Reference": p.reference or "—",
                "Linked Invoice": p.invoice.invoice_number if p.invoice else "Unallocated",
            }
            for p in payments
        ])
        st.dataframe(df, use_container_width=True)
        st.metric("Total Payments in Range", money(df["Amount"].sum()))

        csv = df.to_csv(index=False).encode()
        st.download_button("⬇️ Download CSV", data=csv, file_name="payments_export.csv", mime="text/csv")
