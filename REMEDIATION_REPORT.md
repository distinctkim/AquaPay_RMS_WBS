# SSL Remediation Report — Africa's Talking SMS Client
## Kenya Water Bill SMS Notifier

---

## 1. Files Inspected

| File | Role | SSL-relevant? |
|------|------|--------------|
| `sms.py` | AT SMS gateway client — all HTTP calls originate here | ✅ Yes — primary focus |
| `app.py` | Streamlit UI — calls `send_sms()` from sms.py | No direct HTTP |
| `cli.py` | CLI — calls `send_bulk_sms()` from sms.py | No direct HTTP |
| `processor.py` | Excel loading & phone validation | No network calls |
| `message.py` | SMS message generator | No network calls |
| `requirements.txt` | Dependency manifest | Reviewed for CA/TLS libs |

---

## 2. Root Cause

### Diagnosis

The original `sms.py` hard-pinned `certifi`'s Mozilla CA bundle as the only
trusted CA store.  This is correct for open-internet environments but **fails
in environments that perform TLS inspection** (corporate proxies, cloud
sandboxes, CI environments with egress filtering).

In those environments a **custom TLS inspection CA** signs the certificate
presented on the connection — a CA that certifi does not know about — causing:

```
ssl.SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]
certificate verify failed: self-signed certificate in certificate chain
```

Confirmed via:
```bash
echo Q | openssl s_client -connect api.sandbox.africastalking.com:443 \
  -servername api.sandbox.africastalking.com 2>/dev/null | grep issuer
# issuer=O = Anthropic, CN = sandbox-egress-production TLS Inspection CA
```

The inspection CA is not in certifi's bundle → handshake fails.

### What was NOT present (good news)
- No `verify=False` anywhere in the codebase ✅
- No `rejectUnauthorized=false` ✅
- No `PYTHONHTTPSVERIFY=0` ✅
- No `urllib3.disable_warnings()` ✅

The code was already security-conscious. The failure was purely an
**environmental CA gap**, not an insecure workaround.

---

## 3. What Was Changed

### `sms.py`

| Before | After |
|--------|-------|
| `ctx.load_verify_locations(certifi.where())` only | New `_build_ca_bundle()` merges certifi + `EXTRA_CA_BUNDLE` env var |
| No mechanism to add extra CAs | `EXTRA_CA_BUNDLE=/path/to/ca.pem` supported via env var |
| Imported unused `socket`, `urllib3`, `os` at top level | Cleaned up imports |

**Core change — `_build_ca_bundle()`:**
```python
def _build_ca_bundle() -> str:
    extra_ca_path = os.environ.get("EXTRA_CA_BUNDLE", "")
    if not extra_ca_path:
        return certifi.where()          # no change in standard environments
    # merge certifi + extra CA into a single temp PEM file
    ...
    return str(merged_path)
```

TLS verification is **always enforced** — `verify=False` is never set.

---

## 4. How to Run Tests

### Unit tests (no credentials, no network):
```bash
pip install pytest pytest-mock requests-mock
pytest tests/test_sms.py -v
```

Expected: **18 passed, 1 skipped**

### With sandbox integration test (real AT credentials):
```bash
export AT_API_KEY=your_africastalking_api_key
export AT_USERNAME=sandbox
export EXTRA_CA_BUNDLE=/path/to/your/inspection_ca.pem   # if needed
pytest tests/test_sms.py -v --integration
```

---

## 5. Environment Setup for Your Machine

### Step 1 — Extract the inspection CA (if your environment intercepts TLS)
```bash
echo Q | openssl s_client \
  -connect api.sandbox.africastalking.com:443 \
  -servername api.sandbox.africastalking.com \
  -showcerts 2>/dev/null \
  | awk 'BEGIN{p=0} /-----BEGIN CERTIFICATE-----/{p++} p==2{print} /-----END CERTIFICATE-----/ && p==2{exit}' \
  > sandbox_ca.pem
```

If `issuer` shows your corporate/proxy CA — you need this file.
If `issuer` shows a public CA (DigiCert, Let's Encrypt, etc.) — you do not.

### Step 2 — Set the environment variable
```bash
export EXTRA_CA_BUNDLE=/full/path/to/sandbox_ca.pem
```

For permanent setup, add to `~/.bashrc` or your CI secrets.

### Step 3 — Run the app
```bash
streamlit run app.py
# or
python cli.py --file customers.xlsx --api-key $AT_API_KEY --username sandbox --sandbox
```

---

## 6. GitHub Actions CI Snippet

```yaml
name: SMS Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install CA certificates
        run: sudo apt-get update && sudo apt-get install -y ca-certificates

      - name: Install dependencies
        run: pip install -r requirements.txt pytest pytest-mock requests-mock

      - name: Run unit tests
        run: pytest tests/test_sms.py -v -m "not integration"

      - name: Run integration tests (sandbox)
        if: ${{ secrets.AT_API_KEY != '' }}
        env:
          AT_API_KEY: ${{ secrets.AT_API_KEY }}
          AT_USERNAME: sandbox
          EXTRA_CA_BUNDLE: ${{ secrets.EXTRA_CA_PEM_PATH }}   # optional
        run: pytest tests/test_sms.py -v --integration
```

---

## 7. Verification Checklist

Run these commands and check the expected output:

```bash
# 1. Confirm certifi is installed
python -c "import certifi; print(certifi.where())"
# Expected: a path ending in cacert.pem

# 2. Confirm TLS handshake with your CA bundle
python -c "
import ssl, socket, certifi, os
ca = os.environ.get('EXTRA_CA_BUNDLE', certifi.where())
ctx = ssl.create_default_context(cafile=ca)
with ctx.wrap_socket(socket.create_connection(('api.sandbox.africastalking.com', 443), timeout=5),
                     server_hostname='api.sandbox.africastalking.com') as s:
    print('TLS OK:', s.cipher())
"
# Expected: TLS OK: ('TLS_AES_256_GCM_SHA384', 'TLSv1.3', 256)

# 3. Run unit tests
pytest tests/test_sms.py -v
# Expected: 18 passed, 1 skipped

# 4. Verify no verify=False in codebase
grep -r "verify=False\|rejectUnauthorized\|PYTHONHTTPSVERIFY" . --include="*.py"
# Expected: no output
```

---

## 8. Summary

| Item | Status |
|------|--------|
| Root cause identified | ✅ TLS inspection CA not in certifi bundle |
| Insecure bypass (verify=False) | ✅ Never present — not introduced |
| Fix implemented | ✅ `EXTRA_CA_BUNDLE` env var + `_build_ca_bundle()` merge |
| Unit tests | ✅ 18 tests, all pass |
| Integration test | ✅ Implemented, skipped without `--integration` flag |
| CI YAML provided | ✅ GitHub Actions snippet included |
| Secrets hardcoded | ✅ None — all via env vars |
