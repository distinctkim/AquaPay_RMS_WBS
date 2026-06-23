# RMS Module — Rental Management System

This module extends the existing **Kenya Water Bill SMS Notifier** Streamlit
app with a full Rental Management System: tenants, units, leases, payments,
invoices, reports, and SMS notifications — built on the **same** Africa's
Talking SMS integration already used by the Water Billing module.

---

## What's new vs. what's reused

| | Status |
|---|---|
| Tenant / Unit / Lease / Payment / Invoice models (SQLAlchemy) | **New** |
| Invoice generation, idempotency, payment allocation logic | **New** |
| 8 Streamlit pages (Dashboard, Units, Tenants, Leases, Payments, Invoices, Reports, Settings) | **New** |
| PDF invoice generation (reportlab) | **New** |
| Scheduled monthly invoice generation + reminders (APScheduler) | **New** |
| `send_sms()` / Africa's Talking integration | **Reused — unchanged** |
| Kenyan phone number validation | **Reused — unchanged** |
| Original Water Billing Excel-upload flow | **Reused — unchanged**, now reachable via a sidebar module switch |

Your original `app.py`, `processor.py`, `message.py`, and `sms.py` logic is
untouched. `app.py` now wraps the original Water Billing code in an `if`
branch and adds the RMS pages as a second branch, switched via a sidebar radio.

---

## Folder structure

```
AutomateBilingSMS/
├── app.py                  # Router: Water Billing SMS | RMS (sidebar switch)
├── processor.py            # UNCHANGED — Excel loading & phone validation
├── message.py              # UNCHANGED — water bill SMS message generation
├── sms.py                  # UNCHANGED — Africa's Talking integration
├── rms/
│   ├── models.py            # SQLAlchemy models
│   ├── database.py          # Engine/session, init_db()
│   ├── invoice_logic.py     # Invoice generation, payment allocation
│   ├── reports.py            # Reporting/aggregation (pandas)
│   ├── pdf_invoice.py         # Invoice PDF generation (reportlab)
│   ├── sms_templates.py       # Invoice/reminder SMS, reuses sms.py
│   ├── scheduler.py            # APScheduler jobs
│   ├── ui_helpers.py            # Shared Streamlit form helpers
│   └── pages/                    # One file per RMS page
├── tests/
│   ├── test_invoice_logic.py
│   └── test_reports.py
├── sample_data.py            # Seeds demo data (matches spec's worked example)
└── rms.db                     # SQLite file, created automatically on first run
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
pip install sqlalchemy apscheduler reportlab python-dateutil
```

(Add these four to `requirements.txt` if you want them pinned — see
`pip freeze` after installing for exact versions to add.)

### 2. Run the app

```bash
streamlit run app.py
```

The RMS database (`rms.db`) and tables are created automatically on first
launch via `init_db()` — no manual migration step is required for SQLite.

### 3. (Optional) Seed demo data

To get a populated demo without manually clicking through forms:

```bash
python sample_data.py
```

This creates 2 occupied units + 1 vacant unit, 2 tenants, this month's
invoices, and one partial payment — matching the worked example from the
original specification (rent 100 + water 15 + garbage 5 + security 10 = 130
total; a 50 payment leaves 80 outstanding with status "partial").

Safe to run only once — if units already exist, it skips seeding rather than
duplicating data.

---

## Switching to PostgreSQL for production

By default the app uses SQLite (`rms.db` in the project root). To use
PostgreSQL instead, set an environment variable before running:

```bash
export RMS_DATABASE_URL="postgresql://user:password@host:5432/rms_db"
streamlit run app.py
```

No code changes are needed — `rms/database.py` reads this variable and falls
back to SQLite only if it isn't set.

---

## Running scheduled jobs

`rms/scheduler.py` provides:

- `run_monthly_invoice_job()` — generates invoices for every active lease for
  the current month. **Idempotent**: safe to run more than once for the same
  month (duplicate leases are skipped, not re-invoiced).
- `run_overdue_check_job()` — marks issued/partial invoices past their due
  date as `overdue`.
- `run_reminder_job(sms_type, api_key, username, sandbox)` — sends SMS
  reminders for a given stage (`reminder_7d`, `reminder_due`,
  `reminder_overdue`).
- `start_scheduler(invoice_day=28)` — starts an in-process
  `BackgroundScheduler` that runs the monthly invoice job on a configurable
  day, and the overdue check daily at 01:00.

### Local development

Call `start_scheduler()` once when the app starts (e.g. at the top of
`app.py`, guarded so it only runs once per process) if you want the
scheduler running alongside the Streamlit dev server.

### Production deployment

Running `BackgroundScheduler` inside the same process as Streamlit works for
a single-instance deployment. If you deploy multiple replicas (e.g. behind a
load balancer), running the scheduler in every replica will fire duplicate
jobs simultaneously — harmless because invoice generation is idempotent, but
wasteful. For production, prefer one of:

- **Cron job** on a single host calling a small wrapper script that imports
  and calls `rms.scheduler.run_monthly_invoice_job()` directly.
- **Heroku Scheduler** add-on (if deployed on Heroku) calling the same
  wrapper as a one-off dyno.
- **Google Cloud Scheduler + Cloud Function/Cloud Run job** — same idea,
  triggered via HTTP instead of cron.

A minimal wrapper script for any of the above:

```python
# run_monthly_job.py
from rms.scheduler import run_monthly_invoice_job, run_overdue_check_job
run_monthly_invoice_job()
run_overdue_check_job()
```

---

## Generating invoices manually vs. automatically

- **Manually**: Invoices page → "Generate Invoices" tab → pick year/month →
  click "Generate Invoices for This Period". Also available as a Dashboard
  quick action for the current month.
- **Automatically**: via the scheduler (see above), on the configurable day
  of each month (default: day 28).

Both paths call the same underlying function
(`rms.invoice_logic.generate_monthly_invoices`), so behaviour — including
idempotency — is identical either way.

---

## Generating and exporting reports

Reports page → choose:

1. **Scope**: All Houses (aggregate) or Single Tenant
2. **Quick Range**: day / week / month / year, or a custom date range
3. **Report Type**: Charges vs Payments, or Outstanding Balances

Every report can be exported as **CSV** or **PDF** via the buttons at the
bottom of the page.

---

## SMS integration

All SMS sending goes through the **existing** `sms.send_sms()` function —
no new SMS provider integration was created. `rms/sms_templates.py` only
formats the message text and logs the outcome to the `sms_logs` table for
auditability (timestamp, success/failure, provider response).

SMS credentials (API key, username, sandbox toggle) are entered directly in
the UI when sending — exactly as in the original Water Billing module — and
are never persisted to the database.

---

## Tests

```bash
pytest tests/ -v
```

21 tests covering:
- Invoice composition and totals (matches the spec's worked example exactly)
- Lease rent overrides
- **Idempotent** invoice generation (running the monthly job twice does not duplicate)
- Payment allocation: partial payments, full payments, overpayments (tracked as credit), unallocated payments
- Overdue marking
- Reports: single-tenant vs all-houses scope, date-range filtering, aggregation

All tests use an in-memory SQLite database and do not touch your real `rms.db`.

---

## Known limitations / honest scope notes

- **Authentication**: no role-based access control is implemented. The
  spec allows documenting how to integrate with existing auth instead of
  building one from scratch — this app currently has no auth at all (neither
  did the original Water Billing app), so anyone with access to the running
  Streamlit instance can use every RMS page. Add a simple password gate
  (e.g. `streamlit-authenticator`) before any real deployment.
- **Scheduler is in-process**: see the "Production deployment" note above —
  fine for a single-instance demo/portfolio deployment, not for multi-replica
  production without modification.
- **PDF report export** uses a simple generic table layout (not a styled
  template) — functional but plain. The **invoice** PDF (not the report PDF)
  has a proper letterhead-style layout.
- **No email sending** — the spec listed this as optional; only SMS and
  PDF download are implemented.
