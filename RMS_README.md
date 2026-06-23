# Rental Management System (RMS) Module

Extends the Kenya Water Bill SMS Notifier with tenant, unit, lease, payment,
invoice, and reporting management — reusing the existing Africa's Talking
SMS integration rather than duplicating it.

## What was added

```
AutomateBilingSMS/
├── rms/
│   ├── models.py          SQLAlchemy models (Unit, Tenant, Lease, FeeType,
│   │                      WaterCharge, Payment, Invoice, InvoiceLine, SmsLog)
│   ├── db.py               Engine/session setup (SQLite by default)
│   ├── invoicing.py         Invoice generation logic (idempotent)
│   ├── payments.py          Payment recording and allocation
│   ├── reports.py           Day/week/month/year, single-tenant or aggregate reports
│   ├── pdf.py                Invoice PDF generation (ReportLab)
│   ├── sms_templates.py      Invoice/reminder SMS templates — calls the
│   │                         EXISTING send_sms() in sms.py, does not duplicate it
│   ├── scheduler.py          APScheduler background jobs (separate process)
│   ├── seed.py               Sample data for demos
│   └── ui_helpers.py          Shared Streamlit session/db helpers
├── pages/                    Streamlit multipage UI (auto-discovered by
│   1_Dashboard.py            Streamlit's `pages/` convention — no change
│   2_Units.py                needed to app.py for these to appear in the
│   3_Tenants.py               sidebar nav)
│   4_Leases.py
│   5_Payments.py
│   6_Invoices.py
│   7_Reports.py
│   8_Settings.py
├── tests/
│   ├── conftest.py
│   ├── test_invoicing.py     16/16 passing — see "Tests" below
│   ├── test_payments.py
│   └── test_reports.py
└── .env.example
```

The existing `app.py`, `sms.py`, `message.py`, `processor.py` were **not
modified** — the water-bill SMS blast tool keeps working exactly as before.
The RMS module sits alongside it and reuses `sms.py`'s `send_sms()` directly.

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Required for SMS sending from the RMS module:
- `AT_API_KEY`, `AT_USERNAME` — same Africa's Talking credentials as the main app
- `AT_SANDBOX=true` while testing; set to `false` to send real SMS

Optional:
- `RMS_DATABASE_URL` — defaults to a local SQLite file (`rms_data.db`). Set
  to a `postgresql://` URL to use Postgres in production; no code changes
  needed elsewhere.
- `RMS_REMINDER_DAYS_BEFORE_DUE` — defaults to 7.

**Credentials are never stored in the database.** The Streamlit pages take
SMS credentials via the sidebar (session-only); the scheduler process reads
them from environment variables. Never commit `.env` to version control.

## Running

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run the Streamlit app (UI)

```bash
streamlit run app.py
```

The RMS pages (Dashboard, Units, Tenants, Leases, Payments, Invoices,
Reports, Settings) appear automatically in the left sidebar — Streamlit
auto-discovers anything in `pages/`.

### Seed sample data (optional, for a demo)

```bash
python -m rms.seed
```

Creates 3 units, 2 tenants, 2 active leases, and generates invoices for the
current month — including one partial payment — so the Dashboard and Reports
pages have something to show immediately.

### Run the background scheduler (separate process)

The scheduler must run as its **own process**, separate from `streamlit
run` — see the docstring in `rms/scheduler.py` for why (Streamlit's rerun
model isn't suited to long-running background jobs).

```bash
python -m rms.scheduler
```

This starts a blocking scheduler with three jobs:
- Monthly invoice generation — checks daily at 23:00 whether tomorrow is the
  1st of a new month, and if so generates invoices for every active lease
- Reminders N days before due (default 7) — daily at 08:00
- Due-date and overdue reminders — daily at 08:15 (also flips invoice status
  to `overdue` for unpaid invoices past their due date)

**In production**, run this via a process manager (systemd service, Heroku
worker dyno) or trigger the individual job functions
(`job_generate_monthly_invoices`, etc.) from a Cloud Scheduler + Cloud
Function / cron job instead of running it as a permanent blocking process —
both are supported since the job functions are plain, standalone functions.

### Generating invoices manually (without the scheduler)

From the **Invoices** page → "Generate Invoices" tab → pick year/month →
"Generate Invoices Now". Safe to click multiple times for the same month;
existing invoices for that period are detected and skipped, not duplicated.

## Tests

```bash
pytest tests/ -v
```

16 tests, covering:
- Invoice composition matches the spec's worked example exactly (rent + water
  + garbage + security = correct subtotal/total)
- Lease-level rent override behaviour
- **Idempotency**: generating invoices twice for the same lease/period does
  not create a duplicate (the spec's explicit requirement)
- Partial payments, full payments, multiple partial payments accumulating to
  paid, and overpayments being tracked as tenant credit rather than lost
- Unallocated payments not affecting any invoice
- Report scoping (single tenant vs. all houses) and date-range filtering

PDF generation and the multipage Streamlit UI were also verified by:
- Rendering an actual invoice PDF from seeded data and visually confirming
  totals match (12,000 rent + 750 water + 300 garbage + 500 security =
  13,550 subtotal/total, with the seeded 50% payment showing as 6,775 paid /
  6,775 outstanding)
- Running every page in `pages/` through Streamlit's `AppTest` harness
  against a real seeded database with zero runtime exceptions

## Known simplifications (documented honestly, not hidden)

- **Invoice numbering** is a simple per-month sequential counter
  (`INV-YYYY-MM-NNNN`), not a database sequence — adequate for a
  single-instance deployment but would need locking/atomicity work for
  concurrent multi-writer production use.
- **A tenant can hold only one active lease at a time** in this
  implementation (enforced in the Leases page UI, not at the DB level) —
  the spec's model allows multiple leases historically (lease history is
  preserved), but does not explicitly require simultaneous active leases
  per tenant, so this was a reasonable scope decision rather than a
  guessed requirement.
- **Authorization** (spec section 10) is not implemented — there's no
  existing auth in the base app to integrate with, and the spec says to
  "document how to integrate with existing auth" in that case rather than
  invent one. Treat all RMS pages as trusted/internal-use only.
- **Email sending** (`Invoice.sent_email`) has a field reserved for it but
  no email backend is wired up, since the spec marks email as optional and
  the base app has no existing email integration to reuse.
