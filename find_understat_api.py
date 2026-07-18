"""
find_understat_api.py — one-off diagnostic, not part of the pipeline.

Understat's league page no longer embeds data as JSON in the HTML — the
#league-chemp and #league-players divs are empty until JavaScript fetches
data and fills them in. This script opens the page in a real browser and
listens to every network response, printing any that look like JSON data,
so we can find the real API endpoint and hit it directly (faster, no
browser needed) going forward.

Run:  python find_understat_api.py
      (uses patchright, which is already installed from the fbref work)
"""

from patchright.sync_api import sync_playwright

URL = "https://understat.com/league/EPL/2024"

found = []

def handle_response(response):
    # Only care about understat.com's own traffic — ignore ad/analytics domains
    if "understat.com" not in response.url:
        return
    # Skip obvious static assets
    if any(response.url.endswith(ext) for ext in [".js", ".css", ".png", ".jpg", ".svg", ".woff", ".woff2", ".ico"]):
        return
    ctype = response.headers.get("content-type", "")
    try:
        body_preview = response.text()[:500]
    except Exception:
        body_preview = "<could not read body — possibly binary>"
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
    page.wait_for_timeout(3000)

    # Click the actual "Players" filter radio button visible in the page
    # (id="scheme2" is Charts, the players section is a separate <div id="league-players">
    # further down — scroll to it and see if that triggers a lazy load)
    try:
        page.locator("#league-players").scroll_into_view_if_needed(timeout=5000)
        page.wait_for_timeout(3000)
        print("(Scrolled #league-players into view)")
    except Exception as e:
        print(f"(Could not scroll to #league-players: {e})")

    browser.close()

print(f"\n\n=== Done. Found {len(found)} understat.com data responses. ===")
if not found:
    print("Still nothing from understat.com itself. Data may load via a")
    print("mechanism this script isn't triggering — send Claude this full output.")
