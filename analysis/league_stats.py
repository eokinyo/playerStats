"""
analysis/league_stats.py
Cross-league comparisons across the top 5 European leagues.

This module deliberately reads from MULTIPLE league databases and
combines them into the cross_league database for comparison.
Nothing here mixes data accidentally — every row always carries
its league label.

Questions this answers:
  - Which league produces the most xG per match?
  - Are Premier League players more physical (fouls, duels)?
  - Which league has the most intense pressing?
  - Where do the best progressive passers play?
  - Is the Bundesliga really more open than Serie A?
"""

import logging

import pandas as pd
import numpy as np

from config import LEAGUES, league_paths
from storage.db import get_teams, get_players, query, write_df, init_db

logger = logging.getLogger(__name__)

ALL_LEAGUES = list(LEAGUES.keys())
CROSS_LEAGUE = "cross_league"


# ── Data assembly ──────────────────────────────────────────────────────────────

def build_cross_league_players(
    season: str,
    stat_type: str = "standard",
    min_minutes: int = 450,
) -> pd.DataFrame:
    """
    Pulls player stats from all five league databases and combines them.
    Writes the result to the cross_league database for caching.

    Each row includes a 'league' column so data is never mixed.
    """
    frames = []
    for league_name in ALL_LEAGUES:
        try:
            df = get_players(league_name, season, stat_type=stat_type,
                             min_minutes=min_minutes)
            if not df.empty:
                df["league"] = league_name
                frames.append(df)
                logger.info(f"Loaded {len(df)} players — {league_name}")
        except FileNotFoundError:
            logger.warning(f"No database for {league_name} — skipping")

    if not frames:
        logger.error("No player data found across any league")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    # Cache to cross_league db
    init_db(CROSS_LEAGUE)
    write_df(combined, "player_stats", CROSS_LEAGUE)

    logger.info(f"Cross-league player dataset: {len(combined)} rows")
    return combined


def build_cross_league_teams(season: str) -> pd.DataFrame:
    """
    Pulls team stats from all five league databases and combines them.
    """
    frames = []
    for league_name in ALL_LEAGUES:
        try:
            df = get_teams(league_name, season)
            if not df.empty:
                df["league"] = league_name
                frames.append(df)
        except FileNotFoundError:
            logger.warning(f"No database for {league_name} — skipping")

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    init_db(CROSS_LEAGUE)
    write_df(combined, "team_stats", CROSS_LEAGUE)

    logger.info(f"Cross-league team dataset: {len(combined)} rows")
    return combined


# ── League-level comparisons ───────────────────────────────────────────────────

def league_xg_comparison(season: str) -> pd.DataFrame:
    """
    Compares average xG per match and xGA per match across all five leagues.
    Higher xG = more open / higher quality chance creation on average.

    Returns: league, avg_xg_per_match, avg_xga_per_match, avg_xg_diff,
             total_goals, avg_goals_per_match
    """
    df = build_cross_league_teams(season)
    if df.empty:
        return df

    if "matches_played" not in df.columns:
        df["matches_played"] = 38  # fallback for 20-team leagues

    df["xg_per_match"]  = df["xg"]  / df["matches_played"].replace(0, np.nan)
    df["xga_per_match"] = df["xga"] / df["matches_played"].replace(0, np.nan)

    summary = (
        df.groupby("league")
        .agg(
            avg_xg_per_match=("xg_per_match",   "mean"),
            avg_xga_per_match=("xga_per_match",  "mean"),
            total_goals=("goals_for",             "sum"),
            teams=("team",                        "count"),
        )
        .reset_index()
    )
    summary["avg_goals_per_match"] = summary["total_goals"] / (summary["teams"] * 19)
    summary["avg_xg_diff"]         = summary["avg_xg_per_match"] - summary["avg_xga_per_match"]

    logger.info(f"League xG comparison — {season}")
    return summary.sort_values("avg_xg_per_match", ascending=False).reset_index(drop=True)


def league_pressing_comparison(season: str) -> pd.DataFrame:
    """
    Compares pressing intensity across leagues using PPDA.
    Lower median PPDA = the league as a whole presses more intensely.
    """
    df = build_cross_league_teams(season)
    if df.empty or "ppda" not in df.columns:
        return pd.DataFrame()

    summary = (
        df.groupby("league")["ppda"]
        .agg(
            median_ppda="median",
            mean_ppda="mean",
            min_ppda="min",
            max_ppda="max",
        )
        .reset_index()
    )

    summary["press_style"] = pd.cut(
        summary["median_ppda"],
        bins=[0, 9, 11, float("inf")],
        labels=["High Press League", "Mid Press League", "Low Press League"],
    )

    logger.info(f"Pressing comparison — {season}")
    return summary.sort_values("median_ppda", ascending=True).reset_index(drop=True)


def league_goals_vs_xg(season: str) -> pd.DataFrame:
    """
    Per league: are teams collectively over or underperforming their xG?
    Reveals which league has the best finishers / goalkeepers on aggregate.
    """
    df = build_cross_league_teams(season)
    if df.empty:
        return df

    if "goals_for" in df.columns and "xg" in df.columns:
        df["goals_vs_xg"] = df["goals_for"] - df["xg"]

    summary = (
        df.groupby("league")
        .agg(
            total_goals=("goals_for", "sum"),
            total_xg=("xg", "sum"),
            total_goals_vs_xg=("goals_vs_xg", "sum"),
            avg_goals_vs_xg=("goals_vs_xg", "mean"),
        )
        .reset_index()
    )
    summary["overperformance_pct"] = (
        (summary["total_goals"] - summary["total_xg"]) / summary["total_xg"] * 100
    ).round(1)

    logger.info(f"Goals vs xG by league — {season}")
    return summary.sort_values("total_goals_vs_xg", ascending=False).reset_index(drop=True)


def top_players_across_leagues(
    season: str,
    metric: str = "xg_p90",
    top_n: int = 20,
    min_minutes: int = 900,
    position_group: str | None = None,
) -> pd.DataFrame:
    """
    Ranks the best players in Europe by a given metric — across all leagues.

    Args:
        metric:         Any numeric column, e.g. "xg_p90", "sca_p90",
                        "progressive_carries", "tackles_interceptions_p90"
        top_n:          How many players to return.
        min_minutes:    Higher default here (900) since we're comparing
                        across leagues — want meaningful samples.
        position_group: Optional FBref position filter, e.g. "MF", "FW"

    Returns:
        DataFrame with player, team, league, minutes, [metric], league_rank
    """
    df = build_cross_league_players(season, min_minutes=min_minutes)
    if df.empty:
        return df

    if position_group and "position" in df.columns:
        df = df[df["position"].str.contains(position_group, na=False)]

    if metric not in df.columns:
        available = list(df.select_dtypes("number").columns)
        raise ValueError(f"Metric '{metric}' not found. Available: {available}")

    df = df.dropna(subset=[metric])

    # Add a rank within each league for context
    df["league_rank"] = df.groupby("league")[metric].rank(
        ascending=False, method="min"
    ).astype(int)

    cols = ["player", "team", "league", "minutes", metric, "league_rank"]
    if "position" in df.columns:
        cols.insert(3, "position")

    df = df[cols].sort_values(metric, ascending=False).head(top_n)
    logger.info(f"Top {top_n} players across Europe by {metric} — {season}")
    return df.reset_index(drop=True)


def league_stat_distribution(
    season: str,
    metric: str,
    min_minutes: int = 450,
) -> pd.DataFrame:
    """
    Returns the distribution of a player metric per league —
    useful for violin/box plots comparing how stats are spread
    across different competitions.

    Returns raw player-level rows with league labels so the
    visualisation layer can build distribution plots directly.
    """
    df = build_cross_league_players(season, min_minutes=min_minutes)
    if df.empty:
        return df

    if metric not in df.columns:
        raise ValueError(f"Metric '{metric}' not found.")

    df = df[["player", "team", "league", "minutes", metric]].dropna(subset=[metric])

    logger.info(f"Distribution data — {metric} across {df['league'].nunique()} leagues")
    return df.reset_index(drop=True)


def league_profile_radar(season: str) -> pd.DataFrame:
    """
    Builds a league-level radar profile — average team stats normalised
    to 0–1 scale across all five leagues.

    Metrics: avg_xg_per_match, avg_ppda (inverted), avg_progressive_passes,
             avg_shots, avg_tackles, avg_goals_per_match

    Returns a wide DataFrame: one row per league, one column per metric.
    Useful for a radar/spider chart comparing league styles.
    """
    df = build_cross_league_teams(season)
    if df.empty:
        return df

    if "matches_played" not in df.columns:
        df["matches_played"] = 38

    df["xg_pm"]           = df["xg"]               / df["matches_played"]
    df["goals_pm"]        = df["goals_for"]         / df["matches_played"]
    df["prog_passes_pm"]  = df["progressive_passes"] / df["matches_played"]
    df["shots_pm"]        = df["shots"]             / df["matches_played"]
    df["tackles_pm"]      = df["tackles"]           / df["matches_played"]
    df["press_inv"]       = 1 / df["ppda"].replace(0, np.nan)  # invert PPDA so higher = more press

    agg_metrics = ["xg_pm", "goals_pm", "prog_passes_pm", "shots_pm",
                   "tackles_pm", "press_inv"]

    league_avg = (
        df.groupby("league")[agg_metrics]
        .mean()
        .reset_index()
    )

    # Normalise each column to 0–1
    for col in agg_metrics:
        col_min = league_avg[col].min()
        col_max = league_avg[col].max()
        rng     = col_max - col_min
        league_avg[f"{col}_norm"] = (
            (league_avg[col] - col_min) / rng if rng > 0 else 0.5
        )

    rename = {
        "xg_pm_norm":          "Chance Quality",
        "goals_pm_norm":       "Goals",
        "prog_passes_pm_norm": "Progressive Play",
        "shots_pm_norm":       "Shot Volume",
        "tackles_pm_norm":     "Defensive Activity",
        "press_inv_norm":      "Press Intensity",
    }
    league_avg = league_avg.rename(columns=rename)

    logger.info(f"League radar profile built — {season}")
    return league_avg[["league"] + list(rename.values())]
