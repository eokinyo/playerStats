"""
ingestion/fbref_scraper.py
Scrapes advanced player and team stats from FBref.com.

FBref exposes clean HTML tables powered by StatsBomb data — the deepest
free advanced stats available. We use pandas.read_html() to pull them.

Polite scraping rules applied:
  - 6-second delay between every request (config.SCRAPE_DELAY_SECONDS)
  - Raw HTML cached to data/<league>/raw/ so we don't re-scrape unnecessarily

NOTE on the HTTP client — READ THIS BEFORE CHANGING IT:
  FBref sits behind Cloudflare Turnstile — an INTERACTIVE JAVASCRIPT
  CHALLENGE, confirmed by the `cf-mitigated: challenge` response header and
  a "Just a moment..." challenge page in the body.

  Stock Playwright was tried first and failed: even headed and even when
  manually clicking the checkbox, it kept re-looping. That's because
  Playwright's automation protocol (CDP) leaves detectable fingerprints
  (e.g. navigator.webdriver=true) that Cloudflare checks for BEFORE the
  click is ever evaluated — once flagged, no amount of manual clicking
  clears it.

  Fix: `patchright` — a stealth-patched fork of Playwright that strips
  those automation fingerprints. It's API-compatible with Playwright
  (same sync_api, same methods), so this is a near drop-in swap. We also
  use a persistent browser profile (a real user-data-dir on disk) rather
  than a throwaway context, since Cloudflare is more lenient on profiles
  it's seen pass a challenge before — cookies/session persist run-to-run.

  Setup (one-time):
      pip install patchright
      patchright install chromium

  If Patchright still gets challenged repeatedly, the reliable fallback is
  a paid CAPTCHA-solving API (e.g. 2Captcha, ~$3 per 1000 solves via the
  `playwright-captcha` package) — tell Claude and we'll wire that in.
"""

import atexit
import time
import logging
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from patchright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from config import LEAGUES, FBREF_STAT_TYPES, HEADERS, SCRAPE_DELAY_SECONDS, REQUEST_TIMEOUT, MAX_RETRIES, league_paths

logger = logging.getLogger(__name__)

FBREF_BASE = "https://fbref.com/en"

# Persistent browser profile — reusing the same profile across runs lets
# Cloudflare recognise a previously-verified session, not just a fresh one.
_PROFILE_DIR = Path(__file__).parent / ".fbref_browser_profile"


# ── Persistent browser session ──────────────────────────────────────────────────
# One browser context stays open for the whole scrape run (across all stat
# types / leagues) rather than launching a fresh one per request — much
# faster, and cookies earned by passing one challenge get reused later.

_playwright = None
_context = None  # launch_persistent_context returns the context directly


def _get_context():
    global _playwright, _context
    if _context is None:
        logger.info("Launching browser for FBref (a visible window will open — this is expected)...")
        _playwright = sync_playwright().start()
        _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        _context = _playwright.chromium.launch_persistent_context(
            str(_PROFILE_DIR),
            headless=False,
            user_agent=HEADERS["User-Agent"],
        )
    return _context


def close_browser():
    """Closes the shared browser session. Safe to call even if never opened."""
    global _playwright, _context
    if _context is not None:
        _context.close()
    if _playwright is not None:
        _playwright.stop()
    _context = _playwright = None


atexit.register(close_browser)


# ── URL builders ───────────────────────────────────────────────────────────────

def _player_stats_url(league_name: str, stat_type: str, season: str) -> str:
    """
    Builds the FBref URL for a player stat table.
    Example: https://fbref.com/en/comps/9/2024-2025/stats/players/2024-2025-Premier-League-Stats
    """
    cfg        = LEAGUES[league_name]
    league_id  = cfg["fbref_id"]
    slug       = cfg["fbref_slug"]
    fbref_type = FBREF_STAT_TYPES[stat_type]
    return (
        f"{FBREF_BASE}/comps/{league_id}/{season}/{fbref_type}/players/"
        f"{season}-{slug}-Stats"
    )


def _team_stats_url(league_name: str, stat_type: str, season: str) -> str:
    """
    Builds the FBref URL for a squad stat table.
    """
    cfg        = LEAGUES[league_name]
    league_id  = cfg["fbref_id"]
    slug       = cfg["fbref_slug"]
    fbref_type = FBREF_STAT_TYPES[stat_type]
    return (
        f"{FBREF_BASE}/comps/{league_id}/{season}/{fbref_type}/squads/"
        f"{season}-{slug}-Stats"
    )


# ── HTTP layer ─────────────────────────────────────────────────────────────────

def _fetch_html(url: str, cache_path: Path) -> str:
    """
    Fetches raw HTML from a URL, caching to disk.
    If the cache file already exists, returns it without hitting the network.

    Uses a real (headed) Chromium browser via Playwright to clear FBref's
    Cloudflare Turnstile challenge — see module docstring for why a plain
    HTTP client can't do this. Detects success by waiting for an actual
    <table> to appear rather than the "Just a moment..." challenge page.
    """
    if cache_path.exists():
        logger.info(f"Cache hit: {cache_path.name}")
        return cache_path.read_text(encoding="utf-8")

    logger.info(f"Fetching: {url}")
    context = _get_context()
    page = context.new_page()
    try:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                page.goto(url, timeout=REQUEST_TIMEOUT * 1000, wait_until="domcontentloaded")
                # A real stats page has a <table>; the Cloudflare challenge page doesn't.
                # Give the challenge up to ~15s to auto-clear before giving up this attempt.
                page.wait_for_selector("table", timeout=15000)
                html = page.content()
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(html, encoding="utf-8")
                logger.info(f"Saved to cache: {cache_path.name}")
                time.sleep(SCRAPE_DELAY_SECONDS)
                return html
            except PlaywrightTimeoutError:
                logger.warning(f"Attempt {attempt}/{MAX_RETRIES}: still challenged for {url}")
                if attempt < MAX_RETRIES:
                    time.sleep(SCRAPE_DELAY_SECONDS * attempt)
                else:
                    raise RuntimeError(
                        f"Could not get past Cloudflare challenge for {url} "
                        f"after {MAX_RETRIES} attempts."
                    )
    finally:
        page.close()


# ── Table parser ───────────────────────────────────────────────────────────────

def _parse_fbref_table(html: str, table_id: str) -> pd.DataFrame:
    """
    Extracts a specific table from FBref HTML by its id attribute.
    FBref wraps some tables in comments to prevent easy scraping —
    this function handles that by searching comment nodes too.
    """
    soup = BeautifulSoup(html, "lxml")

    # Try direct find first
    table = soup.find("table", {"id": table_id})

    # If not found, search inside HTML comments (FBref hides some tables this way)
    if table is None:
        from bs4 import Comment
        comments = soup.find_all(string=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment_soup = BeautifulSoup(comment, "lxml")
            table = comment_soup.find("table", {"id": table_id})
            if table is not None:
                break

    if table is None:
        raise ValueError(f"Table '{table_id}' not found in page. "
                         f"FBref may have changed their layout.")

    df = pd.read_html(str(table))[0]

    # FBref uses multi-level column headers — flatten them
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            f"{top}_{bottom}" if not bottom.startswith("Unnamed") else top
            for top, bottom in df.columns
        ]

    # Drop summary rows FBref injects (e.g. rows where player == "Player")
    if "Player" in df.columns:
        df = df[df["Player"] != "Player"].reset_index(drop=True)

    return df


# ── Public API ─────────────────────────────────────────────────────────────────

def scrape_player_stats(
    league_name: str,
    stat_type: str,
    season: str,
) -> pd.DataFrame:
    """
    Scrapes a player stat table from FBref for the given league and season.

    Args:
        league_name: One of the keys in config.LEAGUES, e.g. "Premier League"
        stat_type:   One of the keys in config.FBREF_STAT_TYPES, e.g. "shooting"
        season:      Season string, e.g. "2024-2025"

    Returns:
        Raw DataFrame straight from FBref (normalizer cleans it next).

    Example:
        df = scrape_player_stats("Premier League", "shooting", "2024-2025")
    """
    if league_name not in LEAGUES:
        raise ValueError(f"Unknown league: '{league_name}'. "
                         f"Choose from: {list(LEAGUES.keys())}")
    if stat_type not in FBREF_STAT_TYPES:
        raise ValueError(f"Unknown stat type: '{stat_type}'. "
                         f"Choose from: {list(FBREF_STAT_TYPES.keys())}")

    paths    = league_paths(league_name)
    url      = _player_stats_url(league_name, stat_type, season)
    filename = f"players_{stat_type}_{season}.html"
    cache    = paths["raw"] / season / filename

    html     = _fetch_html(url, cache)
    table_id = f"stats_standard_{LEAGUES[league_name]['fbref_id']}" \
               if stat_type == "standard" \
               else f"stats_{FBREF_STAT_TYPES[stat_type]}_{LEAGUES[league_name]['fbref_id']}"

    df = _parse_fbref_table(html, table_id)
    df["league"] = league_name
    df["season"] = season
    df["stat_type"] = stat_type

    logger.info(f"Scraped {len(df)} player rows — {league_name} / {stat_type} / {season}")
    return df


def scrape_team_stats(
    league_name: str,
    stat_type: str,
    season: str,
) -> pd.DataFrame:
    """
    Scrapes a squad stat table from FBref.
    Same interface as scrape_player_stats but returns team-level rows.
    """
    if league_name not in LEAGUES:
        raise ValueError(f"Unknown league: '{league_name}'.")
    if stat_type not in FBREF_STAT_TYPES:
        raise ValueError(f"Unknown stat type: '{stat_type}'.")

    paths    = league_paths(league_name)
    url      = _team_stats_url(league_name, stat_type, season)
    filename = f"teams_{stat_type}_{season}.html"
    cache    = paths["raw"] / season / filename

    html     = _fetch_html(url, cache)
    table_id = f"stats_squads_{FBREF_STAT_TYPES[stat_type]}_for"

    df = _parse_fbref_table(html, table_id)
    df["league"] = league_name
    df["season"] = season
    df["stat_type"] = stat_type

    logger.info(f"Scraped {len(df)} team rows — {league_name} / {stat_type} / {season}")
    return df


def scrape_all_player_stats(league_name: str, season: str) -> dict[str, pd.DataFrame]:
    """
    Convenience function — scrapes every stat type for players in one call.
    Returns a dict keyed by stat_type, e.g. {"standard": df, "shooting": df, ...}
    Includes progress logging so you can see it working.
    """
    results = {}
    stat_types = list(FBREF_STAT_TYPES.keys())

    for i, stat_type in enumerate(stat_types, 1):
        logger.info(f"[{i}/{len(stat_types)}] Scraping player {stat_type}...")
        try:
            results[stat_type] = scrape_player_stats(league_name, stat_type, season)
        except Exception as e:
            logger.error(f"Failed to scrape {stat_type}: {e}")
            results[stat_type] = pd.DataFrame()  # empty, not a crash

    return results


def scrape_all_team_stats(league_name: str, season: str) -> dict[str, pd.DataFrame]:
    """
    Convenience function — scrapes every stat type for teams in one call.
    """
    results = {}
    stat_types = list(FBREF_STAT_TYPES.keys())

    for i, stat_type in enumerate(stat_types, 1):
        logger.info(f"[{i}/{len(stat_types)}] Scraping team {stat_type}...")
        try:
            results[stat_type] = scrape_team_stats(league_name, stat_type, season)
        except Exception as e:
            logger.error(f"Failed to scrape {stat_type}: {e}")
            results[stat_type] = pd.DataFrame()

    return results
