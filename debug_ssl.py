import ssl
import certifi
from urllib3.util.ssl_ import create_urllib3_context
from urllib3 import PoolManager

print("=== Test 1: urllib3 default (no custom context) ===")
try:
    http = PoolManager()
    r = http.request('GET', 'https://api.sandbox.africastalking.com')
    print(f"SUCCESS: {r.status}")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== Test 2: urllib3 with custom context, no version cap ===")
try:
    ctx = create_urllib3_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_verify_locations(certifi.where())
    http = PoolManager(ssl_context=ctx)
    r = http.request('GET', 'https://api.sandbox.africastalking.com')
    print(f"SUCCESS: {r.status}")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== Test 3: urllib3 with custom context, TLS 1.2 cap ===")
try:
    ctx = create_urllib3_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_verify_locations(certifi.where())
    http = PoolManager(ssl_context=ctx)
    r = http.request('GET', 'https://api.sandbox.africastalking.com')
    print(f"SUCCESS: {r.status}")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== Test 4: requests with _TLS12Adapter as currently coded ===")
import requests
from requests.adapters import HTTPAdapter
from urllib3 import PoolManager

class DebugAdapter(HTTPAdapter):
    def __init__(self, ca_bundle, *args, **kwargs):
        self.ca_bundle = ca_bundle
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, num_pools, maxsize, block=False, **kwargs):
        ctx = create_urllib3_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_verify_locations(self.ca_bundle)
        print(f"  SSL context created, CA bundle: {self.ca_bundle}")
        print(f"  TLS min: {ctx.minimum_version}, max: {ctx.maximum_version}")
        self.poolmanager = PoolManager(
            num_pools=num_pools,
            maxsize=maxsize,
            block=block,
            ssl_context=ctx,
            **kwargs,
        )
try:
    s = requests.Session()
    s.trust_env = False
    s.verify = certifi.where()
    s.mount("https://", DebugAdapter(certifi.where()))
    r = s.get('https://api.sandbox.africastalking.com', timeout=10)
    print(f"SUCCESS: {r.status_code}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")

print("\n=== Test 5: requests with NO custom adapter, just verify= ===")
try:
    s = requests.Session()
    s.trust_env = False
    s.verify = certifi.where()
    # No custom adapter mounted
    r = s.get('https://api.sandbox.africastalking.com', timeout=10)
    print(f"SUCCESS: {r.status_code}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")

print("\n=== Test 6: requests with custom adapter, trust_env=True ===")
try:
    s = requests.Session()
    s.trust_env = True  # changed
    s.verify = certifi.where()
    s.mount("https://", DebugAdapter(certifi.where()))
    r = s.get('https://api.sandbox.africastalking.com', timeout=10)
    print(f"SUCCESS: {r.status_code}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")

print("\n=== Test 7: requests with custom adapter, no verify on session ===")
try:
    s = requests.Session()
    s.trust_env = False
    # No session.verify set — let adapter handle it
    s.mount("https://", DebugAdapter(certifi.where()))
    r = s.get('https://api.sandbox.africastalking.com', timeout=10)
    print(f"SUCCESS: {r.status_code}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")

print("\n=== Test 8: Pure urllib3 POST (bypass requests entirely) ===")
import urllib3
import os

api_key = os.environ.get("AT_API_KEY", "")
http = urllib3.PoolManager(ca_certs=certifi.where())
try:
    r = http.request(
        'POST',
        'https://api.sandbox.africastalking.com/version1/messaging',
        fields={
            'username': 'sandbox',
            'to': '+254708538496',
            'message': 'Test via urllib3 direct',
        },
        headers={
            'apiKey': api_key,
            'Accept': 'application/json',
        },
        timeout=30,
    )
    print(f"SUCCESS: status={r.status}, body={r.data[:200]}")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== Test 9: urllib3 PoolManager with ca_certs vs without ===")
import urllib3

print("Without ca_certs:")
try:
    http = urllib3.PoolManager()
    r = http.request('GET', 'https://api.sandbox.africastalking.com', timeout=10)
    print(f"  SUCCESS: {r.status}")
except Exception as e:
    print(f"  FAILED: {e}")

print("With ca_certs=certifi.where():")
try:
    http = urllib3.PoolManager(ca_certs=certifi.where())
    r = http.request('GET', 'https://api.sandbox.africastalking.com', timeout=10)
    print(f"  SUCCESS: {r.status}")
except Exception as e:
    print(f"  FAILED: {e}")

print("With ca_certs but cert_reqs=CERT_NONE:")
try:
    http = urllib3.PoolManager(ca_certs=certifi.where(), cert_reqs='CERT_NONE')
    r = http.request('GET', 'https://api.sandbox.africastalking.com', timeout=10)
    print(f"  SUCCESS: {r.status}")
except Exception as e:
    print(f"  FAILED: {e}")

print("With ssl_context only (no ca_certs):")
try:
    import ssl
    ctx = ssl.create_default_context(cafile=certifi.where())
    http = urllib3.PoolManager(ssl_context=ctx)
    r = http.request('GET', 'https://api.sandbox.africastalking.com', timeout=10)
    print(f"  SUCCESS: {r.status}")
except Exception as e:
    print(f"  FAILED: {e}")

print("\n=== Test 10: ssl.create_default_context(cafile=) via requests adapter ===")
import ssl, certifi, requests
from requests.adapters import HTTPAdapter
from urllib3 import PoolManager

class CreateDefaultCtxAdapter(HTTPAdapter):
    def init_poolmanager(self, num_pools, maxsize, block=False, **kwargs):
        ctx = ssl.create_default_context(cafile=certifi.where())
        self.poolmanager = PoolManager(
            num_pools=num_pools,
            maxsize=maxsize,
            block=block,
            ssl_context=ctx,
            **kwargs,
        )

try:
    s = requests.Session()
    s.trust_env = False
    s.mount("https://", CreateDefaultCtxAdapter())
    r = s.get('https://api.sandbox.africastalking.com', timeout=10)
    print(f"SUCCESS: {r.status_code}")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== Test 11: ssl_context from Test 9 winner, via requests adapter ===")
class ReuseCtxAdapter(HTTPAdapter):
    def __init__(self, ctx, *args, **kwargs):
        self.ctx = ctx
        super().__init__(*args, **kwargs)
    def init_poolmanager(self, num_pools, maxsize, block=False, **kwargs):
        self.poolmanager = PoolManager(
            num_pools=num_pools,
            maxsize=maxsize,
            block=block,
            ssl_context=self.ctx,
            **kwargs,
        )

try:
    # Reuse exact same context that worked in Test 9
    ctx = ssl.create_default_context(cafile=certifi.where())
    s = requests.Session()
    s.trust_env = False
    s.mount("https://", ReuseCtxAdapter(ctx))
    r = s.get('https://api.sandbox.africastalking.com', timeout=10)
    print(f"SUCCESS: {r.status_code}")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== Test 12: requests with NO verify, NO adapter ===")
try:
    s = requests.Session()
    s.trust_env = False
    # Don't set verify at all
    r = s.get('https://api.sandbox.africastalking.com', timeout=10)
    print(f"SUCCESS: {r.status_code}")
except Exception as e:
    print(f"FAILED: {e}")