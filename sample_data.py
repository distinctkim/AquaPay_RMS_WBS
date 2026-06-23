"""
sample_data.py — Seed the RMS database with demo data matching the spec's
worked example, plus a couple of extra units/tenants for a more convincing demo.

Run with: python sample_data.py
Safe to re-run: it checks for existing data and skips seeding if any units
already exist, so it won't create duplicates.
"""
from datetime import date

from rms.database import init_db, get_session
from rms.models import Unit, Tenant, Lease, WaterCharge, LeaseStatus
from rms.invoice_logic import generate_monthly_invoices, record_payment


def seed():
    init_db()

    with get_session() as session:
        if session.query(Unit).count() > 0:
            print("Sample data already exists (units table is non-empty). Skipping seed.")
            return

        # Unit A1 / Tenant John — matches the spec's worked example exactly:
        # rent=100, water=15, garbage=5, security=10 -> total=130
        unit_a = Unit(code="A1", address="Plot 12, Riverside Drive", unit_type="house",
                      monthly_rent=100, garbage_fee=5, security_fee=10)
        john = Tenant(first_name="John", last_name="Mwangi", phone_number="254712345678",
                     email="john.mwangi@example.com")

        # Two extra units/tenants for a fuller demo
        unit_b = Unit(code="B2", address="Plot 14, Riverside Drive", unit_type="room",
                      monthly_rent=60, garbage_fee=3, security_fee=5)
        jane = Tenant(first_name="Jane", last_name="Achieng", phone_number="254722334455",
                     email="jane.achieng@example.com")

        unit_c = Unit(code="C3", address="Plot 16, Riverside Drive", unit_type="house",
                      monthly_rent=120, garbage_fee=5, security_fee=10)
        # unit_c left vacant intentionally, to demo the "vacant unit" filter

        session.add_all([unit_a, john, unit_b, jane, unit_c])
        session.commit()

        lease_a = Lease(tenant_id=john.id, unit_id=unit_a.id, start_date=date(2026, 1, 1),
                        status=LeaseStatus.ACTIVE.value)
        lease_b = Lease(tenant_id=jane.id, unit_id=unit_b.id, start_date=date(2026, 3, 1),
                        status=LeaseStatus.ACTIVE.value)
        session.add_all([lease_a, lease_b])
        session.commit()

        # Water charge for John matching the spec example (water cost = 15)
        session.add(WaterCharge(unit_id=unit_a.id, month=date.today().strftime("%Y-%m"), charge_amount=15))
        session.commit()

        # Generate this month's invoices for both active leases
        result = generate_monthly_invoices(session, date.today().year, date.today().month)
        print(f"Generated {len(result.created)} invoice(s).")

        # Record a partial payment for John, matching the spec example (pays 50 of 130)
        if result.created:
            john_invoice_id = next(
                (iid for iid in result.created
                 if session.get(__import__("rms.models", fromlist=["Invoice"]).Invoice, iid).tenant_id == john.id),
                None,
            )
            if john_invoice_id:
                record_payment(session, tenant_id=john.id, amount=50,
                               payment_date=date.today(), invoice_id=john_invoice_id,
                               payment_method="M-Pesa", reference="DEMO-PAYMENT-001")
                print("Recorded a partial payment of KES 50 for John Mwangi (matches spec example).")

    print("Sample data seeded successfully.")
    print("Units: A1 (occupied, John), B2 (occupied, Jane), C3 (vacant)")


if __name__ == "__main__":
    seed()
