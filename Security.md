# Security Policy

## Supported Versions

The following versions of the **Python SMS-Based Water Billing Application** are currently receiving security updates:

| Version | Supported          |
| ------- | ------------------ |
| 2.x.x   | :white_check_mark: |
| 1.5.x   | :white_check_mark: |
| 1.0.x   | :x:                |
| < 1.0   | :x:                |

> Only the two most recent minor versions are actively maintained. Users on unsupported versions are strongly encouraged to upgrade.

---

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue in this project — including but not limited to SMS spoofing, authentication bypasses, payment data exposure, or injection vulnerabilities — please follow the responsible disclosure process below.

### How to Report

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please report them privately via one of the following:

- **GitHub Private Vulnerability Reporting** *(preferred)*: Navigate to the [Security tab](../../security/advisories/new) of this repository and click **"Report a vulnerability"**.
- **Email**: Send a detailed report to `distinctionkim@gmail.com` with the subject line `[SECURITY] <brief description>`.

### What to Include in Your Report

To help us triage and resolve the issue quickly, please provide:

- A clear description of the vulnerability and its potential impact
- The affected version(s)
- Step-by-step instructions to reproduce the issue
- Any relevant code snippets, logs, or screenshots
- Your suggested fix or mitigation (optional but appreciated)

### What to Expect

| Stage | Timeframe |
| ----- | --------- |
| Acknowledgement of your report | Within **48 hours** |
| Initial triage and severity assessment | Within **5 business days** |
| Status update (accepted / declined) | Within **10 business days** |
| Patch release for accepted critical issues | Within **72 hours** of confirmation |
| Patch release for accepted high/medium issues | Within **14 days** of confirmation |
| Public disclosure (coordinated) | After patch is released and deployed |

### Severity Classification

We use the following severity levels based on CVSS scores:

| Severity | CVSS Score | Examples |
| -------- | ---------- | -------- |
| **Critical** | 9.0 – 10.0 | Payment data breach, remote code execution, SMS gateway takeover |
| **High** | 7.0 – 8.9 | Authentication bypass, customer PII exposure, SQL injection |
| **Medium** | 4.0 – 6.9 | Rate limit bypass, insecure session handling, information leakage |
| **Low** | 0.1 – 3.9 | Minor info disclosure, non-exploitable misconfigurations |

### Accepted vs. Declined Vulnerabilities

- **Accepted**: You will be credited in the release notes (unless you prefer anonymity), notified when the fix is live, and kept updated throughout the resolution process.
- **Declined**: We will provide a clear explanation of why the report does not qualify as a vulnerability (e.g., intended behaviour, out of scope, duplicate).

---

## Scope

The following are **in scope** for vulnerability reports:

- Python application source code (`/app`, `/src`)
- SMS gateway integration and webhook handling
- Authentication and session management
- Payment processing and M-Pesa/mobile money integration
- REST API endpoints
- Database query logic (SQL injection, data exposure)

The following are **out of scope**:

- Vulnerabilities in third-party SMS gateway provider infrastructure
- Social engineering attacks against project maintainers
- Issues in unsupported versions (see table above)
- Denial-of-service attacks requiring significant resources
- Reports generated purely by automated scanners without a proof-of-concept

---

## Security Best Practices for Deployment

If you are self-hosting this application, ensure you follow these baseline security practices:

- Store all API keys and secrets in environment variables — **never hardcode credentials**
- Use HTTPS/TLS 1.2+ for all endpoints and SMS gateway communication
- Enable Multi-Factor Authentication (MFA) on all admin accounts
- Keep all Python dependencies up to date (`pip-audit` or `safety check`)
- Rotate SMS gateway API keys every 90 days
- Restrict database access to the application server only (no public exposure)
- Review application logs regularly for anomalous activity

---

## Disclosure Policy

This project follows **Coordinated Vulnerability Disclosure (CVD)**. We ask that you:

1. Give us a reasonable time to investigate and patch before any public disclosure
2. Avoid accessing, modifying, or deleting user data during your research
3. Not perform actions that could disrupt service for other users

We are committed to working with security researchers in good faith and will not pursue legal action against researchers who follow this policy.

---

## Hall of Fame

We gratefully acknowledge researchers who have responsibly disclosed vulnerabilities:

<!-- Researchers will be listed here after coordinated disclosure -->
*No entries yet — be the first responsible discloser!*

---

*This security policy is reviewed and updated annually or after any significant security incident.*
