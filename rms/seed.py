"""
rms/seed.py — Sample data fixtures for demoing the RMS module.

Run directly to populate rms_data.db with example tenants/units/leases:

    python -m rms.seed
"""
from __future__ import annotations

from datetime import date

from rms.db import SessionLocal, init_db
from rms.invoicing import generate_invoices_for_month
from rms.models import FeeCalculationMethod, FeeType, Lease, LeaseStatus, Tenant, Unit, WaterCharge
from rms.payments import record_payment


def seed() -> None:
    init_db()
    session = SessionLocal()

    if session.query(Unit).first():
        print("Database already has data — skipping seed. Delete rms_data.db to reseed from scratch.")
        session.close()
        return

    units = [
        Unit(code="A1", address="Plot 14, Kasarani Estate, Nairobi", monthly_rent=12000, garbage_fee=300, security_fee=500),
        Unit(code="A2", address="Plot 14, Kasarani Estate, Nairobi", monthly_rent=10000, garbage_fee=300, security_fee=500),
        Unit(code="B1", address="Mwembe Tayari Road, Kilifi", monthly_rent=8000, garbage_fee=200, security_fee=400),
    ]
    session.add_all(units)
    session.flush()

    tenants = [
        Tenant(first_name="John", last_name="Mwangi", phone_number="254712345678", email="john.mwangi@example.com"),
        Tenant(first_name="Amina", last_name="Hassan", phone_number="254723456789", email="amina.hassan@example.com"),
    ]
    session.add_all(tenants)
    session.flush()

    session.add_all([
        Lease(tenant_id=tenants[0].id, unit_id=units[0].id, start_date=date(2026, 1, 1), status=LeaseStatus.ACTIVE),
        Lease(tenant_id=tenants[1].id, unit_id=units[1].id, start_date=date(2026, 3, 1), status=LeaseStatus.ACTIVE),
    ])

    session.add_all([
        WaterCharge(unit_id=units[0].id, month=date.today().strftime("%Y-%m"),
                    reading_start=100, reading_end=115, consumption=15, charge_amount=750),
        WaterCharge(unit_id=units[1].id, month=date.today().strftime("%Y-%m"),
                    reading_start=50, reading_end=58, consumption=8, charge_amount=400),
    ])

    session.add_all([
        FeeType(name="Garbage", calculation_method=FeeCalculationMethod.FIXED, default_amount=300),
        FeeType(name="Security", calculation_method=FeeCalculationMethod.FIXED, default_amount=500),
        FeeType(name="Water", calculation_method=FeeCalculationMethod.PER_UNIT, default_amount=50),
    ])

    session.commit()

    today = date.today()
    invoices = generate_invoices_for_month(session, today.year, today.month)
    session.commit()

    if invoices and invoices[0] is not None:
        record_payment(
            session=session,
            tenant_id=invoices[0].tenant_id,
            amount=float(invoices[0].total) / 2,
            payment_date=today,
            payment_method="M-Pesa",
            invoice_id=invoices[0].id,
            reference="SEED-DEMO-001",
        )
        session.commit()

    print(f"Seeded {len(units)} units, {len(tenants)} tenants, "
          f"{len([i for i in invoices if i is not None])} invoice(s) for {today.strftime('%Y-%m')}.")
    session.close()


if __name__ == "__main__":
    seed()
