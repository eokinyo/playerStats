"""
inspect_understat_api.py — confirms the shape of the discovered endpoint.
No browser needed here — this is a plain JSON API.
"""

import requests
import json

session = requests.Session()
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}

league_page = "https://understat.com/league/EPL/2024"
api_url = "https://understat.com/getLeagueData/EPL/2024"

# Step 1: visit the league page first to pick up any session cookies
print(f"Visiting {league_page} to establish a session...")
page_resp = session.get(league_page, headers=headers, timeout=30)
print(f"  Status: {page_resp.status_code}, cookies received: {list(session.cookies.keys())}")

# Step 2: hit the API with a Referer + XHR header, like the real page's JS does
api_headers = {
    **headers,
    "Referer": league_page,
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}
print(f"\nFetching {api_url} ...")
resp = session.get(api_url, headers=api_headers, timeout=30)
print(f"Status: {resp.status_code}")
print(f"Content-Type: {resp.headers.get('content-type')}\n")

if resp.status_code != 200:
    print(f"Still failing. First 500 chars of body:\n{resp.text[:500]}")
    raise SystemExit(1)

data = resp.json()
print("Top-level keys:", list(data.keys()))

for key, value in data.items():
    print(f"\n--- '{key}' ---")
    if isinstance(value, dict):
        first_id = next(iter(value))
        print(f"  It's a dict keyed by id. Example key: '{first_id}'")
        print(f"  Fields on that entry: {list(value[first_id].keys())}")
        # Show one nested history/sample row too if present
        entry = value[first_id]
        for subkey, subval in entry.items():
            if isinstance(subval, list) and subval:
                print(f"  '{subkey}' is a list — first item fields: {list(subval[0].keys())}")
    elif isinstance(value, list) and value:
        print(f"  It's a list. Fields on first item: {list(value[0].keys())}")

# Save the raw response too, in case Claude needs to see more of it
with open("understat_getLeagueData_sample.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print("\nFull response saved to understat_getLeagueData_sample.json")
