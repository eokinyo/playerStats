"""
analysis/xg_analysis.py
Deep xG analysis — shot quality, xG flow, finishing skill, and luck separation.

This module works heavily with Understat's shot-level data (shot_events table)
because FBref only gives us season totals. The shot events give us:
  - Where shots are taken from (distance, angle)
  - What situation they came from (open play, set piece, counter)
  - The xG value per shot
  - The outcome (goal, saved, missed, blocked)

From these we can separate finishing quality from chance quality —
a player who scores 12 goals from 8 xG is genuinely clinical,
not just lucky to have had good chances.
"""

import logging

import pandas as pd
import numpy as np

from storage.db import get_shots, get_players, query

logger = logging.getLogger(__name__)


# ── Shot quality analysis ──────────────────────────────────────────────────────

def shot_quality_profile(
    league_name: str,
    season: str,
    entity: str,
    entity_type: str = "team",
) -> pd.DataFrame:
    """
    Breaks down shot quality by situation and zone for a team or player.

    Args:
        entity:      Team name or player name.
        entity_type: "team" or "player"

    Returns DataFrame with:
        situation, shots, goals, xg, xg_per_shot, goals_per_shot, conversion_rate
    """
    if entity_type == "team":
        shots = get_shots(league_name, season, team=entity)
    else:
        shots = get_shots(league_name, season, player=entity)

    if shots.empty:
        logger.warning(f"No shot data found for {entity} ({entity_type})")
        return shots

    shots["is_goal"] = shots["result"].str.lower() == "goal"

    group_col = "situation" if "situation" in shots.columns else None
    if group_col is None:
        # Fallback: overall profile only
        return pd.DataFrame([{
            "situation":        "All",
            "shots":            len(shots),
            "goals":            shots["is_goal"].sum(),
            "xg":               shots["xg"].sum(),
            "xg_per_shot":      shots["xg"].mean(),
            "goals_per_shot":   shots["is_goal"].mean(),
        }])

    profile = (
        shots.groupby("situation")
        .agg(
            shots=("xg", "count"),
            goals=("is_goal", "sum"),
            xg=("xg", "sum"),
            xg_per_shot=("xg", "mean"),
        )
        .reset_index()
    )
    profile["goals_per_shot"]   = profile["goals"] / profile["shots"].replace(0, np.nan)
    profile["finishing_quality"] = profile["goals_per_shot"] - profile["xg_per_shot"]

    logger.info(f"Shot quality profile — {entity} ({entity_type})")
    return profile.sort_values("xg", ascending=False).reset_index(drop=True)


def xg_by_zone(
    league_name: str,
    season: str,
    entity: str,
    entity_type: str = "team",
) -> pd.DataFrame:
    """
    Aggregates shots and xG by pitch zone.
    Zones defined by distance from goal and angle.

    Returns columns: zone, shots, goals, xg, xg_per_shot, conversion_rate
    """
    if entity_type == "team":
        shots = get_shots(league_name, season, team=entity)
    else:
        shots = get_shots(league_name, season, player=entity)

    if shots.empty or "x" not in shots.columns or "y" not in shots.columns:
        return pd.DataFrame()

    shots = shots.copy()
    shots["is_goal"] = shots["result"].str.lower() == "goal"

    # Distance from goal (goal at x=105, y=34 on a 105x68 pitch)
    shots["dist_to_goal"] = np.sqrt(
        (105 - shots["x"]) ** 2 + (34 - shots["y"]) ** 2
    )

    def _zone(row):
        d = row["dist_to_goal"]
        y = row["y"]
        if d < 11:   return "Six-yard box"
        if d < 20 and 20 < y < 48: return "Penalty area (central)"
        if d < 25:   return "Penalty area (wide)"
        if d < 32:   return "Edge of box"
        return "Long range"

    shots["zone"] = shots.apply(_zone, axis=1)

    zone_order = ["Six-yard box", "Penalty area (central)",
                  "Penalty area (wide)", "Edge of box", "Long range"]

    profile = (
        shots.groupby("zone")
        .agg(shots=("xg", "count"), goals=("is_goal", "sum"), xg=("xg", "sum"),
             xg_per_shot=("xg", "mean"))
        .reindex(zone_order)
        .dropna(how="all")
        .reset_index()
    )
    profile["conversion_rate"] = profile["goals"] / profile["shots"].replace(0, np.nan)

    logger.info(f"xG by zone — {entity}")
    return profile


# ── Finishing skill vs luck ────────────────────────────────────────────────────

def finishing_skill_table(
    league_name: str,
    season: str,
    min_shots: int = 20,
) -> pd.DataFrame:
    """
    Estimates finishing skill for all players with enough shots.

    Method:
      - goals_minus_xg  : raw overperformance (conflates skill and luck)
      - goals_per_shot  : actual conversion rate
      - xg_per_shot     : expected conversion rate (chance quality)
      - finishing_delta : goals_per_shot - xg_per_shot
                          positive = converting above chance quality (clinical)
                          negative = converting below (wasteful / unlucky)

    A player with high finishing_delta on a good sample is genuinely clinical.
    A player with high goals_minus_xg but average finishing_delta just had
    good chances — credit the creator, not the finisher.

    Args:
        min_shots: Minimum shots to include — filters out tiny samples.
    """
    shots = get_shots(league_name, season)
    if shots.empty:
        return shots

    shots = shots.copy()
    shots["is_goal"] = shots["result"].str.lower() == "goal"

    profile = (
        shots.groupby("player")
        .agg(
            team=("team", "first"),
            shots=("xg", "count"),
            goals=("is_goal", "sum"),
            xg=("xg", "sum"),
            xg_per_shot=("xg", "mean"),
        )
        .reset_index()
    )

    profile = profile[profile["shots"] >= min_shots].copy()
    profile["goals_per_shot"]   = profile["goals"] / profile["shots"]
    profile["goals_minus_xg"]   = profile["goals"] - profile["xg"]
    profile["finishing_delta"]  = profile["goals_per_shot"] - profile["xg_per_shot"]

    # Categorise
    profile["finishing_label"] = pd.cut(
        profile["finishing_delta"],
        bins=[-1, -0.05, 0.05, 1],
        labels=["Below Average", "Average", "Clinical"],
    )

    logger.info(f"Finishing skill table — {league_name} {season} ({len(profile)} players)")
    return profile.sort_values("finishing_delta", ascending=False).reset_index(drop=True)


# ── xG flow ───────────────────────────────────────────────────────────────────

def xg_flow(
    league_name: str,
    season: str,
    match_id: str,
) -> pd.DataFrame:
    """
    Returns cumulative xG over time for both teams in a single match.
    Perfect for an xG flow chart — shows momentum swings during a game.

    Returns: minute, home_team, away_team, home_xg_cumulative, away_xg_cumulative
    """
    sql = """
        SELECT minute, team, side, xg, result
        FROM   shot_events
        WHERE  match_id = ?
          AND  league   = ?
          AND  season   = ?
        ORDER  BY minute
    """
    shots = query(sql, league_name, params=(match_id, league_name, season))

    if shots.empty:
        logger.warning(f"No shots found for match {match_id}")
        return shots

    home_shots = shots[shots["side"] == "home"].copy()
    away_shots = shots[shots["side"] == "away"].copy()

    home_shots["home_xg_cumulative"] = home_shots["xg"].cumsum()
    away_shots["away_xg_cumulative"] = away_shots["xg"].cumsum()

    # Combine into a single timeline
    home_shots = home_shots[["minute", "home_xg_cumulative"]].rename(
        columns={"minute": "minute"}
    )
    away_shots = away_shots[["minute", "away_xg_cumulative"]]

    flow = pd.merge_asof(
        pd.DataFrame({"minute": range(0, 91)}),
        home_shots.sort_values("minute"),
        on="minute",
        direction="backward",
    )
    flow = pd.merge_asof(
        flow,
        away_shots.sort_values("minute"),
        on="minute",
        direction="backward",
    )
    flow[["home_xg_cumulative", "away_xg_cumulative"]] = \
        flow[["home_xg_cumulative", "away_xg_cumulative"]].fillna(method="ffill").fillna(0)

    logger.info(f"xG flow built — match {match_id}")
    return flow


# ── League-wide xG analysis ───────────────────────────────────────────────────

def xg_league_summary(league_name: str, season: str) -> pd.DataFrame:
    """
    Season-level xG summary per team:
      - xG for and against
      - Goals vs xG (over/underperformance)
      - Shot volume and quality
      - xG difference (proxy for league position deservedness)
    """
    teams_df = query(
        """
        SELECT team, xg, xga, np_xg, np_xga, goals_for, goals_against,
               wins, draws, losses, points, matches_played, ppda
        FROM   team_stats
        WHERE  league = ? AND season = ? AND stat_type = 'standard'
        """,
        league_name,
        params=(league_name, season),
    )

    if teams_df.empty:
        return teams_df

    teams_df["xg_diff"]          = teams_df["xg"]         - teams_df["xga"]
    teams_df["goals_vs_xg"]      = teams_df["goals_for"]  - teams_df["xg"]
    teams_df["goals_vs_xga"]     = teams_df["goals_against"] - teams_df["xga"]
    teams_df["expected_pts_diff"] = teams_df["xg_diff"] * 0.5  # rough heuristic

    logger.info(f"xG league summary — {league_name} {season}")
    return teams_df.sort_values("xg_diff", ascending=False).reset_index(drop=True)


def chance_creation_vs_conversion(league_name: str, season: str) -> pd.DataFrame:
    """
    Scatter plot data: chance quality created (xG/shot for) vs conversion rate.
    Reveals whether a team scores because they create quality chances
    or because they finish above expectation.
    """
    shots = get_shots(league_name, season)
    if shots.empty:
        return shots

    shots["is_goal"] = shots["result"].str.lower() == "goal"

    profile = (
        shots.groupby("team")
        .agg(
            shots=("xg", "count"),
            goals=("is_goal", "sum"),
            total_xg=("xg", "sum"),
            avg_xg_per_shot=("xg", "mean"),
        )
        .reset_index()
    )
    profile["conversion_rate"]  = profile["goals"] / profile["shots"]
    profile["finishing_above_xg"] = profile["conversion_rate"] - profile["avg_xg_per_shot"]

    logger.info(f"Chance creation vs conversion — {league_name} {season}")
    return profile.sort_values("total_xg", ascending=False).reset_index(drop=True)
