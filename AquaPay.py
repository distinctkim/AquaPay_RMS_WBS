"""
Kenya Water Bill SMS Notifier
Streamlit web app to upload Excel files and send SMS notifications to customers.
"""

import streamlit as st
import pandas as pd
from io import BytesIO

from processor import load_and_validate_excel, REQUIRED_COLUMNS
from sms import send_sms, SMSResult
from message import generate_message


# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AquaPay Water Bill SMS Notifier",
    page_icon="💧",
    layout="centered",
)

st.title("💧 AquaPay Water Bill SMS Notifier")
st.markdown(
    "Upload an Excel file with customer billing data and send SMS notifications via Africa's Talking."
)

# ── Sidebar: API credentials ───────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Africa's Talking Credentials")
    api_key = st.text_input("API Key", type="password", placeholder="Your AT API key")
    username = st.text_input("Username", placeholder="sandbox  or  your-username")
    use_sandbox = st.checkbox("Use Sandbox (testing)", value=True)
    st.divider()
    st.caption("Phone numbers must be in Kenyan format: **2547XXXXXXXX**")

# ── File upload ────────────────────────────────────────────────────────────────
uploaded_file = st.file_uploader("Upload Excel file (.xlsx)", type=["xlsx"])

if uploaded_file:
    file_bytes = BytesIO(uploaded_file.read())

    # ── Load & validate ────────────────────────────────────────────────────────
    with st.spinner("Reading and validating Excel file…"):
        df, errors = load_and_validate_excel(file_bytes)

    if df is None:
        st.error(f"❌ Failed to load file: {errors[0] if errors else 'Unknown error'}")
        st.stop()

    st.success(f"✅ Loaded **{len(df)}** rows successfully.")

    # Show validation warnings for individual rows
    if errors:
        with st.expander(f"⚠️ {len(errors)} validation warning(s)", expanded=False):
            for err in errors:
                st.warning(err)

    # ── Preview ────────────────────────────────────────────────────────────────
    with st.expander("📋 Preview data", expanded=True):
        st.dataframe(df, use_container_width=True)

    # ── Message preview ────────────────────────────────────────────────────────
    if not df.empty:
        sample = df.iloc[0]
        st.subheader("📝 Sample SMS Message")
        st.code(generate_message(sample), language=None)

    st.divider()

    # ── Send button ────────────────────────────────────────────────────────────
    if not api_key or not username:
        st.info("👈 Enter your Africa's Talking credentials in the sidebar to send SMS.")
    else:
        valid_rows = df[df["_valid"]].copy()
        invalid_count = len(df) - len(valid_rows)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total rows", len(df))
        col2.metric("Valid (will send)", len(valid_rows))
        col3.metric("Skipped (invalid)", invalid_count)

        if st.button("🚀 Send SMS to all valid customers", type="primary", use_container_width=True):
            if valid_rows.empty:
                st.warning("No valid rows to send.")
            else:
                results: list[SMSResult] = []
                progress = st.progress(0, text="Sending messages…")
                status_placeholder = st.empty()

                for i, (_, row) in enumerate(valid_rows.iterrows(), start=1):
                    message = generate_message(row)
                    result = send_sms(
                        phone=str(row["Phone Number"]),
                        message=message,
                        api_key=api_key,
                        username=username,
                        sandbox=use_sandbox,
                    )
                    results.append(result)
                    progress.progress(i / len(valid_rows), text=f"Sent {i}/{len(valid_rows)}")
                    status_icon = "✅" if result.success else "❌"
                    status_placeholder.caption(
                        f"{status_icon} {row['Phone Number']} — {result.message}"
                    )

                progress.empty()
                status_placeholder.empty()

                # ── Results summary ────────────────────────────────────────────
                sent = sum(1 for r in results if r.success)
                failed = len(results) - sent
                st.success(f"✅ Sent: **{sent}** | ❌ Failed: **{failed}**")

                # Detailed results table
                result_data = [
                    {
                        "Phone": r.phone,
                        "Status": "✅ Sent" if r.success else "❌ Failed",
                        "Details": r.message,
                    }
                    for r in results
                ]
                st.dataframe(pd.DataFrame(result_data), use_container_width=True)

                # Download results as CSV
                csv = pd.DataFrame(result_data).to_csv(index=False).encode()
                st.download_button(
                    "⬇️ Download results CSV",
                    data=csv,
                    file_name="sms_results.csv",
                    mime="text/csv",
                )
# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import subprocess
    import sys
    import os

    # Prevent re-launching when Streamlit reloads the script internally
    if os.environ.get("STREAMLIT_RUNNING") != "1":
        os.environ["STREAMLIT_RUNNING"] = "1"
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", __file__,
            "--server.headless", "true",   # don't auto-open browser on reload
        ])