"""
rms/pages/reports_page.py — Reports page: configurable day/week/month/year
reports, single tenant or all houses, with charts and CSV/PDF export.
"""
from __future__ import annotations

from datetime import date

import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from io import BytesIO

from rms.database import get_session
from rms.models import Tenant
from rms.reports import (
    charges_vs_payments, aggregate_by_tenant, aggregate_by_unit,
    outstanding_balances, quick_select_report, _date_range_for_period,
)


def _build_report_pdf(title: str, df) -> bytes:
    """Quick generic tabular PDF export for any report DataFrame."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]

    if df.empty:
        story.append(Paragraph("No data for the selected range.", styles["Normal"]))
    else:
        data = [list(df.columns)] + df.astype(str).values.tolist()
        table = Table(data)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(table)

    doc.build(story)
    return buffer.getvalue()


def render():
    st.header("📈 Reports")

    with get_session() as session:
        scope_col, gran_col = st.columns(2)
        scope = scope_col.radio("Scope", ["All Houses (aggregate)", "Single Tenant"], horizontal=True)

        tenant_id = None
        if scope == "Single Tenant":
            tenants = session.query(Tenant).order_by(Tenant.first_name).all()
            if not tenants:
                st.info("No tenants available yet.")
                return
            options = {t.full_name: t.id for t in tenants}
            tenant_choice = st.selectbox("Select Tenant", list(options.keys()))
            tenant_id = options[tenant_choice]

        granularity = gran_col.selectbox("Quick Range", ["day", "week", "month", "year", "Custom range"])

        if granularity == "Custom range":
            c1, c2 = st.columns(2)
            start = c1.date_input("Start date", value=date.today().replace(day=1))
            end = c2.date_input("End date", value=date.today())
        else:
            start, end = _date_range_for_period(granularity, date.today())
            st.caption(f"Range: {start} to {end}")

        report_type = st.selectbox(
            "Report Type",
            ["Charges vs Payments", "Outstanding Balances"],
        )

        if report_type == "Charges vs Payments":
            df = charges_vs_payments(session, start, end, tenant_id)
            st.subheader("Charges vs Payments")
            if df.empty:
                st.info("No invoices in this range.")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)

                if scope == "All Houses (aggregate)":
                    st.write("**Aggregated by Tenant:**")
                    agg_tenant = aggregate_by_tenant(df)
                    st.dataframe(agg_tenant, use_container_width=True, hide_index=True)
                    st.bar_chart(agg_tenant.set_index("tenant")[["charged", "paid", "outstanding"]])

                    st.write("**Aggregated by Unit:**")
                    agg_unit = aggregate_by_unit(df)
                    st.dataframe(agg_unit, use_container_width=True, hide_index=True)
                else:
                    st.bar_chart(df.set_index("period")[["charged", "paid", "outstanding"]])

        else:  # Outstanding Balances
            df = outstanding_balances(session, tenant_id)
            st.subheader("Outstanding Balances")
            if df.empty:
                st.success("No outstanding balances. 🎉")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.bar_chart(df.set_index("tenant")["outstanding"])

        st.divider()
        exp1, exp2 = st.columns(2)
        with exp1:
            csv = df.to_csv(index=False).encode()
            st.download_button("⬇️ Export CSV", data=csv, file_name=f"report_{report_type.replace(' ', '_').lower()}.csv", mime="text/csv")
        with exp2:
            pdf_bytes = _build_report_pdf(report_type, df)
            st.download_button("📄 Export PDF", data=pdf_bytes, file_name=f"report_{report_type.replace(' ', '_').lower()}.pdf", mime="application/pdf")
