"""
rms/db.py — Database engine and session management for the RMS module.

Uses SQLite by default (file-based, zero-config — good for local/dev and
portfolio/demo use). Set RMS_DATABASE_URL in the environment to point at
PostgreSQL or another backend in production without changing any other code,
since all RMS modules import `get_session` / `engine` from here rather than
constructing their own connections.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> None:
        return None

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from rms.models import Base

load_dotenv()

DATABASE_URL = os.environ.get("RMS_DATABASE_URL", "sqlite:///rms_data.db")

# check_same_thread=False is required for SQLite when used from Streamlit,
# since Streamlit may access the session from different threads across reruns.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Create all tables if they do not already exist. Safe to call repeatedly."""
    Base.metadata.create_all(engine)


@contextmanager
def get_session():
    """
    Context-managed session for use in scripts/tests:

        with get_session() as session:
            session.add(obj)
    """
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
