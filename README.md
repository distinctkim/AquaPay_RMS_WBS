# 💧 Kenya Water Bill SMS Notifier

Send automated SMS water-bill notifications to Kenyan customers via Africa's Talking.

---

## Project Structure

```
Waterbilling sms_notifier/
├── app.py               # Streamlit web app (main interface)
├── cli.py               # Command-line interface alternative
├── processor.py         # Excel loading & validation logic
├── message.py           # SMS message generation
├── sms.py               # Africa's Talking SMS gateway
├── generate_sample.py   # Creates a test Excel file
└── requirements.txt
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Get Africa's Talking credentials

1. Sign up at [africastalking.com](https://africastalking.com)
2. Create an app and note your **API Key** and **Username**
3. Use the **sandbox** for free testing (no real SMS sent)

---

## Usage

### Web App (recommended)

```bash
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

- Enter your AT credentials in the sidebar
- Upload your Excel file
- Preview the data and a sample message
- Click **Send SMS**

### Command Line

```bash
# Dry run — preview messages only
python cli.py --file customers.xlsx --api-key YOUR_KEY --username sandbox --sandbox --dry-run

# Send via sandbox
python cli.py --file customers.xlsx --api-key YOUR_KEY --username sandbox --sandbox

# Send live
python cli.py --file customers.xlsx --api-key YOUR_KEY --username YOUR_USERNAME
```

---

## Excel File Format

The uploaded `.xlsx` file must have these **exact column names**:

| Column           | Description                        | Example      |
|------------------|------------------------------------|--------------|
| Phone Number     | Kenya number (any common format)   | 0712345678   |
| Previous Reading | Last meter reading (m³)            | 100          |
| Current Reading  | Current meter reading (m³)         | 145          |
| Units Consumed   | Difference in readings             | 45           |
| Cost per Unit    | Price per m³ (KES)                 | 65           |
| Total Cost       | Total bill amount (KES)            | 2925         |

### Accepted phone number formats

| Format            | Example          |
|-------------------|------------------|
| Local             | `0712345678`     |
| International +   | `+254712345678`  |
| International     | `254712345678`   |

Supports Safaricom (07xx), Airtel (073x/074x/075x/076x), and Telkom (077x).

---

## Generate a Test File

```bash
python generate_sample.py
# Creates: customers_sample.xlsx
```

---

## Sample SMS Output

```
Dear Customer, your water bill summary:
Prev Reading : 100.0 m3
Curr Reading : 145.0 m3
Units Used   : 45.0 m3
Rate         : KES 65.00/m3
TOTAL DUE    : KES 2,925.00
Pay via M-Pesa or visit our offices. Thank you!
```
Here's a summary of what I found and fixed over a debugging session where I continually received a WRONG_VERSION_NUMBER error when testing the application:
Root cause: A bug in Python 3.14 + OpenSSL 3.0.19 on Windows where passing ca_certs= directly to urllib3's PoolManager corrupts the TLS handshake with WRONG_VERSION_NUMBER. This affected requests entirely since it passes the CA bundle that way internally.
Fixes applied:

Replaced requests with urllib3 directly — urllib3 works correctly when the SSL context is built via ssl.create_default_context(cafile=...) and passed in as ssl_context=
Used urlencode() for the POST body — urllib3's fields= sends multipart/form-data by default; Africa's Talking requires application/x-www-form-urlencoded
Updated tests to mock _make_pool_manager instead of requests_mock, and check body= bytes instead of fields= dict
