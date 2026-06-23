"""
rms/ui_helpers.py — Shared Streamlit helpers used across all RMS pages.

Centralising session/db init here means every page in pages/ starts with
the same two lines, and a future change to how the session is created
only needs to happen in one place.
"""
from __future__ import annotations

import streamlit as st

from rms.db import SessionLocal, init_db


def get_db_session():
    """
    Return a SQLAlchemy session stored in Streamlit's session_state, creating
    tables on first use. Reusing one session per browser session (rather than
    opening/closing a new one every rerun) avoids repeatedly hitting SQLite's
    file-open overhead on every widget interaction.
    """
    if "rms_db_initialized" not in st.session_state:
        init_db()
        st.session_state["rms_db_initialized"] = True

    if "rms_session" not in st.session_state:
        st.session_state["rms_session"] = SessionLocal()

    return st.session_state["rms_session"]


def sidebar_sms_credentials():
    """
    Shared sidebar widget for Africa's Talking credentials, reusing the same
    keys as the main app.py sidebar so a value entered on one page is
    available on the RMS pages too (Streamlit session_state is shared across
    pages within one browser session).
    """
    with st.sidebar:
        st.subheader("SMS Credentials (Africa's Talking)")
        api_key = st.text_input(
            "API Key", type="password", key="rms_api_key",
            value=st.session_state.get("rms_api_key", ""),
        )
        username = st.text_input(
            "Username", key="rms_username",
            value=st.session_state.get("rms_username", ""),
        )
        sandbox = st.checkbox("Use Sandbox", value=True, key="rms_sandbox")
    return api_key, username, sandbox


def money(value) -> str:
    """Format a Decimal/float as KES currency for display."""
    return f"KES {float(value):,.2f}"
