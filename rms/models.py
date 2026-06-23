"""
rms/models.py — SQLAlchemy ORM models for the Rental Management System (RMS).

Design notes
------------
- Money fields use Numeric(12, 2) rather than Float to avoid binary
  floating-point rounding errors in financial totals.
- Invoice line items are a separate table (InvoiceLine) rather than JSON,
  so totals can be queried/aggregated directly in SQL for reports.
- `Invoice.invoice_number` and the (tenant_id, unit_id, period_start) tuple
  are both unique, which is what makes invoice generation idempotent —
  re-running the monthly job for a period that already has an invoice
  will not create a duplicate (see rms/invoicing.py).
"""
from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String,
    Text, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ──────────────────────────────────────────────────────────────────

class UnitType(str, enum.Enum):
    HOUSE = "house"
    ROOM = "room"


class LeaseStatus(str, enum.Enum):
    ACTIVE = "active"
    TERMINATED = "terminated"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PARTIAL = "partial"
    PAID = "paid"
    OVERDUE = "overdue"


class FeeCalculationMethod(str, enum.Enum):
    FIXED = "fixed"
    PER_UNIT = "per_unit"
    CUSTOM = "custom"


# ── Unit ───────────────────────────────────────────────────────────────────

class Unit(Base):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_type: Mapped[UnitType] = mapped_column(Enum(UnitType), default=UnitType.HOUSE)
    monthly_rent: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    garbage_fee: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    security_fee: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    leases: Mapped[list["Lease"]] = relationship(back_populates="unit")
    water_charges: Mapped[list["WaterCharge"]] = relationship(back_populates="unit")

    @property
    def current_lease(self) -> "Lease | None":
        """Return the active lease for this unit, if any."""
        return next((l for l in self.leases if l.status == LeaseStatus.ACTIVE), None)

    @property
    def is_occupied(self) -> bool:
        return self.current_lease is not None


# ── Tenant ─────────────────────────────────────────────────────────────────

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    national_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    leases: Mapped[list["Lease"]] = relationship(back_populates="tenant")
    payments: Mapped[list["Payment"]] = relationship(back_populates="tenant")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="tenant")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def current_unit(self) -> "Unit | None":
        active = next((l for l in self.leases if l.status == LeaseStatus.ACTIVE), None)
        return active.unit if active else None


# ── Lease ──────────────────────────────────────────────────────────────────

class Lease(Base):
    __tablename__ = "leases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rent_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[LeaseStatus] = mapped_column(Enum(LeaseStatus), default=LeaseStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tenant: Mapped["Tenant"] = relationship(back_populates="leases")
    unit: Mapped["Unit"] = relationship(back_populates="leases")

    def effective_rent(self) -> float:
        """Lease-level rent override takes precedence over the unit's default rent."""
        return float(self.rent_amount) if self.rent_amount is not None else float(self.unit.monthly_rent)


# ── FeeType (catalog) ────────────────────────────────────────────────────────

class FeeType(Base):
    __tablename__ = "fee_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    calculation_method: Mapped[FeeCalculationMethod] = mapped_column(
        Enum(FeeCalculationMethod), default=FeeCalculationMethod.FIXED
    )
    default_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)


# ── WaterCharge ───────────────────────────────────────────────────────────────

class WaterCharge(Base):
    """
    Monthly water charge per unit. Reuses the same reading/consumption/cost
    concepts as the existing water-billing SMS app (Previous/Current Reading,
    Units Consumed, Cost per Unit, Total Cost) rather than duplicating logic —
    invoicing.py reads `charge_amount` directly from here for a given period.
    """
    __tablename__ = "water_charges"
    __table_args__ = (UniqueConstraint("unit_id", "month", name="uq_water_charge_unit_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)  # "YYYY-MM"
    reading_start: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    reading_end: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    consumption: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    charge_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    unit: Mapped["Unit"] = relationship(back_populates="water_charges")


# ── Payment ────────────────────────────────────────────────────────────────

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), nullable=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), default="M-Pesa")
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tenant: Mapped["Tenant"] = relationship(back_populates="payments")
    invoice: Mapped["Invoice | None"] = relationship(back_populates="payments")


# ── Invoice ────────────────────────────────────────────────────────────────

class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "unit_id", "period_start", name="uq_invoice_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus), default=InvoiceStatus.DRAFT)
    sent_sms: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_email: Mapped[bool] = mapped_column(Boolean, default=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="invoices")
    unit: Mapped["Unit"] = relationship()
    lines: Mapped[list["InvoiceLine"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice")

    @property
    def amount_paid(self) -> float:
        return float(sum((float(p.amount) for p in self.payments), 0.0))

    @property
    def outstanding_balance(self) -> float:
        return round(float(self.total) - self.amount_paid, 2)


# ── InvoiceLine ────────────────────────────────────────────────────────────

class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    invoice: Mapped["Invoice"] = relationship(back_populates="lines")


# ── SMS log (supporting model — referenced in spec section 7) ──────────────

class SmsLog(Base):
    """Audit log of SMS sends triggered from the RMS module (invoices/reminders)."""
    __tablename__ = "rms_sms_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), nullable=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success / failed
    provider_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
