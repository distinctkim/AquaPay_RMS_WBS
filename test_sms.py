"""
test_sms.py
===========
Unit tests for sms.py — Africa's Talking SMS gateway client.

Run all unit tests (no credentials needed):
    pytest test_sms.py -v

Run including optional sandbox integration test:
    AT_API_KEY=your_key AT_USERNAME=sandbox pytest test_sms.py -v --integration

What is tested
--------------
Unit tests  (always run — no network, no credentials):
  1.  Correct URL and username for sandbox mode.
  2.  Correct URL and username for production mode.
  3.  apiKey header is set correctly.
  4.  SMSResult.success=True on HTTP 200.
  5.  SMSResult.success=True on HTTP 201.
  6.  SMSResult.success=False on HTTP 400.
  7.  SMSResult.success=False on HTTP 500.
  8.  SSLError is caught and returned as SMSResult(success=False).
  9.  Timeout is caught and returned as SMSResult(success=False).
  10. Generic exception is caught and returned as SMSResult(success=False).
  11. TLS verification is ENABLED — ssl_context uses default CA verification.
  12. PYTHONHTTPSVERIFY env var does not disable TLS.
  13. _build_ca_bundle() returns certifi path when EXTRA_CA_BUNDLE is unset.
  14. _build_ca_bundle() merges bundles when EXTRA_CA_BUNDLE points to a valid file.
  15. _build_ca_bundle() falls back to certifi when EXTRA_CA_BUNDLE path is invalid.
  16. send_bulk_sms() sends one request per row and collects all results.
  17. Partial failures in bulk send are collected, not raised.

Integration test (only when --integration flag and AT_API_KEY env var are set):
  18. Real HTTP POST to AT sandbox returns a 200/201 with queued message status.
"""

from __future__ import annotations

import os
import ssl
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import certifi
import pytest
import urllib3.exceptions

import sys
sys.path.insert(0, str(Path(__file__).parent))

from sms import (
    SMSResult,
    _build_ca_bundle,
    _make_pool_manager,
    send_bulk_sms,
    send_sms,
)

# ── paths & constants ──────────────────────────────────────────────────────────
SANDBOX_URL = "https://api.sandbox.africastalking.com/version1/messaging"
PROD_URL    = "https://api.africastalking.com/version1/messaging"

FAKE_API_KEY  = "*****"
FAKE_USERNAME = "Sandbox"
FAKE_PHONE    = "25471234567"
FAKE_MESSAGE  = "Your bill is KES 500."

AT_SUCCESS_BODY = b'{"SMSMessageData":{"Message":"Sent to 1/1 Total Cost: KES 1.0000","Recipients":[{"statusCode":101,"number":"+25471234567","status":"Success","cost":"KES 1.0000","messageId":"ATXid_abc123"}]}}'


# ── pytest hook: add --integration flag ───────────────────────────────────────
def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run optional sandbox integration tests (requires AT_API_KEY env var).",
    )


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_mock_response(status: int, data: bytes = AT_SUCCESS_BODY) -> MagicMock:
    """Build a mock urllib3 HTTPResponse."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.data = data
    return mock_resp


def _patch_pool_manager(mock_response: MagicMock):
    """
    Patch _make_pool_manager so http.request() returns mock_response.
    Returns the context manager for use in `with` statements.
    """
    mock_http = MagicMock()
    mock_http.request.return_value = mock_response
    return patch("sms._make_pool_manager", return_value=mock_http), mock_http


# ── fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def extra_ca_pem(tmp_path):
    """Create a tiny dummy PEM file to test EXTRA_CA_BUNDLE merging."""
    pem = tmp_path / "extra_ca.pem"
    pem.write_text("# dummy extra CA\n")
    return str(pem)


# ══════════════════════════════════════════════════════════════════════════════
# 1-3  Request shape: correct URL, method, headers, body
# ══════════════════════════════════════════════════════════════════════════════

class TestRequestShape:
    def test_sandbox_url_and_username(self):
        """Test 1 — sandbox=True uses sandbox URL and 'sandbox' as username."""
        mock_resp = _make_mock_response(200)
        ctx_mgr, mock_http = _patch_pool_manager(mock_resp)

        with ctx_mgr:
            send_sms(FAKE_PHONE, FAKE_MESSAGE, FAKE_API_KEY, FAKE_USERNAME, sandbox=True)

        mock_http.request.assert_called_once()
        _, call_url = mock_http.request.call_args[0]
        assert call_url == SANDBOX_URL

        # body is url-encoded bytes e.g. b"username=sandbox&to=...&message=..."
        body = mock_http.request.call_args[1]["body"].decode()
        assert "username=sandbox" in body
        assert f"to={FAKE_PHONE}" in body
        assert "message=" in body

    def test_production_url_and_username(self):
        """Test 2 — sandbox=False uses production URL and the real username."""
        mock_resp = _make_mock_response(200)
        ctx_mgr, mock_http = _patch_pool_manager(mock_resp)

        with ctx_mgr:
            send_sms(FAKE_PHONE, FAKE_MESSAGE, FAKE_API_KEY, FAKE_USERNAME, sandbox=False)

        _, call_url = mock_http.request.call_args[0]
        assert call_url == PROD_URL

        body = mock_http.request.call_args[1]["body"].decode()
        assert f"username={FAKE_USERNAME}" in body

    def test_api_key_in_header(self):
        """Test 3 — apiKey header is set correctly."""
        mock_resp = _make_mock_response(200)
        ctx_mgr, mock_http = _patch_pool_manager(mock_resp)

        with ctx_mgr:
            send_sms(FAKE_PHONE, FAKE_MESSAGE, FAKE_API_KEY, FAKE_USERNAME, sandbox=True)

        headers = mock_http.request.call_args[1]["headers"]
        assert headers["apiKey"] == FAKE_API_KEY
        assert headers["Accept"] == "application/json"
        assert "application/x-www-form-urlencoded" in headers["Content-Type"]


# ══════════════════════════════════════════════════════════════════════════════
# 4-7  HTTP status code handling
# ══════════════════════════════════════════════════════════════════════════════

class TestHTTPStatusHandling:
    def test_http_200_returns_success(self):
        """Test 4 — HTTP 200 → SMSResult.success is True."""
        mock_resp = _make_mock_response(200)
        ctx_mgr, mock_http = _patch_pool_manager(mock_resp)

        with ctx_mgr:
            result = send_sms(FAKE_PHONE, FAKE_MESSAGE, FAKE_API_KEY, FAKE_USERNAME)

        assert result.success is True
        assert result.phone == FAKE_PHONE

    def test_http_201_returns_success(self):
        """Test 5 — HTTP 201 → SMSResult.success is True."""
        mock_resp = _make_mock_response(201)
        ctx_mgr, mock_http = _patch_pool_manager(mock_resp)

        with ctx_mgr:
            result = send_sms(FAKE_PHONE, FAKE_MESSAGE, FAKE_API_KEY, FAKE_USERNAME)

        assert result.success is True

    def test_http_400_returns_failure(self):
        """Test 6 — HTTP 400 → SMSResult.success is False."""
        mock_resp = _make_mock_response(400, b'{"error": "Bad Request"}')
        ctx_mgr, mock_http = _patch_pool_manager(mock_resp)

        with ctx_mgr:
            result = send_sms(FAKE_PHONE, FAKE_MESSAGE, FAKE_API_KEY, FAKE_USERNAME)

        assert result.success is False
        assert "400" in result.message

    def test_http_500_returns_failure(self):
        """Test 7 — HTTP 500 → SMSResult.success is False."""
        mock_resp = _make_mock_response(500, b"Internal Server Error")
        ctx_mgr, mock_http = _patch_pool_manager(mock_resp)

        with ctx_mgr:
            result = send_sms(FAKE_PHONE, FAKE_MESSAGE, FAKE_API_KEY, FAKE_USERNAME)

        assert result.success is False
        assert "500" in result.message


# ══════════════════════════════════════════════════════════════════════════════
# 8-10  Exception handling
# ══════════════════════════════════════════════════════════════════════════════

class TestExceptionHandling:
    def test_ssl_error_returns_failure(self):
        """Test 8 — SSLError is caught; result is failure, not a raised exception."""
        mock_http = MagicMock()
        mock_http.request.side_effect = urllib3.exceptions.SSLError("cert verify failed")

        with patch("sms._make_pool_manager", return_value=mock_http):
            result = send_sms(FAKE_PHONE, FAKE_MESSAGE, FAKE_API_KEY, FAKE_USERNAME)

        assert result.success is False
        assert "SSL" in result.message

    def test_timeout_returns_failure(self):
        """Test 9 — Timeout is caught; result is failure."""
        mock_http = MagicMock()
        mock_http.request.side_effect = urllib3.exceptions.TimeoutError()

        with patch("sms._make_pool_manager", return_value=mock_http):
            result = send_sms(FAKE_PHONE, FAKE_MESSAGE, FAKE_API_KEY, FAKE_USERNAME)

        assert result.success is False
        assert "timed out" in result.message.lower()

    def test_generic_exception_returns_failure(self):
        """Test 10 — Unexpected exceptions are caught and returned as failure."""
        mock_http = MagicMock()
        mock_http.request.side_effect = RuntimeError("something broke")

        with patch("sms._make_pool_manager", return_value=mock_http):
            result = send_sms(FAKE_PHONE, FAKE_MESSAGE, FAKE_API_KEY, FAKE_USERNAME)

        assert result.success is False


# ══════════════════════════════════════════════════════════════════════════════
# 11-12  TLS security assertions
# ══════════════════════════════════════════════════════════════════════════════

class TestTLSSecurity:
    def test_tls_verification_is_enabled(self):
        """Test 11 — _make_pool_manager uses an ssl_context with cert verification on."""
        with patch("sms.ssl.create_default_context") as mock_ctx_factory:
            mock_ctx = MagicMock()
            mock_ctx_factory.return_value = mock_ctx
            _make_pool_manager()
            # Must be called with a cafile — never with check_hostname=False or verify_mode=NONE
            mock_ctx_factory.assert_called_once()
            _, kwargs = mock_ctx_factory.call_args
            cafile = kwargs.get("cafile") or mock_ctx_factory.call_args[0][0] if mock_ctx_factory.call_args[0] else kwargs.get("cafile")
            # cafile must be a non-empty path string
            assert cafile, "SECURITY VIOLATION: cafile not passed to create_default_context!"

    def test_tls_verify_is_not_disabled_in_environment(self):
        """Test 12 — PYTHONHTTPSVERIFY env var must not disable TLS."""
        assert os.environ.get("PYTHONHTTPSVERIFY") != "0", (
            "PYTHONHTTPSVERIFY=0 disables TLS verification globally — remove it."
        )


# ══════════════════════════════════════════════════════════════════════════════
# 13-15  CA bundle building
# ══════════════════════════════════════════════════════════════════════════════

class TestCABundle:
    def test_no_extra_ca_returns_certifi(self, monkeypatch):
        """Test 13 — Without EXTRA_CA_BUNDLE, certifi path is returned."""
        monkeypatch.delenv("EXTRA_CA_BUNDLE", raising=False)
        merged = Path(tempfile.gettempdir()) / "merged_ca_bundle.pem"
        merged.unlink(missing_ok=True)
        result = _build_ca_bundle()
        assert result == certifi.where()

    def test_extra_ca_bundle_merges_files(self, monkeypatch, extra_ca_pem):
        """Test 14 — With a valid EXTRA_CA_BUNDLE, a merged file is produced."""
        monkeypatch.setenv("EXTRA_CA_BUNDLE", extra_ca_pem)
        merged = Path(tempfile.gettempdir()) / "merged_ca_bundle.pem"
        merged.unlink(missing_ok=True)

        result = _build_ca_bundle()

        assert result != certifi.where()
        content = Path(result).read_text()
        assert "dummy extra CA" in content
        assert "-----BEGIN CERTIFICATE-----" in content

    def test_invalid_extra_ca_falls_back_to_certifi(self, monkeypatch):
        """Test 15 — Non-existent EXTRA_CA_BUNDLE path falls back to certifi."""
        monkeypatch.setenv("EXTRA_CA_BUNDLE", "/nonexistent/path/ca.pem")
        merged = Path(tempfile.gettempdir()) / "merged_ca_bundle.pem"
        merged.unlink(missing_ok=True)
        result = _build_ca_bundle()
        assert result == certifi.where()


# ══════════════════════════════════════════════════════════════════════════════
# 16-17  Bulk sending
# ══════════════════════════════════════════════════════════════════════════════

class TestBulkSMS:
    def test_bulk_sms_sends_one_request_per_row(self):
        """Test 16 — send_bulk_sms() sends N requests for N rows."""
        mock_http = MagicMock()
        mock_http.request.return_value = _make_mock_response(200)

        rows = [
            {"phone": "254712345678", "message": "Bill: KES 500"},
            {"phone": "254723456789", "message": "Bill: KES 750"},
            {"phone": "254734567890", "message": "Bill: KES 300"},
        ]

        with patch("sms._make_pool_manager", return_value=mock_http):
            results = send_bulk_sms(rows, FAKE_API_KEY, FAKE_USERNAME, sandbox=True)

        assert len(results) == 3
        assert mock_http.request.call_count == 3
        assert all(r.success for r in results)
        phones = [r.phone for r in results]
        assert "254712345678" in phones
        assert "254723456789" in phones

    def test_bulk_sms_collects_mixed_results(self):
        """Test 17 — Partial failures are collected, not raised."""
        mock_http = MagicMock()
        mock_http.request.side_effect = [
            _make_mock_response(200),
            _make_mock_response(400, b'{"error": "bad"}'),
        ]

        rows = [
            {"phone": "254712345678", "message": "OK"},
            {"phone": "254799999999", "message": "Fail"},
        ]

        with patch("sms._make_pool_manager", return_value=mock_http):
            results = send_bulk_sms(rows, FAKE_API_KEY, FAKE_USERNAME, sandbox=True)

        assert results[0].success is True
        assert results[1].success is False


# ══════════════════════════════════════════════════════════════════════════════
# 18  Optional integration test (real AT sandbox)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestSandboxIntegration:
    """
    Real network call to Africa's Talking sandbox.

    Required environment variables:
        AT_API_KEY   — your Africa's Talking API key
        AT_USERNAME  — your AT username (usually 'sandbox' for sandbox)
        EXTRA_CA_BUNDLE — path to extra CA PEM if your environment needs it

    Skip unless --integration flag is passed:
        pytest test_sms.py --integration -v
    """

    @pytest.fixture(autouse=True)
    def require_integration_flag(self, request):
        if not request.config.getoption("--integration", default=False):
            pytest.skip("Pass --integration to run sandbox integration tests.")

    @pytest.fixture(autouse=True)
    def require_credentials(self):
        if not os.environ.get("AT_API_KEY"):
            pytest.skip("AT_API_KEY environment variable not set.")

    def test_send_to_sandbox_returns_success(self):
        """
        Test 18 — Real POST to AT sandbox; assert HTTP 200/201 and queued status.

        Set credentials:
            export AT_API_KEY=your_key
            export AT_USERNAME=sandbox          # or your actual username
            export EXTRA_CA_BUNDLE=/path/to/ca.pem   # if needed in your environment
        """
        api_key  = os.environ["AT_API_KEY"]
        username = os.environ.get("AT_USERNAME", "sandbox")

        result = send_sms(
            phone="+2547080000000",
            message="Test: Kenya Water Bill Notifier integration test.",
            api_key=api_key,
            username=username,
            sandbox=True,
        )

        assert result.success is True, (
            f"Sandbox send failed. Message: {result.message}\n"
            "Check that:\n"
            "  1. AT_API_KEY is correct.\n"
            "  2. EXTRA_CA_BUNDLE points to the right CA if your env uses TLS inspection.\n"
            "  3. The network can reach api.sandbox.africastalking.com:443."
        )
        
