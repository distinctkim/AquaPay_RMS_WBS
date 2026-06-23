"""
sms.py — Send SMS messages via Africa's Talking gateway.

SSL/TLS strategy
----------------
certifi ships the Mozilla CA bundle.  In some environments (corporate proxies,
cloud sandboxes) an additional TLS-inspection CA sits in front of the remote
host.  We merge certifi's bundle with any extra CA supplied via the environment
variable EXTRA_CA_BUNDLE (path to a PEM file) so that certificate validation is
always enforced — verify=False is never used.

Python 3.14 / OpenSSL 3.0.x compatibility
------------------------------------------
requests has a known bug on Python 3.14 + OpenSSL 3.0.x on Windows where ANY
HTTPS call fails with WRONG_VERSION_NUMBER.  We use urllib3 directly instead,
building the ssl context via ssl.create_default_context(cafile=...) which works
correctly on all platforms.
"""
from __future__ import annotations

import logging
import os
import ssl
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import certifi
import urllib3

logger = logging.getLogger(__name__)


# ── CA bundle helpers ──────────────────────────────────────────────────────────

def _build_ca_bundle() -> str:
    """
    Return the path to a CA bundle that includes:
      1. certifi's Mozilla CA bundle (always present)
      2. Any PEM file pointed to by EXTRA_CA_BUNDLE env var (optional)

    The combined bundle is written to a temp file so urllib3 can
    consume it as a single path.
    """
    extra_ca_path = os.environ.get("EXTRA_CA_BUNDLE", "")

    if not extra_ca_path:
        return certifi.where()

    extra = Path(extra_ca_path)
    if not extra.is_file():
        logger.warning(
            "EXTRA_CA_BUNDLE=%s is not a readable file; falling back to certifi only.",
            extra_ca_path,
        )
        return certifi.where()

    merged_path = Path(tempfile.gettempdir()) / "merged_ca_bundle.pem"
    if not merged_path.exists():
        with open(certifi.where()) as f:
            certifi_pem = f.read()
        with open(extra) as f:
            extra_pem = f.read()
        merged_path.write_text(certifi_pem + "\n" + extra_pem)
        logger.debug("Merged CA bundle written to %s", merged_path)

    return str(merged_path)


def _make_pool_manager() -> urllib3.PoolManager:
    """
    Returns a urllib3 PoolManager with certificate verification enforced.

    Uses ssl.create_default_context(cafile=...) to load the CA bundle.
    Passing ca_certs= directly to PoolManager triggers WRONG_VERSION_NUMBER
    on Python 3.14 + OpenSSL 3.0.x on Windows — this approach avoids that.
    """
    ca_bundle = _build_ca_bundle()
    ctx = ssl.create_default_context(cafile=ca_bundle)
    return urllib3.PoolManager(ssl_context=ctx)


# ── Data class ─────────────────────────────────────────────────────────────────

@dataclass
class SMSResult:
    phone: str
    success: bool
    message: str
    message_id: str = ""


# ── Public API ─────────────────────────────────────────────────────────────────

def send_sms(
    phone: str,
    message: str,
    api_key: str,
    username: str,
    sandbox: bool = True,
    sender_id: str = "",
) -> SMSResult:
    """
    Send a single SMS via Africa's Talking.

    Args:
        phone:      Recipient in international format e.g. +254712345678
        message:    SMS body text.
        api_key:    Africa's Talking API key.
        username:   Africa's Talking account username.
        sandbox:    True for AT sandbox (testing); False for live messages.
        sender_id:  Approved alphanumeric sender ID e.g. 'WATERCO'.
                    Leave empty to use AT's default shortcode.
                    Sender IDs are ignored in sandbox mode.
    """
    url = (
        "https://api.sandbox.africastalking.com/version1/messaging"
        if sandbox
        else "https://api.africastalking.com/version1/messaging"
    )

    fields: dict[str, str] = {
        "username": "sandbox" if sandbox else username,
        "to": phone,
        "message": message,
    }

    # Sender IDs only apply in production — AT sandbox ignores them.
    if sender_id and not sandbox:
        fields["from"] = sender_id

    encoded_body = urlencode(fields).encode("utf-8")

    headers = {
        "apiKey": api_key,
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": str(len(encoded_body)),
    }

    try:
        http = _make_pool_manager()
        response = http.request(
            "POST",
            url,
            body=encoded_body,
            headers=headers,
            timeout=30,
        )

        if response.status in (200, 201):
            return SMSResult(phone, True, "Sent successfully")

        logger.error("AT API error %s: %s", response.status, response.data)
        return SMSResult(phone, False, f"HTTP {response.status}: {response.data.decode()}")

    except urllib3.exceptions.SSLError as e:
        logger.error("SSL error sending to %s: %s", phone, e)
        return SMSResult(phone, False, f"SSL Error: {str(e)}")

    except urllib3.exceptions.TimeoutError:
        logger.error("Timeout sending to %s", phone)
        return SMSResult(phone, False, "Request timed out")

    except Exception as e:
        logger.exception("Unexpected error sending to %s", phone)
        return SMSResult(phone, False, str(e))


def send_bulk_sms(
    rows: list[dict],
    api_key: str,
    username: str,
    sandbox: bool = False,
    sender_id: str = "",
) -> list[SMSResult]:
    """
    Send SMS messages to multiple recipients.

    Args:
        rows:       List of dicts, each with 'phone' and 'message' keys.
        api_key:    Africa's Talking API key.
        username:   Africa's Talking account username.
        sandbox:    True for AT sandbox (testing); False for live messages.
        sender_id:  Approved alphanumeric sender ID e.g. 'WATERCO'.
                    Leave empty to use AT's default shortcode.

    Returns:
        List of SMSResult — one per row, in the same order as the input.
        Failed rows are included rather than raising exceptions so a partial
        failure never aborts the remaining sends.
    """
    return [
        send_sms(
            phone=item["phone"],
            message=item["message"],
            api_key=api_key,
            username=username,
            sandbox=sandbox,
            sender_id=sender_id,
        )
        for item in rows
    ]