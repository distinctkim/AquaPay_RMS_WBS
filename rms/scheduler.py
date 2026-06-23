"""
rms/scheduler.py — Background scheduled jobs for invoice generation and reminders.

Run as a SEPARATE PROCESS from the Streamlit app:

    python -m rms.scheduler

Why a separate process: Streamlit reruns the whole script on every UI
interaction, and multiple browser tabs/users would each spin up their own
in-process scheduler if this were started from within app.py. A single
standalone process (run via cron, systemd, a Heroku worker dyno, or a Cloud
Scheduler-triggered Cloud Function per spec section 6) avoids duplicate jobs
and keeps the Streamlit process focused on serving the UI.

Idempotency: generate_invoices_for_month() (rms/invoicing.py) already skips
leases that have an existing invoice for the period, so it's safe for this
job to fire more than once for the same month (e.g. after a restart).
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from rms.db import SessionLocal, init_db
from rms.invoicing import generate_invoices_for_month
from rms.models import Invoice, InvoiceStatus
from rms.sms_templates import send_invoice_sms

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("rms.scheduler")

AT_API_KEY = os.environ.get("AT_API_KEY", "")
AT_USERNAME = os.environ.get("AT_USERNAME", "")
AT_SANDBOX = os.environ.get("AT_SANDBOX", "true").lower() == "true"

REMINDER_DAYS_BEFORE_DUE = int(os.environ.get("RMS_REMINDER_DAYS_BEFORE_DUE", "7"))


def job_generate_monthly_invoices() -> None:
    """Generate invoices for every active lease for the current month."""
    today = date.today()
    session = SessionLocal()
    try:
        invoices = generate_invoices_for_month(session, today.year, today.month)
        session.commit()
        logger.info("Monthly invoice generation: processed %d active lease(s) for %04d-%02d.",
                    len(invoices), today.year, today.month)
    except Exception:
        session.rollback()
        logger.exception("Monthly invoice generation failed.")
    finally:
        session.close()


def _send_reminders_for(session, invoices, label: str) -> None:
    if not AT_API_KEY or not AT_USERNAME:
        logger.warning("Skipping %s reminders: AT_API_KEY/AT_USERNAME not configured in environment.", label)
        return
    for invoice in invoices:
        if invoice.outstanding_balance <= 0:
            continue
        result = send_invoice_sms(session, invoice, AT_API_KEY, AT_USERNAME, AT_SANDBOX, reminder=True)
        logger.info("%s reminder to %s for %s: %s",
                    label, invoice.tenant.phone_number, invoice.invoice_number,
                    "sent" if result.success else f"FAILED ({result.message})")


def job_send_due_date_reminders() -> None:
    """Send reminders for invoices due today, and for overdue invoices."""
    today = date.today()
    session = SessionLocal()
    try:
        due_today = session.query(Invoice).filter(
            Invoice.due_date == today,
            Invoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.PARTIAL]),
        ).all()
        _send_reminders_for(session, due_today, "Due-today")

        overdue = session.query(Invoice).filter(
            Invoice.due_date < today,
            Invoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.PARTIAL]),
        ).all()
        for inv in overdue:
            inv.status = InvoiceStatus.OVERDUE
        session.commit()
        _send_reminders_for(session, overdue, "Overdue")

        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Due-date/overdue reminder job failed.")
    finally:
        session.close()


def job_send_upcoming_due_reminders() -> None:
    """Send reminders N days before an invoice's due date (default 7)."""
    target_date = date.today() + timedelta(days=REMINDER_DAYS_BEFORE_DUE)
    session = SessionLocal()
    try:
        upcoming = session.query(Invoice).filter(
            Invoice.due_date == target_date,
            Invoice.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.PARTIAL]),
        ).all()
        _send_reminders_for(session, upcoming, f"{REMINDER_DAYS_BEFORE_DUE}-days-before-due")
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Upcoming-due reminder job failed.")
    finally:
        session.close()


def main() -> None:
    init_db()
    scheduler = BlockingScheduler(timezone="Africa/Nairobi")

    # Last day of month is variable, so check daily at 23:00 and no-op unless
    # tomorrow rolls into a new month — simpler and more robust than computing
    # the exact last-day cron expression per month.
    scheduler.add_job(
        lambda: job_generate_monthly_invoices() if (date.today() + timedelta(days=1)).day == 1 else None,
        CronTrigger(hour=23, minute=0),
        id="monthly_invoice_generation",
    )
    scheduler.add_job(job_send_upcoming_due_reminders, CronTrigger(hour=8, minute=0), id="upcoming_due_reminders")
    scheduler.add_job(job_send_due_date_reminders, CronTrigger(hour=8, minute=15), id="due_and_overdue_reminders")

    logger.info("RMS scheduler started. Jobs: %s", [j.id for j in scheduler.get_jobs()])
    scheduler.start()


if __name__ == "__main__":
    main()
