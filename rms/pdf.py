"""
rms/pdf.py — Invoice PDF generation using ReportLab.

Chosen over WeasyPrint/PDFKit because it has no external system-binary
dependency (WeasyPrint needs Pango/Cairo; PDFKit needs wkhtmltopdf), which
keeps deployment simpler — relevant since the existing app is a single
`pip install -r requirements.txt` Streamlit deployment with no Docker layer
described in the spec's deliverables.
"""
from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from rms.models import Invoice

COMPANY_NAME = "AquaPay Rentals"
COMPANY_CONTACT = "support@aquapay.example  |  +254 7XX XXX XXX"


def generate_invoice_pdf(invoice: Invoice) -> bytes:
    """
    Build a single-page invoice PDF and return it as raw bytes, ready to
    pass to st.download_button or attach elsewhere. Layout follows spec
    section 8: header, tenant/unit details, invoice meta, itemised lines
    and totals, payment instructions.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleX", parent=styles["Title"], fontSize=18, spaceAfter=4)
    normal = styles["Normal"]

    story = [
        Paragraph(COMPANY_NAME, title_style),
        Paragraph(COMPANY_CONTACT, normal),
        Spacer(1, 14),
        Paragraph(f"<b>Invoice Number:</b> {invoice.invoice_number}", normal),
        Paragraph(f"<b>Date Issued:</b> {invoice.created_at.strftime('%d %b %Y')}", normal),
        Paragraph(f"<b>Period:</b> {invoice.period_start.strftime('%d %b %Y')} – {invoice.period_end.strftime('%d %b %Y')}", normal),
        Paragraph(f"<b>Due Date:</b> {invoice.due_date.strftime('%d %b %Y')}", normal),
        Spacer(1, 10),
        Paragraph(f"<b>Tenant:</b> {invoice.tenant.full_name}", normal),
        Paragraph(f"<b>Unit:</b> {invoice.unit.code} — {invoice.unit.address}", normal),
        Spacer(1, 16),
    ]

    table_data = [["Description", "Qty", "Unit Price (KES)", "Amount (KES)"]]
    for line in invoice.lines:
        table_data.append([
            line.description,
            f"{float(line.quantity):.0f}",
            f"{float(line.unit_price):,.2f}",
            f"{float(line.total_amount):,.2f}",
        ])
    table_data.append(["", "", "Subtotal", f"{float(invoice.subtotal):,.2f}"])
    table_data.append(["", "", "TOTAL DUE", f"{float(invoice.total):,.2f}"])
    table_data.append(["", "", "Amount Paid", f"{invoice.amount_paid:,.2f}"])
    table_data.append(["", "", "Outstanding Balance", f"{invoice.outstanding_balance:,.2f}"])

    table = Table(table_data, colWidths=[70 * mm, 20 * mm, 45 * mm, 45 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, len(invoice.lines)), 0.4, colors.grey),
        ("LINEABOVE", (2, len(invoice.lines) + 1), (-1, len(invoice.lines) + 1), 0.8, colors.black),
        ("FONTNAME", (2, len(invoice.lines) + 2), (-1, len(invoice.lines) + 2), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Payment Instructions: Pay via M-Pesa Paybill or visit our offices. "
        "Please quote your invoice number as the payment reference.",
        normal,
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Queries: {COMPANY_CONTACT}", normal))

    doc.build(story)
    return buf.getvalue()
