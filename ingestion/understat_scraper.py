"""
ingestion/understat_scraper.py
Scrapes shot-level xG data from understat.com.

UPDATED: Understat used to embed data as `var playersData = JSON.parse(...)`
directly in the league page's HTML. They've since moved to loading it via
client-side JS into empty divs, fetched from a JSON API endpoint. We now
hit that endpoint directly with plain `requests` — no browser needed.

Endpoint discovered by sniffing network traffic in a real browser session:
    https://understat.com/getLeagueData/{understat_name}/{year}

It requires:
  - A Referer header matching the league page (protects against hotlinking)
  - An X-Requested-With: XMLHttpRequest header (marks it as an AJAX call)
  - Session cookies from having visited the league page first

Without all three, it 404s even though the URL itself is correct.

Returns one combined JSON blob with three keys: "teams", "players", "dates"
— covering everything the old three separate functions needed, in one
request instead of three. We cache that raw JSON, not HTML.

What we still get from Understat that FBref-shaped data doesn't provide:
  - Player xG and xA split by home/away and situation (xGChain/xGBuildup)
  - Team-level xG/xGA and pressing intensity (PPDA)
  - Match xG per fixture

NOTE — scrape_match_shots() below is UNTESTED against this new site
architecture. It still uses the old HTML/regex approach and was not part
of this fix, since the current pipeline doesn't call it yet. It likely
needs the same JSON-API treatment once shot maps are worked on — flag
this to Claude when you get there rather than assuming it still works.
"""

import re
import json
import time
import logging
from pathlib import Path

import requests
import pandas as pd

from config import LEAGUES, HEADERS, SCRAPE_DELAY_SECONDS, REQUEST_TIMEOUT, MAX_RETRIES, league_paths

logger = logging.getLogger(__name__)

UNDERSTAT_BASE = "https://understat.com"


# ── Combined data fetch (players + teams + dates in one request) ───────────────

def _fetch_league_data(league_name: str, season: str) -> dict:
    """
    Fetches the combined {"teams", "players", "dates"} JSON blob for a league
    season from Understat's internal API, caching to disk as JSON.
    """
    understat_name = LEAGUES[league_name]["understat_name"]
    year           = season.split("-")[0]   # "2024-2025" → "2024"

    paths      = league_paths(league_name)
    cache_path = paths["raw"] / season / f"understat_data_{season}.json"

    if cache_path.exists():
        logger.info(f"Cache hit: {cache_path.name}")
        return json.loads(cache_path.read_text(encoding="utf-8"))

    league_page = f"{UNDERSTAT_BASE}/league/{understat_name}/{year}"
    api_url     = f"{UNDERSTAT_BASE}/getLeagueData/{understat_name}/{year}"

    session = requests.Session()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Establishing session: {league_page}")
            page_resp = session.get(league_page, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            page_resp.raise_for_status()

            logger.info(f"Fetching: {api_url}")
            api_headers = {
                **HEADERS,
                "Referer": league_page,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            }
            resp = session.get(api_url, headers=api_headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data), encoding="utf-8")
            logger.info(f"Saved to cache: {cache_path.name}")
            time.sleep(SCRAPE_DELAY_SECONDS)
            return data
        except (requests.RequestException, ValueError) as e:
            logger.warning(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(SCRAPE_DELAY_SECONDS * attempt)
            else:
                raise


# ── HTTP + cache (still used by scrape_match_shots — see note above) ───────────

def _fetch_html(url: str, cache_path: Path) -> str:
    if cache_path.exists():
        logger.info(f"Cache hit: {cache_path.name}")
        return cache_path.read_text(encoding="utf-8")

    logger.info(f"Fetching: {url}")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            html = response.text
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(html, encoding="utf-8")
            time.sleep(SCRAPE_DELAY_SECONDS)
            return html
        except requests.RequestException as e:
            logger.warning(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(SCRAPE_DELAY_SECONDS * attempt)
            else:
                raise


def _extract_json_var(html: str, var_name: str) -> list | dict:
    """
    Understat used to store data as JSON inside JavaScript variable
    declarations, e.g.: var playersData = JSON.parse('...')
    Kept only for scrape_match_shots() — untested whether match pages
    still work this way.
    """
    pattern = rf"var\s+{var_name}\s*=\s*JSON\.parse\('(.+?)'\)"
    match   = re.search(pattern, html)
    if not match:
        raise ValueError(f"Could not find '{var_name}' in page source. "
                         f"Understat may have changed their layout.")

    raw = match.group(1).encode("utf-8").decode("unicode_escape")
    return json.loads(raw)


# ── Public API ─────────────────────────────────────────────────────────────────

def scrape_league_players(league_name: str, season: str) -> pd.DataFrame:
    """
    Scrapes per-player xG, xA, and shot stats for a full league season.

    Returns one row per player with columns including:
        player_name, team, games, time, goals, xG, assists, xA,
        shots, key_passes, yellow_cards, red_cards, npg, npxG, xGChain, xGBuildup

    Args:
        league_name: e.g. "Premier League"
        season:      e.g. "2024-2025" — converted to Understat's year format (2024)
    """
    data = _fetch_league_data(league_name, season)
    df   = pd.DataFrame(data["players"])

    # Rename to match our internal schema
    df = df.rename(columns={
        "id":          "understat_id",
        "player_name": "player",
        "team_title":  "team",
        "time":        "minutes",
        "npg":         "np_goals",
        "npxG":        "np_xg",
    })

    # Values arrive as strings from the API — convert numeric columns
    numeric_cols = ["games", "minutes", "goals", "xG", "assists", "xA",
                    "shots", "key_passes", "np_goals", "np_xg",
                    "xGChain", "xGBuildup", "yellow_cards", "red_cards"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["league"] = league_name
    df["season"] = season

    logger.info(f"Scraped {len(df)} players from Understat — {league_name} {season}")
    return df


def scrape_league_teams(league_name: str, season: str) -> pd.DataFrame:
    """
    Scrapes per-team xG, xGA, and results for a full league season.

    Returns one row per team with columns including:
        team, wins, draws, losses, scored, missed, xG, xGA, pts, npxG, npxGA,
        ppda_coef, oppda_coef
    """
    data = _fetch_league_data(league_name, season)

    rows = []
    for team_id, team_info in data["teams"].items():
        row = {"understat_team_id": team_id, "team": team_info["title"]}
        history = team_info.get("history", [])

        if history:
            hist_df = pd.DataFrame(history)
            numeric = ["xG", "xGA", "npxG", "npxGA", "scored", "missed",
                       "wins", "draws", "loses", "pts", "deep", "deep_allowed"]
            for col in numeric:
                if col in hist_df.columns:
                    row[col] = pd.to_numeric(hist_df[col], errors="coerce").sum()
            row["matches_played"] = len(hist_df)

            # PPDA now arrives as nested {"att": x, "def": y} per match rather
            # than a precomputed ratio. Season PPDA = sum(att) / sum(def) —
            # the correct way to aggregate a rate stat across matches.
            ppda_att  = sum(m["ppda"]["att"] for m in history if "ppda" in m)
            ppda_def  = sum(m["ppda"]["def"] for m in history if "ppda" in m)
            row["ppda_coef"] = (ppda_att / ppda_def) if ppda_def else None

            oppda_att = sum(m["ppda_allowed"]["att"] for m in history if "ppda_allowed" in m)
            oppda_def = sum(m["ppda_allowed"]["def"] for m in history if "ppda_allowed" in m)
            row["oppda_coef"] = (oppda_att / oppda_def) if oppda_def else None

        rows.append(row)

    df = pd.DataFrame(rows)
    df = df.rename(columns={"loses": "losses"})
    df["league"] = league_name
    df["season"] = season

    logger.info(f"Scraped {len(df)} teams from Understat — {league_name} {season}")
    return df


def scrape_match_shots(match_id: str, league_name: str, season: str) -> pd.DataFrame:
    """
    Scrapes every shot from a single match — gives (x, y) coordinates and xG per shot.
    This is the data that powers shot maps.

    UNTESTED against Understat's current site architecture (see module
    docstring) — this still assumes the old embedded-JSON approach and may
    need the same JSON-API treatment as the functions above.

    Args:
        match_id:    Understat's internal match ID (get from scrape_league_matches)
        league_name: e.g. "Premier League"
        season:      e.g. "2024-2025"
    """
    url        = f"{UNDERSTAT_BASE}/match/{match_id}"
    paths      = league_paths(league_name)
    cache_path = paths["raw"] / season / "matches" / f"shots_{match_id}.html"

    html = _fetch_html(url, cache_path)
    data = _extract_json_var(html, "shotsData")

    # shotsData has "h" (home) and "a" (away) keys
    home_shots = pd.DataFrame(data.get("h", []))
    away_shots = pd.DataFrame(data.get("a", []))

    if not home_shots.empty:
        home_shots["side"] = "home"
    if not away_shots.empty:
        away_shots["side"] = "away"

    df = pd.concat([home_shots, away_shots], ignore_index=True)

    if df.empty:
        return df

    # Normalise coordinates: Understat uses 0–1 scale, we convert to pitch metres
    # Standard pitch: 105m × 68m
    for coord, scale in [("X", 105), ("Y", 68)]:
        if coord in df.columns:
            df[coord] = pd.to_numeric(df[coord], errors="coerce") * scale

    df["xG"] = pd.to_numeric(df.get("xG", 0), errors="coerce")
    df["match_id"] = match_id
    df["league"]   = league_name
    df["season"]   = season

    logger.info(f"Scraped {len(df)} shots — match {match_id}")
    return df


def scrape_league_matches(league_name: str, season: str) -> pd.DataFrame:
    """
    Scrapes the full list of matches for a league season from Understat.
    Returns match IDs, teams, scores, and match-level xG.
    Use the match IDs with scrape_match_shots() to drill into shot data.
    """
    data    = _fetch_league_data(league_name, season)
    matches = data["dates"]

    rows = []
    for m in matches:
        rows.append({
            "match_id":   m["id"],
            "home_team":  m["h"]["title"],
            "away_team":  m["a"]["title"],
            "home_goals": m["goals"]["h"],
            "away_goals": m["goals"]["a"],
            "home_xg":    m["xG"]["h"],
            "away_xg":    m["xG"]["a"],
            "match_date": m["datetime"],
            "is_played":  m["isResult"],
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    numeric_cols = ["home_goals", "away_goals", "home_xg", "away_xg"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["league"] = league_name
    df["season"] = season

    logger.info(f"Scraped {len(df)} matches from Understat — {league_name} {season}")
    return df
