"""pages/8_Settings.py — Fee defaults, SMS settings, scheduling configuration."""
import streamlit as st

from rms.models import FeeCalculationMethod, FeeType
from rms.ui_helpers import get_db_session

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")
session = get_db_session()

st.title("⚙️ Settings")

tab_fees, tab_sms, tab_schedule = st.tabs(["💰 Fee Defaults", "📲 SMS Settings", "🕒 Scheduling"])

with tab_fees:
    st.subheader("Fee Type Catalog")
    st.caption(
        "These are organisation-wide defaults. Individual units can still override "
        "garbage/security fees directly on the Units page."
    )

    fee_types = session.query(FeeType).all()
    if fee_types:
        st.dataframe(
            [{"Name": f.name, "Method": f.calculation_method.value, "Default Amount": float(f.default_amount)}
             for f in fee_types],
            use_container_width=True,
        )

    with st.form("create_fee_type", clear_on_submit=True):
        name = st.text_input("Fee Name *", placeholder="e.g. Garbage, Security, Parking")
        method = st.selectbox("Calculation Method", [m.value for m in FeeCalculationMethod])
        default_amount = st.number_input("Default Amount (KES)", min_value=0.0, step=50.0)

        if st.form_submit_button("Add Fee Type", type="primary"):
            if not name:
                st.error("Fee name is required.")
            elif session.query(FeeType).filter_by(name=name).first():
                st.error(f"Fee type '{name}' already exists.")
            else:
                session.add(FeeType(
                    name=name,
                    calculation_method=FeeCalculationMethod(method),
                    default_amount=default_amount,
                ))
                session.commit()
                st.success(f"✅ Fee type '{name}' added.")

with tab_sms:
    st.subheader("SMS Configuration")
    st.markdown(
        """
        SMS sending reuses the existing **Africa's Talking** integration from the main
        water-bill notifier app (`sms.py`). Credentials are entered per-session in the
        sidebar of the Invoices page — they are intentionally **not stored in the
        database**, only kept in environment variables or Streamlit session state, per
        the spec's security requirement to never hardcode API keys or credentials.
        """
    )
    st.code(
        "# Recommended: set these as environment variables instead of typing them each session\n"
        "AT_API_KEY=your_api_key_here\n"
        "AT_USERNAME=your_username_here\n"
        "RMS_DATABASE_URL=sqlite:///rms_data.db   # or a postgresql:// URL for production",
        language="bash",
    )

with tab_schedule:
    st.subheader("Automated Invoice Generation Schedule")
    st.markdown(
        """
        Automated monthly invoice generation and reminders run via **APScheduler**
        (see `rms/scheduler.py`). This page is informational — the scheduler itself
        runs as a separate background process (see README for run instructions),
        since Streamlit's own process model is not well-suited to long-running
        background jobs.
        """
    )
    st.write("**Current configured schedule (from environment / scheduler.py defaults):**")
    st.code(
        "Monthly invoice generation : last day of each month, 23:00\n"
        "Reminder — 7 days before due : daily check, 08:00\n"
        "Reminder — on due date       : daily check, 08:00\n"
        "Reminder — overdue           : daily check, 08:00",
        language=None,
    )
    st.caption("To change these, edit the cron expressions in rms/scheduler.py.")
