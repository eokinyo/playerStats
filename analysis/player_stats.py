"""
analysis/player_stats.py
Player-level stat analysis — rankings, per-90s, overperformance, percentile scores.

All functions read from the database via storage.db and return DataFrames
ready for visualisation or export. Nothing here writes to the database.

Key concepts:
  - Per-90 rates normalise for playing time so a player with 500 mins
    is fairly compared to one with 2000 mins
  - Overperformance (goals - xG) tells you who is beating or missing
    their expected output
  - Percentile scores (0-100) let you compare players across different
    positions and metrics on a common scale — useful for radar charts
"""

import logging

import pandas as pd
import numpy as np

from config import MIN_MINUTES_PLAYER, PER90_SCALE
from storage.db import get_players, query

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _per90(series: pd.Series, minutes: pd.Series) -> pd.Series:
    return (series / minutes.replace(0, np.nan)) * PER90_SCALE


def _percentile_rank(series: pd.Series) -> pd.Series:
    """Converts a numeric series to percentile ranks (0–100)."""
    return series.rank(pct=True) * 100


def _require_cols(df: pd.DataFrame, cols: list[str], context: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"[{context}] Missing columns: {missing}")


def _col_missing(df: pd.DataFrame, col: str) -> bool:
    """
    True if `col` isn't usable — either genuinely absent, or present but
    entirely NULL. Every table is read via SELECT *, so a column some data
    source never populates (e.g. FBref-only fields, now that FBref is
    dropped) is still PRESENT in the DataFrame, just all-NaN. A plain
    `col not in df.columns` check misses this and silently skips
    fallback/derived-value logic that should have run — worse, letting an
    all-NaN column through to something like idxmax() or a percentile
    calc (dividing by an empty pool) crashes instead of degrading cleanly.
    Use this instead wherever code decides whether a column has real data.
    """
    return col not in df.columns or df[col].isna().all()


def _top_row_label(df: pd.DataFrame, col: str, label_fmt) -> str | None:
    """
    Safely finds the row with the max value in `col` and formats a label
    from it. Returns None (instead of crashing) if the column is missing
    or entirely empty — idxmax() on an all-NaN column returns nan, and
    df.loc[nan] then raises, which is exactly the failure mode this avoids.
    """
    if col not in df.columns or df[col].dropna().empty:
        return None
    top = df.loc[df[col].idxmax()]
    return label_fmt(top)


# ── Core rankings ──────────────────────────────────────────────────────────────

def top_scorers(
    league_name: str,
    season: str,
    top_n: int = 20,
    min_minutes: int = MIN_MINUTES_PLAYER,
) -> pd.DataFrame:
    """
    Returns top N scorers with goals, xG, and overperformance.

    Columns returned:
        player, team, minutes, goals, xg, np_goals, np_xg,
        goals_p90, xg_p90, goals_minus_xg, np_goals_minus_xg
    """
    df = get_players(league_name, season, stat_type="standard", min_minutes=min_minutes)
    if df.empty:
        logger.warning(f"No standard player data found for {league_name} {season}")
        return df

    needed = ["player", "team", "minutes", "goals", "xg", "np_goals", "np_xg"]
    df = df[[c for c in needed if c in df.columns]].copy()

    if "minutes" in df.columns:
        if "goals" in df.columns:
            df["goals_p90"] = _per90(df["goals"], df["minutes"])
        if "xg" in df.columns:
            df["xg_p90"] = _per90(df["xg"], df["minutes"])

    if "goals" in df.columns and "xg" in df.columns:
        df["goals_minus_xg"] = df["goals"] - df["xg"]
    if "np_goals" in df.columns and "np_xg" in df.columns:
        df["np_goals_minus_xg"] = df["np_goals"] - df["np_xg"]

    df = df.sort_values("goals", ascending=False).head(top_n)
    logger.info(f"Top {top_n} scorers — {league_name} {season}")
    return df.reset_index(drop=True)


def top_assisters(
    league_name: str,
    season: str,
    top_n: int = 20,
    min_minutes: int = MIN_MINUTES_PLAYER,
) -> pd.DataFrame:
    """
    Returns top N assisters with assists, xAG, and overperformance.
    xAG (expected assisted goals) is FBref's metric — the xG of shots
    that came directly from a player's passes.
    """
    df = get_players(league_name, season, stat_type="standard", min_minutes=min_minutes)
    if df.empty:
        return df

    needed = ["player", "team", "minutes", "assists", "xag"]
    df = df[[c for c in needed if c in df.columns]].copy()

    if "minutes" in df.columns:
        if "assists" in df.columns:
            df["assists_p90"] = _per90(df["assists"], df["minutes"])
        if "xag" in df.columns:
            df["xag_p90"] = _per90(df["xag"], df["minutes"])

    if "assists" in df.columns and "xag" in df.columns:
        df["assists_minus_xag"] = df["assists"] - df["xag"]

    df = df.sort_values("assists", ascending=False).head(top_n)
    logger.info(f"Top {top_n} assisters — {league_name} {season}")
    return df.reset_index(drop=True)


def top_goal_contributors(
    league_name: str,
    season: str,
    top_n: int = 20,
    min_minutes: int = MIN_MINUTES_PLAYER,
) -> pd.DataFrame:
    """
    Goals + assists combined, per 90. Good all-round attacking output metric.
    """
    df = get_players(league_name, season, stat_type="standard", min_minutes=min_minutes)
    if df.empty:
        return df

    needed = ["player", "team", "minutes", "goals", "assists", "xg", "xag"]
    df = df[[c for c in needed if c in df.columns]].copy()

    if "goals" in df.columns and "assists" in df.columns:
        df["goal_contributions"] = df["goals"] + df["assists"]
        df["xg_xag"]             = df.get("xg", 0) + df.get("xag", 0)
        if "minutes" in df.columns:
            df["contributions_p90"] = _per90(df["goal_contributions"], df["minutes"])
            df["xg_xag_p90"]        = _per90(df["xg_xag"], df["minutes"])

    df = df.sort_values("goal_contributions", ascending=False).head(top_n)
    logger.info(f"Top {top_n} goal contributors — {league_name} {season}")
    return df.reset_index(drop=True)


def shot_creation_leaders(
    league_name: str,
    season: str,
    top_n: int = 20,
    min_minutes: int = MIN_MINUTES_PLAYER,
) -> pd.DataFrame:
    """
    Ranks players by shot-creating actions (SCA) per 90.
    SCA counts the two actions leading to any shot — passes, dribbles, fouls drawn.
    A high SCA/90 player is a consistent creator even if assists don't reflect it.
    """
    df = get_players(league_name, season, stat_type="gca", min_minutes=min_minutes)
    if df.empty:
        return df

    needed = ["player", "team", "minutes", "shot_creating_actions", "sca_p90",
              "goal_creating_actions", "gca_p90"]
    df = df[[c for c in needed if c in df.columns]].copy()

    if "shot_creating_actions" in df.columns and "minutes" in df.columns:
        if "sca_p90" not in df.columns:
            df["sca_p90"] = _per90(df["shot_creating_actions"], df["minutes"])

    sort_col = "sca_p90" if "sca_p90" in df.columns else "shot_creating_actions"
    df = df.sort_values(sort_col, ascending=False).head(top_n)
    logger.info(f"Top {top_n} SCA leaders — {league_name} {season}")
    return df.reset_index(drop=True)


def progressive_action_leaders(
    league_name: str,
    season: str,
    top_n: int = 20,
    min_minutes: int = MIN_MINUTES_PLAYER,
) -> pd.DataFrame:
    """
    Progressive carries + progressive passes per 90.
    'Progressive' means moving the ball at least 10 yards closer to goal.
    Identifies players who drive the team forward — not always the headline names.
    """
    standard = get_players(league_name, season, stat_type="standard", min_minutes=min_minutes)
    passing  = get_players(league_name, season, stat_type="passing",  min_minutes=min_minutes)

    if standard.empty:
        return standard

    prog_cols = ["player", "team", "minutes", "progressive_carries", "progressive_passes",
                 "progressive_receptions"]
    df = standard[[c for c in prog_cols if c in standard.columns]].copy()

    # Merge passing progressive passes if available
    if not passing.empty and "progressive_passes" in passing.columns:
        pass_prog = passing[["player", "team", "progressive_passes"]].rename(
            columns={"progressive_passes": "prog_passes_detailed"}
        )
        df = df.merge(pass_prog, on=["player", "team"], how="left")

    for col in ["progressive_carries", "progressive_passes", "progressive_receptions"]:
        if col in df.columns:
            df[f"{col}_p90"] = _per90(df[col], df["minutes"])

    if "progressive_carries" in df.columns and "progressive_passes" in df.columns:
        df["progressive_actions"]      = df["progressive_carries"] + df["progressive_passes"]
        df["progressive_actions_p90"]  = _per90(df["progressive_actions"], df["minutes"])

    sort_col = "progressive_actions_p90" if "progressive_actions_p90" in df.columns \
               else "progressive_carries"
    df = df.sort_values(sort_col, ascending=False).head(top_n)
    logger.info(f"Top {top_n} progressive action leaders — {league_name} {season}")
    return df.reset_index(drop=True)


def defensive_leaders(
    league_name: str,
    season: str,
    top_n: int = 20,
    min_minutes: int = MIN_MINUTES_PLAYER,
) -> pd.DataFrame:
    """
    Tackles + interceptions per 90 — a combined defensive action rate.
    Also includes tackles won % for quality context.
    """
    df = get_players(league_name, season, stat_type="defense", min_minutes=min_minutes)
    if df.empty:
        return df

    needed = ["player", "team", "minutes", "tackles", "tackles_won", "tackle_pct",
              "interceptions", "tackles_interceptions", "blocks", "clearances", "errors"]
    df = df[[c for c in needed if c in df.columns]].copy()

    if "minutes" in df.columns:
        for col in ["tackles", "interceptions", "tackles_interceptions", "blocks"]:
            if col in df.columns:
                df[f"{col}_p90"] = _per90(df[col], df["minutes"])

    sort_col = "tackles_interceptions_p90" if "tackles_interceptions_p90" in df.columns \
               else "tackles"
    df = df.sort_values(sort_col, ascending=False).head(top_n)
    logger.info(f"Top {top_n} defensive leaders — {league_name} {season}")
    return df.reset_index(drop=True)


def passing_leaders(
    league_name: str,
    season: str,
    top_n: int = 20,
    min_minutes: int = MIN_MINUTES_PLAYER,
) -> pd.DataFrame:
    """
    Key passing metrics: completion %, progressive passes, key passes, xAG.
    """
    df = get_players(league_name, season, stat_type="passing", min_minutes=min_minutes)
    if df.empty:
        return df

    needed = ["player", "team", "minutes", "passes_completed", "passes_attempted",
              "pass_completion_pct", "key_passes", "progressive_passes",
              "passes_final_third", "xag", "xa"]
    df = df[[c for c in needed if c in df.columns]].copy()

    if "minutes" in df.columns:
        for col in ["key_passes", "progressive_passes", "xag"]:
            if col in df.columns:
                df[f"{col}_p90"] = _per90(df[col], df["minutes"])

    sort_col = "xag_p90" if "xag_p90" in df.columns else "key_passes"
    df = df.sort_values(sort_col, ascending=False).head(top_n)
    logger.info(f"Top {top_n} passers — {league_name} {season}")
    return df.reset_index(drop=True)


# ── Overperformance analysis ───────────────────────────────────────────────────

def overperformers(
    league_name: str,
    season: str,
    metric: str = "goals",
    top_n: int = 15,
    min_minutes: int = MIN_MINUTES_PLAYER,
) -> pd.DataFrame:
    """
    Players beating their expected output the most.
    metric: "goals" (goals vs xG) or "assists" (assists vs xAG)

    A large positive value means the player is converting at a rate
    above what the shot quality alone would predict — clinical finishing
    or an exceptional assist pass that created a high-probability chance.
    """
    df = get_players(league_name, season, stat_type="standard", min_minutes=min_minutes)
    if df.empty:
        return df

    if metric == "goals":
        if "goals" not in df.columns or "xg" not in df.columns:
            raise ValueError("goals or xg column missing")
        df["overperformance"] = df["goals"] - df["xg"]
        df["actual"]          = df["goals"]
        df["expected"]        = df["xg"]
        label = "Goals vs xG"
    elif metric == "assists":
        if "assists" not in df.columns or "xag" not in df.columns:
            raise ValueError("assists or xag column missing")
        df["overperformance"] = df["assists"] - df["xag"]
        df["actual"]          = df["assists"]
        df["expected"]        = df["xag"]
        label = "Assists vs xAG"
    else:
        raise ValueError(f"metric must be 'goals' or 'assists', got '{metric}'")

    df["metric_label"] = label
    df = df[["player", "team", "minutes", "actual", "expected",
             "overperformance", "metric_label"]].copy()
    df = df.sort_values("overperformance", ascending=False).head(top_n)
    logger.info(f"Top {top_n} overperformers ({metric}) — {league_name} {season}")
    return df.reset_index(drop=True)


def underperformers(
    league_name: str,
    season: str,
    metric: str = "goals",
    top_n: int = 15,
    min_minutes: int = MIN_MINUTES_PLAYER,
) -> pd.DataFrame:
    """
    Players most below their expected output — unlucky, wasteful, or both.
    Same interface as overperformers() but sorted ascending.
    """
    df = overperformers(league_name, season, metric=metric,
                        top_n=999, min_minutes=min_minutes)
    df = df.sort_values("overperformance", ascending=True).head(top_n)
    return df.reset_index(drop=True)


# ── Percentile profiles ────────────────────────────────────────────────────────

def player_percentile_profile(
    player_name: str,
    league_name: str,
    season: str,
    position_group: str | None = None,
    min_minutes: int = MIN_MINUTES_PLAYER,
) -> pd.DataFrame:
    """
    Calculates a player's percentile rank (0–100) across key metrics
    relative to all other players in the league (optionally same position).
    This is the data that feeds radar/spider charts.

    Args:
        player_name:    Exact player name as stored in the database.
        league_name:    e.g. "Premier League"
        season:         e.g. "2024-2025"
        position_group: Optional filter — "FW", "MF", "DF", "GK"
                        If None, compares against all outfield players.
        min_minutes:    Minimum minutes threshold for comparison pool.

    Returns:
        DataFrame with columns: metric, value, percentile, label
    """
    df = get_players(league_name, season, stat_type="standard", min_minutes=min_minutes)
    if df.empty:
        return df

    # Filter to position group if specified
    if position_group and "position" in df.columns:
        df = df[df["position"].str.contains(position_group, na=False)]

    # Define which metrics to profile — tailored by position if known
    metrics = {
        "xg_p90":                    "xG per 90",
        "xag_p90":                   "xAG per 90",
        "goals_p90":                 "Goals per 90",
        "assists_p90":               "Assists per 90",
        "progressive_carries":       "Progressive Carries",
        "progressive_passes":        "Progressive Passes",
        "shot_creating_actions":     "Shot-Creating Actions",
        "goal_creating_actions":     "Goal-Creating Actions",
        "tackles_interceptions":     "Tackles + Interceptions",
        "aerial_win_pct":            "Aerial Win %",
    }

    # Compute per-90s if not already present (schema has these columns, but
    # Understat data never populates them at ingest time, unlike FBref which
    # provided some directly — _col_missing catches that "present but empty" case)
    if "minutes" in df.columns:
        for raw, p90 in [("xg", "xg_p90"), ("xag", "xag_p90"),
                          ("goals", "goals_p90"), ("assists", "assists_p90")]:
            if raw in df.columns and _col_missing(df, p90):
                df[p90] = _per90(df[raw], df["minutes"])

    # Check player exists
    player_row = df[df["player"] == player_name]
    if player_row.empty:
        logger.warning(f"Player '{player_name}' not found in {league_name} {season}")
        return pd.DataFrame()

    rows = []
    for col, label in metrics.items():
        if _col_missing(df, col):
            continue
        pool        = df[col].dropna()
        player_val  = player_row[col].iloc[0]
        if pd.isna(player_val) or pool.empty:
            continue
        pct         = (pool < player_val).sum() / len(pool) * 100
        rows.append({
            "metric":     col,
            "label":      label,
            "value":      round(player_val, 3),
            "percentile": round(pct, 1),
        })

    result = pd.DataFrame(rows)
    logger.info(f"Percentile profile built for {player_name} — {len(result)} metrics")
    return result


# ── Position-aware rankings ────────────────────────────────────────────────────

def rank_by_position(
    league_name: str,
    season: str,
    position_group: str,
    metric: str,
    top_n: int = 15,
    min_minutes: int = MIN_MINUTES_PLAYER,
) -> pd.DataFrame:
    """
    Ranks players within a specific position group by a given metric.

    Args:
        position_group: "FW", "MF", "DF", or "GK"
        metric:         Any numeric column in player_stats, e.g. "xg_p90"

    Example:
        rank_by_position("Premier League", "2024-2025", "MF", "sca_p90")
        → Top midfielders by shot-creating actions per 90
    """
    df = get_players(league_name, season, stat_type="standard", min_minutes=min_minutes)
    if df.empty:
        return df

    if "position" in df.columns:
        df = df[df["position"].str.contains(position_group, na=False)]

    if "minutes" in df.columns:
        for raw, p90 in [("xg", "xg_p90"), ("xag", "xag_p90"),
                          ("goals", "goals_p90"), ("assists", "assists_p90")]:
            if raw in df.columns and _col_missing(df, p90):
                df[p90] = _per90(df[raw], df["minutes"])

    if _col_missing(df, metric):
        usable = [c for c in df.select_dtypes("number").columns if not df[c].isna().all()]
        raise ValueError(f"Metric '{metric}' not found or has no data for "
                         f"{league_name} {season}. Available: {usable}")

    df = df.sort_values(metric, ascending=False).head(top_n)
    logger.info(f"Top {top_n} {position_group}s by {metric} — {league_name} {season}")
    return df[["player", "team", "position", "minutes", metric]].reset_index(drop=True)


# ── Season summary ─────────────────────────────────────────────────────────────

def season_summary(
    league_name: str,
    season: str,
    min_minutes: int = MIN_MINUTES_PLAYER,
) -> dict:
    """
    High-level season summary stats — useful for a printed report header.

    Returns a dict with:
        total_players, total_goals, total_xg, avg_goals_p90,
        most_goals (player), most_xg (player), top_creator (player)
    """
    df = get_players(league_name, season, stat_type="standard", min_minutes=min_minutes)
    if df.empty:
        return {}

    if "minutes" in df.columns and "goals" in df.columns:
        df["goals_p90"] = _per90(df["goals"], df["minutes"])

    summary = {
        "league":         league_name,
        "season":         season,
        "total_players":  len(df),
        "total_goals":    df["goals"].sum()       if "goals"  in df.columns else None,
        "total_xg":       round(df["xg"].sum(), 1) if "xg"   in df.columns else None,
        "avg_goals_p90":  round(df["goals_p90"].mean(), 3) if "goals_p90" in df.columns else None,
    }

    most_goals = _top_row_label(
        df, "goals", lambda r: f"{r['player']} ({int(r['goals'])})"
    )
    if most_goals:
        summary["most_goals"] = most_goals

    most_xg = _top_row_label(
        df, "xg", lambda r: f"{r['player']} ({round(r['xg'], 1)})"
    )
    if most_xg:
        summary["most_xg"] = most_xg

    top_creator = _top_row_label(
        df, "xag", lambda r: f"{r['player']} ({round(r['xag'], 1)} xAG)"
    )
    if top_creator:
        summary["top_creator"] = top_creator

    return summary
