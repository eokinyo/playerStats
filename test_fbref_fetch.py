"""
test_fbref_fetch.py — standalone diagnostic, isolated from the main pipeline.

Run this directly:  python test_fbref_fetch.py

It makes ONE request and prints everything about the response, so we can see
what FBref is actually sending back instead of a swallowed "HTTP Error 403:".
"""

from curl_cffi import requests

url = "https://fbref.com/en/comps/9/2024-2025/stats/players/2024-2025-Premier-League-Stats"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

print(f"Requesting: {url}\n")

try:
    resp = requests.get(url, headers=headers, timeout=30, impersonate="chrome")
    print(f"Status code: {resp.status_code}")
    print(f"Response headers:")
    for k, v in resp.headers.items():
        print(f"  {k}: {v}")
    print(f"\nFirst 1000 chars of body:\n{resp.text[:1000]}")
except Exception as e:
    print(f"Request raised an exception: {type(e).__name__}: {e}")

print("\n" + "="*60)
print("Now trying WITHOUT impersonation, for comparison:")
print("="*60 + "\n")

try:
    resp2 = requests.get(url, headers=headers, timeout=30)
    print(f"Status code: {resp2.status_code}")
    print(f"First 500 chars of body:\n{resp2.text[:500]}")
except Exception as e:
    print(f"Request raised an exception: {type(e).__name__}: {e}")
