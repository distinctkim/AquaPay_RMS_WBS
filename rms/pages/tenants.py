"""
rms/pages/tenants.py — Tenants page: list, create/edit, profile detail.
"""
from __future__ import annotations

import streamlit as st

from rms.database import get_session
from rms.models import Tenant
from rms.ui_helpers import validate_phone_input, status_badge


def render():
    st.header("👤 Tenants")

    tab_list, tab_create = st.tabs(["List Tenants", "Create / Edit Tenant"])

    with tab_list:
        with get_session() as session:
            tenants = session.query(Tenant).order_by(Tenant.first_name).all()
            if not tenants:
                st.info("No tenants yet. Add one in the 'Create / Edit Tenant' tab.")
            else:
                rows = [{
                    "Name": t.full_name,
                    "Phone": t.phone_number,
                    "Email": t.email or "—",
                    "Current Unit": t.current_unit.code if t.current_unit else "— (no active lease)",
                    "Active": "Yes" if t.is_active else "No",
                } for t in tenants]
                st.dataframe(rows, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("Tenant Detail")
            if tenants:
                choice = st.selectbox("Select a tenant", [t.full_name for t in tenants])
                tenant = next(t for t in tenants if t.full_name == choice)

                d1, d2 = st.columns(2)
                with d1:
                    st.write(f"**Phone:** {tenant.phone_number}")
                    st.write(f"**Email:** {tenant.email or '—'}")
                    st.write(f"**National ID:** {tenant.national_id or '—'}")
                with d2:
                    st.write(f"**Current Unit:** {tenant.current_unit.code if tenant.current_unit else '—'}")
                    st.write(f"**Active:** {'Yes' if tenant.is_active else 'No'}")

                st.write("**Lease(s):**")
                if tenant.leases:
                    lease_rows = [{
                        "Unit": l.unit.code, "Start": l.start_date, "End": l.end_date or "—",
                        "Status": status_badge(l.status),
                    } for l in tenant.leases]
                    st.dataframe(lease_rows, use_container_width=True, hide_index=True)
                else:
                    st.caption("No leases on record.")

                st.write("**Payment History:**")
                if tenant.payments:
                    pay_rows = [{
                        "Date": p.payment_date, "Amount (KES)": float(p.amount),
                        "Method": p.payment_method or "—",
                        "Invoice": p.invoice.invoice_number if p.invoice else "Unallocated",
                    } for p in tenant.payments]
                    st.dataframe(pay_rows, use_container_width=True, hide_index=True)
                else:
                    st.caption("No payments on record.")

                st.write("**Invoices:**")
                if tenant.invoices:
                    inv_rows = [{
                        "Invoice #": i.invoice_number, "Period": i.period_start.strftime("%Y-%m"),
                        "Total (KES)": float(i.total), "Outstanding (KES)": i.outstanding,
                        "Status": status_badge(i.status),
                    } for i in tenant.invoices]
                    st.dataframe(inv_rows, use_container_width=True, hide_index=True)
                else:
                    st.caption("No invoices on record.")

    with tab_create:
        st.subheader("Create New Tenant")
        with st.form("create_tenant_form", clear_on_submit=True):
            first_name = st.text_input("First Name *")
            last_name = st.text_input("Last Name *")
            phone = st.text_input("Phone Number *", placeholder="0712345678 or 254712345678")
            email = st.text_input("Email")
            national_id = st.text_input("National ID (optional)")
            notes = st.text_area("Notes (optional)")
            submitted = st.form_submit_button("Create Tenant", type="primary")

            if submitted:
                errors = []
                if not first_name.strip():
                    errors.append("First name is required.")
                if not last_name.strip():
                    errors.append("Last name is required.")

                phone_ok, phone_result = validate_phone_input(phone) if phone.strip() else (False, "Phone number is required.")
                if not phone_ok:
                    errors.append(phone_result)

                if email and "@" not in email:
                    errors.append("Email address looks invalid.")

                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    with get_session() as session:
                        tenant = Tenant(
                            first_name=first_name.strip(), last_name=last_name.strip(),
                            phone_number=phone_result, email=email.strip() or None,
                            national_id=national_id.strip() or None, notes=notes.strip() or None,
                        )
                        session.add(tenant)
                        session.commit()
                        st.success(f"✅ Tenant '{tenant.full_name}' created.")

        st.divider()
        st.subheader("Edit Existing Tenant")
        with get_session() as session:
            tenants = session.query(Tenant).order_by(Tenant.first_name).all()
            if not tenants:
                st.caption("No tenants to edit yet.")
            else:
                edit_choice = st.selectbox("Select tenant to edit", [t.full_name for t in tenants], key="edit_tenant_choice")
                tenant = next(t for t in tenants if t.full_name == edit_choice)

                with st.form("edit_tenant_form"):
                    new_email = st.text_input("Email", value=tenant.email or "")
                    new_phone = st.text_input("Phone Number", value=tenant.phone_number)
                    new_notes = st.text_area("Notes", value=tenant.notes or "")
                    new_active = st.checkbox("Active", value=tenant.is_active)
                    update_submitted = st.form_submit_button("Save Changes", type="primary")

                    if update_submitted:
                        phone_ok, phone_result = validate_phone_input(new_phone)
                        if not phone_ok:
                            st.error(phone_result)
                        elif new_email and "@" not in new_email:
                            st.error("Email address looks invalid.")
                        else:
                            tenant.email = new_email.strip() or None
                            tenant.phone_number = phone_result
                            tenant.notes = new_notes.strip() or None
                            tenant.is_active = new_active
                            session.commit()
                            st.success("✅ Tenant updated.")
                            st.rerun()
