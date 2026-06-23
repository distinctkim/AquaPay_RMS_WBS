import socket
import ssl
import certifi

print("=== Test 1: Raw socket TLS ===")
try:
    ctx = ssl.create_default_context(cafile=certifi.where())
    with socket.create_connection(("api.sandbox.africastalking.com", 443), timeout=10) as sock:
        with ctx.wrap_socket(sock, server_hostname="api.sandbox.africastalking.com") as ssock:
            print(f"TLS version: {ssock.version()}")
            print(f"Cipher: {ssock.cipher()}")
            print("SUCCESS")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== Test 2: Check certifi CA bundle ===")
print(f"certifi path: {certifi.where()}")

print("\n=== Test 3: Raw socket without SSL (check if port 443 returns HTTP) ===")
try:
    with socket.create_connection(("api.sandbox.africastalking.com", 443), timeout=10) as sock:
        sock.sendall(b"GET / HTTP/1.0\r\nHost: api.sandbox.africastalking.com\r\n\r\n")
        data = sock.recv(1024)
        print(f"Raw response (first 200 bytes): {data[:200]}")
        print("NOTE: If you see 'HTTP/' here, a proxy is stripping TLS!")
except Exception as e:
    print(f"FAILED: {e}")

print("\n=== Test 4: What proxy does requests see? ===")
import requests
from urllib.request import getproxies
print(f"System proxies: {getproxies()}")
s = requests.Session()
settings = s.merge_environment_settings('https://api.sandbox.africastalking.com', {}, True, None, None)
print(f"Requests effective settings: {settings}")

print("\n=== Test 5: requests direct GET ===")
try:
    r = requests.get('https://api.sandbox.africastalking.com', timeout=10)
    print(f"Status: {r.status_code}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")