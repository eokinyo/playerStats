"""
analysis/team_stats.py
Team-level analysis — style fingerprints, form, press intensity, attack vs defence profiles.

Everything here reads from the database and returns DataFrames.
The emphasis is on metrics that reveal *how* a team plays, not just results.
"""

import logging

import pandas as pd
import numpy as np

from storage.db import get_teams, get_matches, query

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _per_match(series: pd.Series, matches: pd.Series) -> pd.Series:
    return series / matches.replace(0, np.nan)


def _col_missing(df: pd.DataFrame, col: str) -> bool:
    """
    True if `col` isn't usable — genuinely absent, or present but entirely
    NULL. Every table is read via SELECT *, so a column no current data
    source populates (e.g. "position", which only football-data.org would
    fill) is still PRESENT, just all-NaN — a plain `col not in df.columns`
    check misses that and skips fallback logic that should have run.
    """
    return col not in df.columns or df[col].isna().all()


# ── League table ───────────────────────────────────────────────────────────────

def league_table(league_name: str, season: str) -> pd.DataFrame:
    """
    Returns the league table enriched with xG metrics.
    Columns: position, team, played, won, drawn, lost, goals_for,
             goals_against, goal_diff, points, xg, xga, xg_diff
    """
    df = get_teams(league_name, season, stat_type="standard")
    if df.empty:
        logger.warning(f"No team data for {league_name} {season}")
        return df

    if "xg" in df.columns and "xga" in df.columns:
        df["xg_diff"] = df["xg"] - df["xga"]

    if "goals_for" in df.columns and "goals_against" in df.columns:
        df["goal_diff"] = df["goals_for"] - df["goals_against"]

    sort_col = "points" if "points" in df.columns else "wins"
    df = df.sort_values(sort_col, ascending=False)

    if _col_missing(df, "position"):
        df["position"] = range(1, len(df) + 1)
    df = df[["position"] + [c for c in df.columns if c != "position"]]

    logger.info(f"League table built — {league_name} {season}")
    return df.reset_index(drop=True)


# ── Style fingerprints ─────────────────────────────────────────────────────────

def team_style_fingerprint(league_name: str, season: str) -> pd.DataFrame:
    """
    Builds a style profile for each team based on how they play.

    Metrics used:
      - ppda          : passes allowed per defensive action (pressing intensity)
                        lower = more intense press
      - deep          : completed passes into the opposition box per match
                        (directness / penetration)
      - xg_per_match  : average xG generated per match (attack quality)
      - xga_per_match : average xG allowed per match (defensive solidity)
      - shots_per_match
      - progressive_passes_per_match

    Style labels assigned:
      - "High Press"  : ppda < 8
      - "Mid Block"   : ppda 8–12
      - "Low Block"   : ppda > 12
      - "Direct"      : deep > league median
      - "Possession"  : pass_completion > league median
    """
    df = get_teams(league_name, season, stat_type="standard")
    if df.empty:
        return df

    if "matches_played" not in df.columns:
        df["matches_played"] = 1   # fallback if not available

    per_match_cols = {
        "xg":                  "xg_per_match",
        "xga":                 "xga_per_match",
        "goals_for":           "goals_per_match",
        "goals_against":       "goals_against_per_match",
        "shots":               "shots_per_match",
        "progressive_passes":  "progressive_passes_per_match",
        "deep":                "deep_per_match",
    }
    for raw, per_m in per_match_cols.items():
        if raw in df.columns:
            df[per_m] = _per_match(df[raw], df["matches_played"])

    # Press intensity label
    if "ppda" in df.columns:
        df["press_style"] = pd.cut(
            df["ppda"],
            bins=[0, 8, 12, float("inf")],
            labels=["High Press", "Mid Block", "Low Block"],
        )

    # Attack style: above/below median xG per match
    if "xg_per_match" in df.columns:
        median_xg = df["xg_per_match"].median()
        df["attack_profile"] = np.where(
            df["xg_per_match"] >= median_xg, "High Volume Attack", "Low Volume Attack"
        )

    # Defensive style: above/below median xGA per match
    if "xga_per_match" in df.columns:
        median_xga = df["xga_per_match"].median()
        df["defense_profile"] = np.where(
            df["xga_per_match"] <= median_xga, "Solid Defence", "Open Defence"
        )

    cols = ["team", "ppda", "press_style", "xg_per_match", "xga_per_match",
            "attack_profile", "defense_profile", "shots_per_match",
            "progressive_passes_per_match", "deep_per_match"]
    df = df[[c for c in cols if c in df.columns]]

    logger.info(f"Style fingerprints built — {league_name} {season}")
    return df.sort_values("ppda", ascending=True).reset_index(drop=True)


def pressing_rankings(league_name: str, season: str) -> pd.DataFrame:
    """
    Ranks teams by pressing intensity using PPDA (passes per defensive action).
    Lower PPDA = more aggressive press.
    Also includes opponent PPDA (how much the opposition presses them).
    """
    df = get_teams(league_name, season, stat_type="standard")
    if df.empty:
        return df

    needed = ["team", "ppda", "oppda", "press_intensity", "matches_played"]
    df = df[[c for c in needed if c in df.columns]].copy()

    if "ppda" in df.columns:
        df = df.sort_values("ppda", ascending=True)

    logger.info(f"Pressing rankings — {league_name} {season}")
    return df.reset_index(drop=True)


# ── Attack and defence profiles ────────────────────────────────────────────────

def attack_profiles(league_name: str, season: str) -> pd.DataFrame:
    """
    Breaks down each team's attacking output:
      - Total and np_xG
      - Shot volume and quality (np_xg_per_shot where available)
      - Deep completions (passes into box)
      - Goals vs xG (overperformance)
    """
    df = get_teams(league_name, season, stat_type="standard")
    if df.empty:
        return df

    if "matches_played" in df.columns:
        for col in ["xg", "np_xg", "goals_for", "shots", "deep"]:
            if col in df.columns:
                df[f"{col}_per_match"] = _per_match(df[col], df["matches_played"])

    if "goals_for" in df.columns and "xg" in df.columns:
        df["goals_vs_xg"] = df["goals_for"] - df["xg"]

    if "shots" in df.columns and "np_xg" in df.columns:
        df["shot_quality"] = df["np_xg"] / df["shots"].replace(0, np.nan)

    needed = ["team", "xg", "np_xg", "goals_for", "goals_vs_xg",
              "shots", "shot_quality", "xg_per_match", "deep_per_match"]
    df = df[[c for c in needed if c in df.columns]]

    logger.info(f"Attack profiles — {league_name} {season}")
    return df.sort_values("xg", ascending=False).reset_index(drop=True)


def defence_profiles(league_name: str, season: str) -> pd.DataFrame:
    """
    Breaks down each team's defensive record:
      - xGA (expected goals against)
      - Goals conceded vs xGA (over/underperformance)
      - Tackles, interceptions, blocks per match from FBref
    """
    df = get_teams(league_name, season, stat_type="standard")
    if df.empty:
        return df

    if "matches_played" in df.columns:
        for col in ["xga", "np_xga", "goals_against", "tackles",
                    "interceptions", "blocks", "clearances"]:
            if col in df.columns:
                df[f"{col}_per_match"] = _per_match(df[col], df["matches_played"])

    if "goals_against" in df.columns and "xga" in df.columns:
        df["goals_vs_xga"] = df["goals_against"] - df["xga"]

    needed = ["team", "xga", "np_xga", "goals_against", "goals_vs_xga",
              "xga_per_match", "tackles", "interceptions", "ppda"]
    df = df[[c for c in needed if c in df.columns]]

    logger.info(f"Defence profiles — {league_name} {season}")
    return df.sort_values("xga", ascending=True).reset_index(drop=True)


# ── Form analysis ──────────────────────────────────────────────────────────────

def team_form(
    league_name: str,
    season: str,
    team: str,
    last_n: int = 10,
) -> pd.DataFrame:
    """
    Returns a team's last N results with running xG totals.
    Good for a form chart showing momentum over the season.

    Columns: match_date, opponent, home_away, goals_for, goals_against,
             result, xg_for, xg_against, cumulative_points
    """
    matches = get_matches(league_name, season, status="FINISHED")
    if matches.empty:
        logger.warning(f"No finished matches found for {league_name} {season}")
        return matches

    home = matches[matches["home_team"] == team].copy()
    away = matches[matches["away_team"] == team].copy()

    home["home_away"]      = "H"
    home["opponent"]       = home["away_team"]
    home["goals_for"]      = home["home_score"]
    home["goals_against"]  = home["away_score"]
    home["xg_for"]         = home.get("home_xg", np.nan)
    home["xg_against"]     = home.get("away_xg", np.nan)

    away["home_away"]      = "A"
    away["opponent"]       = away["home_team"]
    away["goals_for"]      = away["away_score"]
    away["goals_against"]  = away["home_score"]
    away["xg_for"]         = away.get("away_xg", np.nan)
    away["xg_against"]     = away.get("home_xg", np.nan)

    df = pd.concat([home, away], ignore_index=True)
    df = df.sort_values("match_date")

    def _result(row):
        if row["goals_for"] > row["goals_against"]:  return "W"
        if row["goals_for"] == row["goals_against"]: return "D"
        return "L"

    def _points(result):
        return {"W": 3, "D": 1, "L": 0}.get(result, 0)

    df["result"]             = df.apply(_result, axis=1)
    df["points"]             = df["result"].apply(_points)
    df["cumulative_points"]  = df["points"].cumsum()
    df["cumulative_xg_diff"] = (df["xg_for"] - df["xg_against"]).cumsum()

    df = df.tail(last_n)[["match_date", "opponent", "home_away", "goals_for",
                           "goals_against", "result", "points", "cumulative_points",
                           "xg_for", "xg_against", "cumulative_xg_diff"]]

    logger.info(f"Form table built — {team} last {last_n} matches")
    return df.reset_index(drop=True)


def form_table(league_name: str, season: str, last_n: int = 6) -> pd.DataFrame:
    """
    Builds a form table for all teams — their record over the last N games.
    Returns: team, form_string (e.g. "W W D L W W"), form_points, form_gd
    """
    matches = get_matches(league_name, season, status="FINISHED")
    if matches.empty:
        return matches

    all_teams = pd.concat([matches["home_team"], matches["away_team"]]).unique()
    rows = []
    for team in all_teams:
        home = matches[matches["home_team"] == team].copy()
        away = matches[matches["away_team"] == team].copy()

        home["gf"] = home["home_score"]; home["ga"] = home["away_score"]
        away["gf"] = away["away_score"]; away["ga"] = away["home_score"]

        combined = pd.concat([home, away]).sort_values("match_date").tail(last_n)
        combined["result"] = combined.apply(
            lambda r: "W" if r["gf"] > r["ga"] else ("D" if r["gf"] == r["ga"] else "L"),
            axis=1,
        )
        combined["pts"] = combined["result"].map({"W": 3, "D": 1, "L": 0})

        rows.append({
            "team":          team,
            "form_string":   " ".join(combined["result"].tolist()),
            "form_points":   combined["pts"].sum(),
            "form_gd":       (combined["gf"] - combined["ga"]).sum(),
            "form_wins":     (combined["result"] == "W").sum(),
        })

    df = pd.DataFrame(rows).sort_values("form_points", ascending=False)
    logger.info(f"Form table built — {league_name} last {last_n} games")
    return df.reset_index(drop=True)


# ── Head-to-head ───────────────────────────────────────────────────────────────

def head_to_head(
    league_name: str,
    season: str,
    team_a: str,
    team_b: str,
) -> pd.DataFrame:
    """
    Returns all matches between two teams in the season.
    Includes xG for context.
    """
    matches = get_matches(league_name, season)
    if matches.empty:
        return matches

    mask = (
        ((matches["home_team"] == team_a) & (matches["away_team"] == team_b)) |
        ((matches["home_team"] == team_b) & (matches["away_team"] == team_a))
    )
    df = matches[mask].copy()

    logger.info(f"H2H: {team_a} vs {team_b} — {len(df)} matches found")
    return df.reset_index(drop=True)
