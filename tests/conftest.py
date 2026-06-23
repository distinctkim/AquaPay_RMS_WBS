"""tests/conftest.py — shared pytest fixtures for RMS tests."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rms.models import Base, Lease, LeaseStatus, Tenant, Unit


@pytest.fixture()
def session():
    """Fresh in-memory SQLite database per test — fast and fully isolated."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture()
def sample_lease(session):
    """One unit, one tenant, one active lease — the minimal fixture most tests need."""
    unit = Unit(code="A1", address="Test Address", monthly_rent=100, garbage_fee=5, security_fee=10)
    tenant = Tenant(first_name="John", last_name="Doe", phone_number="254712345678")
    session.add_all([unit, tenant])
    session.flush()

    lease = Lease(tenant_id=tenant.id, unit_id=unit.id, start_date=date(2026, 1, 1), status=LeaseStatus.ACTIVE)
    session.add(lease)
    session.commit()
    return lease
