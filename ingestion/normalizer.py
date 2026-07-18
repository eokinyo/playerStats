"""
ingestion/normalizer.py
Cleans and unifies raw DataFrames from FBref, Understat, and football-data.org
into a consistent internal schema before anything goes into the database.

The core problem this solves:
  - FBref calls a column "Gls", Understat calls it "goals" — we want "goals"
  - FBref player names sometimes have suffixes like " (GK)" — strip those
  - Numeric columns arrive as strings — convert them
  - Per-90 stats need to be calculated from raw totals
  - Some players appear multiple times (mid-season transfers) — they need merging

One normalizer function per source type. All return a consistent schema
ready to be written to the database.
"""

import logging
import re

import pandas as pd
import numpy as np

from config import MIN_MINUTES_PLAYER, PER90_SCALE

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Safely convert columns to numeric, coercing errors to NaN."""
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _clean_player_name(name: str) -> str:
    """
    Strips suffixes FBref adds to player names, e.g.:
      "Erling Haaland"   → "Erling Haaland"   (unchanged)
      "David Raya (GK)"  → "David Raya"        (removes GK tag)
    """
    if not isinstance(name, str):
        return name
    name = re.sub(r"\s*\(GK\)$", "", name).strip()
    return name


def _per90(series: pd.Series, minutes: pd.Series) -> pd.Series:
    """Calculates per-90-minute rate. Returns NaN if minutes is 0."""
    return (series / minutes.replace(0, np.nan)) * PER90_SCALE


# ── FBref normalization ────────────────────────────────────────────────────────

# Maps raw FBref column names → our internal names, per stat type
_FBREF_RENAME = {
    "standard": {
        "Player":          "player",
        "Nation":          "nationality",
        "Pos":             "position",
        "Squad":           "team",
        "Age":             "age",
        "Born":            "birth_year",
        "MP":              "matches_played",
        "Starts":          "starts",
        "Min":             "minutes",
        "90s":             "nineties",
        "Gls":             "goals",
        "Ast":             "assists",
        "G+A":             "goals_assists",
        "G-PK":            "np_goals",
        "PK":              "penalties_scored",
        "PKatt":           "penalties_attempted",
        "CrdY":            "yellow_cards",
        "CrdR":            "red_cards",
        "xG":              "xg",
        "npxG":            "np_xg",
        "xAG":             "xag",
        "npxG+xAG":        "np_xg_xag",
        "PrgC":            "progressive_carries",
        "PrgP":            "progressive_passes",
        "PrgR":            "progressive_receptions",
        # per-90 versions (FBref also provides these — we store both)
        "Gls_Per 90 Minutes": "goals_p90",
        "Ast_Per 90 Minutes": "assists_p90",
        "xG_Per 90 Minutes":  "xg_p90",
        "xAG_Per 90 Minutes": "xag_p90",
    },
    "shooting": {
        "Player":   "player",
        "Squad":    "team",
        "Gls":      "goals",
        "Sh":       "shots",
        "SoT":      "shots_on_target",
        "SoT%":     "shots_on_target_pct",
        "Sh/90":    "shots_p90",
        "SoT/90":   "shots_on_target_p90",
        "G/Sh":     "goals_per_shot",
        "G/SoT":    "goals_per_shot_on_target",
        "Dist":     "avg_shot_distance",
        "FK":       "free_kick_shots",
        "PK":       "penalties_scored",
        "PKatt":    "penalties_attempted",
        "xG":       "xg",
        "npxG":     "np_xg",
        "npxG/Sh":  "np_xg_per_shot",
        "G-xG":     "goals_minus_xg",
        "np:G-xG":  "np_goals_minus_xg",
    },
    "passing": {
        "Player":   "player",
        "Squad":    "team",
        "Cmp":      "passes_completed",
        "Att":      "passes_attempted",
        "Cmp%":     "pass_completion_pct",
        "TotDist":  "pass_total_distance",
        "PrgDist":  "pass_progressive_distance",
        "Ast":      "assists",
        "xAG":      "xag",
        "xA":       "xa",
        "A-xAG":    "assists_minus_xag",
        "KP":       "key_passes",
        "1/3":      "passes_final_third",
        "PPA":      "passes_penalty_area",
        "CrsPA":    "crosses_penalty_area",
        "PrgP":     "progressive_passes",
    },
    "gca": {
        "Player":   "player",
        "Squad":    "team",
        "SCA":      "shot_creating_actions",
        "SCA90":    "sca_p90",
        "GCA":      "goal_creating_actions",
        "GCA90":    "gca_p90",
    },
    "defense": {
        "Player":   "player",
        "Squad":    "team",
        "Tkl":      "tackles",
        "TklW":     "tackles_won",
        "Def 3rd":  "tackles_def_third",
        "Mid 3rd":  "tackles_mid_third",
        "Att 3rd":  "tackles_att_third",
        "Att":      "dribbles_challenged",
        "Tkl%":     "tackle_pct",
        "Lost":     "dribbles_lost",
        "Blocks":   "blocks",
        "Sh":       "shots_blocked",
        "Pass":     "passes_blocked",
        "Int":      "interceptions",
        "Tkl+Int":  "tackles_interceptions",
        "Clr":      "clearances",
        "Err":      "errors",
    },
    "possession": {
        "Player":   "player",
        "Squad":    "team",
        "Touches":  "touches",
        "Def Pen":  "touches_def_pen",
        "Def 3rd":  "touches_def_third",
        "Mid 3rd":  "touches_mid_third",
        "Att 3rd":  "touches_att_third",
        "Att Pen":  "touches_att_pen",
        "Att":      "dribbles_attempted",
        "Succ":     "dribbles_successful",
        "Succ%":    "dribble_success_pct",
        "Mis":      "miscontrols",
        "Dis":      "dispossessed",
        "Rec":      "passes_received",
        "PrgR":     "progressive_receptions",
        "PrgC":     "progressive_carries",
        "TotDist":  "carry_total_distance",
        "PrgDist":  "carry_progressive_distance",
    },
    "misc": {
        "Player":   "player",
        "Squad":    "team",
        "CrdY":     "yellow_cards",
        "CrdR":     "red_cards",
        "2CrdY":    "second_yellow_cards",
        "Fls":      "fouls_committed",
        "Fld":      "fouls_drawn",
        "Off":      "offsides",
        "Crs":      "crosses",
        "TklW":     "tackles_won",
        "PKwon":    "penalties_won",
        "PKcon":    "penalties_conceded",
        "OG":       "own_goals",
        "Recov":    "ball_recoveries",
        "Won":      "aerials_won",
        "Lost":     "aerials_lost",
        "Won%":     "aerial_win_pct",
    },
}

def normalize_fbref_players(df: pd.DataFrame, stat_type: str) -> pd.DataFrame:
    """
    Normalizes a raw FBref player DataFrame into our internal schema.

    Steps:
      1. Rename columns using the lookup table above
      2. Clean player names
      3. Convert numeric columns
      4. Drop rows with no player name or minutes
      5. Handle multi-club rows (players who transferred mid-season)
    """
    rename_map = _FBREF_RENAME.get(stat_type, {})

    # Only rename columns that exist (FBref occasionally changes names)
    existing_rename = {k: v for k, v in rename_map.items() if k in df.columns}
    df = df.rename(columns=existing_rename)

    # Clean player name
    if "player" in df.columns:
        df["player"] = df["player"].apply(_clean_player_name)
        df = df[df["player"].notna() & (df["player"] != "")]

    # FBref marks a player's combined row with "2 Teams", "3 Teams" etc. in the
    # team column when they moved clubs mid-season. Keep only the combined row.
    if "team" in df.columns:
        multi_team_mask  = df["team"].str.contains(r"\d+\s+Teams?", na=False)
        player_has_multi = df.loc[multi_team_mask, "player"].unique()
        # Remove individual club rows for players who have a combined row
        df = df[~(df["player"].isin(player_has_multi) & ~multi_team_mask)]
        df["team"] = df["team"].str.replace(r"\d+\s+Teams?", "Multiple Teams", regex=True)

    # Convert numeric columns
    numeric_cols = [
        "minutes", "goals", "assists", "xg", "np_xg", "xag", "xa",
        "shots", "shots_on_target", "progressive_carries", "progressive_passes",
        "progressive_receptions", "tackles", "interceptions", "blocks",
        "touches", "dribbles_attempted", "dribbles_successful",
        "shot_creating_actions", "sca_p90", "goal_creating_actions", "gca_p90",
        "yellow_cards", "red_cards", "fouls_committed", "fouls_drawn",
        "matches_played", "starts", "age",
    ]
    df = _to_numeric(df, [c for c in numeric_cols if c in df.columns])

    # Calculate per-90s where not already provided by FBref
    if "minutes" in df.columns and "xg" in df.columns:
        if "xg_p90" not in df.columns:
            df["xg_p90"] = _per90(df["xg"], df["minutes"])
    if "minutes" in df.columns and "xag" in df.columns:
        if "xag_p90" not in df.columns:
            df["xag_p90"] = _per90(df["xag"], df["minutes"])

    # Add overperformance columns where base stats exist
    if "goals" in df.columns and "xg" in df.columns:
        df["goals_minus_xg"] = df["goals"] - df["xg"]
    if "assists" in df.columns and "xag" in df.columns:
        df["assists_minus_xag"] = df["assists"] - df["xag"]

    logger.info(f"Normalized FBref {stat_type} — {len(df)} rows")
    return df.reset_index(drop=True)


def normalize_fbref_teams(df: pd.DataFrame, stat_type: str) -> pd.DataFrame:
    """Normalizes a raw FBref team/squad DataFrame."""
    rename_map = _FBREF_RENAME.get(stat_type, {})
    existing_rename = {k: v for k, v in rename_map.items() if k in df.columns}
    df = df.rename(columns=existing_rename)

    if "team" in df.columns:
        df = df[df["team"].notna()].copy()

    numeric_cols = [
        "goals", "xg", "np_xg", "xag", "shots", "shots_on_target",
        "progressive_carries", "progressive_passes", "tackles",
        "interceptions", "minutes",
    ]
    df = _to_numeric(df, [c for c in numeric_cols if c in df.columns])

    logger.info(f"Normalized FBref teams {stat_type} — {len(df)} rows")
    return df.reset_index(drop=True)


def normalize_understat_players(df: pd.DataFrame) -> pd.DataFrame:
    """Normalizes raw Understat player data."""
    numeric_cols = [
        "games", "minutes", "goals", "xG", "assists", "xA",
        "shots", "key_passes", "np_goals", "np_xg", "xGChain", "xGBuildup",
    ]
    df = _to_numeric(df, [c for c in numeric_cols if c in df.columns])

    # Rename to match internal schema
    df = df.rename(columns={
        "xG":       "xg_understat",
        "xA":       "xa_understat",
        "xGChain":  "xg_chain",
        "xGBuildup":"xg_buildup",
        "key_passes":"key_passes",
    })

    if "player" in df.columns:
        df["player"] = df["player"].apply(_clean_player_name)

    # Mirror into the CANONICAL xg/xa/xag columns too. Those are what nearly
    # every function in analysis/ reads by default (top_scorers,
    # season_summary, overperformers, player_percentile_profile, etc.) — that
    # naming split only made sense when FBref was also populating "xg"/"xag"
    # directly and the *_understat columns existed for cross-referencing two
    # sources side by side. With FBref dropped, "xg"/"xag" would otherwise
    # stay NULL forever. We keep the *_understat columns too, in case
    # FBref-sourced data is ever reintroduced alongside this later.
    #   xag: FBref's "expected assisted goals" has no exact Understat
    #   equivalent, but Understat's "xA" (expected assists) is the same
    #   underlying concept from a different model — the closest available
    #   value, so it's mirrored into both "xa" and "xag".
    if "xg_understat" in df.columns:
        df["xg"] = df["xg_understat"]
    if "xa_understat" in df.columns:
        df["xa"]  = df["xa_understat"]
        df["xag"] = df["xa_understat"]

    # player_stats.stat_type is NOT NULL and part of the UNIQUE constraint.
    # Understat gives one unified row per player (unlike FBref's separate
    # tables per stat category), so "standard" is the right single value —
    # it also matches the default get_players() already queries for.
    df["stat_type"] = "standard"

    logger.info(f"Normalized Understat players — {len(df)} rows")
    return df.reset_index(drop=True)


def normalize_understat_teams(df: pd.DataFrame) -> pd.DataFrame:
    """Normalizes raw Understat team data."""
    numeric_cols = [
        "xG", "xGA", "npxG", "npxGA", "scored", "missed",
        "wins", "draws", "losses", "pts", "matches_played",
        "deep", "deep_allowed", "ppda_coef", "oppda_coef",
    ]
    df = _to_numeric(df, [c for c in numeric_cols if c in df.columns])

    df = df.rename(columns={
        "xG":        "xg",
        "xGA":       "xga",
        "npxG":      "np_xg",
        "npxGA":     "np_xga",
        "scored":    "goals_for",
        "missed":    "goals_against",
        "pts":       "points",       # schema column is "points", Understat's raw field is "pts"
        "ppda_coef": "ppda",       # passes allowed per defensive action (press intensity)
        "oppda_coef":"oppda",      # opponent PPDA
    })

    # PPDA: lower = more intense press. Add a readable label
    if "ppda" in df.columns:
        df["press_intensity"] = pd.cut(
            df["ppda"],
            bins=[0, 8, 11, 15, float("inf")],
            labels=["High Press", "Mid Press", "Low Press", "Passive"],
        )

    # team_stats.stat_type is NOT NULL and part of the UNIQUE constraint —
    # see normalize_understat_players() for why "standard" is the right value.
    df["stat_type"] = "standard"

    logger.info(f"Normalized Understat teams — {len(df)} rows")
    return df.reset_index(drop=True)


def apply_minutes_filter(df: pd.DataFrame, min_minutes: int = MIN_MINUTES_PLAYER) -> pd.DataFrame:
    """
    Filters out players who haven't played enough to be meaningful in rankings.
    Default threshold is set in config.MIN_MINUTES_PLAYER (450 mins).
    """
    if "minutes" not in df.columns:
        logger.warning("No 'minutes' column found — skipping minutes filter")
        return df
    before = len(df)
    df = df[df["minutes"] >= min_minutes].reset_index(drop=True)
    logger.info(f"Minutes filter ({min_minutes}+): {before} → {len(df)} players")
    return df
