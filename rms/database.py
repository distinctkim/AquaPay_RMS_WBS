"""
rms/database.py — SQLAlchemy engine, session factory, and DB initialisation.

Uses SQLite by default (rms.db in the project root). To move to PostgreSQL in
production, set the RMS_DATABASE_URL environment variable, e.g.:

    RMS_DATABASE_URL=postgresql://user:pass@host:5432/rms_db

No code changes are required elsewhere — all modules import `get_session()`
or `SessionLocal` from this file rather than constructing engines themselves.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from rms.models import Base, FeeType, FeeCalculationMethod

DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rms.db")
DATABASE_URL = os.environ.get("RMS_DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}")

# check_same_thread=False is required for SQLite when used from Streamlit,
# which may access the connection from different threads across reruns.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create all tables if they do not already exist, and seed default fee types."""
    Base.metadata.create_all(engine)
    _seed_default_fee_types()


def _seed_default_fee_types() -> None:
    """Insert default FeeType rows (water, garbage, security) if the table is empty."""
    with get_session() as session:
        existing = session.query(FeeType).count()
        if existing > 0:
            return
        defaults = [
            FeeType(name="water", calculation_method=FeeCalculationMethod.CUSTOM.value, default_amount=0),
            FeeType(name="garbage", calculation_method=FeeCalculationMethod.FIXED.value, default_amount=0),
            FeeType(name="security", calculation_method=FeeCalculationMethod.FIXED.value, default_amount=0),
        ]
        session.add_all(defaults)
        session.commit()


@contextmanager
def get_session():
    """Context-managed session: commits on success, rolls back on exception."""
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
