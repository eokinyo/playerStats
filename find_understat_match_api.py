"""
find_understat_match_api.py — one-off diagnostic, not part of the pipeline.

Same technique that found /getLeagueData/ earlier: open a real match page
in a browser and log every understat.com network response, so we can see
what API call actually delivers the shot data now.
"""

from patchright.sync_api import sync_playwright

MATCH_ID = "26602"  # Man United vs Fulham, matchday 1 — same one test_shot_scraping.py used
URL = f"https://understat.com/match/{MATCH_ID}"

found = []

def handle_response(response):
    if "understat.com" not in response.url:
        return
    if any(response.url.endswith(ext) for ext in [".js", ".css", ".png", ".jpg", ".svg", ".woff", ".woff2", ".ico"]):
        return
    ctype = response.headers.get("content-type", "")
    try:
        body_preview = response.text()[:600]
    except Exception:
        body_preview = "<could not read body>"
    found.append((response.url, response.status, ctype, body_preview))
    print(f"\n[UNDERSTAT RESPONSE] {response.status}  content-type={ctype}")
    print(f"  url: {response.url}")
    print(f"  preview: {body_preview}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.on("response", handle_response)

    print(f"Navigating to {URL} ...")
    page.goto(URL, timeout=30000, wait_until="networkidle")
    page.wait_for_timeout(2000)

    browser.close()

print(f"\n\n=== Done. Found {len(found)} understat.com responses. ===")
