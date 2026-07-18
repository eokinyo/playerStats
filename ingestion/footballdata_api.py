"""
ingestion/footballdata_api.py
Fetches fixtures, results, and standings from football-data.org (free tier).

Free tier limits:
  - 10 requests per minute
  - Competitions covered: all top 5 leagues ✓
  - No advanced stats — used only for fixture context and results

Setup:
  1. Register at https://www.football-data.org/client/register
  2. Add to your .env file:  FOOTBALL_DATA_API_KEY=your_key_here
"""

import os
import time
import logging
from pathlib import Path

import requests
import pandas as pd
from dotenv import load_dotenv

from config import LEAGUES, FOOTBALLDATA_BASE_URL, league_paths, REQUEST_TIMEOUT

load_dotenv()
logger = logging.getLogger(__name__)

# Free tier allows 10 requests/minute → 6 seconds between calls to be safe
_REQUEST_DELAY = 6


def _get_headers() -> dict:
    api_key = os.getenv("FOOTBALL_DATA_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "FOOTBALL_DATA_API_KEY not found. "
            "Add it to your .env file: FOOTBALL_DATA_API_KEY=your_key_here"
        )
    return {"X-Auth-Token": api_key}


def _get(endpoint: str) -> dict:
    """Makes a single authenticated GET request to the football-data.org API."""
    url = f"{FOOTBALLDATA_BASE_URL}/{endpoint.lstrip('/')}"
    logger.info(f"API request: {url}")
    response = requests.get(url, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    time.sleep(_REQUEST_DELAY)
    return response.json()


# ── Public API ─────────────────────────────────────────────────────────────────

def fetch_standings(league_name: str, season: str) -> pd.DataFrame:
    """
    Fetches the current league table / standings.

    Returns one row per team with: position, team, played, won, drawn,
    lost, goals_for, goals_against, goal_diff, points.
    """
    competition_id = LEAGUES[league_name]["footballdata_id"]
    year           = season.split("-")[0]   # "2024-2025" → "2024"
    data           = _get(f"competitions/{competition_id}/standings?season={year}")

    standings_raw = data.get("standings", [])
    # football-data.org returns TOTAL, HOME, and AWAY tables — we want TOTAL
    total_table = next(
        (t for t in standings_raw if t.get("type") == "TOTAL"), None
    )
    if total_table is None:
        raise ValueError(f"No TOTAL standings found for {league_name} {season}")

    rows = []
    for entry in total_table.get("table", []):
        rows.append({
            "position":       entry["position"],
            "team":           entry["team"]["name"],
            "team_id":        entry["team"]["id"],
            "played":         entry["playedGames"],
            "won":            entry["won"],
            "drawn":          entry["draw"],
            "lost":           entry["lost"],
            "goals_for":      entry["goalsFor"],
            "goals_against":  entry["goalsAgainst"],
            "goal_diff":      entry["goalDifference"],
            "points":         entry["points"],
        })

    df = pd.DataFrame(rows)
    df["league"] = league_name
    df["season"] = season
    logger.info(f"Fetched standings — {league_name} {season} ({len(df)} teams)")
    return df


def fetch_fixtures(league_name: str, season: str) -> pd.DataFrame:
    """
    Fetches all fixtures (played and upcoming) for a league season.

    Returns columns: match_id, match_date, status, home_team, away_team,
    home_score, away_score, matchday.

    Status values from the API: SCHEDULED, LIVE, IN_PLAY, PAUSED, FINISHED,
    POSTPONED, CANCELLED, SUSPENDED.
    """
    competition_id = LEAGUES[league_name]["footballdata_id"]
    year           = season.split("-")[0]
    data           = _get(f"competitions/{competition_id}/matches?season={year}")

    rows = []
    for match in data.get("matches", []):
        score = match.get("score", {})
        full  = score.get("fullTime", {})
        rows.append({
            "match_id":    match["id"],
            "match_date":  match.get("utcDate", "")[:10],   # "2024-08-17T14:00:00Z" → "2024-08-17"
            "matchday":    match.get("matchday"),
            "status":      match.get("status"),
            "home_team":   match["homeTeam"]["name"],
            "away_team":   match["awayTeam"]["name"],
            "home_score":  full.get("home"),
            "away_score":  full.get("away"),
        })

    df = pd.DataFrame(rows)
    df["league"] = league_name
    df["season"] = season
    logger.info(f"Fetched {len(df)} fixtures — {league_name} {season}")
    return df


def fetch_upcoming_fixtures(league_name: str, matchdays: int = 5) -> pd.DataFrame:
    """
    Fetches the next N matchdays of upcoming fixtures.
    Useful for context around current-form analysis.
    """
    competition_id = LEAGUES[league_name]["footballdata_id"]
    data           = _get(f"competitions/{competition_id}/matches?status=SCHEDULED")

    rows = []
    matchday_seen = set()
    for match in data.get("matches", []):
        md = match.get("matchday")
        matchday_seen.add(md)
        if len(matchday_seen) > matchdays:
            break
        rows.append({
            "match_id":   match["id"],
            "match_date": match.get("utcDate", "")[:10],
            "matchday":   md,
            "home_team":  match["homeTeam"]["name"],
            "away_team":  match["awayTeam"]["name"],
        })

    df = pd.DataFrame(rows)
    df["league"] = league_name
    logger.info(f"Fetched {len(df)} upcoming fixtures — {league_name}")
    return df
