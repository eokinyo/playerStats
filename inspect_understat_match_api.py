"""
inspect_understat_match_api.py — confirms the full shape of getMatchData.
Same session + Referer + XHR technique that worked for getLeagueData.
"""

import requests
import json

match_id = "26602"
match_page = f"https://understat.com/match/{match_id}"
api_url = f"https://understat.com/getMatchData/{match_id}"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}

session = requests.Session()
print(f"Visiting {match_page} to establish a session...")
page_resp = session.get(match_page, headers=headers, timeout=30)
print(f"  Status: {page_resp.status_code}")

api_headers = {
    **headers,
    "Referer": match_page,
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}
print(f"\nFetching {api_url} ...")
resp = session.get(api_url, headers=api_headers, timeout=30)
print(f"Status: {resp.status_code}")

data = resp.json()
print("\nTop-level keys:", list(data.keys()))

for key, value in data.items():
    print(f"\n--- '{key}' ---")
    if isinstance(value, dict):
        # e.g. rosters: {"h": {...}, "a": {...}}
        for subkey, subval in value.items():
            print(f"  '{subkey}':")
            if isinstance(subval, dict):
                first_id = next(iter(subval), None)
                if first_id is not None:
                    print(f"    dict keyed by id, example fields: {list(subval[first_id].keys())}")
            elif isinstance(subval, list) and subval:
                print(f"    list, first item fields: {list(subval[0].keys())}")
                print(f"    first item: {json.dumps(subval[0], indent=6)[:500]}")
    elif isinstance(value, list) and value:
        print(f"  list, first item fields: {list(value[0].keys())}")

with open("understat_getMatchData_sample.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print("\nFull response saved to understat_getMatchData_sample.json")
