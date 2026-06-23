"""
rms/pdf_invoice.py — Generate a PDF invoice using reportlab.

Returns bytes so the caller (a Streamlit page) can pass them directly to
st.download_button without writing to disk, and so the same bytes can later
be attached to an email/SMS-link flow if needed.
"""
from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT

from rms.models import Invoice

COMPANY_NAME = "RentalEase Property Management"
COMPANY_CONTACT = "Nairobi, Kenya  |  support@rentalease.example  |  +254 700 000000"


def generate_invoice_pdf(invoice: Invoice) -> bytes:
    """Build a PDF for the given Invoice ORM object and return it as bytes."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleX", parent=styles["Title"], fontSize=18, textColor=colors.HexColor("#1F3864"))
    label_style = ParagraphStyle("LabelX", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
    normal = styles["Normal"]
    right_normal = ParagraphStyle("RightX", parent=styles["Normal"], alignment=TA_RIGHT)

    story = []

    # Header
    story.append(Paragraph(COMPANY_NAME, title_style))
    story.append(Paragraph(COMPANY_CONTACT, label_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1F3864")))
    story.append(Spacer(1, 10))

    # Invoice meta + tenant/unit details, side by side
    meta_table = Table(
        [
            [Paragraph(f"<b>Invoice #:</b> {invoice.invoice_number}", normal),
             Paragraph(f"<b>Tenant:</b> {invoice.tenant.full_name}", normal)],
            [Paragraph(f"<b>Date Issued:</b> {invoice.created_at.strftime('%Y-%m-%d')}", normal),
             Paragraph(f"<b>Unit:</b> {invoice.unit.code} — {invoice.unit.address or ''}", normal)],
            [Paragraph(f"<b>Period:</b> {invoice.period_start} to {invoice.period_end}", normal),
             Paragraph(f"<b>Phone:</b> {invoice.tenant.phone_number}", normal)],
            [Paragraph(f"<b>Due Date:</b> {invoice.due_date}", normal), Paragraph("", normal)],
        ],
        colWidths=[90 * mm, 90 * mm],
    )
    story.append(meta_table)
    story.append(Spacer(1, 14))

    # Itemised lines
    data = [["Description", "Qty", "Unit Price (KES)", "Amount (KES)"]]
    for line in invoice.lines:
        data.append([
            line.description,
            f"{float(line.quantity):.0f}",
            f"{float(line.unit_price):,.2f}",
            f"{float(line.total_amount):,.2f}",
        ])
    data.append(["", "", "Subtotal", f"{float(invoice.subtotal):,.2f}"])
    data.append(["", "", "TOTAL DUE", f"{float(invoice.total):,.2f}"])

    items_table = Table(data, colWidths=[80 * mm, 20 * mm, 40 * mm, 40 * mm])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -3), 0.4, colors.HexColor("#cccccc")),
        ("LINEABOVE", (2, -2), (-1, -2), 0.6, colors.black),
        ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (2, -1), (-1, -1), 1, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 16))

    # Status + payment instructions
    story.append(Paragraph(f"<b>Status:</b> {invoice.status.upper()}  |  <b>Paid so far:</b> KES {invoice.amount_paid:,.2f}  |  <b>Outstanding:</b> KES {invoice.outstanding:,.2f}", normal))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Payment Instructions: Please pay via M-Pesa Paybill or bank transfer using the invoice "
        "number as your payment reference. For queries, contact the property manager using the "
        "details above.",
        normal,
    ))

    doc.build(story)
    return buffer.getvalue()
