"""
config.py — central configuration for the playerStats engine.
Edit this file to change leagues, seasons, or paths. Everything else imports from here.
"""

from pathlib import Path

# ── Project paths ──────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

# ── League folder names (used to build all paths) ─────────────────────────────
LEAGUE_FOLDERS = {
    "Premier League": "premier_league",
    "La Liga":        "la_liga",
    "Bundesliga":     "bundesliga",
    "Serie A":        "serie_a",
    "Ligue 1":        "ligue_1",
    "cross_league":   "cross_league",
}

def league_paths(league_name: str) -> dict:
    """
    Returns all relevant paths for a given league name.
    Usage:  paths = league_paths("Premier League")
            paths["raw"]        → data/premier_league/raw/
            paths["processed"]  → data/premier_league/processed/
            paths["db"]         → data/premier_league/football_stats.db
            paths["reports"]    → output/premier_league/reports/
            paths["charts"]     → output/premier_league/charts/
    """
    folder = LEAGUE_FOLDERS[league_name]
    return {
        "raw":       DATA_DIR   / folder / "raw",
        "processed": DATA_DIR   / folder / "processed",
        "db":        DATA_DIR   / folder / "football_stats.db",
        "reports":   OUTPUT_DIR / folder / "reports",
        "charts":    OUTPUT_DIR / folder / "charts",
    }

# ── Scraping behaviour ─────────────────────────────────────────────────────────
SCRAPE_DELAY_SECONDS = 6      # polite delay between FBref requests
REQUEST_TIMEOUT      = 30     # seconds before a request gives up
MAX_RETRIES          = 3      # retry failed requests this many times

HEADERS = {
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
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}

# ── Seasons ────────────────────────────────────────────────────────────────────
CURRENT_SEASON = "2024-2025"
AVAILABLE_SEASONS = [
    "2022-2023",
    "2023-2024",
    "2024-2025",
]

# ── Top 5 leagues ──────────────────────────────────────────────────────────────
LEAGUES = {
    "Premier League": {
        "fbref_slug":      "Premier-League",
        "fbref_id":        "9",
        "understat_name":  "EPL",
        "footballdata_id": "PL",
        "country":         "England",
    },
    "La Liga": {
        "fbref_slug":      "La-Liga",
        "fbref_id":        "12",
        "understat_name":  "La_liga",
        "footballdata_id": "PD",
        "country":         "Spain",
    },
    "Bundesliga": {
        "fbref_slug":      "Bundesliga",
        "fbref_id":        "20",
        "understat_name":  "Bundesliga",
        "footballdata_id": "BL1",
        "country":         "Germany",
    },
    "Serie A": {
        "fbref_slug":      "Serie-A",
        "fbref_id":        "11",
        "understat_name":  "Serie_A",
        "footballdata_id": "SA",
        "country":         "Italy",
    },
    "Ligue 1": {
        "fbref_slug":      "Ligue-1",
        "fbref_id":        "13",
        "understat_name":  "Ligue_1",
        "footballdata_id": "FL1",
        "country":         "France",
    },
}

# ── FBref stat categories ──────────────────────────────────────────────────────
FBREF_STAT_TYPES = {
    "standard":     "stats",
    "shooting":     "shooting",
    "passing":      "passing",
    "pass_types":   "passing_types",
    "gca":          "gca",
    "defense":      "defense",
    "possession":   "possession",
    "playing_time": "playingtime",
    "misc":         "misc",
}

# ── Analysis settings ──────────────────────────────────────────────────────────
MIN_MINUTES_PLAYER = 450    # minimum minutes to include a player in rankings
PER90_SCALE        = 90

# ── football-data.org API ──────────────────────────────────────────────────────
# Get your free key at https://www.football-data.org/client/register
# Add to your .env file:  FOOTBALL_DATA_API_KEY=your_key_here
FOOTBALLDATA_BASE_URL = "https://api.football-data.org/v4"
