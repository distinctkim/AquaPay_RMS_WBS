"""pages/3_Tenants.py — Tenants: list, detail (payments/invoices/leases), create/edit."""
import re

import streamlit as st

from rms.models import Tenant
from rms.ui_helpers import get_db_session, money

st.set_page_config(page_title="Tenants", page_icon="👤", layout="wide")
session = get_db_session()

st.title("👤 Tenants")

PHONE_RE = re.compile(r"^254(7\d{8}|1\d{8})$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalise_phone(raw: str) -> str | None:
    phone = raw.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+"):
        phone = phone[1:]
    if phone.startswith("0") and len(phone) == 10:
        phone = "254" + phone[1:]
    return phone if PHONE_RE.match(phone) else None


tab_list, tab_create = st.tabs(["📋 All Tenants", "➕ Create / Edit Tenant"])

with tab_list:
    show_inactive = st.checkbox("Show inactive tenants", value=False)
    query = session.query(Tenant)
    if not show_inactive:
        query = query.filter_by(is_active=True)
    tenants = query.all()

    if not tenants:
        st.info("No tenants yet. Create one in the second tab.")
    else:
        st.dataframe(
            [
                {
                    "Name": t.full_name,
                    "Phone": t.phone_number,
                    "Email": t.email or "—",
                    "Current Unit": t.current_unit.code if t.current_unit else "— (no active lease)",
                }
                for t in tenants
            ],
            use_container_width=True,
        )

        st.divider()
        st.subheader("Tenant Detail")
        selected_name = st.selectbox("Select a tenant", [t.full_name for t in tenants])
        tenant = next(t for t in tenants if t.full_name == selected_name)

        d1, d2 = st.columns(2)
        with d1:
            st.write(f"**Phone:** {tenant.phone_number}")
            st.write(f"**Email:** {tenant.email or '—'}")
        with d2:
            st.write(f"**National ID:** {tenant.national_id or '—'}")
            st.write(f"**Current Unit:** {tenant.current_unit.code if tenant.current_unit else '—'}")

        st.write("**Lease History**")
        if tenant.leases:
            st.dataframe(
                [{"Unit": l.unit.code, "Start": l.start_date, "End": l.end_date or "—", "Status": l.status.value}
                 for l in tenant.leases],
                use_container_width=True,
            )
        else:
            st.caption("No leases on record.")

        st.write("**Invoice History**")
        if tenant.invoices:
            st.dataframe(
                [{"Invoice #": i.invoice_number, "Period": i.period_start.strftime("%Y-%m"),
                  "Total": money(i.total), "Outstanding": money(i.outstanding_balance), "Status": i.status.value}
                 for i in tenant.invoices],
                use_container_width=True,
            )
        else:
            st.caption("No invoices on record.")

        st.write("**Payment History**")
        if tenant.payments:
            st.dataframe(
                [{"Date": p.payment_date, "Amount": money(p.amount), "Method": p.payment_method,
                  "Reference": p.reference or "—"} for p in tenant.payments],
                use_container_width=True,
            )
        else:
            st.caption("No payments on record.")

with tab_create:
    st.subheader("Create New Tenant")
    with st.form("create_tenant_form", clear_on_submit=True):
        first_name = st.text_input("First Name *")
        last_name = st.text_input("Last Name *")
        phone_raw = st.text_input("Phone Number *", placeholder="07XXXXXXXX or 254 7XXXXXXXX")
        email = st.text_input("Email (optional)")
        national_id = st.text_input("National ID (optional)")
        notes = st.text_area("Notes (optional)")

        submitted = st.form_submit_button("Create Tenant", type="primary")
        if submitted:
            errors = []
            if not first_name or not last_name:
                errors.append("First and last name are required.")

            normalised_phone = normalise_phone(phone_raw) if phone_raw else None
            if not normalised_phone:
                errors.append("Phone number must be a valid Kenyan number (e.g. 2547XXXXXXXX).")

            if email and not EMAIL_RE.match(email):
                errors.append("Email address format looks invalid.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                tenant = Tenant(
                    first_name=first_name,
                    last_name=last_name,
                    phone_number=normalised_phone,
                    email=email or None,
                    national_id=national_id or None,
                    notes=notes or None,
                )
                session.add(tenant)
                session.commit()
                st.success(f"✅ Tenant '{first_name} {last_name}' created.")
